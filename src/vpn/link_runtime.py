"""Подключение по ссылке: запуск и остановка ядра Xray.

Ровно то же место, что `tunnel_runtime` занимает для WireGuard, только
для другого рода профилей. Страница зовёт `connect` и `disconnect`, не
разбираясь, кто там внутри.

## Зачем понадобилось

Серверы из подписки добавлялись, показывались и переключались, а на
«Подключить» приходило «В профиле нет приватного ключа». Ответ верный,
но не от того клиента: ссылку отдавали клиенту AmneziaWG, который ждёт
файл `.conf` с ключами WireGuard. Ядро Xray, ради которого всё и
делалось, к странице подключено не было.

## Чем отличается от туннеля

Туннель поднимает службу Windows и заворачивает в себя весь трафик
машины. Ядро Xray поднимает **локальный прокси** на 127.0.0.1 и ничего
само по себе не заворачивает: программы должны в него ходить. Поэтому
успех здесь означает «прокси слушает порт», а не «весь трафик пошёл
через сервер», и говорить об этом человеку надо прямо.

## Про одиночку

Ядро одно на приложение: два процесса на одном порту не поднимутся, а
разные порты означали бы, что человек не знает, куда указывать
браузер. Поэтому здесь модульный экземпляр, а не создание на каждый
вызов.
"""

from __future__ import annotations

import threading

from log.log import log


#: Единственный на приложение экземпляр ядра.
_RUNTIME = None
_RUNTIME_LOCK = threading.Lock()


def _runtime():
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            from vpn.xray import XrayRuntime

            _RUNTIME = XrayRuntime()
        return _RUNTIME


def _settings_dir():
    from config.runtime_layout import APPLICATION_PATHS

    return APPLICATION_PATHS.settings_dir


def is_link_profile(profile) -> bool:
    """Профиль поднимается ядром Xray, а не клиентом WireGuard.

    Признак — исходная ссылка в поле `raw`. Проверять по классу нельзя:
    страница работает и с профилями, восстановленными из файла.
    """
    return bool(str(getattr(profile, "raw", "") or "").strip())


def check_core_available() -> tuple[bool, str]:
    """Есть ли на месте xray.exe. Возвращает (есть, сообщение)."""
    from vpn.xray import core_path, is_core_available

    if is_core_available():
        return (True, "")

    return (
        False,
        "Не найден xray.exe — подключение по ссылке без него не работает. "
        f"Ожидается здесь: {core_path()}",
    )


def is_connected() -> bool:
    """Слушает ли локальный прокси."""
    from vpn.xray import is_port_open

    # is_running и port — свойства, а не методы. Вызов со скобками давал
    # «'bool' object is not callable» ровно в тот момент, когда человек
    # жмёт «Подключить».
    runtime = _runtime()
    return bool(runtime.is_running and is_port_open(runtime.port))


def local_proxy_address() -> str:
    """Адрес локального прокси — его вписывают в программы."""
    return f"127.0.0.1:{_runtime().port}"


#: Поднятый туннель. Один на приложение, как и ядро.
_TUN_SESSION = None

#: Ключ настройки «весь трафик системы».
TUN_MODE_SETTING = "vpn_tun_mode"


def tun_mode_enabled() -> bool:
    """Включён ли режим «весь трафик».

    По умолчанию выключен: туннель требует прав администратора и
    трогает таблицу маршрутов, а прокси — нет. Включать такое молча за
    человека неправильно.
    """
    try:
        from settings import store

        return bool(store.get_program_settings().get(TUN_MODE_SETTING, False))
    except Exception:
        return False


def set_tun_mode_enabled(enabled: bool) -> None:
    try:
        from settings import store

        store.set_program_settings({TUN_MODE_SETTING: bool(enabled)})
    except Exception as exc:
        log(f"Не удалось сохранить режим туннеля: {exc}", "⚠ VPN")


def _resolve_server_ips(profile) -> list[str]:
    """Все адреса сервера — для маршрутов в обход туннеля.

    Имя разрешаем сейчас, пока сеть ещё обычная. После поднятия туннеля
    этот же запрос ушёл бы в туннель, которого без него не существует.

    Берём весь список, а не первый адрес. У имени бывает несколько
    A-записей, и отдаются они по кругу: три подключения подряд дали
    212.46.33.95, .92 и .96. Ядро Xray разрешает имя своим запросом и
    выбирает из того же списка — но не обязательно то же самое. Когда
    исключение стояло по одному адресу, а ядро уходило по другому, его
    соединение с сервером заворачивалось в туннель, который на этом
    соединении и держится. Петля молчаливая: жаловаться некому, просто
    ничего не движется.
    """
    from vpn.tun_mode import is_ip_address

    host = str(getattr(profile, "host", "") or "").strip()
    if not host:
        return []
    if is_ip_address(host):
        return [host]

    try:
        import socket

        found: list[str] = []
        for item in socket.getaddrinfo(host, None, socket.AF_INET):
            address = str(item[4][0])
            if address and address not in found:
                found.append(address)
        if not found:
            log(f"Имя сервера {host} не дало ни одного адреса", "⚠ VPN")
        return found
    except Exception as exc:
        log(f"Не удалось разрешить адрес сервера {host}: {exc}", "⚠ VPN")
        return []


def _start_tunnel(profile) -> tuple[bool, str]:
    """Поднимает туннель поверх уже работающего ядра."""
    global _TUN_SESSION

    from vpn import tun_mode, tun_runtime

    _stop_tunnel()

    try:
        plan = tun_mode.build_plan(
            proxy_address=local_proxy_address(),
            server_ips=_resolve_server_ips(profile),
        )
        _TUN_SESSION = tun_runtime.start(plan)
    except tun_mode.TunModeError as exc:
        return (False, str(exc))
    except Exception as exc:
        return (False, f"Не удалось поднять туннель: {exc}")

    return (True, "")


def _drop_system_proxy() -> None:
    """Снимает системный прокси при переходе в режим туннеля.

    Иначе путей наружу два, и это хуже, чем один плохой.

    Туннель заворачивает трафик всей машины. Системный прокси правит
    ветку WinINET, которую читает браузер. Оба включённые одновременно
    означают, что браузер идёт в ядро напрямую, мимо туннеля, а все
    остальные приложения — через туннель.

    Пока туннель исправен, разницы не видно. Как только он ломается,
    получается картина, которую нельзя разобрать: сайты в браузере
    открываются и честно показывают адрес сервера, а любая другая
    программа сети не видит вовсе. На этом расхождении при разборе
    туннеля было потеряно больше всего времени — проверка шла браузером,
    а ломалось не у него.
    """
    try:
        from vpn import system_proxy

        if not system_proxy.is_supported():
            return
        ok, message = system_proxy.disable()
        if not ok and message:
            log(f"Системный прокси снять не удалось: {message}", "⚠ VPN")
    except Exception as exc:
        log(f"Системный прокси снять не удалось: {exc}", "⚠ VPN")


def _stop_tunnel() -> None:
    global _TUN_SESSION

    session = _TUN_SESSION
    _TUN_SESSION = None
    if session is None:
        return
    try:
        from vpn import tun_runtime

        tun_runtime.stop(session)
    except Exception as exc:
        log(f"Туннель не свернулся штатно: {exc}", "⚠ VPN")


def connect(profile) -> tuple[bool, str]:
    """Поднимает ядро на выбранном сервере. Возвращает (получилось, что сказать)."""
    from vpn.xray import XrayError

    available, message = check_core_available()
    if not available:
        return (False, message)

    runtime = _runtime()
    try:
        # Прежнее ядро останавливаем сами: порт один, и второй процесс
        # на нём просто не поднимется, а сообщение будет про занятый
        # порт вместо смены сервера.
        runtime.stop()
        runtime.start(profile, settings_dir=_settings_dir())
    except XrayError as exc:
        return (False, str(exc))
    except Exception as exc:
        return (False, f"Не удалось запустить ядро Xray: {exc}")

    title = str(getattr(profile, "title", "") or getattr(profile, "host", "") or "сервер")

    # Подключение записываем в журнал целиком: и что подключаемся, и с
    # каким охватом. Раньше сюда не попадало ничего — при жалобе «текст
    # не соответствует» в журнале не было ни строчки о том, пытались ли
    # вообще поднять туннель. Разбирать такое нечем.
    log(
        f"Подключение к «{title}»: режим "
        f"{'весь трафик' if tun_mode_enabled() else 'только браузер'}",
        "🌐 VPN",
    )

    # Второй шаг, без которого первый бесполезен: направить трафик в
    # поднятый прокси. Иначе на экране «Подключено», а сайт проверки
    # показывает прежний адрес — ядро работает, только никто в него не
    # заходит.
    #
    # Способов два, и разница между ними принципиальная.
    #
    # Туннель заворачивает весь трафик машины. Системный прокси правит
    # ветку реестра WinINET, которую читают Chromium и Edge — и почти
    # никто больше: приложения на Electron, Node, .NET и Go ходят своим
    # стеком и в реестр не смотрят. Отсюда и жалоба, ради которой
    # туннель появился: в браузере адрес сменился, а установщик
    # Claude Desktop «не может достучаться до серверов».
    tun_requested = tun_mode_enabled()
    tun_failure = ""

    if tun_requested:
        started, tun_failure = _start_tunnel(profile)
        if started:
            # Один путь наружу, а не два. Пояснение — в _drop_system_proxy().
            _drop_system_proxy()
            log(f"Туннель поднят, весь трафик идёт через «{title}»", "🌐 VPN")
            return (True, f"Подключено к «{title}». Весь трафик системы идёт через сервер.")
        log(f"Туннель не поднялся, откатываемся на системный прокси: {tun_failure}", "⚠ VPN")
        # Не обрываем подключение: прокси хуже туннеля, но лучше, чем
        # ничего. А вот молчать об этом нельзя.

    from vpn import system_proxy

    applied, proxy_message = system_proxy.enable(local_proxy_address())
    if not applied:
        return (
            True,
            f"Подключено к «{title}», но системный прокси включить не вышло: "
            f"{proxy_message}. Пропишите {local_proxy_address()} вручную.",
        )

    # Сообщение обязано сойтись с тем, что человек видит на экране.
    #
    # Здесь была неправда: при включённом переключателе «весь трафик» и
    # сорвавшемся туннеле показывалось ровное «через сервер идёт только
    # браузер» — будто так и задумано. Человек смотрел на включённый
    # тумблер и на текст, который ему противоречит, а настоящая причина
    # оставалась в журнале, куда он не заглядывает.
    from vpn.tun_mode import describe_mode

    if tun_requested:
        reason = str(tun_failure or "").strip() or "причина неизвестна"
        return (
            True,
            f"Подключено к «{title}», но режим «весь трафик» не включился: {reason} "
            "Пока через сервер идёт только браузер.",
        )

    return (True, f"Подключено к «{title}». {describe_mode(tun_enabled=False)}")


def disconnect() -> tuple[bool, str]:
    """Останавливает ядро."""
    # Туннель и системный прокси снимаем первыми и всегда.
    #
    # Порядок важен: если сначала погасить ядро, а потом упасть на
    # маршрутах или реестре, система останется завёрнутой в туннель без
    # выхода или настроенной на порт, которого больше нет, — то есть без
    # интернета. Поэтому сначала снимаем перенаправление.
    _stop_tunnel()

    from vpn import system_proxy

    restored, proxy_message = system_proxy.disable()

    try:
        _runtime().stop()
    except Exception as exc:
        return (False, f"Не удалось остановить ядро Xray: {exc}")

    if not restored:
        return (True, f"Отключено, но {proxy_message}")
    return (True, "Отключено")


__all__ = [
    "check_core_available",
    "connect",
    "disconnect",
    "is_connected",
    "is_link_profile",
    "local_proxy_address",
]
