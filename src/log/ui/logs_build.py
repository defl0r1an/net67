"""Build-helper основной вкладки логов."""

from __future__ import annotations

from dataclasses import dataclass
from PyQt6.QtWidgets import QSizePolicy
from qfluentwidgets import FluentIcon
from ui.accessibility import set_control_accessibility, set_state_text
from ui.log_limits import (
    ERROR_LOG_VIEW_MAX_LINES,
    MAIN_LOG_VIEW_MAX_LINES,
    apply_text_line_limit,
)

@dataclass(slots=True)
class LogsPrimaryTabWidgets:
    log_card: object
    log_text: object
    stats_label: object


@dataclass(slots=True)
class LogsManagementTabWidgets:
    controls_card: object
    logs_table: object
    refresh_btn: object
    info_label: object
    controls_actions_title: object
    controls_actions_bar: object
    copy_btn: object
    clear_btn: object
    folder_btn: object


@dataclass(slots=True)
class LogsSecondaryPanelsWidgets:
    errors_card: object
    warning_icon_label: object
    errors_title_label: object
    errors_count_label: object
    clear_errors_btn: object
    errors_text: object


def build_logs_primary_tab_ui(
    *,
    parent_layout,
    content_parent,
    ui_language: str,
    tr_catalog_fn,
    settings_card_cls,
    qvbox_layout_cls,
    qhbox_layout_cls,
    caption_label_cls,
    strong_body_label_cls,
    text_edit_cls,
    qfont_cls,
    get_theme_tokens_fn,
) -> LogsPrimaryTabWidgets:
    _ = get_theme_tokens_fn()

    log_card = settings_card_cls()
    log_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    log_layout = qvbox_layout_cls()
    log_layout.setContentsMargins(0, 0, 0, 0)
    log_layout.setSpacing(8)

    log_text = text_edit_cls()
    log_text.setReadOnly(True)
    log_text.setLineWrapMode(text_edit_cls.LineWrapMode.NoWrap)
    log_text.setFont(qfont_cls("Consolas", 9))
    log_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    log_text.setMinimumHeight(380)
    apply_text_line_limit(log_text, MAIN_LOG_VIEW_MAX_LINES)
    set_control_accessibility(
        log_text,
        name=tr_catalog_fn("page.logs.accessibility.log_text.name", language=ui_language, default="Содержимое текущего лога"),
        description=tr_catalog_fn(
            "page.logs.accessibility.log_text.description",
            language=ui_language,
            default="Текст выбранного файла лога. Поле только для чтения.",
        ),
    )
    set_state_text(
        log_text,
        tr_catalog_fn(
            "page.logs.accessibility.log_text.initial_state",
            language=ui_language,
            default="Содержимое текущего лога: лог пока не загружен",
        ),
    )
    log_layout.addWidget(log_text, 1)

    stats_label = caption_label_cls()
    set_control_accessibility(
        stats_label,
        name=tr_catalog_fn("page.logs.accessibility.stats.name", language=ui_language, default="Статистика логов"),
        description=tr_catalog_fn(
            "page.logs.accessibility.stats.description",
            language=ui_language,
            default="Краткая статистика по файлам логов.",
        ),
    )
    set_state_text(
        stats_label,
        tr_catalog_fn(
            "page.logs.accessibility.stats.initial_state",
            language=ui_language,
            default="Статистика логов: пока нет данных",
        ),
    )
    log_layout.addWidget(stats_label)

    log_card.add_layout(log_layout)
    parent_layout.addWidget(log_card, 1)

    return LogsPrimaryTabWidgets(
        log_card=log_card,
        log_text=log_text,
        stats_label=stats_label,
    )


def build_logs_management_tab_ui(
    *,
    parent_layout,
    content_parent,
    ui_language: str,
    tr_catalog_fn,
    settings_card_cls,
    qvbox_layout_cls,
    qhbox_layout_cls,
    caption_label_cls,
    tool_button_cls,
    push_button_cls,
    table_widget_cls,
    table_item_cls,
    header_view_cls,
    quick_actions_bar_cls,
    get_theme_tokens_fn,
    on_log_selected,
    on_refresh,
    on_spin_tick,
    on_copy,
    on_clear_view,
    on_open_folder,
    refresh_timer_parent,
) -> LogsManagementTabWidgets:
    _ = (get_theme_tokens_fn(), table_item_cls)

    controls_card = settings_card_cls()
    controls_main = qvbox_layout_cls()
    controls_main.setSpacing(12)

    top_row = qhbox_layout_cls()
    top_row.setSpacing(8)
    info_label = caption_label_cls()
    set_control_accessibility(
        info_label,
        name=tr_catalog_fn("page.logs.accessibility.info.name", language=ui_language, default="Сообщение страницы логов"),
        description=tr_catalog_fn(
            "page.logs.accessibility.info.description",
            language=ui_language,
            default="Здесь показывается результат последнего действия с логами.",
        ),
    )
    set_state_text(
        info_label,
        tr_catalog_fn(
            "page.logs.accessibility.info.initial_state",
            language=ui_language,
            default="Сообщение страницы логов: пока нет сообщений",
        ),
    )
    top_row.addWidget(info_label, 1)

    refresh_btn = tool_button_cls()
    refresh_icon_normal = FluentIcon.SYNC
    spin_timer = refresh_timer_parent._spin_timer = refresh_timer_parent._spin_timer if hasattr(refresh_timer_parent, "_spin_timer") else None
    if spin_timer is None:
        from PyQt6.QtCore import QTimer
        spin_timer = QTimer(refresh_timer_parent)
        refresh_timer_parent._spin_timer = spin_timer
    spin_timer.setInterval(33)
    refresh_timer_parent._spin_angle = 0
    spin_timer.timeout.connect(on_spin_tick)
    refresh_timer_parent._refresh_icon_normal = refresh_icon_normal
    refresh_btn.setIcon(refresh_icon_normal)
    refresh_btn.setFixedSize(36, 36)
    refresh_btn.setCursor(refresh_timer_parent.cursor() if hasattr(refresh_timer_parent, "cursor") else refresh_btn.cursor())
    refresh_name = tr_catalog_fn("page.logs.accessibility.refresh.name", language=ui_language, default="Обновить список логов")
    set_control_accessibility(
        refresh_btn,
        name=refresh_name,
        description=tr_catalog_fn(
            "page.logs.accessibility.refresh.description",
            language=ui_language,
            default="Обновить список файлов логов и статистику.",
        ),
    )
    set_state_text(refresh_btn, refresh_name)
    refresh_btn.clicked.connect(on_refresh)
    top_row.addWidget(refresh_btn)
    controls_main.addLayout(top_row)

    logs_table = table_widget_cls()
    logs_table.setColumnCount(4)
    logs_table.setRowCount(0)
    logs_table.setHorizontalHeaderLabels(["Файл", "Статус", "Размер", "Путь"])
    try:
        logs_table.setBorderVisible(True)
        logs_table.setBorderRadius(8)
    except Exception:
        pass
    header = logs_table.horizontalHeader()
    header.setSectionResizeMode(0, header_view_cls.ResizeMode.Stretch)
    header.setSectionResizeMode(1, header_view_cls.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(2, header_view_cls.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(3, header_view_cls.ResizeMode.Stretch)
    logs_table.verticalHeader().setVisible(False)
    logs_table.verticalHeader().setDefaultSectionSize(34)
    logs_table.setEditTriggers(table_widget_cls.EditTrigger.NoEditTriggers)
    logs_table.setSelectionBehavior(table_widget_cls.SelectionBehavior.SelectRows)
    logs_table.setSelectionMode(table_widget_cls.SelectionMode.SingleSelection)
    logs_table.cellClicked.connect(on_log_selected)
    logs_table.setMinimumHeight(260)
    logs_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    set_control_accessibility(
        logs_table,
        name="Таблица файлов логов",
        description="Выберите строку, чтобы открыть файл лога для просмотра.",
    )
    set_state_text(logs_table, "Таблица файлов логов: строки пока не загружены")
    controls_main.addWidget(logs_table, 1)

    controls_card.add_layout(controls_main)
    parent_layout.addWidget(controls_card, 1)

    controls_actions_title = None
    controls_actions_bar = quick_actions_bar_cls(content_parent)

    copy_btn = push_button_cls(
        tr_catalog_fn("page.logs.button.copy", language=ui_language, default="Копировать"),
        icon=FluentIcon.COPY,
    )
    copy_name = tr_catalog_fn("page.logs.accessibility.copy.name", language=ui_language, default="Копировать текущий лог")
    set_control_accessibility(
        copy_btn,
        name=copy_name,
        description=tr_catalog_fn(
            "page.logs.action.copy.description",
            language=ui_language,
            default="Скопировать содержимое текущего лога в буфер обмена.",
        ),
    )
    set_state_text(copy_btn, copy_name)
    copy_btn.clicked.connect(on_copy)
    controls_actions_bar.add_button(copy_btn)

    clear_btn = push_button_cls(
        tr_catalog_fn("page.logs.button.clear", language=ui_language, default="Очистить"),
        icon=FluentIcon.ERASE_TOOL,
    )
    clear_name = tr_catalog_fn("page.logs.accessibility.clear_view.name", language=ui_language, default="Очистить окно просмотра лога")
    set_control_accessibility(
        clear_btn,
        name=clear_name,
        description=tr_catalog_fn(
            "page.logs.action.clear.description",
            language=ui_language,
            default="Очистить только текущее окно просмотра, не удаляя файл лога.",
        ),
    )
    set_state_text(clear_btn, clear_name)
    clear_btn.clicked.connect(on_clear_view)
    controls_actions_bar.add_button(clear_btn)

    folder_btn = push_button_cls(
        tr_catalog_fn("page.logs.button.folder", language=ui_language, default="Папка"),
        icon=FluentIcon.FOLDER,
    )
    folder_name = tr_catalog_fn("page.logs.accessibility.folder.name", language=ui_language, default="Открыть папку логов")
    set_control_accessibility(
        folder_btn,
        name=folder_name,
        description=tr_catalog_fn(
            "page.logs.action.folder.description",
            language=ui_language,
            default="Открыть папку logs с файлами приложения.",
        ),
    )
    set_state_text(folder_btn, folder_name)
    folder_btn.clicked.connect(on_open_folder)
    controls_actions_bar.add_button(folder_btn)

    parent_layout.addWidget(controls_actions_bar)

    return LogsManagementTabWidgets(
        controls_card=controls_card,
        logs_table=logs_table,
        refresh_btn=refresh_btn,
        info_label=info_label,
        controls_actions_title=controls_actions_title,
        controls_actions_bar=controls_actions_bar,
        copy_btn=copy_btn,
        clear_btn=clear_btn,
        folder_btn=folder_btn,
    )


def build_logs_secondary_panels_ui(
    *,
    parent_layout,
    ui_language: str,
    tr_catalog_fn,
    settings_card_cls,
    qvbox_layout_cls,
    qhbox_layout_cls,
    qlabel_cls,
    caption_label_cls,
    strong_body_label_cls,
    fluent_push_button_cls,
    text_edit_cls,
    qfont_cls,
    errors_text_min_height: int,
    errors_text_max_height: int,
    on_clear_errors,
    on_update_errors_height,
) -> LogsSecondaryPanelsWidgets:
    errors_card = settings_card_cls()
    errors_layout = qvbox_layout_cls()
    errors_header = qhbox_layout_cls()

    warning_icon = qlabel_cls()
    errors_header.addWidget(warning_icon)

    errors_title_label = strong_body_label_cls(
        tr_catalog_fn("page.logs.errors.title", language=ui_language, default="Ошибки и предупреждения")
    )
    errors_header.addWidget(errors_title_label)
    errors_header.addSpacing(8)

    errors_count_label = caption_label_cls(
        tr_catalog_fn("page.logs.errors.count", language=ui_language, default="Ошибок: {count}").format(count=0)
    )
    set_state_text(errors_count_label, errors_count_label.text())
    errors_header.addWidget(errors_count_label)
    errors_header.addStretch()

    clear_errors_btn = fluent_push_button_cls(
        tr_catalog_fn("page.logs.button.clear", language=ui_language, default="Очистить"),
        icon=FluentIcon.DELETE,
    )
    set_control_accessibility(
        clear_errors_btn,
        name=tr_catalog_fn(
            "page.logs.accessibility.clear_errors.name",
            language=ui_language,
            default="Очистить ошибки и предупреждения",
        ),
        description=tr_catalog_fn(
            "page.logs.accessibility.clear_errors.description",
            language=ui_language,
            default="Очистить панель найденных ошибок и предупреждений.",
        ),
    )
    clear_errors_btn.clicked.connect(on_clear_errors)
    errors_header.addWidget(clear_errors_btn)

    errors_layout.addLayout(errors_header)

    errors_text = text_edit_cls()
    errors_text.setReadOnly(True)
    errors_text.setLineWrapMode(text_edit_cls.LineWrapMode.NoWrap)
    errors_text.setFont(qfont_cls("Consolas", 9))
    errors_text.setMinimumHeight(errors_text_min_height)
    errors_text.setMaximumHeight(errors_text_max_height)
    apply_text_line_limit(errors_text, ERROR_LOG_VIEW_MAX_LINES)
    set_control_accessibility(
        errors_text,
        name=tr_catalog_fn(
            "page.logs.accessibility.errors_text.name",
            language=ui_language,
            default="Найденные ошибки и предупреждения",
        ),
        description=tr_catalog_fn(
            "page.logs.accessibility.errors_text.description",
            language=ui_language,
            default="Список строк лога, которые программа распознала как ошибки или предупреждения.",
        ),
    )
    set_state_text(
        errors_text,
        tr_catalog_fn(
            "page.logs.accessibility.errors_text.initial_state",
            language=ui_language,
            default="Найденные ошибки и предупреждения: пока нет записей",
        ),
    )
    errors_text.document().contentsChanged.connect(on_update_errors_height)
    errors_layout.addWidget(errors_text)

    errors_card.add_layout(errors_layout)
    parent_layout.addWidget(errors_card)

    return LogsSecondaryPanelsWidgets(
        errors_card=errors_card,
        warning_icon_label=warning_icon,
        errors_title_label=errors_title_label,
        errors_count_label=errors_count_label,
        clear_errors_btn=clear_errors_btn,
        errors_text=errors_text,
    )
