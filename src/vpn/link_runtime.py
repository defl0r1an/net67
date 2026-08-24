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

    # Второй шаг, без которого первый бесполезен: сказать Windows ходить
    # через наш прокси. Иначе на экране «Подключено», а сайт проверки
    # показывает прежний адрес и «Прокси: не используется» — ядро-то
    # работает, только никто в него не заходит.
    from vpn import system_proxy

    applied, proxy_message = system_proxy.enable(local_proxy_address())
    if not applied:
        return (
            True,
            f"Подключено к «{title}», но системный прокси включить не вышло: "
            f"{proxy_message}. Пропишите {local_proxy_address()} вручную.",
        )

    return (True, f"Подключено к «{title}». Трафик идёт через сервер.")


def disconnect() -> tuple[bool, str]:
    """Останавливает ядро."""
    # Системный прокси возвращаем первым и всегда.
    #
    # Порядок важен: если сначала погасить ядро, а потом упасть на
    # реестре, система останется настроенной на порт, которого больше
    # нет, — то есть без интернета. Поэтому сначала снимаем настройку.
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
