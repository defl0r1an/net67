"""Короткие HTTPS-пробы по адресам видеосерверов из этой сети."""

from __future__ import annotations

from diagnostics import net_access
from diagnostics.tls_probe import KIND_CANCELLED
from utils.dns_wire import TYPE_AAAA


def _row(host: str, version: int, result=None) -> dict:
    row = {"host": host, "version": version, "address": "", "status": None, "state": "unknown"}
    if result is not None:
        row["address"] = result.ip
        if result.kind != KIND_CANCELLED:
            row.update(status=result.status, state="ok" if result.status is not None else "warn")
    return row


def _check(run, host: str, version: int) -> dict:
    if run.dns_cancelled():
        return _row(host, version)
    # По одному адресу на семейство: основной тест уже подробно разбирает сбои.
    addresses = net_access.browser_ipv4(run, host) if version == 4 else net_access.doh_lookup(run, host, TYPE_AAAA)[1]
    if not addresses or run.dns_cancelled():
        return _row(host, version)
    result = net_access.fetch(run, host, addresses[0], "/", timeout=2.5)
    return _row(host, version, result)


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
            jobs.append((host, version, result, None if result else run.submit(_check, run, host, version)))
    return jobs


def collect(run, jobs) -> tuple[dict, ...]:
    rows = []
    for host, version, known, job in jobs:
        try:
            result = _row(host, version, known) if job is None else run.wait(job)
        except OSError:
            # Неудача дополнительной пробы не отменяет основной результат.
            result = _row(host, version)
        rows.append(result)
    return tuple(rows)
