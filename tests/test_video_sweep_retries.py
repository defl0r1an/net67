from concurrent.futures import Future
from types import SimpleNamespace

from diagnostics import service_view, video_sweep
from diagnostics.tls_probe import KIND_CANCELLED, KIND_CONNECT, KIND_OK, KIND_TIMEOUT, STAGE_TLS, ProbeResult


HOST = "rr1---sn-test.googlevideo.com"
ADDRESS = "192.0.2.5"


def _run():
    def submit(fn, *args):
        job = Future()
        job.set_result(fn(*args))
        return job

    return SimpleNamespace(dns_cancelled=lambda: False, submit=submit, wait=lambda job: job.result())


def test_alternating_responses_are_not_reported_as_a_stable_node(monkeypatch):
    run = _run()
    answers = iter((
        ProbeResult(ADDRESS, KIND_OK, status=404, connect_ms=140),
        ProbeResult(ADDRESS, KIND_TIMEOUT),
        ProbeResult(ADDRESS, KIND_OK, status=404, connect_ms=130),
        ProbeResult(ADDRESS, KIND_TIMEOUT),
        ProbeResult(ADDRESS, KIND_OK, status=404, connect_ms=135),
    ))
    monkeypatch.setattr(video_sweep.net_access, "browser_ipv4", lambda *_: (ADDRESS,))
    monkeypatch.setattr(video_sweep.net_access, "fetch", lambda *_args, **_kwargs: next(answers))
    row = video_sweep._check(run, HOST, 4)
    assert (row["state"], row["passes"], row["tries"], row["connect_ms"]) == ("warn", 3, 5, 130)
    section = service_view._video_nodes_section((row,))
    assert "Ответили 1 из 1" in section.rows[0].text
    assert "отвечает через раз: 3 из 5" in section.rows[1].text
    assert "TCP 130 мс" in section.rows[1].text


def test_a_silent_node_stops_after_three_attempts(monkeypatch):
    calls = []

    def fetch(*_args, **_kwargs):
        calls.append(1)
        return ProbeResult(ADDRESS, KIND_TIMEOUT)

    monkeypatch.setattr(video_sweep.net_access, "browser_ipv4", lambda *_: (ADDRESS,))
    monkeypatch.setattr(video_sweep.net_access, "fetch", fetch)
    row = video_sweep._check(_run(), HOST, 4)
    assert len(calls) == 3
    assert (row["state"], row["tries"], row["passes"]) == ("warn", 3, 0)


def test_cancelling_preserves_observed_response_without_counting_cancel_as_failure(monkeypatch):
    known = ProbeResult(ADDRESS, KIND_OK, status=200)
    monkeypatch.setattr(video_sweep.net_access, "fetch", lambda *_args, **_kwargs: ProbeResult(ADDRESS, KIND_CANCELLED))
    row = video_sweep._check(_run(), HOST, 4, known)
    assert (row["passes"], row["tries"], row["interrupted"]) == (1, 1, True)


def test_an_unreachable_address_is_not_retried(monkeypatch):
    def unexpected_request(*_args, **_kwargs):
        raise AssertionError("Адрес без соединения не нужно опрашивать повторно")

    monkeypatch.setattr(video_sweep.net_access, "fetch", unexpected_request)
    row = video_sweep._check(_run(), HOST, 4, ProbeResult(ADDRESS, KIND_CONNECT))
    assert (row["tries"], row["passes"]) == (1, 0)


def test_small_window_answer_is_kept_separate_from_https_response(monkeypatch):
    from diagnostics import block_cause

    run = _run()
    run.probe_cancel = None
    monkeypatch.setattr(video_sweep.net_access, "browser_ipv4", lambda *_: (ADDRESS,))
    monkeypatch.setattr(video_sweep.net_access, "fetch", lambda *_args, **_kwargs: ProbeResult(ADDRESS, KIND_TIMEOUT, stage=STAGE_TLS))
    monkeypatch.setattr(block_cause, "window_hello", lambda *_args, **_kwargs: block_cause.HelloResult(block_cause.HELLO_OK))
    row = video_sweep._check(run, HOST, 4)
    assert row["small_window"]
    assert (row["status"], row["passes"], row["tries"]) == (None, 0, 3)
