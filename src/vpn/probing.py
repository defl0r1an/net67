"""Проверка отдельного сервера без изменения системного прокси и маршрутов."""

from pathlib import Path
from tempfile import TemporaryDirectory


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
            runtime.start(profile, settings_dir=Path(directory), should_stop=should_stop)
            if should_stop():
                return HttpProbeResult(False, None, "Проверка отменена")
            return check_through_proxy(proxy_address=f"127.0.0.1:{runtime.port}",
                                       should_stop=should_stop)
    except Exception as exc:
        return HttpProbeResult(False, None, str(exc))
    finally:
        runtime.stop()
