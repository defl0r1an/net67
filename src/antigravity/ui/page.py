"""Все переключатели управляют одной очередью движка, как и «Включить всё»."""

from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, CaptionLabel, CheckBox, ComboBox, FluentIcon, InfoBar, LineEdit,
    PasswordLineEdit, PrimaryPushButton, PushButton, SegmentedWidget, StrongBodyLabel, TransparentPushButton,
)

from antigravity.controller import AntigravityController
from ui.accessibility import set_control_accessibility
from hosts.ui.services_tiles import HostsTile, HostsTilesGrid
from ui.fluent_widgets import SettingsCard
from ui.pages.base_page import BasePage, ScrollBlockingPlainTextEdit
from ui.theme import get_cached_qta_pixmap, get_theme_tokens
from ui.theme_semantic import get_semantic_palette
from ui.widgets.stagger_float_in import attach_stagger_float_in


class _SectionPanel(QWidget):
    """Сетка рисует свой вход; обычные блоки используют общую волну net67."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._motion = attach_stagger_float_in(self)

    def play_float_in(self, delay_ms=0):
        # Эффект на всей длинной странице заставлял бы перерисовывать сетку.
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
    def __init__(self, parent=None, *, open_hosts=None, controller=None):
        super().__init__("Antigravity", "Вход в аккаунт и работа моделей в Antigravity, IDE и CLI", parent)
        self._open_hosts = open_hosts
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
        button.clicked.connect(lambda _checked=False: callback())
        set_control_accessibility(button, name=title)
        self._controls.append(button)
        return button

    def _build_ui(self):
        # Заголовок, сводка и сетка используют те же компоненты, что hosts.
        header_host = QWidget(self.content)
        header = QHBoxLayout(header_host)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self.layout.removeWidget(self.title_label)
        self.title_label.setParent(header_host)
        header.addWidget(self.title_label, 1)
        self.refresh_button = self._button("Проверить", self._refresh)
        self.refresh_button.setIcon(FluentIcon.SYNC)
        if callable(self._open_hosts):
            self.hosts_button = self._button("В hosts", self._open_hosts)
            self.hosts_button.setIcon(FluentIcon.DOCUMENT)
            self.hosts_button.setToolTip("Показать «Gemini AI и Antigravity» в редакторе hosts")
            set_control_accessibility(self.hosts_button, name="Показать Antigravity в hosts")
            # Переход доступен и пока движок проверяет систему.
            self._controls.remove(self.hosts_button)
            header.addWidget(self.hosts_button)
        self.layout.insertWidget(0, header_host)
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
        self.state_detail = CaptionLabel("«Включить всё» проверит состояние и включит функции. «Проверить» только прочитает состояние.", self.state_card)
        self.state_detail.setWordWrap(True)
        state_text.addWidget(self.state_title)
        state_text.addWidget(self.state_detail)
        state_row.addLayout(state_text, 1)
        state_layout.addLayout(state_row)
        buttons = QHBoxLayout()
        self.enable_button = self._button("Включить всё", self._enable_all, primary=True)
        self.enable_button.setIcon(FluentIcon.POWER_BUTTON)
        self.repair_button = self._button("Восстановить службу", lambda: self._send("repair"))
        self.repair_button.setIcon(FluentIcon.SYNC)
        self.repair_button.hide()
        for button in (self.enable_button, self.refresh_button, self.repair_button):
            buttons.addWidget(button)
        buttons.addStretch()
        state_layout.addLayout(buttons)
        self.enable_scope = CaptionLabel("Вход в аккаунт · работа моделей · автопатч. При изменении клиента Antigravity может закрыться.", self.state_card)
        self.enable_scope.setWordWrap(True)
        state_layout.addWidget(self.enable_scope)
        self.activity = BodyLabel("", self.state_card)
        self.activity.setWordWrap(True)
        self.activity.hide()
        state_layout.addWidget(self.activity)
        self.verify_button = self._button("Пройти верификацию Google", self._verify)
        self.verify_button.hide()
        state_layout.addWidget(self.verify_button)
        self.add_widget(self.state_card)

        section_row = QWidget(self.content)
        section_layout = QHBoxLayout(section_row)
        section_layout.setContentsMargins(0, 0, 0, 0)
        self.sections = SegmentedWidget(section_row)
        set_control_accessibility(self.sections, name="Раздел Antigravity")
        section_layout.addWidget(self.sections, 0, Qt.AlignmentFlag.AlignLeft)
        section_layout.addStretch(1)
        self.add_widget(section_row)
        self.main_card = _SectionPanel(self.content)
        main_layout = QVBoxLayout(self.main_card)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(16)
        self.main_tiles = HostsTilesGrid(self.main_card)
        set_control_accessibility(self.main_tiles, name="Основные настройки Antigravity")
        self.main_tiles.activated.connect(self._toggle_cap)
        main_layout.addWidget(self.main_tiles)

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
            forget.setToolTip("Убрать указанный вручную путь")
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
        self.advanced_tiles = HostsTilesGrid(self.advanced_card)
        set_control_accessibility(self.advanced_tiles, name="Сетевые настройки Antigravity")
        self.advanced_tiles.activated.connect(self._toggle_cap)
        advanced_layout.addWidget(self.advanced_tiles)
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
        self.route_request_button = self._button("Скопировать запрос для дополнительного маршрута", self._copy_route_request)
        routes_layout.addWidget(self.route_request_button)
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

    def on_page_activated(self):
        # Переходы из hosts и экскурсии не выражают намерения запускать движок.
        pass

    def onboarding_target(self, name):
        return {
            "controls": [self.enable_button, self.refresh_button, self.main_tiles],
            "hosts": getattr(self, "hosts_button", None),
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
        if not self._ready:
            self.controller.start()
        else:
            if not self.controller.send("refresh"):
                self.controller.start()

    def _all_enabled(self):
        caps = self._status.get("caps", {})
        return self._ready and all(caps.get(name, {}).get("on") and caps.get(name, {}).get("kind") != "partial"
                                   for name in ("client_patch", "watchdog", "dns", "local_proxy", "builtin_exits", "group_proxy"))

    def _install_missing(self):
        return "installs" in self._status and not any(install.get("path") for install in self._status["installs"])

    def _enable_all(self):
        if self.controller.busy:
            return
        if not self._ready:
            self._requested_action = "enable_all"
            self._pending_cap = "all"
            if not self.controller.start():
                self._requested_action = None
                self._pending_cap = ""
                self._busy_changed(False, "")
        elif not self._all_enabled() and not self._install_missing():
            self._pending_cap = "all"
            self._send("enable_all")

    def _send(self, command, **values):
        if not self.controller.send(command, **values):
            self._pending_cap = ""
            self._busy_changed(self.controller.busy, "")
            return False
        return True

    def _busy_changed(self, busy, message):
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
        self.enable_button.setEnabled(not busy and not self._all_enabled() and not self._install_missing())
        self.enable_button.setText("Подготовка…" if busy and self._requested_action else "Включаю…" if busy and self._pending_cap == "all" else "Включить всё")
        set_control_accessibility(self.enable_button, name=self.enable_button.text(),
                                  description="Включает вход в аккаунт, работу моделей и автопатч. Может закрыть Antigravity для изменения клиента.")
        self.enable_button.setToolTip("Укажите папку установленного Antigravity" if self._install_missing() else
                                     "Все функции уже включены" if self._all_enabled() else "Включить вход, модели и автопатч")
        self.enable_scope.setText("Все функции включены. Проверьте ответ выбранной модели." if self._all_enabled() else
                                 "Вход в аккаунт · работа моделей · автопатч. При изменении клиента Antigravity может закрыться.")
        if not busy:
            if self._requested_action is None:
                self._pending_cap = ""
        self._sync_switches()

    def _sync_switches(self):
        short_titles = {"client_patch": "Вход в аккаунт", "bypass": "Работа моделей", "watchdog": "Автопатч"}
        icons = {"client_patch": "own:antigravity:AG", "bypass": "fa5s.globe", "watchdog": "fa5s.sync-alt",
                 "local_proxy": "fa5s.plug", "dns": "fa5s.server", "builtin_exits": "fa5s.random",
                 "own_proxy": "fa5s.route", "group_proxy": "fa5s.network-wired", "dns_rotation": "fa5s.exchange-alt",
                 "verify_tls": "fa5s.shield-alt"}
        tiles = []
        for name, title, hint in CAPS:
            state = self._status.get("caps", {}).get(name, {})
            note = state.get("note") or hint
            tiles.append(HostsTile(kind="tile", key=name, title=short_titles.get(name, title), note=note,
                                   icon_name=icons[name], is_on=bool(state.get("on")), has_switch=True,
                                   enabled=self._ready and not self.controller.busy and state.get("kind") != "blocked",
                                   pending=self._pending_cap == name or (self._pending_cap == "all" and name in {"client_patch", "bypass", "watchdog"}),
                                   accessible_text=f"{title}. {note}"))
        self.main_tiles.set_tiles([HostsTile(kind="group", title="Разблокировка"), *tiles[:3]])
        self.advanced_tiles.set_tiles([HostsTile(kind="group", title="Сетевой обход"), *tiles[3:8],
                                      HostsTile(kind="group", title="DNS и безопасность"), *tiles[8:]])

    def _toggle_cap(self, name):
        state = self._status.get("caps", {}).get(name, {})
        if self._ready and not self.controller.busy and state.get("kind") != "blocked":
            self._pending_cap = name
            self._send("set", cap=name, on=not bool(state.get("on")))
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
            if self._requested_action is not None and not self.controller.busy:
                action, self._requested_action = self._requested_action, None
                if self._install_missing() or self._all_enabled():
                    self._busy_changed(False, "")
                else:
                    self._send(action)
        elif kind == "headline":
            self._headline = event
            self._apply_page_theme()
            self.state_title.setText(event.get("title", ""))
            self.state_detail.setText(event.get("detail", ""))
            self.verify_button.setVisible(event.get("action") == "Verify")
            self.repair_button.setVisible(event.get("action") == "Repair")
            self.repair_button.setEnabled(self._ready and not self.controller.busy and event.get("action") == "Repair")
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
            self._busy_changed(self.controller.busy, "")
            message = str(event.get("message", "Не удалось выполнить действие"))
            self.state_detail.setText(message)
            self.journal.appendPlainText(message)
            InfoBar.error(title="Antigravity", content=message, parent=self)
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
        self.controller.stop()
        super().cleanup()
