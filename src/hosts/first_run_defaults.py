"""Однократное включение сервисов hosts после установки.

Пишется группа «Напрямую из hosts» — см. hosts/defaults.py, там же
объяснено, почему подмена DNS осталась выключенной.

Однократно — принципиально. Если применять на каждом запуске, тумблер,
который человек осознанно выключил, возвращался бы обратно, и выключить
его навсегда было бы нельзя.

Но «однократно» пришлось сделать версионным. Первая версия умолчаний
включала подмену DNS и ломала доступ к сайтам, а простой булев флаг
означал бы «у всех, кто уже установил, так и останется». Смена номера
версии переписывает блок один раз.

Запись идёт в системный файл и занимает заметное время, поэтому шаг
выполняется в отдельном потоке и никогда не роняет запуск: не удалось —
пишем в лог, приложение работает дальше.
"""

from __future__ import annotations

import threading

from log.log import log


#: Номер текущего набора умолчаний.
#:
#: 1 — все 72 сервиса, включая подмену DNS. Ломала доступ к сайтам.
#: 2 — только «Напрямую из hosts».
#: 3 — плюс группа «ИИ» на XBOX DNS: без подмены адреса нейросети не
#:     работают вообще, они отказывают по стране запроса.
DEFAULTS_VERSION = 3


def is_needed() -> bool:
    """Нужно ли применять умолчания при запуске.

    Пока мастер первого запуска не пройден — не нужно. Он спрашивает,
    что должно работать без VPN, и сам применяет ответ; сработай этот
    шаг раньше, он записал бы в hosts весь каталог, а ответ человека
    лёг бы поверх или не лёг вовсе — как повезёт по времени. Ровно из-за
    этого галочки в мастере ничего не меняли на странице «Сервисы».

    Тем, кто мастер уже прошёл, всё работает как прежде: сверка версии.
    """
    try:
        from settings.store import get_wizard_completed

        if not bool(get_wizard_completed()):
            return False
    except Exception:
        # Флага не добыли — ведём себя как раньше и решаем по версии.
        pass

    try:
        from settings.store import get_hosts_defaults_version

        return int(get_hosts_defaults_version()) < DEFAULTS_VERSION
    except Exception:
        # Настройки не прочитались — лучше не трогать системный файл.
        return False


def apply_now(selection: dict | None = None) -> tuple[bool, str]:
    """Записывает выбор сервисов в hosts. Возвращает (успех, сообщение).

    ``selection`` — готовое отображение «сервис -> профиль». Его передаёт
    мастер первого запуска по ответам человека. Не передали — берём
    умолчания каталога, как было.

    Писатель в системный файл остаётся один и тот же. Мастер не пишет
    сам, а зовёт сюда: два писателя в hosts — это гонка, где результат
    зависит от того, кто допишет последним.
    """
    try:
        from hosts.defaults import load_default_selection
        from hosts.public import (
            apply_service_profiles,
            create_hosts_runtime,
            save_user_selection,
        )
        from settings.store import set_hosts_defaults_version
    except Exception as exc:
        return (False, f"модули hosts недоступны: {exc}")

    try:
        if selection is None:
            selection = load_default_selection()
        else:
            selection = dict(selection)
    except Exception as exc:
        return (False, f"каталог сервисов не прочитан: {exc}")

    if not selection:
        return (False, "каталог сервисов пуст")

    try:
        result = apply_service_profiles(create_hosts_runtime(), selection)
    except Exception as exc:
        return (False, f"запись в hosts не удалась: {exc}")

    if not bool(getattr(result, "success", False)):
        return (False, str(getattr(result, "message", "") or "запись в hosts не удалась"))

    # Сохранённый выбор — то, что показывают тумблеры и что переприменяет
    # кнопка «Включить». Без записи он остался бы пустым, и первое же
    # нажатие «Включить» переписало бы блок hosts своим набором.
    try:
        save_user_selection(selection)
    except Exception as exc:
        log(f"Выбор сервисов не сохранён: {exc}", "⚠ WARNING")

    # Флаг ставим только после удачной записи. Иначе неудачная попытка
    # (нет прав, файл занят антивирусом) навсегда осталась бы неудачной.
    try:
        set_hosts_defaults_version(DEFAULTS_VERSION)
    except Exception as exc:
        return (True, f"записано, но версия не сохранена: {exc}")

    return (True, f"включено сервисов: {len(selection)}")


def apply_in_background(selection: dict | None = None) -> threading.Thread | None:
    """Запускает применение в отдельном потоке.

    С ``selection`` — по ответам мастера, и тогда проверка ``is_needed``
    не спрашивается: мастер только что закончился, применить ответ надо
    в любом случае. Без него — обычный однократный шаг при запуске.
    """
    if selection is None and not is_needed():
        return None

    def _run() -> None:
        ok, message = apply_now(selection)
        if ok:
            log(f"Сервисы hosts включены по умолчанию: {message}", "INFO")
        else:
            log(f"Не удалось включить сервисы hosts по умолчанию: {message}", "⚠ WARNING")

    thread = threading.Thread(target=_run, name="hosts-defaults", daemon=True)
    thread.start()
    return thread


__all__ = ["DEFAULTS_VERSION", "apply_in_background", "apply_now", "is_needed"]
