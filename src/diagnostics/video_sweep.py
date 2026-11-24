"""Короткие HTTPS-пробы по адресам видеосерверов из этой сети."""

from __future__ import annotations

from diagnostics import net_access
from diagnostics.tls_probe import (
    KIND_CANCELLED, KIND_CERT, KIND_CONNECT, KIND_RESET, KIND_TIMEOUT, KIND_TLS, STAGE_TLS, STAGE_READ,
)
from utils.dns_wire import TYPE_AAAA

# Одна проба пропускает нестабильный узел. Три неудачи без единого ответа
# завершают серию раньше, чтобы молчащие адреса не задерживали отчёт.
ATTEMPTS = 5
SILENT_ATTEMPTS = 3


def _row(host: str, version: int, results=(), *, interrupted: bool = False, small_window: bool = False) -> dict:
    row = {"host": host, "version": version, "address": "", "status": None, "state": "unknown"}
    samples = [result for result in results if result.kind != KIND_CANCELLED]
    if samples:
        answers = [result for result in samples if result.status is not None]
        result = answers[-1] if answers else samples[-1]
        connect = [result.connect_ms for result in samples if result.connect_ms is not None]
        row.update(
            address=result.ip, status=result.status,
            state="ok" if len(answers) == len(samples) and not interrupted else "warn",
            passes=len(answers), tries=len(samples), interrupted=interrupted, small_window=small_window,
            connect_ms=min(connect) if connect else None,
        )
    return row


def _check(run, host: str, version: int, known=None) -> dict:
    if run.dns_cancelled():
        return _row(host, version)
    # По одному адресу на семейство: основной тест уже подробно разбирает сбои.
    if known is not None:
        addresses = (known.ip,)
    else:
        addresses = net_access.browser_ipv4(run, host) if version == 4 else net_access.doh_lookup(run, host, TYPE_AAAA)[1]
    if not addresses or run.dns_cancelled():
        return _row(host, version)
    samples = [known] if known is not None else []
    interrupted = False
    while len(samples) < ATTEMPTS:
        if run.dns_cancelled():
            interrupted = True
            break
        if samples and samples[-1].kind in (KIND_CONNECT, KIND_CERT):
            break
        if len(samples) >= SILENT_ATTEMPTS and not any(result.status is not None for result in samples):
            break
        try:
            result = net_access.fetch(run, host, addresses[0], "/", timeout=2.5)
        except OSError:
            interrupted = True
            break
        if result.kind == KIND_CANCELLED:
            interrupted = True
            break
        samples.append(result)
    small_window = False
    if (
        samples and not interrupted and not run.dns_cancelled()
        and not any(result.status is not None for result in samples)
        and samples[-1].kind in (KIND_RESET, KIND_TIMEOUT, KIND_TLS)
        and samples[-1].stage in (STAGE_TLS, STAGE_READ)
    ):
        from diagnostics.block_cause import window_hello

        small = window_hello(addresses[0], host, cancel=run.probe_cancel, timeout=2.5)
        small_window = small.answered
        interrupted = small.kind == KIND_CANCELLED
    return _row(host, version, samples, interrupted=interrupted, small_window=small_window)


def start(run, hosts, checked=()):
    # Повторное рукопожатие к тому же узлу может повлиять на результат
    # фильтра. Где уже есть измерения, используем их.
    known = {}
    for probe in checked:
        for result in (probe.reach, probe.ipv6_result, probe.local_check):
            if result is not None and result.ip and result.kind != KIND_CANCELLED:
                known.setdefault((probe.host, 6 if ":" in result.ip else 4), result)
    jobs = []
    for host in hosts:
        for version in (4, 6):
            result = known.get((host, version))
            jobs.append((host, version, run.submit(_check, run, host, version, result)))
    return jobs


def collect(run, jobs) -> tuple[dict, ...]:
    rows = []
    for host, version, job in jobs:
        try:
            result = run.wait(job)
        except OSError:
            # Неудача дополнительной пробы не отменяет основной результат.
            result = _row(host, version)
        rows.append(result)
    return tuple(rows)
