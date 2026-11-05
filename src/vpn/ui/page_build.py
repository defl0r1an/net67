"""Список серверов слева, привычное крупное подключение справа."""
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QListWidget, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, ComboBox, LineEdit, PrimaryPushButton, PushButton, SegmentedWidget, StrongBodyLabel, TextEdit
from ui.accessibility import set_control_accessibility
from ui.widgets.fluent_item_tooltip import install_fluent_item_tooltips
from vpn.flags import FLAG_HEIGHT
from vpn.tabs import TAB_ORDER, TAB_TITLES
from vpn.ui.controls import LargeVpnButton, ScopeSelector
from vpn.ui.server_list_motion import attach_server_list_motion


class VpnImportDialog(QDialog):
    def showEvent(self, event):  # noqa: N802
        from shell.theme import palette
        from ui.theme import get_theme_tokens

        # У отдельного окна собственная палитра: иначе Qt оставляет светлый
        # фон даже при тёмных элементах основной страницы.
        colors = palette(not get_theme_tokens().is_light)
        current = self.palette()
        current.setColor(QPalette.ColorRole.Window, QColor(colors.content))
        self.setPalette(current)
        self.setAutoFillBackground(True)
        super().showEvent(event)

    def set_title(self, title):
        self.setWindowTitle("Добавить VPN")


def build_vpn_page(page):
    page.subtitle_label.hide()
    page.tabs = SegmentedWidget(page)
    for key in TAB_ORDER:
        page.tabs.addItem(key, TAB_TITLES[key])
    page.tabs.setCurrentItem(page._tab)
    page.tabs.currentItemChanged.connect(page._on_tab_changed)
    page._announce_tabs()
    page.add_widget(page.tabs)

    main = QWidget(page.content)
    main.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    columns = QHBoxLayout(main)
    columns.setContentsMargins(0, 0, 0, 0)
    columns.setSpacing(32)
    servers = QVBoxLayout()
    servers.setSpacing(12)
    tools = QHBoxLayout()
    tools.setSpacing(8)
    page.search_edit = LineEdit(page.content)
    page.search_edit.setPlaceholderText("Найти сервер")
    page.search_edit.setClearButtonEnabled(True)
    page.search_edit.textChanged.connect(page._experience.filter_changed)
    tools.addWidget(page.search_edit, 1)
    page.favorites_btn = PushButton("Избранные")
    page.favorites_btn.setCheckable(True)
    page.favorites_btn.toggled.connect(page._experience.filter_changed)
    tools.addWidget(page.favorites_btn)
    page.refresh_subs_btn = PushButton("Обновить")
    page.refresh_subs_btn.setToolTip("Обновить подписки")
    page.refresh_subs_btn.clicked.connect(page._on_refresh_subscriptions)
    tools.addWidget(page.refresh_subs_btn)
    page.add_btn = PrimaryPushButton("Добавить")
    page.add_btn.clicked.connect(page._experience.toggle_import)
    tools.addWidget(page.add_btn)
    servers.addLayout(tools)

    page.profile_list = QListWidget(page.content)
    page.profile_list.setObjectName("net67ServerList")
    page.profile_list.setMinimumHeight(360)
    page.profile_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    page.profile_list.setIconSize(QSize(FLAG_HEIGHT, FLAG_HEIGHT))
    page.profile_list.setTextElideMode(Qt.TextElideMode.ElideRight)
    install_fluent_item_tooltips(page.profile_list)
    page.profile_list.currentRowChanged.connect(page._on_profile_changed)
    page.profile_list.itemClicked.connect(page._on_list_item_clicked)
    page._list_motion = attach_server_list_motion(page.profile_list)
    set_control_accessibility(page.profile_list, name="Серверы VPN", description="Выберите сервер для подключения")
    servers.addWidget(page.profile_list, 1)
    page.empty_label = BodyLabel("")
    page.empty_label.setWordWrap(True)
    servers.addWidget(page.empty_label)
    page.profile_combo = ComboBox(page.content)
    page.profile_combo.hide()
    page.profile_combo.currentIndexChanged.connect(page._on_profile_changed)
    actions = QHBoxLayout()
    page.ping_btn = PushButton("Проверить сервер")
    page.ping_btn.clicked.connect(page._on_check_server)
    actions.addWidget(page.ping_btn)
    page.export_btn = PushButton("Сохранить конфигурацию")
    page.export_btn.clicked.connect(page._on_export)
    actions.addWidget(page.export_btn)
    page.delete_btn = PushButton("Удалить")
    page.delete_btn.clicked.connect(page._on_delete)
    actions.addWidget(page.delete_btn)
    actions.addStretch()
    servers.addLayout(actions)
    columns.addLayout(servers, 1)

    panel = QWidget(page.content)
    panel.setFixedWidth(240)
    right = QVBoxLayout(panel)
    right.setContentsMargins(12, 12, 12, 12)
    right.setSpacing(10)
    right.addStretch()
    page.server_flag = QLabel()
    page.server_flag.setAlignment(Qt.AlignmentFlag.AlignCenter)
    right.addWidget(page.server_flag)
    page.server_title = StrongBodyLabel("Выберите сервер")
    page.server_title.setWordWrap(True)
    page.server_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    right.addWidget(page.server_title)
    page.connect_button = LargeVpnButton(panel)
    page.connect_button.clicked.connect(page._on_toggle_connection)
    right.addWidget(page.connect_button, 0, Qt.AlignmentFlag.AlignHCenter)
    page.connect_caption = StrongBodyLabel(page.connect_button.title())
    page.connect_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
    right.addWidget(page.connect_caption)
    page.state_label = BodyLabel("Отключено")
    page.state_label.setWordWrap(True)
    page.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    right.addWidget(page.state_label)
    page.ping_label = BodyLabel("")
    page.ping_label.setWordWrap(True)
    page.ping_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    right.addWidget(page.ping_label)
    page.tun_mode_toggle = ScopeSelector(panel)
    from vpn.link_runtime import tun_mode_enabled
    page.tun_mode_toggle.setChecked(tun_mode_enabled(), block_signals=True)
    page.tun_mode_toggle.toggled.connect(page._on_tun_mode_toggled)
    right.addWidget(page.tun_mode_toggle, 0, Qt.AlignmentFlag.AlignHCenter)
    page.scope_label = BodyLabel("")
    page.scope_label.setWordWrap(True)
    page.scope_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    right.addWidget(page.scope_label)
    page.favorite_btn = PushButton("В избранное")
    page.favorite_btn.clicked.connect(page._experience.toggle_favorite)
    right.addWidget(page.favorite_btn, 0, Qt.AlignmentFlag.AlignHCenter)
    page.selection_label = BodyLabel("")
    page.selection_label.setWordWrap(True)
    right.addWidget(page.selection_label)
    right.addStretch()
    columns.addWidget(panel)
    page.add_widget(main, stretch=1)

    # Импорт не занимает строк списка ни в закрытом, ни в свёрнутом виде.
    page.add_section = VpnImportDialog(page)
    page.add_section.setWindowTitle("Добавить VPN")
    page.add_section.setModal(True)
    page.add_section.resize(480, 210)
    page.add_section.setMaximumWidth(560)
    form = QVBoxLayout(page.add_section)
    form.setContentsMargins(16, 16, 16, 16)
    form.setSpacing(12)
    form.addWidget(StrongBodyLabel("Добавить VPN", page.add_section))
    page.input_edit = TextEdit(page.add_section)
    page.input_edit.setFixedHeight(80)
    page.input_edit.setPlaceholderText("Ссылка, подписка или конфигурация VPN")
    form.addWidget(page.input_edit)
    page.import_status_label = BodyLabel("")
    page.import_status_label.hide()
    form.addWidget(page.import_status_label)
    buttons = QHBoxLayout()
    page.import_file_btn = PushButton("Выбрать файл")
    page.import_file_btn.clicked.connect(page._on_pick_file)
    buttons.addWidget(page.import_file_btn)
    buttons.addStretch()
    page.save_btn = PrimaryPushButton("Добавить")
    page.save_btn.clicked.connect(page._on_save_profile)
    buttons.addWidget(page.save_btn)
    close = PushButton("Отмена")
    close.clicked.connect(page.add_section.hide)
    buttons.addWidget(close)
    form.addLayout(buttons)

    # Эти подписи нужны существующим обработчикам и подсказкам; блоков на
    # странице нет. Диагностические детали не заслоняют выбор сервера.
    for attr in ("input_title_label", "hint_label", "details_label", "warning_label", "note_label"):
        label = BodyLabel("", page)
        label.hide()
        setattr(page, attr, label)
