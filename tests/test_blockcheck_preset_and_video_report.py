from __future__ import annotations

from concurrent.futures import Future
from dataclasses import replace
from types import SimpleNamespace

from blockcheck import active_preset
from blockcheck.preset_match import https_profile_matches
from blockcheck.ui.result_cards import card_plain_text
from blockcheck.ui.result_cards_model import site_card
from diagnostics import path_report, report_text, video_sweep
from diagnostics.run_context import Probe
from diagnostics.services import Target
from diagnostics.tls_probe import KIND_ERROR, KIND_OK, KIND_TIMEOUT, STAGE_CONNECT, STAGE_READ, ProbeResult
from diagnostics.verdict import ReachState
from profile.parser import parse_preset_text
from settings.mode import ENGINE_WINWS2
from winws_runtime.runners.preset_runner_support import PreparedPresetArtifact, preset_cache_key


def test_report_opens_the_profile_from_the_running_file_and_refuses_an_old_result(tmp_path, monkeypatch):
    path = tmp_path / "Стандартный.txt"
    lists = tmp_path / "lists"
    lists.mkdir()
    (lists / "media.txt").write_text("example.test\n", encoding="utf-8")
    text = (
        "--wf-tcp-out=443\n"
        "--new\n--name=Исключение\n--filter-tcp=443\n"
        "--hostlist-exclude-domains=example.test\n--lua-desync=pass\n"
        "--new\n--name=Видео\n--filter-tcp=443\n--hostlist=lists/media.txt\n--lua-desync=none\n"
    )
    path.write_text(text, encoding="utf-8")
    state = SimpleNamespace(preset_path=str(path), strategy_name="Пресет: Стандартный", pid=435, generation=7)
    artifact = PreparedPresetArtifact(str(path), preset_cache_key(str(path)), text, (), True, "")
    monkeypatch.setattr(active_preset, "current", lambda: (state, artifact))
    monkeypatch.setattr("lists.core.paths.get_lists_dir", lambda: str(lists))
    monkeypatch.setattr("profile.strategy_catalog.load_strategy_catalogs", lambda *_: {})
    probe = Probe(Target("example.test", "сайт", main=True), "test", "example.test")
    probe.reach = ProbeResult("192.0.2.5", KIND_TIMEOUT)
    probe.reach_state = ReachState.DPI
    active_preset.annotate((state, artifact), [probe])
    card = site_card({"key": "test", "label": "Тест", "targets": [report_text.target_report(probe)]})
    assert "профиль «Видео»" in card_plain_text(card)
    assert "Стратегия:" in card_plain_text(card)
    action = card.preset_action["action"]
    assert action["profile_key"] == "profile:1"
    opened = []
    navigate = lambda _method, key: opened.append(key) or True
    assert not active_preset.open_profile(action, selected_path=lambda _method: tmp_path / "Другой.txt", navigate=navigate)
    assert active_preset.open_profile(action, selected_path=lambda _method: path, navigate=navigate)
    assert opened == ["profile:1"]
    path.write_text(text + "\n# Изменено\n", encoding="utf-8")
    assert not active_preset.open_profile(action, selected_path=lambda _method: path, navigate=navigate)
    assert not active_preset.open_profile({**action, "generation": 6}, selected_path=lambda _method: path, navigate=navigate)
    assert opened == ["profile:1"]


def test_youtube_reports_observed_responses_and_unavailable_addresses(monkeypatch):
    a = "rr1---sn-test.googlevideo.com"
    b = "rr2---sn-test.googlevideo.com"

    def submit(call, *args):
        job = Future()
        job.set_result(call(*args))
        return job

    run = SimpleNamespace(dns_cancelled=lambda: False, submit=submit, wait=lambda job: job.result())
    monkeypatch.setattr(video_sweep.net_access, "browser_ipv4", lambda _run, host: ("192.0.2.1",) if host == a else ("192.0.2.2",))
    monkeypatch.setattr(video_sweep.net_access, "doh_lookup", lambda _run, host, _type: (True, ("2001:db8::1",) if host == a else ()))
    monkeypatch.setattr(
        video_sweep.net_access, "fetch",
        lambda _run, host, address, _path, **_kw: (
            ProbeResult(address, KIND_OK, status=404) if host == a else ProbeResult(address, KIND_TIMEOUT)
        ),
    )
    rows = video_sweep.collect(run, video_sweep.start(run, (a, b)))
    probe = Probe(Target("googlevideo.com", "видео"), "youtube", a, video_nodes=rows)
    report = "\n".join(report_text.probe_lines(probe, full=True))
    assert "Ответили 1 из 2 найденных серверов" in report
    assert "2001:db8::1 · ответ HTTP 404" in report
    assert "192.0.2.2 · ответ HTTP не получен" in report
    assert f"{b} · IPv6: нет результата" in report
    assert "без воспроизведения видео" in report


def test_report_does_not_link_a_profile_outside_the_packet_filter(tmp_path):
    preset = parse_preset_text(
        "--wf-tcp-out=80\n--new\n--filter-tcp=443\n--lua-desync=none\n", engine=ENGINE_WINWS2,
    )
    assert https_profile_matches(preset, [("example.test", "192.0.2.5")], lists_dir=str(tmp_path)) == [None]


def test_path_does_not_claim_a_connection_without_a_response():
    probe = Probe(Target("example.test", "сайт"), "test", "example.test")
    probe.reach = ProbeResult("192.0.2.5", KIND_ERROR, stage=STAGE_CONNECT)
    steps = {step.key: step.level for step in path_report.build(probe)}
    assert (steps["tcp"], steps["tls"]) == ("unknown", "unknown")
    # Ответ оборвался уже после того, как TLS был установлен.
    probe.reach = replace(probe.reach, kind=KIND_TIMEOUT, stage=STAGE_READ, tls_version="TLSv1.3")
    probe.reach_state = ReachState.DPI
    steps = {step.key: step.level for step in path_report.build(probe)}
    assert (steps["tcp"], steps["tls"]) == ("ok", "ok")


def test_profile_button_keeps_the_report_open_if_the_link_is_stale():
    from PyQt6.QtWidgets import QApplication, QWidget

    from blockcheck.ui.report_dialog import BlockcheckReportDialog

    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    parent.resize(1100, 760)
    parent.show()
    action = {"profile_key": "profile:1"}
    opened = []
    dialog = BlockcheckReportDialog(
        "Профиль пресета: Видео", parent,
        preset_action={"label": "Видео", "action": action},
        open_profile=lambda payload: opened.append(payload) or False,
    )
    dialog.show()
    app.processEvents()
    dialog._profile_button.click()
    assert opened == [action]
    assert dialog.isVisible()
    assert not dialog._profile_button.isEnabled()
    assert "Повторите проверку" in dialog._profile_label.text()
    dialog.close()
    parent.close()
