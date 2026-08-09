"""Безопасный жизненный цикл диалогов qfluentwidgets."""

from __future__ import annotations

from PyQt6.QtCore import QEvent

from qfluentwidgets import (
    MessageBox as _QFluentMessageBox,
    MessageBoxBase as _QFluentMessageBoxBase,
)


class _ManagedMaskDialogLifecycle:
    """Снимает закрытый диалог со всех фильтров событий и глушит поздние события.

    MaskDialogBase ставит себя фильтром на родительское окно, windowMask и
    centerWidget. На Python 3.14 / PyQt6 6.11 фильтр может получить событие
    уже во время зачистки Python-объекта, когда атрибутов диалога больше нет,
    а C++-объект ещё жив — та же природа, что у setTitleBar в
    AppFluentWindow. Отсюда двойная защита: явное снятие всех фильтров при
    закрытии и guard в eventFilter на случай событий после зачистки.
    """

    def __init__(self, *args, **kwargs):
        # Ставится до qfluentwidgets: если фильтр получит событие прямо во время
        # неполной инициализации, eventFilter безопасно его пропустит.
        self._mask_event_filter_ready = False
        super().__init__(*args, **kwargs)
        self._mask_event_filter_host = self.window()
        self._mask_event_filter_ready = True

    def _detach_mask_event_filter(self) -> None:
        self._mask_event_filter_ready = False
        host = getattr(self, "_mask_event_filter_host", None)
        self._mask_event_filter_host = None
        watched = (
            host,
            getattr(self, "windowMask", None),
            getattr(self, "widget", None),
        )
        for target in watched:
            if target is None:
                continue
            try:
                target.removeEventFilter(self)
            except RuntimeError:
                # Объект уже мог быть уничтожен вместе с диалогом.
                pass

    def eventFilter(self, obj, e):  # noqa: N802 (Qt API)
        # Окно меняет размер и после показа диалога: на первом запуске
        # геометрия восстанавливается из настроек уже потом, и маска,
        # снятая один раз, остаётся от прежнего размера — затемнение
        # накрывает угол, а диалог стоит не по центру.
        try:
            if (
                getattr(self, "_mask_event_filter_ready", False)
                and e.type() == QEvent.Type.Resize
                and obj is getattr(self, "_mask_event_filter_host", None)
            ):
                self._sync_mask_geometry()
        except Exception:
            pass

        if (
            not getattr(self, "_mask_event_filter_ready", False)
            or getattr(self, "windowMask", None) is None
            or getattr(self, "widget", None) is None
        ):
            # Событие пришло до полной инициализации или во время зачистки
            # диалога — базовый eventFilter обращается к обоим дочерним объектам.
            return False
        return super().eventFilter(obj, e)

    def showEvent(self, event):  # noqa: N802 (Qt override)
        """Приводит затемнение к настоящему размеру окна.

        MaskDialogBase запоминает размеры родителя при создании. Если
        окно после этого изменилось — а на первом запуске оно как раз
        только-только появляется, — затемнение остаётся прежним, и на
        экране получается прямоугольник в левом верхнем углу, а диалог
        стоит не по центру. Ровно это и было видно на снимке.

        Пересчитываем при каждом показе: диалог может открыться и на
        развёрнутом окне, и на восстановленном.
        """
        super().showEvent(event)
        self._sync_mask_geometry()

        # Сторож на случай, когда окно меняет размер уже после показа
        # диалога. Так происходит на первом запуске: геометрия
        # восстанавливается из настроек, и окно из 800x600 становится во
        # весь экран — а маска остаётся от прежнего размера, накрывая
        # угол.
        #
        # Почему таймером, а не только фильтром событий. Фильтр ставит
        # библиотека, и её порядок доставки нам не подчиняется: две
        # предыдущие попытки поймать Resize через него результата не
        # дали. Таймер работает независимо от маршрутизации событий, а
        # стоит он ровно ничего: пять кадров в секунду, и только пока на
        # экране висит модальный диалог.
        self._ensure_mask_watchdog()

    #: Как часто сторож сверяет размер маски с окном.
    MASK_WATCH_MS = 200

    def _ensure_mask_watchdog(self) -> None:
        watchdog = getattr(self, "_mask_watchdog", None)
        if watchdog is None:
            from PyQt6.QtCore import QTimer

            watchdog = QTimer(self)
            watchdog.setInterval(self.MASK_WATCH_MS)
            watchdog.timeout.connect(self._sync_mask_geometry)
            self._mask_watchdog = watchdog
        if not watchdog.isActive():
            watchdog.start()

    def hideEvent(self, event):  # noqa: N802 (Qt override)
        watchdog = getattr(self, "_mask_watchdog", None)
        if watchdog is not None:
            watchdog.stop()
        super().hideEvent(event)

    def _sync_mask_geometry(self) -> None:
        host = self.parent() or getattr(self, "_mask_event_filter_host", None)
        mask = getattr(self, "windowMask", None)
        if host is None or mask is None:
            return
        try:
            self.resize(host.size())
            mask.resize(host.size())
        except Exception:
            return

        # Диалог центрируем сами: базовый класс делает это в своём
        # resizeEvent, а изменение размера маски его не вызывает.
        inner = getattr(self, "widget", None)
        if inner is None:
            return
        try:
            inner.move(
                (self.width() - inner.width()) // 2,
                (self.height() - inner.height()) // 2,
            )
        except Exception:
            pass

    def _onDone(self, code):  # noqa: N802 (qfluentwidgets API)
        self._detach_mask_event_filter()
        return super()._onDone(code)

    def exec(self) -> int:
        try:
            return super().exec()
        finally:
            self._detach_mask_event_filter()


class MessageBoxBase(_ManagedMaskDialogLifecycle, _QFluentMessageBoxBase):
    """Основа проектных fluent-диалогов с корректным завершением."""


class MessageBox(_ManagedMaskDialogLifecycle, _QFluentMessageBox):
    """Стандартный fluent-диалог с корректным завершением."""


__all__ = ["MessageBox", "MessageBoxBase"]
