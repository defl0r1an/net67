"""Проверка сайта после «Применить» — уже через настоящий пресет.

Подбор проверял стратегию в своём маленьком профиле. В пресете пользователя
рядом другие профили: выше может стоять общий, который перехватит сайт, фейки
могут быть объявлены иначе, перехват WinDivert — шире. Поэтому, когда обход
запустился с новой стратегией, сайт открывается ещё раз тем же способом, что
и в подборе (адреса из разных подсетей и проверка объёма), и человек
сразу видит, работает ли стратегия у него, а не «проверьте сами».
"""

from __future__ import annotations

import time
import logging
from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QThread, pyqtSignal
from blockcheck.strategy_search.probe_profile import PROTOCOL_TCP_HTTPS, PROTOCOL_HTTP80, PROTOCOL_QUIC

logger = logging.getLogger(__name__)

# Сколько ждать, пока Zapret запустится после «Применить».
START_WAIT_SECONDS = 25.0
# Работающий Zapret перечитывает изменённый пресет сам; столько даём ему на это.
RESTART_SETTLE_SECONDS = 4.0
# После запуска — пауза, чтобы перехват точно встал.
READY_SETTLE_SECONDS = 1.5
POLL_SECONDS = 0.5

CHECK_OK = "ok"
CHECK_FAILED = "failed"
# Проверить не вышло (Zapret не запустился, адреса нет, проверку сняли).
CHECK_SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class ApplyCheck:
    code: str
    text: str = ""


def check_site(host: str, *, cancel, scan_protocol: str = PROTOCOL_TCP_HTTPS) -> ApplyCheck:
    """Открыть сайт так же, как подбор: адреса из разных подсетей, объём по соединению."""
    from blockcheck.strategy_search import probes
    from blockcheck.strategy_search import verdict as rules

    port = 80 if scan_protocol == PROTOCOL_HTTP80 else 443
    addresses, error = probes.resolve_target_addresses(host, port, udp=scan_protocol == PROTOCOL_QUIC)
    if error:
        return ApplyCheck(CHECK_SKIPPED, error)
    stubs = set(probes.stub_addresses(addresses))
    picked = rules.spread_addresses([address for address in addresses if address not in stubs])
    if not picked:
        return ApplyCheck(CHECK_SKIPPED, f"DNS отдаёт для {host} только адрес-заглушку")
    probe = {
        PROTOCOL_HTTP80: probes.probe_http_addresses,
        PROTOCOL_QUIC: probes.probe_quic_addresses,
    }.get(scan_protocol, probes.probe_https_addresses)
    outcomes = probe(host, picked, cancel=cancel)
    if scan_protocol == PROTOCOL_HTTP80 and any(outcome.redirect_https for outcome in outcomes):
        return ApplyCheck(CHECK_SKIPPED, "HTTP перенаправляет на HTTPS; работа конечного адреса не проверена")
    if scan_protocol == PROTOCOL_TCP_HTTPS and rules.attempt_passed(outcomes):
        outcomes = [
            probes.probe_volume(host, address, outcome, cancel=cancel) if rules.needs_volume(outcome) else outcome
            for address, outcome in zip(picked, outcomes)
        ]
    if cancel.cancelled:
        return ApplyCheck(CHECK_SKIPPED, "проверку остановили")
    if rules.attempt_passed(outcomes):
        if scan_protocol != PROTOCOL_TCP_HTTPS:
            return ApplyCheck(CHECK_OK, "HTTP, порт 80" if scan_protocol == PROTOCOL_HTTP80 else "QUIC, UDP 443")
        unknown = any(outcome.volume == rules.VOLUME_UNKNOWN for outcome in outcomes)
        return ApplyCheck(CHECK_OK, "объём не проверен: сайт отвечает коротко" if unknown else "")
    return ApplyCheck(CHECK_FAILED, rules.attempt_reason(outcomes))


def wait_until_running(is_running: Callable[[], bool], *, restarting: bool, sleep, cancelled, clock=time.monotonic) -> bool:
    if restarting:
        sleep(RESTART_SETTLE_SECONDS)
    deadline = clock() + START_WAIT_SECONDS
    while clock() < deadline:
        if cancelled():
            return False
        try:
            if is_running():
                sleep(READY_SETTLE_SECONDS)
                return not cancelled()
        except Exception:
            return False
        sleep(POLL_SECONDS)
    return False


def run_apply_check(host: str, *, is_running, restarting: bool, cancel, scan_protocol: str = PROTOCOL_TCP_HTTPS) -> ApplyCheck:
    """Дождаться Zapret и проверить сайт; при провале — ещё раз чуть позже.

    Второй заход нужен, если работающий Zapret перечитал пресет позже, чем мы
    начали проверку: первая проба тогда шла ещё со старым пресетом.
    """
    if not wait_until_running(is_running, restarting=restarting, sleep=cancel.sleep, cancelled=lambda: cancel.cancelled):
        return ApplyCheck(CHECK_SKIPPED, "обход не запустился за время ожидания")
    check = check_site(host, cancel=cancel, scan_protocol=scan_protocol)
    if check.code != CHECK_FAILED:
        return check
    if not cancel.sleep(RESTART_SETTLE_SECONDS):
        return ApplyCheck(CHECK_SKIPPED, "проверку остановили")
    return check_site(host, cancel=cancel, scan_protocol=scan_protocol)


class StrategyApplyCheckWorker(QThread):
    """Фоновая проверка после «Применить»: итог приходит сигналом в поток окна."""

    completed = pyqtSignal(int, str, str, str)

    def __init__(self, request_id: int, host: str, *, is_running, restarting: bool,
                 scan_protocol: str = PROTOCOL_TCP_HTTPS) -> None:
        super().__init__()
        from utils.socket_cancel import SocketCancel

        self._host = str(host or "")
        self._request_id = request_id
        self._scan_protocol = scan_protocol
        self._is_running = is_running
        self._restarting = bool(restarting)
        self._cancel = SocketCancel()

    def cancel(self) -> None:
        self._cancel.cancel()

    def stop(self) -> None:
        self.cancel()

    def run(self) -> None:
        try:
            check = run_apply_check(self._host, is_running=self._is_running, restarting=self._restarting,
                                    cancel=self._cancel, scan_protocol=self._scan_protocol)
        except Exception:  # проверка — подсказка, её сбой не должен ронять окно
            logger.exception("Не удалось проверить сайт после применения стратегии")
            check = ApplyCheck(CHECK_SKIPPED, "подробности ошибки записаны в журнал")
        if not self._cancel.cancelled:
            self.completed.emit(self._request_id, self._host, check.code, check.text)


def apply_check_message(host: str, code: str, text: str) -> tuple[str, str, str] | None:
    """(вид, заголовок, текст) уведомления; None — сказать нечего."""
    if code == CHECK_OK:
        body = f"{host} ответил при проверке через ваш пресет."
        if text:
            body += f" ({text})"
        return "success", "Проверено в вашем пресете", body
    if code == CHECK_FAILED:
        return (
            "warning",
            "В вашем пресете сайт не открылся",
            f"{host}: {text or 'не открылся'}. В подборе стратегия работала. Возможно, сайт перехватывает "
            "другой профиль выше в пресете или пресет объявляет фейки иначе. Откройте пресет и поднимите "
            "профиль сайта наверх или запустите подбор ещё раз.",
        )
    if code == CHECK_SKIPPED:
        return (
            "warning", "Сайт ещё не проверен",
            f"Стратегия сохранена, но проверку {host} завершить не удалось: {text or 'нет результата'}. "
            "Проверьте сайт после включения обхода.",
        )
    return None
