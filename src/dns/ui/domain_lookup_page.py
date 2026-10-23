"""Вкладка «Проверка домена»: пинг, ответы разных DNS и соседи по адресу.

Живёт вкладкой страницы BlockCheck. Сама в сеть не ходит: просит фасад DNS
запустить фоновую проверку и показывает результаты по мере готовности.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QHBoxLayout, QHeaderView, QSizePolicy, QTableWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel,
    CheckBox,
    FluentIcon,
    IndeterminateProgressBar,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    TableWidget,
)

import dns.domain_lookup_plans as plans
from app.ui_texts import tr as tr_catalog
from blockcheck.ui.check_results import _HeightKeeper
from blockcheck.ui.quick_service_cards import QuickServiceCards
from log.log import log
from ui.accessibility import set_control_accessibility, set_state_text
from ui.fluent_widgets import SettingsCard, set_tooltip
from ui.latest_worker_lane import LatestWorkerLane
from ui.log_report_dialog import show_log_report_dialog
from ui.pages.base_page import BasePage, ScrollBlockingPlainTextEdit
from ui.theme import get_theme_tokens
from ui.theme_refresh import ThemeRefreshBinding
from ui.theme_semantic import get_semantic_palette
from ui.widgets.fluent_item_tooltip import install_fluent_item_tooltips


_HOSTS_WRITERS: set = set()


def _tone_color(tone: str) -> str:
    tokens = get_theme_tokens()
    semantic = get_semantic_palette()
    return {
        plans.TONE_MUTED: tokens.fg_muted,
        plans.TONE_ACCENT: tokens.accent_hex,
        plans.TONE_SUCCESS: semantic.success,
        plans.TONE_WARNING: semantic.warning,
        plans.TONE_ERROR: semantic.error,
    }.get(tone, tokens.fg_muted)


class _InfoLines(_HeightKeeper, QWidget):
    """Несколько строк текста с переносом; высоту держит сам (см. _HeightKeeper)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._labels: list[CaptionLabel] = []
        self._lines: tuple[plans.InfoLine, ...] = ()
        self._theme_refresh = ThemeRefreshBinding(self, self._apply_theme_refresh)

    def set_lines(self, lines) -> None:
        self._lines = tuple(lines)
        while len(self._labels) < len(self._lines):
            label = CaptionLabel("", self)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._layout.addWidget(label)
            self._labels.append(label)
        for index, label in enumerate(self._labels):
            visible = index < len(self._lines)
            label.setVisible(visible)
            if visible:
                label.setText(self._lines[index].text)
        self._apply_theme_refresh()
        set_state_text(self, " ".join(line.text for line in self._lines))
        self._schedule_min_height_sync()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_min_height()

    def _apply_theme_refresh(self, tokens=None, force: bool = False) -> None:
        _ = tokens, force
        for label, line in zip(self._labels, self._lines):
            label.setStyleSheet(f"color: {_tone_color(line.tone)};")


class DnsAnswersTable(TableWidget):
    """Одна строка на DNS-сервер: кто он, что ответил и за сколько."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setColumnCount(4)
        self.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self.verticalHeader().setVisible(False)
        self.setWordWrap(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        install_fluent_item_tooltips(self)
        self._levels: list[str] = []
        self._theme_refresh = ThemeRefreshBinding(self, self._apply_theme_refresh)

    def set_headers(self, headers: tuple[str, str, str, str]) -> None:
        self.setHorizontalHeaderLabels(list(headers))

    def show_rows(self, rows) -> None:
        rows = tuple(rows)
        self.setRowCount(len(rows))
        self._levels = [row.level for row in rows]
        for index, row in enumerate(rows):
            for column, text in enumerate((row.server, row.address, row.result, row.time)):
                item = self.item(index, column)
                if item is None:
                    item = QTableWidgetItem()
                    self.setItem(index, column, item)
                item.setText(text)
                item.setData(Qt.ItemDataRole.ToolTipRole, row.tooltip)
        self._apply_theme_refresh()
        self._fit_height()
        problems = sum(1 for level in self._levels if level in ("warn", "fail"))
        set_state_text(self, f"Ответы DNS-серверов: {len(rows)} строк, с пометками {problems}")

    def _fit_height(self) -> None:
        height = self.horizontalHeader().height() + 2 * self.frameWidth() + 4
        for row in range(self.rowCount()):
            height += self.rowHeight(row)
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)

    def _apply_theme_refresh(self, tokens=None, force: bool = False) -> None:
        _ = tokens, force
        for row, level in enumerate(self._levels):
            item = self.item(row, 2)
            if item is None:
                continue
            if level in ("warn", "fail"):
                item.setForeground(QColor(_tone_color(plans.level_tone(level))))
            else:
                item.setData(Qt.ItemDataRole.ForegroundRole, None)


class DomainLookupPage(BasePage):
    """Пинг, адреса с разных DNS и «кто ещё на этом адресе» для одного домена или IP."""

    def __init__(self, parent=None, *, dns_feature, embedded: bool = False, open_hosts_service=None):
        super().__init__(
            "Проверка домена",
            "Пинг, адреса с разных DNS-серверов и домены на том же адресе",
            parent,
            title_key="page.domain_lookup.title",
            subtitle_key="page.domain_lookup.subtitle",
        )
        self._open_hosts_service = open_hosts_service
        self._dns = dns_feature
        self._closed = False
        self._report = None
        self._running = False
        self._lane = LatestWorkerLane(
            name="domain_lookup",
            create_worker=self._create_worker,
            on_result=lambda _payload, report: self._on_finished(report),
            on_error=lambda _payload, error: self._on_failed(error),
            log_fn=log,
        )
        self._build_ui()
        self._hosts_lane = LatestWorkerLane(
            name="domain_hosts",
            create_worker=self._create_hosts_worker,
            on_result=self._on_hosts_written,
            on_error=self._on_hosts_error,
            result_signal="loaded",
            log_fn=log,
        )
        if embedded:
            self.hide_page_header()
        self._apply_texts()
        self._set_running(False)

    # ── тексты ──────────────────────────────────────────────

    def _t(self, key: str, default: str) -> str:
        return tr_catalog(f"page.domain_lookup.{key}", language=self._ui_language, default=default)

    # ── сборка ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.control_card = SettingsCard()
        row = QHBoxLayout()
        row.setSpacing(10)
        self.target_input = LineEdit(self.control_card)
        self.target_input.setClearButtonEnabled(True)
        self.target_input.returnPressed.connect(self.start_lookup)
        row.addWidget(self.target_input, 1)
        self.start_button = PrimaryPushButton(FluentIcon.PLAY, "", self.control_card)
        self.start_button.clicked.connect(self.start_lookup)
        row.addWidget(self.start_button)
        self.stop_button = PushButton(FluentIcon.CANCEL, "", self.control_card)
        self.stop_button.clicked.connect(self.stop_lookup)
        row.addWidget(self.stop_button)
        self.report_button = PushButton(FluentIcon.DOCUMENT, "", self.control_card)
        self.report_button.clicked.connect(self._open_report)
        row.addWidget(self.report_button)
        self.control_card.add_layout(row)

        # Известные сервисы одним нажатием: адрес подставляется и проверка запускается сразу.
        self.quick_cards = QuickServiceCards(self.control_card, for_site_check=True)
        self.quick_cards.picked.connect(self._on_quick_service)
        self.target_input.textChanged.connect(self.quick_cards.set_target)
        self.control_card.add_widget(self.quick_cards)

        self.external_check = CheckBox("", self.control_card)
        self.external_check.setChecked(True)
        self.control_card.add_widget(self.external_check)

        self.status_lines = _InfoLines(self.control_card)
        self.control_card.add_widget(self.status_lines)
        self.progress_bar = IndeterminateProgressBar(self.control_card)
        self.progress_bar.setVisible(False)
        self.control_card.add_widget(self.progress_bar)
        self.layout.addWidget(self.control_card)

        self.ping_card = SettingsCard()
        self.ping_title = StrongBodyLabel("", self.ping_card)
        self.ping_card.add_widget(self.ping_title)
        self.ping_lines = _InfoLines(self.ping_card)
        self.ping_card.add_widget(self.ping_lines)
        self.network_lines = _InfoLines(self.ping_card)
        self.ping_card.add_widget(self.network_lines)
        self.layout.addWidget(self.ping_card)

        self.neighbors_card = SettingsCard()
        self.neighbors_title = StrongBodyLabel("", self.neighbors_card)
        self.neighbors_card.add_widget(self.neighbors_title)
        self.neighbors_text = ScrollBlockingPlainTextEdit(self.neighbors_card)
        self.neighbors_text.setReadOnly(True)
        self.neighbors_text.setFont(QFont("Consolas", 9))
        self.neighbors_card.add_widget(self.neighbors_text)
        self.layout.addWidget(self.neighbors_card)

        self.dns_card = SettingsCard()
        dns_header = QHBoxLayout()
        self.dns_title = StrongBodyLabel("", self.dns_card)
        dns_header.addWidget(self.dns_title)
        dns_header.addStretch()
        self.add_to_hosts_btn = PushButton(self.dns_card)
        self.add_to_hosts_btn.setVisible(False)
        self.add_to_hosts_btn.clicked.connect(self._on_add_to_hosts)
        dns_header.addWidget(self.add_to_hosts_btn)
        self.dns_card.add_layout(dns_header)
        self.dns_summary = _InfoLines(self.dns_card)
        self.dns_card.add_widget(self.dns_summary)
        self.dns_table = DnsAnswersTable(self.dns_card)
        self.dns_card.add_widget(self.dns_table)
        self.layout.addWidget(self.dns_card)


        for card in (self.ping_card, self.dns_card, self.neighbors_card):
            card.setVisible(False)
        from blockcheck.ui.result_cards import CardsGrid, card_plain_text

        self.detail_cards = CardsGrid(330, self.content)
        self.detail_cards.opened.connect(lambda card: show_log_report_dialog(self.window(), title=card.title, text=card_plain_text(card)))
        self.detail_cards.hide()
        self.layout.insertWidget(self.layout.indexOf(self.control_card) + 1, self.detail_cards)
        self.control_card.main_layout.addWidget(self.add_to_hosts_btn, 0, Qt.AlignmentFlag.AlignLeft)
        from dns.ui.check_history import CheckHistory

        self.check_history = CheckHistory(dns_feature=self._dns, kind="domain", parent=self.content)
        self.layout.addWidget(self.check_history)
        self.layout.addStretch()

    def _apply_texts(self) -> None:
        self.target_input.setPlaceholderText(self._t("placeholder", "Домен или IP-адрес: example.com, 1.2.3.4"))
        set_control_accessibility(
            self.target_input,
            name=self._t("input.name", "Домен или IP-адрес для проверки"),
            description=self._t("input.description", "Введите домен, адрес или ссылку и нажмите «Проверить»."),
        )
        self.start_button.setText(self._t("button.start", "Проверить"))
        start_description = self._t(
            "button.start.description",
            "Пропинговать адрес, спросить его у разных DNS-серверов и найти домены на том же адресе.",
        )
        set_tooltip(self.start_button, start_description)
        set_control_accessibility(self.start_button, name=self._t("button.start.name", "Проверить домен"), description=start_description)
        self.stop_button.setText(self._t("button.stop", "Остановить"))
        set_control_accessibility(
            self.stop_button,
            name=self._t("button.stop.name", "Остановить проверку домена"),
            description=self._t("button.stop.description", "Прервать проверку; останется то, что уже успели узнать."),
        )
        self.report_button.setText(self._t("button.report", "Отчёт"))
        report_description = self._t("button.report.description", "Открыть полный текст проверки — его можно скопировать.")
        set_tooltip(self.report_button, report_description)
        set_control_accessibility(self.report_button, name=self._t("button.report.name", "Открыть отчёт проверки домена"), description=report_description)
        self.external_check.setText(
            self._t("external", "Искать соседей по адресу через внешние сервисы (адрес будет отправлен на их сайты)")
        )
        set_tooltip(
            self.external_check,
            self._t(
                "external.description",
                "Разрешает отправить IP внешним сервисам поиска. Без галочки остаются DNS, "
                "пинг, подключение к адресу и чтение сертификата.",
            ),
        )
        self.ping_title.setText(self._t("section.ping", "Пинг и сеть"))
        self.dns_title.setText(self._t("section.dns", "Адреса с разных DNS-серверов"))
        self.add_to_hosts_btn.setText(self._t("button.add_to_hosts", "Добавить в Hosts"))
        set_tooltip(
            self.add_to_hosts_btn,
            self._t("button.add_to_hosts.description", "Сохранить показанные домен и IP в hosts."),
        )
        self.neighbors_title.setText(self._t("section.neighbors", "Кто ещё на этом адресе"))

        self.dns_table.set_headers(
            (
                self._t("column.server", "DNS-сервер"),
                self._t("column.address", "Адрес сервера"),
                self._t("column.answer", "Ответ"),
                self._t("column.time", "Время"),
            )
        )
        set_control_accessibility(
            self.dns_table,
            name=self._t("table.name", "Ответы DNS-серверов"),
            description=self._t("table.description", "Для каждого сервера: какие адреса он назвал и за сколько."),
        )
        set_control_accessibility(
            self.neighbors_text,
            name=self._t("neighbors.name", "Домены на том же адресе"),
            description=self._t("neighbors.description", "Списки доменов по источникам."),
        )
        if self._report is None:
            self.status_lines.set_lines(
                (plans.InfoLine(self._t("status.ready", "Введите домен или IP-адрес и нажмите «Проверить».")),)
            )
        else:
            self._show_report(self._report)

    # ── запуск и остановка ──────────────────────────────────

    def _create_worker(self, request_id: int, payload):
        worker = self._dns.create_domain_lookup_worker(
            request_id,
            target=payload["target"],
            use_external=payload["use_external"],
            parent=self,
        )
        worker.stage.connect(self._on_stage)
        return worker

    def _set_running(self, running: bool) -> None:
        self._running = bool(running)
        self.start_button.setEnabled(not running)
        self.stop_button.setVisible(running)
        self.target_input.setEnabled(not running)
        self.quick_cards.setEnabled(not running)
        self.external_check.setEnabled(not running)
        self.report_button.setEnabled(self._report is not None and not running)
        self.progress_bar.setVisible(running)
        if running:
            self.progress_bar.start()
        else:
            self.progress_bar.stop()
        set_state_text(self.progress_bar, "Проверка домена: выполняется" if running else "Проверка домена: не выполняется")

    def _on_quick_service(self, address: str) -> None:
        """Карточка сервиса: подставить адрес и сразу проверить."""
        if self._closed or self._running:
            return
        self.set_target(address)
        self.start_lookup()

    def set_target(self, target: str) -> None:
        self.target_input.setText(str(target or ""))

    def start_lookup(self) -> None:
        if self._closed or self._running:
            return
        target = self.target_input.text().strip()
        if not target:
            self.status_lines.set_lines(
                (plans.InfoLine(self._t("status.empty", "Введите домен или IP-адрес."), plans.TONE_WARNING),)
            )
            self.target_input.setFocus()
            return
        # Старые результаты не копим: каждая проверка начинается с чистого экрана.
        self._report = None
        for card in (self.ping_card, self.dns_card, self.neighbors_card):
            card.setVisible(False)
        self.dns_table.setRowCount(0)
        self.neighbors_text.clear()
        self.status_lines.set_lines((plans.InfoLine(f"Проверяем {target}…", plans.TONE_ACCENT),))
        self._set_running(True)
        self._lane.request({"target": target, "use_external": self.external_check.isChecked()})

    def stop_lookup(self) -> None:
        worker = self._lane.runtime.worker
        stop = getattr(worker, "stop", None)
        if callable(stop):
            try:
                stop()
            except RuntimeError:
                pass
        self.stop_button.setEnabled(False)

    # ── результаты ──────────────────────────────────────────

    def _on_stage(self, request_id: int, report) -> None:
        if not self._lane.runtime.is_current(request_id, cleanup_in_progress=self._closed):
            return
        self._show_report(report)

    def _on_finished(self, report) -> None:
        if self._closed:
            return
        self._show_report(report)
        self.check_history.append(getattr(report, "history_entry", None))
        self.stop_button.setEnabled(True)
        self._set_running(False)

    def _on_failed(self, error: str) -> None:
        if self._closed:
            return
        self.status_lines.set_lines(
            (plans.InfoLine(f"{self._t('status.failed', 'Проверка не удалась')}: {error}", plans.TONE_ERROR),)
        )
        self.stop_button.setEnabled(True)
        self._set_running(False)

    def _show_report(self, report) -> None:
        from dns.ui.domain_lookup_cards import build_lookup_cards

        self._report = report
        self.report_button.setEnabled(True)
        self.detail_cards.show_cards(build_lookup_cards(report), animate=False)
        self.detail_cards.setVisible(True)
        self.status_lines.set_lines((plans.build_status(report),))
        # Все измерения уже находятся в карточках и подробном отчёте:
        # прежние таблицы не дублируют их на той же странице.
        for old in (self.ping_card, self.dns_card, self.neighbors_card):
            old.hide()
        can_add = bool(report.primary_ip and report.kind == "domain")
        self.add_to_hosts_btn.setVisible(can_add)
        self.add_to_hosts_btn.setEnabled(can_add and not self._hosts_lane.is_busy())
        self.add_to_hosts_btn.setText("Настроить в hosts" if getattr(report, "hosts_service", "") and self._open_hosts_service is not None else self._t("button.add_to_hosts", "Добавить в Hosts"))

    def _on_add_to_hosts(self) -> None:
        service = getattr(self._report, "hosts_service", "")
        if service and self._open_hosts_service is not None:
            self._open_hosts_service(service)
            return
        if self._closed or self._hosts_lane.is_busy() or not self._report or not self._report.primary_ip:
            return
        domain = str(self._report.target or "").strip()
        ip = str(self._report.primary_ip or "").strip()
        if not domain or not ip:
            return
        self.add_to_hosts_btn.setEnabled(False)
        self._hosts_lane.request((domain, ip))

    def _create_hosts_worker(self, request_id: int, payload):
        from app.feature_facades.hosts import create_domain_hosts_worker

        worker = create_domain_hosts_worker(request_id, *payload)
        # Запись нельзя прерывать удалением страницы: она держит общий замок hosts.
        _HOSTS_WRITERS.add(worker)
        worker.finished.connect(lambda w=worker: _HOSTS_WRITERS.discard(w))
        return worker

    def _on_hosts_written(self, payload, result) -> None:
        from ui.fluent_widgets import InfoBarHelper

        domain, ip = payload
        if result.success:
            if self._report and (self._report.target, self._report.primary_ip) == payload:
                self.add_to_hosts_btn.setText(self._t("button.added_to_hosts", "Добавлено в hosts"))
                self.add_to_hosts_btn.setEnabled(False)
            else:
                self.add_to_hosts_btn.setEnabled(bool(self._report and self._report.primary_ip))
            InfoBarHelper.success(self, self._t("infobar.hosts_added.title", "Запись добавлена"), f"{domain} → {ip}")
        else:
            self._on_hosts_error(payload, result.message or "Не удалось записать в hosts")

    def _on_hosts_error(self, payload, error: str) -> None:
        from ui.fluent_widgets import InfoBarHelper

        self.add_to_hosts_btn.setEnabled(True)
        InfoBarHelper.error(self, self._t("infobar.hosts_error.title", "Ошибка hosts"), error)

    def _open_report(self) -> None:

        if self._report is None:
            return
        show_log_report_dialog(
            self.window(),
            title=self._t("report.title", "Отчёт проверки домена"),
            text=plans.build_text_report(self._report),
            empty_text=self._t("report.empty", "Проверка ещё не запускалась."),
            description=self._t("report.description", "Полный текст проверки: пинг, ответы DNS-серверов и домены на адресе."),
        )

    # ── жизненный цикл ──────────────────────────────────────

    def set_ui_language(self, language: str) -> None:
        super().set_ui_language(language)
        try:
            self._apply_texts()
        except Exception:
            pass

    def cleanup(self) -> None:
        self.check_history.cleanup()
        self._closed = True
        self._hosts_lane.close()
        self._lane.close()
        super().cleanup()


    def set_history(self, runs) -> None:
        self.check_history.set_history(runs)

__all__ = ["DnsAnswersTable", "DomainLookupPage"]
