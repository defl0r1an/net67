# wizard/ui/dialog.py
"""Мастер первого запуска: три экрана в одном диалоге.

Логика вопросов и преобразование ответов живут в wizard/plans.py, запись
настроек — в wizard/apply.py. Здесь только виджеты и переключение шагов.

Диагностика на втором экране идёт в отдельном потоке: check_one_domain
делает DNS, TCP, ping и HTTP-запросы, и в UI-потоке это заморозило бы
окно на десятки секунд.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, ComboBox, StrongBodyLabel, SwitchButton, TitleLabel

from log.log import log
from ui.accessibility import set_control_accessibility
from ui.fluent_dialog import MessageBoxBase
from ui.theme import get_theme_tokens
from provider.catalog import PROVIDERS, UNKNOWN, describe_choice
from wizard.plans import (
    WIZARD_STEPS,
    build_probe_urls,
    default_selection,
    is_last_step,
    next_step_index,
    prev_step_index,
    wizard_progress_percent,
)


class _DetectWorker(QThread):
    """Проверяет доступность выбранных сервисов."""

    progress = pyqtSignal(str)
    finished_with = pyqtSignal(list)

    def __init__(self, urls, parent=None):
        super().__init__(parent)
        self._urls = list(urls or ())
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        from urllib.parse import urlparse

        results: list[tuple[str, bool, str]] = []
        try:
            from blockcheck.models import PreflightVerdict
            from blockcheck.preflight import check_one_domain

            for url in self._urls:
                if self._cancelled:
                    break
                domain = urlparse(url).netloc or url
                self.progress.emit(f"Проверяем {domain}...")
                result = check_one_domain(domain, cancelled=lambda: self._cancelled)
                ok = result.verdict is PreflightVerdict.PASSED
                results.append((domain, ok, str(result.verdict_detail or "")))
        except Exception as exc:
            log(f"Диагностика мастера: {exc}", "⚠ WARNING")

        self.finished_with.emit(results)


class WizardDialog(MessageBoxBase):
    """Три экрана: провайдер, проверка доступности, параметры запуска.

    Провайдер спрашивается первым: он выбирает пресет, а пресет должен
    быть выставлен раньше, чем соберётся запрос на включение.

    Экрана с вопросом «чем вы пользуетесь?» нет. Обходы включаются
    целиком при первом запуске, поэтому ответ ни на что не влиял —
    оставался лишний шаг перед началом работы.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._step = 0
        self._provider = UNKNOWN
        self._selection = set(default_selection())
        self._detect_worker: _DetectWorker | None = None
        self._detect_done = False
        self._checked = 0
        self._to_check = 0
        self._step_animations: list = []

        self._build_ui()
        self._apply_step()

    # ──────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        tokens = get_theme_tokens()

        self.title_label = TitleLabel("")
        self.subtitle_label = BodyLabel("")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet(f"QLabel {{ color: {tokens.fg_muted}; }}")

        self.viewLayout.addWidget(self.title_label)
        self.viewLayout.addWidget(self.subtitle_label)
        self.viewLayout.addSpacing(12)

        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(10)
        self.viewLayout.addWidget(self.body)

        # Проценты в углу блёклым шрифтом. Мастер идёт минуту с лишним,
        # и без них непонятно, это половина пути или начало.
        self.progress_hint = QLabel("", self)
        self.progress_hint.setStyleSheet(
            f"QLabel {{ color: {tokens.fg_muted}; font-size: 11px; }}"
        )
        self.progress_hint.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.viewLayout.addSpacing(6)
        self.viewLayout.addWidget(self.progress_hint)

        self._build_provider_page()
        self._build_detect_page()
        self._build_startup_page()

        self.yesButton.setText("Далее")
        self.cancelButton.setText("Назад")
        self.yesButton.clicked.disconnect()
        self.cancelButton.clicked.disconnect()
        self.yesButton.clicked.connect(self._on_next)
        self.cancelButton.clicked.connect(self._on_back)

        self.widget.setMinimumWidth(520)

    def _build_provider_page(self) -> None:
        self.provider_page = QWidget(self.body)
        layout = QVBoxLayout(self.provider_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.provider_combo = ComboBox()
        for provider in PROVIDERS:
            self.provider_combo.addItem(provider.title, userData=provider.key)
        self.provider_combo.setCurrentIndex(len(PROVIDERS) - 1)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        set_control_accessibility(
            self.provider_combo,
            name="Провайдер",
            description="Выберите своего интернет-провайдера",
        )
        layout.addWidget(self.provider_combo)

        self.provider_note = BodyLabel(describe_choice(self._provider))
        self.provider_note.setWordWrap(True)
        self.provider_note.setStyleSheet(
            f"QLabel {{ color: {get_theme_tokens().fg_faint}; font-size: 12px; }}"
        )
        layout.addWidget(self.provider_note)

        self.body_layout.addWidget(self.provider_page)

    def _on_provider_changed(self, index: int) -> None:
        try:
            key = self.provider_combo.itemData(index)
        except Exception:
            key = None
        self._provider = str(key or UNKNOWN)
        # Обещать «теперь заработает» нельзя: пресет — только точка
        # старта, правду скажет проверка на следующем экране.
        self.provider_note.setText(describe_choice(self._provider))

    def _build_detect_page(self) -> None:
        self.detect_page = QWidget(self.body)
        layout = QVBoxLayout(self.detect_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.detect_status = StrongBodyLabel("Готово к проверке")
        layout.addWidget(self.detect_status)

        self.detect_details = QLabel("")
        self.detect_details.setWordWrap(True)
        self.detect_details.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.detect_details.setStyleSheet(
            f"QLabel {{ color: {get_theme_tokens().fg_muted}; }}"
        )
        layout.addWidget(self.detect_details)

        note = BodyLabel(
            "Проверка занимает до минуты. Её можно пропустить — тогда "
            "останутся настройки по умолчанию, а подобрать стратегию "
            "точнее получится в разделе диагностики."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"QLabel {{ color: {get_theme_tokens().fg_faint}; font-size: 12px; }}")
        layout.addWidget(note)

        self.body_layout.addWidget(self.detect_page)

    def _build_startup_page(self) -> None:
        self.startup_page = QWidget(self.body)
        layout = QVBoxLayout(self.startup_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.autostart_switch = SwitchButton()
        self.autostart_switch.setChecked(True)
        self._add_switch_row(
            layout,
            self.autostart_switch,
            "Запускать вместе с Windows",
            "Обход включится сам после входа в систему",
        )

        self.tray_switch = SwitchButton()
        self.tray_switch.setChecked(True)
        self._add_switch_row(
            layout,
            self.tray_switch,
            "Сворачивать в трей",
            "Кнопка закрытия прячет окно, а не завершает работу",
        )

        # Выбор темы убран: механизм смены темы работает ненадёжно,
        # и спрашивать о ней при первом запуске бессмысленно.

        self.body_layout.addWidget(self.startup_page)

    def _add_switch_row(self, layout, switch, title: str, description: str) -> None:
        from PyQt6.QtWidgets import QHBoxLayout

        row = QHBoxLayout()
        row.setSpacing(12)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        caption = StrongBodyLabel(title)
        texts.addWidget(caption)
        hint = BodyLabel(description)
        hint.setWordWrap(True)
        hint.setStyleSheet(f"QLabel {{ color: {get_theme_tokens().fg_faint}; font-size: 12px; }}")
        texts.addWidget(hint)

        row.addLayout(texts, 1)
        row.addWidget(switch)
        set_control_accessibility(switch, name=title, description=description)
        layout.addLayout(row)

    # ──────────────────────────────────────────────────────────────────

    def _apply_step(self) -> None:
        step = WIZARD_STEPS[self._step]
        self.title_label.setText(step.title)
        self.subtitle_label.setText(step.subtitle)

        self.provider_page.setVisible(step.key == "provider")
        self.detect_page.setVisible(step.key == "detect")
        self.startup_page.setVisible(step.key == "startup")

        # На первом шаге возвращаться некуда. Раньше кнопка была просто
        # неактивной, но серая «Назад» рядом с «Далее» — это вопрос без
        # ответа: человек видит выход, которого нет. Прячем совсем.
        has_previous = self._step > 0
        self.cancelButton.setVisible(has_previous)
        self.cancelButton.setEnabled(has_previous)
        if step.key == "detect":
            self.yesButton.setText("Пропустить" if not self._detect_done else "Далее")
        else:
            self.yesButton.setText("Готово" if is_last_step(self._step) else "Далее")

        self._refresh_progress_hint()

        if step.key == "detect" and not self._detect_done:
            self._start_detect()

    def _refresh_progress_hint(self) -> None:
        percent = wizard_progress_percent(
            self._step, checked=self._checked, to_check=self._to_check
        )
        self.progress_hint.setText(f"Настройка выполнена на {percent}%")

    def _start_detect(self) -> None:
        if self._detect_worker is not None and self._detect_worker.isRunning():
            return

        urls = build_probe_urls(self._selection)
        self.detect_status.setText("Проверяем доступность...")
        self.detect_details.setText("")
        self._to_check = len(urls)
        self._checked = 0
        self._refresh_progress_hint()

        worker = _DetectWorker(urls, parent=self)
        worker.progress.connect(self.detect_status.setText)
        worker.progress.connect(self._on_domain_started)
        worker.finished_with.connect(self._on_detect_done)
        worker.finished.connect(self._on_detect_worker_done)
        self._detect_worker = worker
        worker.start()

    def _on_domain_started(self, _message: str) -> None:
        """Считает опрошенные домены: из них и складываются проценты.

        Сообщение приходит перед каждой проверкой, поэтому первый домен
        даёт 0 из N, а не 1 из N — так и правильно: он ещё не проверен.
        """
        self._checked = min(self._checked + 1, self._to_check)
        self._refresh_progress_hint()

    def _on_detect_done(self, results: list) -> None:
        self._detect_done = True

        if not results:
            self.detect_status.setText("Проверить не удалось")
            self.detect_details.setText(
                "Похоже, нет соединения с сетью. Настройки останутся по умолчанию."
            )
        else:
            blocked = [r for r in results if not r[1]]
            if not blocked:
                self.detect_status.setText("Ограничений не обнаружено")
                self.detect_details.setText(
                    "Выбранные сервисы открываются напрямую. Обход всё равно "
                    "можно включить — она пригодится, если доступ пропадёт."
                )
            else:
                self.detect_status.setText(f"Обнаружены ограничения: {len(blocked)} из {len(results)}")
                self.detect_details.setText(
                    "\n".join(f"• {domain} — {detail or 'нет доступа'}" for domain, _ok, detail in blocked)
                    + "\n\nБудут применены универсальные настройки. Если "
                    "чего-то не хватит, точный подбор есть в разделе диагностики."
                )

        self._mark_detect_complete()

        if WIZARD_STEPS[self._step].key == "detect":
            self.yesButton.setText("Далее")

    def _mark_detect_complete(self) -> None:
        self._checked = self._to_check
        self._refresh_progress_hint()

    def _on_detect_worker_done(self) -> None:
        worker = self._detect_worker
        self._detect_worker = None
        if worker is not None:
            worker.deleteLater()

    # ──────────────────────────────────────────────────────────────────

    def _on_next(self) -> None:
        if is_last_step(self._step):
            self._finish()
            return
        self._step = next_step_index(self._step)
        self._apply_step()
        self._animate_step(forward=True)

    def _on_back(self) -> None:
        if self._step == 0:
            return
        self._step = prev_step_index(self._step)
        self._apply_step()
        self._animate_step(forward=False)

    # ──────────────────────────────────────────────────────────────────

    def _animate_step(self, *, forward: bool) -> None:
        """Новый экран въезжает сбоку и проявляется.

        Двигаем не сам виджет, а отступы его контейнера. Страницы лежат
        в раскладке, и заданная вручную позиция была бы сброшена первым
        же её пересчётом — а он случается от чего угодно, вплоть до
        смены текста кнопки. Отступы раскладка уважает, поэтому такой
        сдвиг переживает пересчёт.

        Направление читается: вперёд — экран приходит справа, назад —
        слева. Без этого переход есть, а куда идём, непонятно.
        """
        from PyQt6.QtCore import QEasingCurve, QVariantAnimation
        from PyQt6.QtWidgets import QGraphicsOpacityEffect

        from ui.animation_policy import start_managed_animation

        shift = 48

        def set_shift(value) -> None:
            offset = max(0, int(value))
            if forward:
                self.body_layout.setContentsMargins(offset, 0, 0, 0)
            else:
                self.body_layout.setContentsMargins(0, 0, offset, 0)

        slide = QVariantAnimation(self)
        slide.setStartValue(shift)
        slide.setEndValue(0)
        slide.setDuration(220)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        slide.valueChanged.connect(set_shift)
        slide.finished.connect(lambda: self.body_layout.setContentsMargins(0, 0, 0, 0))

        effect = QGraphicsOpacityEffect(self.body)
        self.body.setGraphicsEffect(effect)
        fade = QVariantAnimation(self)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setDuration(220)
        fade.valueChanged.connect(lambda value: effect.setOpacity(float(value)))
        # Эффект снимаем после показа: он держит отдельный слой отрисовки
        # и на нём заметно дороже перерисовывать содержимое.
        fade.finished.connect(lambda: self.body.setGraphicsEffect(None))

        self._step_animations = [slide, fade]
        for animation in self._step_animations:
            start_managed_animation(animation)

        if slide.duration() <= 0:
            # Анимации отключены человеком: показываем сразу и начисто.
            set_shift(0)
            effect.setOpacity(1.0)
            self.body.setGraphicsEffect(None)

    def _finish(self) -> None:
        from wizard.apply import apply_wizard

        self._stop_detect()
        # Провайдер применяется до общих настроек: он выбирает пресет, а
        # пресет должен быть выставлен раньше, чем оркестратор соберёт
        # запрос на включение.
        try:
            from provider.apply import apply_provider_choice

            ok, detail = apply_provider_choice(self._provider)
            if not ok:
                log(f"Мастер, провайдер: {detail}", "⚠ WARNING")
        except Exception as exc:
            log(f"Мастер, провайдер: {exc}", "⚠ WARNING")

        result = apply_wizard(
            selection=self._selection,
            autostart_with_windows=self.autostart_switch.isChecked(),
            minimize_to_tray=self.tray_switch.isChecked(),
        )
        if not result.saved:
            log(f"Мастер: {result.message}", "⚠ WARNING")
        for warning in result.warnings:
            log(f"Мастер: {warning}", "⚠ WARNING")
        self.accept()

    def _stop_detect(self) -> None:
        worker = self._detect_worker
        self._detect_worker = None
        if worker is None:
            return
        try:
            worker.cancel()
            if worker.isRunning():
                worker.quit()
                worker.wait(3000)
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        """Останавливает проверку при любом закрытии окна.

        reject() ловит Esc и «Назад», _finish() — «Готово». Но диалог
        может уйти и вместе с родительским окном, а живой QThread в
        момент уничтожения — это фатальная ошибка Qt, не предупреждение:
        процесс падает с дампом.
        """
        self._stop_detect()
        super().closeEvent(event)

    def reject(self) -> None:
        # Мастер нельзя «отменить» на первом шаге — кнопка «Назад» там
        # скрыта, а закрытие окна равносильно пропуску настройки.
        self._stop_detect()
        super().reject()


def show_wizard_if_needed(parent=None) -> bool:
    """Показывает мастер, если он ещё не пройден. True — показали."""
    from wizard.apply import is_wizard_needed

    if not is_wizard_needed():
        return False

    try:
        dialog = WizardDialog(parent)
        dialog.exec()
        return True
    except Exception as exc:
        log(f"Не удалось открыть мастер первого запуска: {exc}", "❌ ERROR")
        return False


__all__ = ["WizardDialog", "show_wizard_if_needed"]
