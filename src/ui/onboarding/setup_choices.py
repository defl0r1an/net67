"""Первичная настройка внутри обучающего тура.

Мастер первого запуска был отдельным окном из четырёх экранов, а тур —
отдельной экскурсией после него. Человек проходил две анкеты подряд, и
вторая начиналась словами «добро пожаловать», когда он уже минуту
отвечал на вопросы. Теперь вопросы мастера задаёт сам тур — у того
раздела, к которому ответ относится: провайдер — у «Пресетов», что
открывать через hosts — у «Редактора hosts», проверка — у BlockCheck,
автозапуск — у «Настроек программы».

Логика ответов не переехала: что спрашивать и во что превращать ответы,
по-прежнему решают wizard/plans.py и wizard/apply.py. Здесь только виджеты
на карточке и момент записи.

Ответы записываются одним разом в конце — по «Готово» или «Пропустить»,
как раньше по «Готово» мастера. Провайдер — исключение: он выбирает
пресет, а пресеты тур показывает сразу после вопроса, и там должен стоять
уже выбранный.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from log.log import log
from ui.onboarding.setup_detect_worker import _DetectWorker

__all__ = [
    "CHOICE_KEYS",
    "SetupAnswers",
    "apply_provider_answer",
    "apply_setup_answers",
    "build_choice_widget",
]

#: Выборы, которые умеет показывать карточка тура.
CHOICE_KEYS = ("provider", "hosts", "detect", "startup")

#: Подписи переключателей. В qfluentwidgets они «On» и «Off» — английские
#: слова посреди русского окна.
SWITCH_ON_TEXT = "Вкл."
SWITCH_OFF_TEXT = "Выкл."


def _default_hosts_groups() -> set[str]:
    from wizard.plans import default_hosts_groups

    return set(default_hosts_groups())


@dataclass(slots=True)
class SetupAnswers:
    """Ответы первичной настройки. Значения по умолчанию — те же, что у мастера."""

    provider: str = "unknown"
    hosts_groups: set[str] = field(default_factory=_default_hosts_groups)
    autostart: bool = True
    tray: bool = True
    #: Какой провайдер уже записан — чтобы не выбирать пресет повторно
    #: на каждом «Далее» туда-обратно.
    provider_applied: str | None = None
    #: Итог проверки доступности: вернулся к шагу — видит его, а не новую
    #: минуту ожидания.
    detect_results: list | None = None
    applied: bool = False


# ── запись ────────────────────────────────────────────────────────────


def apply_provider_answer(answers: SetupAnswers, *, select_preset=None) -> None:
    if answers.provider_applied == answers.provider:
        return
    try:
        from provider.apply import apply_provider_choice

        ok, detail = apply_provider_choice(answers.provider, select_preset=select_preset)
        if not ok:
            log(f"Первичная настройка, провайдер: {detail}", "WARNING")
    except Exception as exc:
        log(f"Первичная настройка, провайдер: {exc}", "WARNING")
    answers.provider_applied = answers.provider


def apply_setup_answers(window, answers: SetupAnswers, *, select_preset=None) -> bool:
    """Записывает ответы и отмечает первичную настройку пройденной.

    Флаг «пройдена» ставит apply_wizard последним: если запись упала,
    настройка откроется при следующем запуске снова, а не потеряется.
    """
    if answers.applied:
        return True
    apply_provider_answer(answers, select_preset=select_preset)
    try:
        from wizard.apply import apply_wizard
        from wizard.plans import default_selection

        result = apply_wizard(
            selection=default_selection(),
            hosts_groups=set(answers.hosts_groups),
            autostart_with_windows=bool(answers.autostart),
            minimize_to_tray=bool(answers.tray),
        )
    except Exception as exc:
        log(f"Первичная настройка не сохранилась: {exc}", "ERROR")
        return False
    if not result.saved:
        log(f"Первичная настройка: {result.message}", "WARNING")
        return False
    for warning in result.warnings:
        log(f"Первичная настройка: {warning}", "WARNING")
    answers.applied = True
    try:
        from settings.store import set_onboarding_tour_done

        set_onboarding_tour_done(True)
    except Exception as exc:
        log(f"Не удалось запомнить, что тур пройден: {exc}", "WARNING")
    try:
        from main.post_startup_wizard import resync_open_pages

        resync_open_pages(window)
    except Exception as exc:
        log(f"Первичная настройка: страницы не перечитали настройки: {exc}", "DEBUG")
    log("Первичная настройка сохранена из обучающего тура", "INFO")
    return True


# ── виджеты карточки ────────────────────────────────────────────────


def _muted(text: str, parent: QWidget, *, size: int = 12) -> QLabel:
    from ui.theme import get_theme_tokens

    label = QLabel(text, parent)
    label.setWordWrap(True)
    label.setStyleSheet(f"QLabel {{ color: {get_theme_tokens().fg_muted}; font-size: {size}px; background: transparent; }}")
    return label


def _switch():
    from ui.widgets.aligned_switch import AlignedSwitchButton

    switch = AlignedSwitchButton()
    switch.setOnText(SWITCH_ON_TEXT)
    switch.setOffText(SWITCH_OFF_TEXT)
    return switch


def _provider_widget(answers: SetupAnswers, parent: QWidget) -> QWidget:
    from qfluentwidgets import ComboBox

    from provider.catalog import PROVIDERS, describe_choice
    from ui.accessibility import set_control_accessibility

    box = QWidget(parent)
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 2, 0, 0)
    layout.setSpacing(6)
    combo = ComboBox(box)
    current = 0
    for index, provider in enumerate(PROVIDERS):
        combo.addItem(provider.title, userData=provider.key)
        if provider.key == answers.provider:
            current = index
    combo.setCurrentIndex(current)
    set_control_accessibility(combo, name="Провайдер", description="Выберите своего интернет-провайдера")
    layout.addWidget(combo, 0, Qt.AlignmentFlag.AlignLeft)
    note = _muted(describe_choice(answers.provider), box)
    layout.addWidget(note)

    def _changed(index: int) -> None:
        answers.provider = str(combo.itemData(index) or "unknown")
        # Обещать «теперь заработает» нельзя: пресет — только точка
        # старта, правду покажет проверка у BlockCheck.
        note.setText(describe_choice(answers.provider))

    combo.currentIndexChanged.connect(_changed)
    return box


def _hosts_widget(answers: SetupAnswers, parent: QWidget) -> QWidget:
    """Галочки «что должно работать без VPN».

    Одна колонка на широкой карточке: примеры помещаются в строку. Две
    колонки обрезали названия групп — галочка qfluentwidgets не переносит
    свой текст, а у ноутбука с крупным шрифтом «Музыка, видео и
    развлечения» в полколонки не влезает.
    """
    from qfluentwidgets import CheckBox

    from ui.accessibility import set_control_accessibility
    from wizard.plans import HOSTS_CAUTION_NOTE, HOSTS_GROUPS

    box = QWidget(parent)
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 2, 0, 0)
    layout.setSpacing(2)
    for group in HOSTS_GROUPS:
        check = CheckBox(group.title, box)
        check.setChecked(group.key in answers.hosts_groups)

        def _toggled(checked: bool, key: str = group.key) -> None:
            if checked:
                answers.hosts_groups.add(key)
            else:
                answers.hosts_groups.discard(key)

        check.toggled.connect(_toggled)
        set_control_accessibility(check, name=group.title, description=group.examples)
        layout.addWidget(check)
        examples = _muted(group.examples, box, size=11)
        # Отступ под галочку: примеры читаются как её подпись.
        examples.setContentsMargins(28, 0, 0, 4)
        layout.addWidget(examples)
    layout.addSpacing(4)
    layout.addWidget(_muted(HOSTS_CAUTION_NOTE, box, size=11))
    return box


def _startup_widget(answers: SetupAnswers, parent: QWidget) -> QWidget:
    from qfluentwidgets import StrongBodyLabel

    from ui.accessibility import set_control_accessibility

    box = QWidget(parent)
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 2, 0, 0)
    layout.setSpacing(10)
    rows = (
        ("autostart", "Запускать вместе с Windows", "Обход включится сам после входа в систему"),
        ("tray", "Сворачивать в трей", "Крестик прячет окно к часам, а не выключает обход"),
    )
    for attr, title, hint in rows:
        row = QHBoxLayout()
        row.setSpacing(12)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        # Подпись qfluentwidgets, а не голый QLabel: у голого нет цвета
        # темы, и на тёмной карточке тура он выходил тёмным по тёмному.
        caption = StrongBodyLabel(title, box)
        texts.addWidget(caption)
        texts.addWidget(_muted(hint, box, size=11))
        row.addLayout(texts, 1)
        switch = _switch()
        switch.setChecked(bool(getattr(answers, attr)))
        switch.checkedChanged.connect(lambda checked, name=attr: setattr(answers, name, bool(checked)))
        set_control_accessibility(switch, name=title, description=hint)
        row.addWidget(switch, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(row)
    return box


def describe_detect_results(results: list | None) -> tuple[str, str]:
    """Заголовок и подробности итога проверки — словами, без кодов.

    Таймаут DNS не считается «закрыто». На машине владельца DNS Windows
    отвечал 12 секунд на каждое новое имя, проверка ждала 3 — и карточка
    объявляла «Закрыто 3 из 4», хотя до блокировок дело не дошло: адрес
    сайта просто не успел прийти.
    """
    if not results:
        return (
            "Проверить не удалось",
            "Похоже, нет соединения с сетью. Настройки останутся по умолчанию, а проверить можно позже здесь же, в BlockCheck.",
        )
    items = [tuple(item) + ("",) * (4 - len(item)) for item in results]
    slow_dns = [item for item in items if not item[1] and item[3] == "dns_timeout"]
    checked = [item for item in items if item not in slow_dns]
    blocked = [item for item in checked if not item[1]]
    slow_note = ""
    if slow_dns:
        names = ", ".join(domain for domain, *_rest in slow_dns)
        slow_note = (
            f"Не проверены: {names} — DNS не успел назвать адрес сайта. Это не блокировка, "
            "а медленный DNS Windows; часто так тормозят DNS-серверы отключённого VPN-адаптера."
        )
    if not checked:
        return ("DNS не успел ответить", slow_note + "\n\nПроверить блокировки можно позже здесь же, в BlockCheck.")
    if not blocked:
        text = "Проверенные сервисы открываются и без обхода. Включить его всё равно стоит: блокировки появляются без предупреждения."
        return ("Ограничений не нашли", text + ("\n\n" + slow_note if slow_note else ""))
    lines = "\n".join(f"• {domain} — {detail or 'нет доступа'}" for domain, _ok, detail, _kind in blocked)
    tail = "Это и лечит обход. Если после включения что-то не откроется, здесь же есть точный подбор стратегии."
    return (
        f"Закрыто {len(blocked)} из {len(checked)}",
        lines + ("\n\n" + slow_note if slow_note else "") + "\n\n" + tail,
    )


#: Потоки проверки, которые ещё работают. Поток живёт без родителя: карточку
#: тура удаляют, когда человек уходит с шага, а живой QThread в момент
#: удаления родителя — это падение Qt, не предупреждение. Ссылка здесь
#: держит поток до конца работы, дальше он удаляет себя сам.
_RUNNING_WORKERS: set = set()


class _DetectPanel(QWidget):
    """Итог проверки доступности. Проверка идёт сама, пока карточка на экране."""

    def __init__(self, answers: SetupAnswers, parent: QWidget, on_resize: Callable[[], None]) -> None:
        super().__init__(parent)
        self._answers = answers
        self._on_resize = on_resize
        self._worker: _DetectWorker | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(4)
        from qfluentwidgets import StrongBodyLabel

        self.status = StrongBodyLabel("", self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.details = _muted("", self)
        layout.addWidget(self.details)
        if answers.detect_results is not None:
            self._show(answers.detect_results)
        else:
            self._start()

    def _start(self) -> None:
        from wizard.plans import build_probe_urls, default_selection

        self.status.setText("Проверяем, что открывается без обхода…")
        self.details.setText("Это займёт до минуты. Ждать не обязательно — «Далее» можно нажать сразу.")
        worker = _DetectWorker(build_probe_urls(default_selection()))
        worker.progress.connect(self._on_progress)
        worker.finished_with.connect(self._on_done)
        _RUNNING_WORKERS.add(worker)
        worker.finished.connect(lambda w=worker: (_RUNNING_WORKERS.discard(w), w.deleteLater()))
        self._worker = worker
        worker.start()

    def _on_progress(self, text: str) -> None:
        self.status.setText(text)
        self._on_resize()

    def _on_done(self, results: list) -> None:
        self._worker = None
        self._answers.detect_results = list(results)
        self._show(results)

    def _show(self, results) -> None:
        title, details = describe_detect_results(results)
        self.status.setText(title)
        self.details.setText(details)
        self._on_resize()

    def stop(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is None:
            return
        try:
            worker.cancel()
            for signal, slot in ((worker.finished_with, self._on_done), (worker.progress, self._on_progress)):
                try:
                    signal.disconnect(slot)
                except TypeError:
                    pass
        except RuntimeError:
            pass


def build_choice_widget(key: str, answers: SetupAnswers, parent: QWidget, *, on_resize: Callable[[], None]) -> QWidget | None:
    if key == "provider":
        return _provider_widget(answers, parent)
    if key == "hosts":
        return _hosts_widget(answers, parent)
    if key == "startup":
        return _startup_widget(answers, parent)
    if key == "detect":
        return _DetectPanel(answers, parent, on_resize)
    return None


def stop_choice_widget(widget) -> None:
    stop = getattr(widget, "stop", None)
    if callable(stop):
        stop()


def choice_frame(parent: QWidget) -> QFrame:
    frame = QFrame(parent)
    frame.setObjectName("onboardingChoice")
    frame.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(0, 4, 0, 4)
    layout.setSpacing(0)
    return frame
