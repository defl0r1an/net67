"""Все переключатели управляют одной очередью движка, как и «Включить всё»."""

from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt, QRect
from PyQt6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, CaptionLabel, CheckBox, ComboBox, FluentIcon, InfoBar, LineEdit,
    PasswordLineEdit, PrimaryPushButton, PushButton, SegmentedWidget, StrongBodyLabel, TransparentPushButton,
    setCustomStyleSheet,
)

from antigravity.controller import AntigravityController
from antigravity.model_hosts import MODEL_HOSTS_SERVICES
from ui.accessibility import set_control_accessibility
from ui.fluent_dialog import MessageBoxBase
from ui.fluent_widgets import SettingsCard, set_tooltip
from ui.one_shot_worker_runtime import OneShotWorkerRuntime
from ui.pages.base_page import BasePage, ScrollBlockingPlainTextEdit
from ui.segmented_accessibility import set_segmented_items_accessibility
from ui.theme import get_cached_qta_pixmap, get_theme_tokens, get_themed_qta_icon
from ui.theme_semantic import get_semantic_palette
from ui.widgets.stagger_float_in import attach_stagger_float_in
from ui.widgets.win11_controls import Win11ToggleRow


MODEL_HOSTS_LABELS = {"Gemini AI": "Gemini и Antigravity", "Claude": "Claude", "ChatGPT & Sora (OpenAI)": "ChatGPT"}


class _DisableAllDialog(MessageBoxBase):
    def __init__(self, parent):
        super().__init__(parent)
        self.remove_hosts = None
        heading = QHBoxLayout()
        heading.setSpacing(12)
        icon = QLabel(self)
        icon.setFixedSize(22, 22)
        icon.setPixmap(get_cached_qta_pixmap("fa5s.exclamation-circle", size=22, color=get_theme_tokens().fg))
        heading.addWidget(icon)
        title = StrongBodyLabel("Убрать адреса нейросетей из hosts?", self)
        title.setWordWrap(True)
        heading.addWidget(title, 1)
        self.viewLayout.addLayout(heading)
        detail = BodyLabel("Функции Antigravity будут выключены. Адреса Gemini, Claude и ChatGPT можно убрать или оставить для работы в браузере. Antigravity может закрыться для восстановления клиента.", self)
        detail.setWordWrap(True)
        self.viewLayout.addWidget(detail)
        self.yesButton.setText("Убрать из hosts")
        self.cancelButton.setText("Оставить в hosts")
        self.yesButton.clicked.disconnect()
        self.cancelButton.clicked.disconnect()
        self.yesButton.clicked.connect(lambda: self._choose(True))
        self.cancelButton.clicked.connect(lambda: self._choose(False))
        self.cancelButton.setFocus()
        self.closeButton = PushButton("Отмена", self)
        self.closeButton.clicked.connect(self.reject)
        self.buttonLayout.addWidget(self.closeButton)
        self.widget.setMinimumWidth(480)

    def _choose(self, remove):
        self.remove_hosts = remove
        self.accept()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self.cancelButton.setFocus)


class _CapRow(Win11ToggleRow):
    """Неизвестное состояние не выдаётся за выключенную функцию."""

    def __init__(self, icon, title, description, parent):
        super().__init__(icon, title, description, parent=parent)
        self.setMaximumHeight(16777215)
        self._title_label.setWordWrap(True)
        self._desc_label.setWordWrap(True)
        self._title_label.setMinimumWidth(0)
        self._desc_label.setMinimumWidth(0)
        # У стандартной строки растягивался пустой spacer, а колонка текста
        # сжималась до длинного столбика и обрезалась по высоте.
        self.hBoxLayout.setStretch(2, 1)
        self.hBoxLayout.setStretch(4, 0)
        for label in (self._title_label, self._desc_label):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            self.vBoxLayout.setAlignment(label, Qt.AlignmentFlag(0))
        self._state_label = CaptionLabel("Не проверено", self)
        self.hBoxLayout.addWidget(self._state_label, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        # Раскладка строки заканчивается после resizeEvent. Смена высоты
        # прямо в нём оставляла колонку текста в геометрии прежней высоты.
        QTimer.singleShot(0, self._fit_text)

    def _fit_text(self):
        width = max(120, self.width() - 190)
        text_height = 0
        for label in (self._title_label, self._desc_label):
            height = label.fontMetrics().boundingRect(QRect(0, 0, width, 1000),
                                                     Qt.TextFlag.TextWordWrap, label.text()).height()
            label.setFixedHeight(height)
            text_height += height
        height = max(70, text_height + 26)
        if self.minimumHeight() != height:
            self.setFixedHeight(height)
        self.hBoxLayout.setGeometry(self.rect())

    def show_state(self, state, *, ready, busy, pending):
        known = ready and bool(state)
        self.setChecked(bool(state.get("on")), block_signals=True)
        self._switch_button.setVisible(known and not pending)
        self._state_label.setVisible(not known or pending)
        self._state_label.setText("Выполняю…" if pending else "Не проверено")
        self.setEnabled(known and not busy and state.get("kind") != "blocked")


class _SectionPanel(QWidget):
    """Строки настроек появляются общей последовательностью net67."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._motion = attach_stagger_float_in(self)

    def play_float_in(self, delay_ms=0):
        # Эффект на всей длинной странице заставлял бы перерисовывать её целиком.
        self._motion.play()

    def finish_float_in(self):
        self._motion.finish_all()


CAPS = (
    ("client_patch", "Разблокировать вход в аккаунт", "Применить изменение к установленным Antigravity, IDE и CLI."),
    ("bypass", "Обход региональной ошибки", "Локальная служба, прокси и маршруты для рабочих серверов Antigravity."),
    ("watchdog", "Сохранять разблокировку после обновлений", "Автоматически применять изменение к новой версии клиента."),
    ("local_proxy", "Локальный прокси", "Соединения Antigravity проходят через службу обхода."),
    ("dns", "Правила DNS", "Направлять запросы рабочих доменов Antigravity на локальную службу."),
    ("builtin_exits", "Встроенные маршруты", "Выбирать маршрут по настоящему ответу модели."),
    ("own_proxy", "Использовать свой HTTP-прокси", "Предпочитать сохранённый ниже прокси, когда он доступен."),
    ("group_proxy", "Дополнительный маршрут", "Использовать маршрут, заданный отдельным кодом доступа."),
    ("dns_rotation", "Ротация DNS-серверов", "Использовать весь включённый пул; при отключении — только первый сервер."),
    ("verify_tls", "Проверять сертификат Google", "Принимать адрес, только если он предъявляет настоящий сертификат Google."),
)


class AntigravityPage(BasePage):
    def __init__(self, parent=None, *, open_model_hosts=None, hosts_feature=None, controller=None):
        super().__init__("Antigravity", "Вход в аккаунт и работа моделей в Antigravity, IDE и CLI", parent)
        self._open_model_hosts = open_model_hosts
        self._hosts_feature = hosts_feature
        self._hosts_snapshot = None
        self._hosts_busy = False
        self._hosts_writing = False
        self._hosts_runtime = OneShotWorkerRuntime()
        self._checking = False
        self._stopping = False
        self._disable_waiting = False
        self._disable_request_id = None
        self._remove_hosts_on_stop = False
        self._hosts_disabling = False
        self.controller = controller if controller is not None else AntigravityController(self)
        self.controller.received.connect(self._received)
        self.controller.failed.connect(self._failed)
        self.controller.busy_changed.connect(self._busy_changed)
        self._ready = False
        self._status = {}
        self._headline = {}
        self._report_path = ""
        self._report_clipboard = False
        self._report_pending = False
        self._pending_cap = ""
        self._requested_action = None
        self._provider_names = []
        self._controls = []
        self._section = "main"
        self._tour_section = None
        self._build_ui()
        self._busy_changed(False, "")

    def _button(self, title, callback, *, primary=False, parent=None):
        button = (PrimaryPushButton if primary else PushButton)(title, parent or self.content)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        button.clicked.connect(lambda _checked=False: callback())
        set_control_accessibility(button, name=title)
        self._controls.append(button)
        return button

    def _build_ui(self):
        self.refresh_button = self._button("Проверить", self._refresh)
        self.refresh_button.setIcon(FluentIcon.SYNC)
        self.state_card = SettingsCard(parent=self.content)
        state_layout = self.state_card.main_layout
        state_layout.setSpacing(6)
        state_row = QHBoxLayout()
        state_row.setSpacing(14)
        self.state_icon = QLabel(self.state_card)
        self.state_icon.setFixedSize(28, 28)
        state_row.addWidget(self.state_icon, 0, Qt.AlignmentFlag.AlignTop)
        state_text = QVBoxLayout()
        state_text.setSpacing(4)
        self.state_title = StrongBodyLabel("Проверка ещё не запускалась", self.state_card)
        self.state_title.setWordWrap(True)
        self.state_detail = CaptionLabel("Состояние функций ещё не прочитано. «Проверить» покажет, что уже включено, и не изменит настройки.", self.state_card)
        self.state_detail.setWordWrap(True)
        state_text.addWidget(self.state_title)
        state_text.addWidget(self.state_detail)
        state_row.addLayout(state_text, 1)
        state_layout.addLayout(state_row)
        buttons = QHBoxLayout()
        self.enable_button = self._button("Включить всё", self._toggle_all, primary=True)
        self.enable_button.setIcon(FluentIcon.POWER_BUTTON)
        self.enable_button.setMinimumWidth(self.enable_button.fontMetrics().horizontalAdvance("Выключить всё") + 48)
        self.repair_button = self._button("Восстановить службу", lambda: self._send("repair"))
        self.repair_button.setIcon(FluentIcon.SYNC)
        self.repair_button.hide()
        for button in (self.enable_button, self.refresh_button, self.repair_button):
            buttons.addWidget(button)
        buttons.addStretch()
        state_layout.addLayout(buttons)
        self.enable_scope = CaptionLabel("Вход · работа моделей · автопатч · Gemini, Claude и ChatGPT в hosts. Antigravity может закрыться для изменения клиента.", self.state_card)
        self.enable_scope.setWordWrap(True)
        state_layout.addWidget(self.enable_scope)
        self.activity = BodyLabel("", self.state_card)
        self.activity.setWordWrap(True)
        self.activity.hide()
        state_layout.addWidget(self.activity)
        self.check_note = CaptionLabel("", self.state_card)
        self.check_note.setWordWrap(True)
        self.check_note.hide()
        state_layout.addWidget(self.check_note)
        self.verify_button = self._button("Пройти верификацию Google", self._verify)
        self.verify_button.hide()
        state_layout.addWidget(self.verify_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.add_widget(self.state_card)

        section_row = QWidget(self.content)
        section_layout = QHBoxLayout(section_row)
        section_layout.setContentsMargins(0, 0, 0, 0)
        self.sections = SegmentedWidget(section_row)
        set_segmented_items_accessibility(self.sections, name="Раздел Antigravity")
        section_layout.addWidget(self.sections, 0, Qt.AlignmentFlag.AlignLeft)
        section_layout.addStretch(1)
        self.add_widget(section_row)
        self.main_card = _SectionPanel(self.content)
        main_layout = QVBoxLayout(self.main_card)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(16)
        self.cap_rows = {}
        self._add_cap_rows(main_layout, CAPS[:3], "Основные функции", self.main_card)

        models = SettingsCard(parent=self.main_card)
        models.main_layout.addWidget(StrongBodyLabel("ИИ в hosts", models))
        hint = CaptionLabel("Для работы без VPN проверьте профили всех трёх сервисов. «Включить всё» добавит выключенные, сохранив ваш выбор.", models)
        hint.setWordWrap(True)
        models.main_layout.addWidget(hint)
        self.model_hosts_labels = {}
        for name in MODEL_HOSTS_SERVICES:
            model_row = QHBoxLayout()
            model_row.addWidget(BodyLabel(MODEL_HOSTS_LABELS[name], models), 1)
            label = CaptionLabel("Не проверено", models)
            model_row.addWidget(label)
            self.model_hosts_labels[name] = label
            models.main_layout.addLayout(model_row)
        if callable(self._open_model_hosts):
            self.model_hosts_button = self._button("Настроить ИИ в hosts", self._open_model_hosts, parent=models)
            set_tooltip(self.model_hosts_button, "Показать Gemini и Antigravity, Claude и ChatGPT в редакторе hosts")
            set_control_accessibility(self.model_hosts_button, name="Настроить ИИ в hosts",
                                      description="Открыть редактор и выделить все три сервиса: Gemini и Antigravity, Claude и ChatGPT.")
            self._controls.remove(self.model_hosts_button)
            models.main_layout.addWidget(self.model_hosts_button, 0, Qt.AlignmentFlag.AlignLeft)
        main_layout.addWidget(models)

        installations = SettingsCard(parent=self.main_card)
        installations_layout = installations.main_layout
        install_header = QHBoxLayout()
        install_header.addWidget(StrongBodyLabel("Установленные приложения", installations), 1)
        choose = self._button("Указать папку", self._choose_install, parent=installations)
        choose.setIcon(FluentIcon.FOLDER)
        install_header.addWidget(choose)
        installations_layout.addLayout(install_header)
        self.install_labels = {}
        for name in ("Antigravity 2.0", "Antigravity IDE", "Antigravity CLI"):
            row = QHBoxLayout()
            text = QVBoxLayout()
            text.setSpacing(2)
            text.addWidget(BodyLabel(name, installations))
            label = CaptionLabel("Ещё не проверено", installations)
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            text.addWidget(label)
            row.addLayout(text, 1)
            forget = TransparentPushButton(FluentIcon.CLOSE, "", installations)
            forget.clicked.connect(lambda _checked=False, kind=name: self._forget_install(kind))
            set_tooltip(forget, "Убрать указанный вручную путь")
            set_control_accessibility(forget, name=f"Убрать путь {name}")
            self._controls.append(forget)
            forget.hide()
            row.addWidget(forget)
            self.install_labels[name] = (label, forget)
            installations_layout.addLayout(row)
        main_layout.addWidget(installations)
        self.add_widget(self.main_card)

        self.advanced_card = _SectionPanel(self.content)
        advanced_layout = QVBoxLayout(self.advanced_card)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.setSpacing(14)
        self._add_cap_rows(advanced_layout, CAPS[3:8], "Компоненты сетевого обхода", self.advanced_card)
        self._add_cap_rows(advanced_layout, CAPS[8:], "DNS и сертификат", self.advanced_card)
        self.add_widget(self.advanced_card)
        self.advanced_card.hide()
        routes = SettingsCard(parent=self.advanced_card)
        routes_layout = routes.main_layout
        routes_layout.addWidget(StrongBodyLabel("Свои маршруты", routes))
        routes_layout.addWidget(CaptionLabel("HTTP-прокси", routes))
        self.own_proxy = LineEdit(routes)
        self.own_proxy.setPlaceholderText("http://адрес:порт или http://логин:пароль@адрес:порт")
        set_control_accessibility(self.own_proxy, name="Свой HTTP-прокси")
        proxy_row = QHBoxLayout()
        proxy_row.addWidget(self.own_proxy, 1)
        proxy_row.addWidget(self._button("Проверить и сохранить", lambda: self._send("own_proxy", value=self.own_proxy.text())))
        routes_layout.addLayout(proxy_row)
        # Это код для отдельного сетевого маршрута, а не активация приложения.
        routes_layout.addWidget(CaptionLabel("Дополнительный маршрут", routes))
        self.route_code = PasswordLineEdit(routes)
        self.route_code.setPlaceholderText("Код дополнительного маршрута (необязательно)")
        set_control_accessibility(self.route_code, name="Код дополнительного маршрута")
        route_row = QHBoxLayout()
        route_row.addWidget(self.route_code, 1)
        route_row.addWidget(self._button("Подключить маршрут", lambda: self._send("group_proxy", value=self.route_code.text())))
        routes_layout.addLayout(route_row)
        self.route_request_button = self._button("Скопировать запрос", self._copy_route_request)
        set_tooltip(self.route_request_button, "Скопировать запрос для подключения дополнительного маршрута")
        routes_layout.addWidget(self.route_request_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.network_label = CaptionLabel("Состояние сети ещё не проверено", routes)
        self.network_label.setWordWrap(True)
        routes_layout.addWidget(self.network_label)
        advanced_layout.addWidget(routes)
        dns = SettingsCard(parent=self.advanced_card)
        dns_layout = dns.main_layout
        self.providers_host = QWidget(dns)
        self.providers_layout = QVBoxLayout(self.providers_host)
        self.providers_layout.setContentsMargins(0, 0, 0, 0)
        dns_layout.addWidget(StrongBodyLabel("DNS-серверы", dns))
        dns_layout.addWidget(CaptionLabel("Отмеченные серверы участвуют в выборе рабочего маршрута.", dns))
        dns_layout.addWidget(self.providers_host)
        order = QHBoxLayout()
        self.first_provider = ComboBox(self.advanced_card)
        set_control_accessibility(self.first_provider, name="Первый DNS-сервер")
        order.addWidget(self.first_provider, 1)
        order.addWidget(self._button("Поставить первым", self._put_provider_first))
        dns_layout.addLayout(order)
        advanced_layout.addWidget(dns)

        self.log_card = SettingsCard(parent=self.content)
        log_layout = self.log_card.main_layout
        log_layout.setSpacing(10)
        log_layout.addWidget(StrongBodyLabel("Журнал Antigravity", self.log_card))
        self.journal = ScrollBlockingPlainTextEdit(self.log_card)
        self.journal.setReadOnly(True)
        self.journal.setMaximumBlockCount(500)
        self.journal.setFixedHeight(220)
        log_layout.addWidget(self.journal)
        reports = QHBoxLayout()
        self.report_button = self._button("Сохранить отчёт", self._save_report)
        self.copy_button = self._button("Скопировать отчёт", self._copy_report)
        self.report_button.setIcon(FluentIcon.SAVE)
        reports.addWidget(self.report_button)
        reports.addWidget(self.copy_button)
        reports.addStretch()
        log_layout.addLayout(reports)
        self.add_widget(self.log_card)
        self.log_card.hide()
        for key, title in (("main", "Основное"), ("network", "Сеть"), ("log", "Журнал")):
            self.sections.addItem(routeKey=key, text=title,
                                  onClick=lambda _checked=False, section=key: self._set_section(section))
        self._set_section("main")
        self._apply_page_theme()

    def _add_cap_rows(self, layout, caps, title, parent):
        layout.addWidget(StrongBodyLabel(title, parent))
        short = {"client_patch": "Вход в аккаунт", "bypass": "Работа моделей", "watchdog": "Автопатч"}
        icons = {"client_patch": "fa5s.user-check", "bypass": "fa5s.globe", "watchdog": "fa5s.sync-alt",
                 "local_proxy": "fa5s.plug", "dns": "fa5s.server", "builtin_exits": "fa5s.random",
                 "own_proxy": "fa5s.route", "group_proxy": "fa5s.network-wired",
                 "dns_rotation": "fa5s.exchange-alt", "verify_tls": "fa5s.shield-alt"}
        for name, full_title, hint in caps:
            row = _CapRow(icons[name], short.get(name, full_title), hint, parent)
            row.toggled.connect(lambda on, cap=name: self._toggle_cap(cap, on))
            self.cap_rows[name] = row
            layout.addWidget(row)

    def _set_section(self, section):
        self._section = section
        self.sections.setCurrentItem(section)
        for key, panel in (("main", self.main_card), ("network", self.advanced_card), ("log", self.log_card)):
            panel.setVisible(key == section)
        QTimer.singleShot(0, self._settle_section_layout)

    def _settle_section_layout(self):
        if self.isVisible():
            self._sync_content_width_to_viewport()
            self.content.layout().activate()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._settle_section_layout)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        # Viewport получает новую ширину после resizeEvent самой страницы.
        QTimer.singleShot(0, self._settle_section_layout)

    def _apply_page_theme(self, tokens=None, force=False):
        if not hasattr(self, "state_icon"):
            return
        semantic = get_semantic_palette()
        tone = self._headline.get("tone", "Off")
        color, icon = {
            "Ok": (semantic.success_text, "fa5s.check-circle"),
            "Action": (semantic.warning_text, "fa5s.exclamation-circle"),
        }.get(tone, (get_theme_tokens().fg_muted, "fa5s.info-circle"))
        self.state_icon.setPixmap(get_cached_qta_pixmap(icon, color=color, size=28))
        self._style_all_button()

    def _style_all_button(self):
        stop = self._stopping or self._all_enabled()
        self.enable_button.setProperty("antigravityStop", stop)
        tokens = get_theme_tokens()
        qss = f'''
PrimaryPushButton[antigravityStop="true"] {{color: {tokens.fg}; background: {tokens.surface_bg}; border: 1px solid {tokens.surface_border};}}
PrimaryPushButton[antigravityStop="true"]:hover {{background: {tokens.surface_bg_hover}; border-color: {tokens.surface_border_hover};}}
PrimaryPushButton[antigravityStop="true"]:pressed {{background: {tokens.surface_bg_pressed};}}
PrimaryPushButton[antigravityStop="true"]:disabled {{color: {tokens.fg_muted}; background: {tokens.surface_bg_disabled}; border-color: {tokens.surface_border_disabled};}}
'''
        if getattr(self, "_all_button_style", None) != (qss, stop):
            self._all_button_style = (qss, stop)
            setCustomStyleSheet(self.enable_button, qss, qss)
        self.enable_button.setIcon(get_themed_qta_icon("fa5s.stop", color=tokens.fg) if stop else FluentIcon.POWER_BUTTON)

    def on_page_activated(self):
        # Переходы из hosts и экскурсии не выражают намерения запускать движок.
        pass

    def onboarding_target(self, name):
        return {
            "controls": [self.enable_button, self.refresh_button, *[self.cap_rows[name] for name in ("client_patch", "bypass", "watchdog")]],
            "hosts": getattr(self, "model_hosts_button", None),
            "sections": self.sections,
        }.get(name)

    def onboarding_set_state(self, state):
        if state is None:
            if self._tour_section is not None:
                self._set_section(self._tour_section)
                self._tour_section = None
        elif state in {"main", "network", "log"}:
            if self._tour_section is None:
                self._tour_section = self._section
            self._set_section(state)

    def _refresh(self):
        if self.controller.busy or self._hosts_busy or self._stopping:
            return
        # Отдельная проверка никогда не исполняет оставшееся намерение включить.
        self._requested_action = None
        self._pending_cap = ""
        self._checking = True
        self.check_note.setText("Проверка только читает состояние приложений, службы и hosts.")
        self.check_note.show()
        if not self._ready:
            self.controller.start()
        else:
            if not self.controller.send("refresh"):
                self.controller.start()
        self._read_model_hosts()

    def _all_enabled(self):
        caps = self._status.get("caps", {})
        return self._ready and self._hosts_all_on() and all(caps.get(name, {}).get("on") and caps.get(name, {}).get("kind") != "partial"
                                   for name in ("client_patch", "watchdog", "dns", "local_proxy", "builtin_exits", "group_proxy"))

    def _install_missing(self):
        return "installs" in self._status and not any(install.get("path") for install in self._status["installs"])

    def _enable_all(self):
        if self.controller.busy or self._hosts_busy or self._stopping:
            return
        self._checking = False
        self.check_note.hide()
        self._requested_action = "enable_all"
        self._pending_cap = "all"
        if not self._ready:
            if not self.controller.start():
                self._requested_action = None
                self._pending_cap = ""
                self._busy_changed(False, "")
                return
        self._read_model_hosts()
        self._maybe_enable_all()

    def _toggle_all(self):
        if self._all_enabled():
            self._confirm_disable_all()
        else:
            self._enable_all()

    def _confirm_disable_all(self):
        if self.controller.busy or self._hosts_busy or self._stopping:
            return
        dialog = _DisableAllDialog(self.window())
        if not dialog.exec() or dialog.remove_hosts is None:
            return
        self._requested_action = None
        self._checking = False
        self.check_note.hide()
        self._remove_hosts_on_stop = dialog.remove_hosts
        self._stopping = self._disable_waiting = True
        self._pending_cap = "all_off"
        if self._send("disable_all"):
            self._disable_request_id = getattr(self.controller, "active_request_id", None)
            self._busy_changed(self.controller.busy, "Выключаю функции Antigravity…")
        else:
            self._stopping = self._disable_waiting = False
            self._busy_changed(self.controller.busy, "")

    def _finish_disable_all(self):
        self._stopping = self._disable_waiting = False
        self._pending_cap = ""
        self.check_note.setText("Отключение завершено. Текущее состояние показано в переключателях. " +
                               ("Адреса нейросетей убраны из hosts." if self._remove_hosts_on_stop else "Адреса нейросетей сохранены в hosts."))
        self.check_note.show()
        self._busy_changed(self.controller.busy, "")

    def _engine_disable_completed(self, verified):
        self._disable_waiting = False
        if verified is not True:
            self._stopping = False
            self._pending_cap = ""
            self.check_note.setText("Полное выключение не подтверждено. Проверьте журнал; адреса нейросетей из hosts не удалялись.")
            self.check_note.show()
            self._busy_changed(self.controller.busy, "")
            return
        if self._remove_hosts_on_stop and self._hosts_feature is not None:
            self._hosts_busy = self._hosts_writing = self._hosts_disabling = True
            self._busy_changed(False, "Убираю адреса нейросетей из hosts…")
            self._hosts_runtime.start_qthread_worker(
                worker_factory=lambda request_id: self._hosts_feature.create_services_disable_worker(request_id, MODEL_HOSTS_SERVICES, self),
                on_loaded=self._model_hosts_loaded, on_failed=self._model_hosts_failed)
        else:
            self._finish_disable_all()

    def _hosts_all_on(self):
        if self._hosts_feature is None:
            return True
        return self._hosts_snapshot is not None and all(
            self._hosts_snapshot.service(name) and self._hosts_snapshot.service(name).current
            for name in MODEL_HOSTS_SERVICES)

    def _read_model_hosts(self):
        if self._hosts_feature is None:
            return
        self._hosts_busy = True
        self._busy_changed(self.controller.busy, "Читаю профили ИИ в hosts…")
        self._hosts_runtime.start_qthread_worker(
            worker_factory=lambda request_id: self._hosts_feature.create_snapshot_worker(request_id, self),
            on_loaded=self._model_hosts_loaded, on_failed=self._model_hosts_failed)

    def _render_model_hosts(self):
        labels = dict(self._hosts_snapshot.dns_profiles) if self._hosts_snapshot else {}
        for name, label in self.model_hosts_labels.items():
            entry = self._hosts_snapshot.service(name) if self._hosts_snapshot else None
            label.setText(labels.get(entry.current, entry.current) if entry and entry.current else
                          "Выкл." if entry else "Не проверено")

    def _model_hosts_loaded(self, request_id, result):
        if not self._hosts_runtime.is_current(request_id):
            return
        writing = self._hosts_writing
        disabling = self._hosts_disabling
        self._hosts_busy = self._hosts_writing = False
        self._hosts_disabling = False
        if writing:
            self._hosts_snapshot = getattr(result, "snapshot", None)
            if not getattr(result, "success", False) or self._hosts_snapshot is None or not self._hosts_snapshot.readable:
                message = getattr(result, "message", "Не удалось записать hosts") if not getattr(result, "success", False) else "Не удалось перечитать hosts после записи"
                self._model_hosts_failed(request_id, message)
                return
        else:
            if result is None or not result.readable:
                self._model_hosts_failed(request_id, "Не удалось прочитать текущий hosts. Включение отменено")
                return
            self._hosts_snapshot = result
        self._render_model_hosts()
        if disabling:
            self._finish_disable_all()
            return
        self._busy_changed(self.controller.busy, "")
        self._maybe_enable_all()

    def _model_hosts_failed(self, request_id, message):
        if not self._hosts_runtime.is_current(request_id):
            return
        self._hosts_busy = self._hosts_writing = False
        self._stopping = self._disable_waiting = self._hosts_disabling = False
        self._requested_action = None
        self._pending_cap = ""
        if self._checking:
            self._checking = False
            self.check_note.setText("Не удалось прочитать профили ИИ в hosts. Откройте редактор hosts.")
        self._busy_changed(self.controller.busy, "")
        self._action_failed(f"Профили ИИ в hosts: {message}. Откройте редактор hosts.")

    def _maybe_enable_all(self):
        if self._requested_action != "enable_all" or not self._ready or self.controller.busy or self._hosts_busy:
            return
        if self._install_missing() or self._all_enabled():
            self._requested_action = None
            self._busy_changed(False, "")
            return
        if not self._hosts_all_on():
            self._hosts_busy = self._hosts_writing = True
            self._busy_changed(False, "Включаю Gemini, Claude и ChatGPT в hosts…")
            self._hosts_runtime.start_qthread_worker(
                worker_factory=lambda request_id: self._hosts_feature.create_services_enable_worker(request_id, MODEL_HOSTS_SERVICES, self),
                on_loaded=self._model_hosts_loaded, on_failed=self._model_hosts_failed)
            return
        self._requested_action = None
        self._send("enable_all")

    def _send(self, command, **values):
        if not self.controller.send(command, **values):
            self._pending_cap = ""
            self._busy_changed(self.controller.busy, "")
            return False
        return True

    def _busy_changed(self, busy, message):
        busy = bool(busy or self._hosts_busy or self._stopping)
        self.activity.setText(message)
        self.activity.setVisible(bool(message))
        for control in self._controls:
            control.setEnabled(self._ready and not busy)
        self.refresh_button.setEnabled(not busy)
        self.own_proxy.setEnabled(not busy)
        self.route_code.setEnabled(not busy)
        self.first_provider.setEnabled(self._ready and not busy)
        for checkbox in self.providers_host.findChildren(CheckBox):
            checkbox.setEnabled(not busy)
        self.report_button.setEnabled(self._ready and not busy and not self._report_pending)
        self.copy_button.setEnabled(self._ready and not busy and not self._report_pending)
        self.repair_button.setEnabled(self._ready and not busy and self._headline.get("action") == "Repair")
        stop = self._all_enabled()
        self.enable_button.setEnabled(not busy and (stop or not self._install_missing()))
        self.enable_button.setText("Выключаю…" if self._stopping else "Включаю…" if self._hosts_writing or (busy and self._pending_cap == "all" and not self._requested_action) else "Подготовка…" if busy and self._requested_action else "Выключить всё" if stop else "Включить всё")
        set_control_accessibility(self.enable_button, name=self.enable_button.text(),
                                  description="Выключает функции Antigravity и спрашивает, убрать ли адреса нейросетей из hosts." if stop or self._stopping else "Включает вход, модели, автопатч и профили Gemini, Claude и ChatGPT в hosts. Может закрыть Antigravity.")
        set_tooltip(
            self.enable_button,
            "Выключить функции и выбрать, сохранить ли адреса в hosts" if stop else
            "Укажите папку установленного Antigravity" if self._install_missing() else "Включить вход, модели и автопатч",
        )
        self.enable_scope.setText("Все функции включены. При выключении выберите, оставить ли адреса нейросетей в hosts." if stop else
                                 "Вход · работа моделей · автопатч · Gemini, Claude и ChatGPT в hosts. Antigravity может закрыться для изменения клиента.")
        if not busy:
            if self._requested_action is None:
                self._pending_cap = ""
        self._sync_switches()
        self._style_all_button()
        if not busy and self._checking and self._ready:
            self.check_note.setText("Состояние прочитано. Проверка не включала функции и не меняла hosts; показан ранее сохранённый выбор.")

    def _sync_switches(self):
        for name, title, hint in CAPS:
            state = self._status.get("caps", {}).get(name, {})
            note = state.get("note") or hint
            row = self.cap_rows[name]
            row.set_texts(row._accessible_title, note)
            QTimer.singleShot(0, row._fit_text)
            row.show_state(state, ready=self._ready, busy=self.controller.busy or self._hosts_busy or self._stopping,
                           pending=self._pending_cap in {name, "all", "all_off"})

    def _toggle_cap(self, name, on=None):
        state = self._status.get("caps", {}).get(name, {})
        if self._ready and not self.controller.busy and not self._hosts_busy and state.get("kind") != "blocked":
            self._pending_cap = name
            self._send("set", cap=name, on=not bool(state.get("on")) if on is None else bool(on))
            self._sync_switches()

    def _received(self, event):
        kind = event.get("event")
        if kind == "status":
            self._ready = True
            self._status = event.get("status") or {}
            self._sync_switches()
            for install in self._status.get("installs", []):
                title = install.get("label")
                if title not in self.install_labels:
                    continue
                label, forget = self.install_labels[title]
                path = install.get("path")
                patched = install.get("patched")
                verdict = "изменение входа применено" if patched is True else "изменение входа не применено" if patched is False else "не проверено"
                label.setText(f"{path}\n{verdict.capitalize()}" if path else "Не найдено")
                forget.setVisible(bool(install.get("manual")))
            if not self.own_proxy.hasFocus():
                self.own_proxy.setText(self._status.get("own_proxy", ""))
            self._render_providers(self._status.get("providers", []))
            self._busy_changed(self.controller.busy, self.activity.text() if self.controller.busy else "")
            self._maybe_enable_all()
        elif kind == "headline":
            self._headline = event
            self._apply_page_theme()
            self.state_title.setText(event.get("title", ""))
            self.state_detail.setText(event.get("detail", ""))
            self.verify_button.setVisible(event.get("action") == "Verify")
            self.repair_button.setVisible(event.get("action") == "Repair")
            self.repair_button.setEnabled(self._ready and not (self.controller.busy or self._hosts_busy or self._stopping)
                                          and event.get("action") == "Repair")
            relay = event.get("relay") or {}
            route = relay.get("route") or "ещё не определён"
            vpn = {
                "None": "выключен", "Unmeasured": "трафик ещё не измерен",
                "NotCarryingClient": "Antigravity идёт мимо туннеля",
                "CarryingClient": "Antigravity идёт через туннель",
                "PartlyCarryingClient": "часть соединений идёт через туннель",
                "ViaLocalProxy": "Antigravity использует локальный прокси",
            }.get(self._status.get("vpn"), "не измерен")
            self.network_label.setText(f"Маршрут: {route}. VPN: {vpn}.")
        elif kind == "log":
            text = str(event.get("message", ""))
            self.journal.appendPlainText(text)
            if event.get("level") in {"Err", "Warn"}:
                from log.log import log

                log(f"Antigravity: {text}", "ERROR" if event.get("level") == "Err" else "WARNING")
                InfoBar.warning(title="Antigravity", content=text, parent=self)
        elif kind == "error":
            self._requested_action = None
            self._stopping = self._disable_waiting = False
            self._busy_changed(self.controller.busy, "")
            message = str(event.get("message", "Не удалось выполнить действие"))
            self.state_detail.setText(message)
            self.journal.appendPlainText(message)
            InfoBar.error(title="Antigravity", content=message, parent=self)
        elif kind == "completed" and self._disable_waiting:
            if self._disable_request_id is None or event.get("request_id") == self._disable_request_id:
                self._engine_disable_completed(event.get("shutdown_verified"))
        elif kind == "report":
            self._accept_report(str(event.get("text", "")))

    def _render_providers(self, providers):
        names = [str(p.get("name", "")) for p in providers]
        if names != self._provider_names:
            while self.providers_layout.count():
                item = self.providers_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._provider_names = names
            self.first_provider.clear()
            self.first_provider.addItems(names)
            for provider in providers:
                name = str(provider["name"])
                checkbox = CheckBox(name, self.providers_host)
                checkbox.setChecked(bool(provider.get("enabled")))
                checkbox.stateChanged.connect(lambda state, server=name: self._send("provider", name=server, on=bool(state)))
                self.providers_layout.addWidget(checkbox)
        else:
            for checkbox, provider in zip(self.providers_host.findChildren(CheckBox), providers):
                checkbox.blockSignals(True)
                checkbox.setChecked(bool(provider.get("enabled")))
                checkbox.blockSignals(False)

    def _put_provider_first(self):
        name = self.first_provider.currentText()
        if name:
            self._send("provider_order", order=[name] + [n for n in self._provider_names if n != name])

    def _choose_install(self):
        path = QFileDialog.getExistingDirectory(self, "Папка Antigravity, IDE или CLI")
        if path:
            self._send("add_path", path=path)

    def _forget_install(self, kind):
        for install in self._status.get("installs", []):
            if install.get("label") == kind and install.get("path"):
                self._send("forget_path", path=install["path"])

    def _verify(self):
        from app.external_actions import open_url

        url = str(self._headline.get("verify_url") or "")
        if url:
            result = open_url(url)
            if not result.ok:
                self._action_failed(result.error)

    def _copy_route_request(self):
        code = str(self._status.get("pc_code") or "")
        if code:
            QApplication.clipboard().setText("/ag+" + code)
            InfoBar.success(title="Antigravity", content="Запрос скопирован. Передайте его поставщику дополнительного маршрута.", parent=self)

    def _save_report(self):
        if self._report_pending:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить отчёт Antigravity", "net67-antigravity.txt", "Текст (*.txt)")
        if path:
            self._report_path = path
            self._report_clipboard = False
            self._request_report()

    def _copy_report(self):
        if self._report_pending:
            return
        self._report_path = ""
        self._report_clipboard = True
        self._request_report()

    def _request_report(self):
        self._report_pending = True
        if not self.controller.send("report"):
            self._report_pending = False
            self._report_path = ""
            self._report_clipboard = False
        self._busy_changed(self.controller.busy, self.activity.text())

    def _accept_report(self, text):
        try:
            if self._report_clipboard:
                QApplication.clipboard().setText(text)
            elif self._report_path:
                from pathlib import Path

                Path(self._report_path).write_text(text, encoding="utf-8")
            else:
                return
            InfoBar.success(title="Antigravity", content="Отчёт скопирован." if self._report_clipboard else "Отчёт сохранён.", parent=self)
        except OSError as exc:
            self._action_failed(f"Не удалось сохранить отчёт: {exc}")
        finally:
            self._report_path = ""
            self._report_clipboard = False
            self._report_pending = False
            self._busy_changed(self.controller.busy, self.activity.text())

    def _action_failed(self, message):
        self.journal.appendPlainText(str(message))
        InfoBar.error(title="Antigravity", content=str(message), parent=self)

    def _failed(self, message):
        self._requested_action = None
        self._checking = False
        self._stopping = self._disable_waiting = False
        self._ready = False
        self._headline = {"tone": "Action"}
        self._apply_page_theme()
        self._report_pending = False
        self._report_path = ""
        self._report_clipboard = False
        self.state_title.setText("Требуется действие")
        self.state_detail.setText(str(message))
        self._busy_changed(False, "")
        InfoBar.error(title="Antigravity", content=str(message), parent=self)

    def cleanup(self):
        self._requested_action = None
        self._hosts_runtime.stop(blocking=False, warning_prefix="Antigravity hosts")
        self._hosts_runtime.cancel()
        self.controller.stop()
        super().cleanup()
