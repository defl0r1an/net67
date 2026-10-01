"""Метка состояния обхода в заголовке окна net67: время работы или «Остановлен».

Включить или выключить обход можно было только с главной страницы: ушёл
в «Пресеты» или «Инструменты» — и не видно, работает ли обход, и нечем
его выключить, не возвращаясь назад. В zapret 21.1.6.45 для этого
появилась метка в заголовке окна; здесь она встроена в заголовок net67
(своя панель, колокольчик), а не в заголовок zapret с меткой PREMIUM.

Метка ничего не запускает сама: щелчок уходит в тот же пульт
(ui/launch_control.py), что и у zapret, а состояние читается из общего
UI-store — того же, из которого рисует себя главная страница. Поэтому
метка и большая кнопка не расходятся, даже если обход включили одной, а
выключили другой.
"""

from __future__ import annotations

from PyQt6 import sip

from ui.launch_control import launch_phase_from_state
from ui.launch_title_badge import LaunchTitleBadge
from ui.launch_uptime import track_phase

__all__ = ["LAUNCH_BADGE_FIELDS", "bind_launch_title_badge"]

LAUNCH_BADGE_FIELDS = frozenset({"launch_phase", "launch_running", "launch_method", "oneclick_phase"})

#: Что пишет метка, пока «одна кнопка» ещё выполняет шаги (как на кнопке).
ONECLICK_BADGE_TEXT = {"preparing": "Запуск…", "checking": "Проверка…"}


def _insert_index(window, layout) -> int:
    """Слева от колокольчика: метка — о состоянии, колокольчик — о событиях."""
    bell = getattr(window, "notificationBell", None)
    if bell is not None:
        index = layout.indexOf(bell)
        if index >= 0:
            return index
    return layout.count()


def bind_launch_title_badge(window, ui_state_store, launch_control) -> LaunchTitleBadge | None:
    title_bar = getattr(window, "titleBar", None)
    layout = getattr(title_bar, "hBoxLayout", None)
    if title_bar is None or layout is None or launch_control is None or ui_state_store is None:
        return None
    existing = title_bar.findChild(LaunchTitleBadge)
    if existing is not None:
        return existing

    badge = LaunchTitleBadge(title_bar, language_provider=lambda: None)
    badge.setObjectName("net67LaunchBadge")
    layout.insertWidget(_insert_index(window, layout), badge)
    badge.clicked.connect(lambda _checked=False: launch_control.toggle())
    window.launchBadge = badge

    def _on_state(state, _changed) -> None:
        if sip.isdeleted(badge):
            return
        # Часы времени работы — до метки: она прочтёт их, когда будет
        # рисовать себя (ui/launch_uptime.py).
        track_phase(launch_phase_from_state(state))
        badge.set_override(ONECLICK_BADGE_TEXT.get(str(getattr(state, "oneclick_phase", "") or "")))
        badge.set_state(
            phase=launch_phase_from_state(state),
            launch_method=str(getattr(state, "launch_method", "") or ""),
        )

    unsubscribe = ui_state_store.subscribe(_on_state, fields=LAUNCH_BADGE_FIELDS, emit_initial=True)

    def _drop(*_args) -> None:
        try:
            unsubscribe()
        except Exception:
            pass

    badge.destroyed.connect(_drop)
    # Пока главный круг страницы виден, метки нет: она — его продолжение.
    from shell.launch_badge_handoff import LaunchBadgeHandoff

    window.launchBadgeHandoff = LaunchBadgeHandoff(window, badge)
    return badge
