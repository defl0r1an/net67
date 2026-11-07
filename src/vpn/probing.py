"""Проверка отдельного сервера без изменения системного прокси и маршрутов."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock


_MAX_GROUP_PROBES = 4
_startup_lock = Lock()


def check_profile(profile, *, should_stop=lambda: False):
    from vpn.http_probe import HttpProbeResult, check_through_proxy
    from vpn.xray import XrayRuntime

    if should_stop():
        return HttpProbeResult(False, None, "Проверка отменена")
    # У пробы собственные процесс, порт и временный конфиг. Рабочее подключение
    # из link_runtime здесь никогда не останавливается и не перенастраивается.
    runtime = XrayRuntime(port=0)
    try:
        with TemporaryDirectory(prefix="net67-vpn-probe-") as directory:
            try:
                # Пока ядро не начало слушать, свободный порт может выбрать
                # соседняя проба. Сам запрос идёт уже без этой блокировки.
                with _startup_lock:
                    runtime.start(profile, settings_dir=Path(directory), should_stop=should_stop)
                if should_stop():
                    return HttpProbeResult(False, None, "Проверка отменена")
                return check_through_proxy(proxy_address=f"127.0.0.1:{runtime.port}",
                                           should_stop=should_stop)
            finally:
                runtime.stop()
    except Exception as exc:
        return HttpProbeResult(False, None, str(exc))


def probe_server(profile, *, address=None, stats=None, should_stop=lambda: False):
    from vpn.link_runtime import is_link_profile

    if address:
        from vpn.http_probe import check_through_proxy
        return check_through_proxy(proxy_address=address, should_stop=should_stop), "HTTPS"
    if is_link_profile(profile):
        return check_profile(profile, should_stop=should_stop), "HTTPS"
    from vpn.ping import check_server
    return check_server(profile.endpoint_host, profile.endpoint_port, stats=stats), "Сервер"


def check_group(profiles, *, should_stop, on_result):
    """Проверяет профили отдельно от действующего подключения."""
    from vpn.http_probe import HttpProbeResult

    def probe(profile):
        if should_stop():
            return None
        try:
            return probe_server(profile, should_stop=should_stop)
        except Exception as exc:
            return HttpProbeResult(False, None, str(exc)), "Проверка"

    with ThreadPoolExecutor(max_workers=_MAX_GROUP_PROBES) as pool:
        futures = {pool.submit(probe, profile): profile for profile in profiles}
        for future in as_completed(futures):
            if should_stop():
                for pending in futures:
                    pending.cancel()
                break
            result = future.result()
            if result is not None:
                on_result((futures[future], *result))
