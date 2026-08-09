# vpn/ui/page.py
"""Страница VPN — ввод ключа или .conf, профили и проверка сервера."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    SegmentedWidget,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    TextEdit,
)

from log.log import log
from ui.accessibility import set_control_accessibility
from ui.pages.base_page import BasePage
from ui.theme import get_theme_tokens

from vpn.parser import VpnConfigError, parse_any, to_conf_text
from vpn.tabs import (
    TAB_HINTS,
    TAB_INPUT_TITLES,
    TAB_LINKS,
    TAB_ORDER,
    TAB_PLACEHOLDERS,
    TAB_SUBTITLES,
    TAB_TITLES,
    empty_text,
    normalize_tab,
    profiles_for_tab,
    tab_counts,
    tab_for_profile,
)
from vpn.ping import check_server, format_latency

#: Высота поля для ключа или ссылки.
#:
#: Три строки. Сюда вставляют одну — ключ или ссылку, — и прежние 150
#: пикселей занимали пол-экрана ради неё.
INPUT_HEIGHT = 68
from vpn.profiles import (
    display_name,
    load_profiles,
    remove_profile,
    save_profiles,
    upsert_profile,
)


#: Высота списка серверов. Шесть строк: дальше начинается прокрутка, а
#: не растущая во весь экран страница.
SERVER_LIST_HEIGHT = 190


def _profiles_root():
    from config.runtime_layout import APPLICATION_PATHS

    return APPLICATION_PATHS.settings_dir


def _profile_name(profile) -> str:
    """Имя профиля независимо от его рода.

    Список на странице общий, а профили в нём двух видов: конфигурация
    WireGuard и сервер из ссылки. Имя у них зовётся по-разному — `name`
    и `title`. Обращение к первому напрямую роняло страницу на каждом
    втором действии:

        AttributeError: 'LinkProfile' object has no attribute 'name'

    Ловилось это не в одном месте, а в четырёх — выбор профиля, показ
    подробностей, подключение, проверка сервера, — потому что каждое
    трогало поле само.
    """
    return str(getattr(profile, "name", "") or getattr(profile, "title", "") or "")


#: Как часто перечитывать статистику туннеля, пока страница открыта.
#: Запрос уходит в фоновый поток, поэтому секунда окна не тормозит.
STATS_REFRESH_MS = 2_000


class VpnPage(BasePage):
    """Управление VPN-профилями AmneziaWG и WireGuard."""

    def __init__(self, parent=None):
        super().__init__(
            "VPN",
            "Подключение через AmneziaWG или WireGuard",
            parent,
            title_key="page.vpn.title",
            subtitle_key="page.vpn.subtitle",
        )
        from vpn.tunnel import TunnelState

        self._profiles = []
        #: Профили активной вкладки. Хранилище общее, вкладки — только
        #: способ показа, поэтому фильтруем на лету, а не режем файл.
        self._visible_profiles = []
        self._tab = TAB_ORDER[0]
        #: Раздел подключения по ссылке закрыт, пока его дорабатывают.
        #: Счёт нажатий и признак открытия живут в окне: перезапуск
        #: закрывает раздел обратно, и это намеренно.
        self._links_unlocked = False
        self._links_clicks = 0
        self._tunnel_state = TunnelState.DISCONNECTED
        # По одному воркеру на операцию: параллельно запускать их незачем,
        # а ссылку держать обязательно — иначе QThread соберёт сборщик
        # мусора прямо во время работы.
        self._status_worker = None
        self._ping_worker = None
        self._tunnel_worker = None
        #: Последняя статистика туннеля. Её же берёт проверка сервера:
        #: состоявшееся рукопожатие — довод сильнее любой внешней пробы.
        self._last_stats = None

        # Счётчики трафика меняются каждую секунду, а состояние
        # запрашивалось один раз при открытии страницы. Из-за этого
        # «Принято 0 Б, отправлено 276 Б» застывало на первом замере и
        # выглядело как поломка, хотя туннель жил своей жизнью.
        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(STATS_REFRESH_MS)
        self._stats_timer.timeout.connect(self._refresh_connection_state)

        self._build_ui()
        self._reload_profiles()

    # ──────────────────────────────────────────────────────────────────
    # Фоновые вызовы
    # ──────────────────────────────────────────────────────────────────

    def _start_worker(self, attr: str, call, on_done, on_failed=None):
        """Запускает вызов в отдельном потоке, если такой уже не идёт."""
        from vpn.ui.workers import VpnCallWorker

        current = getattr(self, attr, None)
        if current is not None and current.isRunning():
            return None

        worker = VpnCallWorker(call, parent=self)
        setattr(self, attr, worker)

        def _clear():
            if getattr(self, attr, None) is worker:
                setattr(self, attr, None)
            worker.deleteLater()

        worker.done.connect(on_done)
        if on_failed is not None:
            worker.failed.connect(on_failed)
        worker.finished.connect(_clear)
        worker.start()
        return worker

    # ──────────────────────────────────────────────────────────────────
    # Построение
    # ──────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        tokens = get_theme_tokens()

        # AmneziaWG и обычный WireGuard поднимаются одним клиентом, но в
        # общем списке их было не различить. Вкладки разделяют показ, не
        # трогая хранилище.
        self.tabs = SegmentedWidget(self)
        # Без этого выбранная вкладка отличается только подсветкой, и
        # программа экранного доступа не скажет, какая из них открыта.
        self._announce_tabs()
        for key in TAB_ORDER:
            self.tabs.addItem(key, TAB_TITLES[key], lambda k=key: self._on_tab_changed(k))
        self.tabs.setCurrentItem(self._tab)
        self.add_widget(self.tabs)

        self.input_title_label = StrongBodyLabel(TAB_INPUT_TITLES[self._tab])
        self.add_widget(self.input_title_label)

        self.hint_label = BodyLabel(TAB_HINTS[self._tab])
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet(f"QLabel {{ color: {tokens.fg_muted}; }}")
        self.add_widget(self.hint_label)

        # Поле ввода низкое намеренно. Сюда вставляют одну строку —
        # ключ или ссылку, — и поле в полтораста пикселей занимало пол-
        # экрана ради неё. Конфиг .conf длиннее, но его вставляют раз в
        # жизни и читают не здесь, а в сохранённом профиле.
        self.input_edit = TextEdit(self.content)
        self.input_edit.setPlaceholderText(TAB_PLACEHOLDERS[self._tab])
        self.input_edit.setFixedHeight(INPUT_HEIGHT)
        set_control_accessibility(
            self.input_edit,
            name="Ключ или конфигурация VPN",
            description="Поле для вставки ключа vpn или содержимого файла .conf",
        )
        self.add_widget(self.input_edit)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        self.import_file_btn = PushButton("Загрузить .conf")
        self.import_file_btn.clicked.connect(self._on_pick_file)
        buttons.addWidget(self.import_file_btn)

        self.save_btn = PrimaryPushButton("Сохранить профиль")
        self.save_btn.clicked.connect(self._on_save_profile)
        buttons.addWidget(self.save_btn)

        buttons.addStretch()
        self._add_row(buttons)

        self.add_widget(StrongBodyLabel("Сохранённые профили"))

        # Список, а не выпадающий: у подписки бывает тридцать серверов,
        # и выбирать из них по одному, каждый раз раскрывая список, —
        # мучение. В списке видно всё сразу, как в Happ.
        from PyQt6.QtWidgets import QListWidget

        self.profile_list = QListWidget(self.content)
        self.profile_list.setObjectName("net67ServerList")
        self.profile_list.setFixedHeight(SERVER_LIST_HEIGHT)
        self.profile_list.currentRowChanged.connect(self._on_profile_changed)
        set_control_accessibility(
            self.profile_list,
            name="Серверы",
            description="Выберите сервер для подключения",
        )
        self.add_widget(self.profile_list)

        # Выпадающий список остаётся невидимым: на него смотрят
        # существующие обработчики страницы, и переписывать их всех ради
        # смены вида значило бы трогать логику вместе с оформлением.
        self.profile_combo = ComboBox(self.content)
        self.profile_combo.hide()
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        set_control_accessibility(
            self.profile_combo,
            name="Сохранённые профили VPN",
            description="Выбор профиля подключения",
        )


        self.details_label = BodyLabel("Профили не добавлены")
        self.details_label.setWordWrap(True)
        self.details_label.setStyleSheet(f"QLabel {{ color: {tokens.fg_muted}; }}")
        self.add_widget(self.details_label)

        connection = QHBoxLayout()
        connection.setSpacing(8)

        self.connect_btn = PrimaryPushButton("Подключить")
        self.connect_btn.clicked.connect(self._on_toggle_connection)
        connection.addWidget(self.connect_btn)

        self.state_label = QLabel("Отключено")
        connection.addWidget(self.state_label, 1)
        self._add_row(connection)

        actions = QHBoxLayout()
        actions.setSpacing(8)

        self.ping_btn = PushButton("Проверить сервер")
        self.ping_btn.clicked.connect(self._on_check_server)
        actions.addWidget(self.ping_btn)

        self.export_btn = PushButton("Сохранить как .conf")
        self.export_btn.clicked.connect(self._on_export)
        actions.addWidget(self.export_btn)

        self.delete_btn = PushButton("Удалить")
        self.delete_btn.clicked.connect(self._on_delete)
        actions.addWidget(self.delete_btn)

        actions.addStretch()
        self._add_row(actions)

        self.ping_label = QLabel("")
        self.ping_label.setWordWrap(True)
        self.ping_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.add_widget(self.ping_label)

        note = BodyLabel(
            "Туннель поднимается службой Windows через клиент AmneziaWG. "
            "Обход DPI при этом не выключается: он может помочь рукопожатию "
            "пройти сквозь фильтрацию, но может и помешать. Если туннель не "
            "поднимается — попробуйте остановить обход и подключиться снова."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"QLabel {{ color: {tokens.fg_faint}; font-size: 12px; }}")
        self.add_widget(note)

    def _add_row(self, layout: QHBoxLayout) -> None:
        from PyQt6.QtWidgets import QWidget

        holder = QWidget(self.content)
        wrapper = QVBoxLayout(holder)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.addLayout(layout)
        self.add_widget(holder)

    # ──────────────────────────────────────────────────────────────────
    # Данные
    # ──────────────────────────────────────────────────────────────────

    def _reload_profiles(self, *, select_endpoint: str = "") -> None:
        """Читает оба хранилища: конфиги WireGuard и ссылки.

        Хранилища разные, потому что и поднимаются они разным: конфиги —
        службой Windows, ссылки — ядром Xray. А список на экране один, и
        собирается он здесь.
        """
        from vpn.link_store import load_links

        self._profiles = list(load_profiles(_profiles_root()))
        links, errors = load_links(_profiles_root())
        self._profiles.extend(links)
        for message in errors:
            log(f"Список серверов: {message}", "WARNING")
        self._refill_combo(select_endpoint=select_endpoint)

    def _refill_combo(self, *, select_endpoint: str = "") -> None:
        """Наполняет список профилями активной вкладки.

        Хранилище общее: вкладка решает только, что показать. Поэтому
        фильтруем при показе, а не режем файл профилей на два.
        """
        self._visible_profiles = profiles_for_tab(self._profiles, self._tab)

        self.profile_combo.blockSignals(True)
        self.profile_list.blockSignals(True)
        self.profile_combo.clear()
        self.profile_list.clear()
        for profile in self._visible_profiles:
            self.profile_combo.addItem(display_name(profile))
            self.profile_list.addItem(display_name(profile))

        index = 0
        if select_endpoint:
            for position, profile in enumerate(self._visible_profiles):
                if profile.endpoint == select_endpoint:
                    index = position
                    break
        if self._visible_profiles:
            self.profile_combo.setCurrentIndex(index)
            self.profile_list.setCurrentRow(index)
        self.profile_combo.blockSignals(False)
        self.profile_list.blockSignals(False)

        self._sync_tab_labels()
        self._update_details()

    def _announce_tabs(self) -> None:
        """Озвучивает вкладки и то, какая выбрана."""
        try:
            from ui.segmented_accessibility import set_segmented_items_accessibility
            from vpn.tabs import TAB_TITLES

            set_segmented_items_accessibility(
                self.tabs,
                name="Тип VPN",
                labels=dict(TAB_TITLES),
            )
        except Exception as exc:
            # Не молчим: озвучивание, отвалившееся тихо, обнаружится
            # только жалобой человека, который им пользуется.
            log(f"Вкладки VPN не озвучены: {exc}", "⚠ WARNING")

    def _sync_tab_labels(self) -> None:
        """Дописывает к названию вкладки число профилей на ней.

        Без счётчика пустая вкладка выглядит как поломка: человек сохранил
        конфиг, а список пуст — просто потому, что конфиг уехал на
        соседнюю вкладку.
        """
        counts = tab_counts(self._profiles)
        for key in TAB_ORDER:
            title = TAB_TITLES[key]
            count = counts.get(key, 0)
            try:
                item = self.tabs.widget(key)
            except Exception:
                item = None
            if item is None:
                continue
            try:
                item.setText(f"{title} ({count})" if count else title)
            except Exception:
                continue

    def _on_tab_changed(self, key: str) -> None:
        tab = normalize_tab(key)
        if tab == self._tab:
            return

        if tab == TAB_LINKS and not self._links_unlocked:
            # Раздел закрыт: подключение по ссылке ещё доделывается, и
            # пускать туда людей рано. Открывается десятью нажатиями —
            # случайно столько не нажимают, а тот, кому надо, знает.
            from vpn.tabs import locked_click_feedback

            self._links_clicks += 1
            unlocked, message = locked_click_feedback(self._links_clicks)
            self._links_unlocked = unlocked
            self.state_label.setText(message)

            if not unlocked:
                # Возвращаем подсветку на открытую вкладку: иначе она
                # горит на разделе, который так и не открылся.
                self.tabs.setCurrentItem(self._tab)
                return

        self._tab = tab
        self.hint_label.setText(TAB_HINTS[tab])
        self.input_title_label.setText(TAB_INPUT_TITLES[tab])
        subtitle = getattr(self, "subtitle_label", None)
        if subtitle is not None:
            subtitle.setText(TAB_SUBTITLES[tab])
        self.input_edit.setPlaceholderText(TAB_PLACEHOLDERS[tab])
        self._refill_combo()

    def _current_profile(self):
        # Спрашиваем список: он на экране, и именно в нём человек выбрал
        # строку. Выпадающий держим в согласии с ним ради обработчиков,
        # которые на него смотрят.
        index = self.profile_list.currentRow()
        if index != self.profile_combo.currentIndex():
            self.profile_combo.blockSignals(True)
            self.profile_combo.setCurrentIndex(index)
            self.profile_combo.blockSignals(False)
        if 0 <= index < len(self._visible_profiles):
            return self._visible_profiles[index]
        return None

    def _sync_stats_timer(self, connected: bool) -> None:
        """Опрашивает туннель только когда есть что показывать.

        Гонять awg.exe каждые две секунды при отключённом туннеле незачем:
        цифры всё равно нулевые, а процесс запускается на каждый вызов.
        """
        timer = getattr(self, "_stats_timer", None)
        if timer is None:
            return
        try:
            should_run = bool(connected) and bool(self.isVisible())
            if should_run and not timer.isActive():
                timer.start()
            elif not should_run and timer.isActive():
                timer.stop()
        except Exception as exc:
            log(f"Таймер статистики туннеля: {exc}", "DEBUG")

    def on_page_hidden(self) -> None:
        # Со скрытой страницы опрашивать нечего.
        self._sync_stats_timer(False)

    def on_page_activated(self) -> None:
        self._refresh_connection_state()

    #: Имена полей со фоновыми потоками страницы.
    _WORKER_ATTRS = ("_status_worker", "_ping_worker", "_tunnel_worker")

    def cleanup(self) -> None:
        self._sync_stats_timer(False)
        self._stop_workers()
        super().cleanup()

    def _stop_workers(self) -> None:
        """Дожидается фоновых потоков перед уходом со страницы.

        Удаление работающего QThread — не предупреждение, а фатальная
        ошибка Qt: «QThread: Destroyed while thread is still running», и
        процесс падает. Строка из crashes.log именно про это.

        Опрос состояния туннеля запускает awg.exe и ждёт его до десяти
        секунд, так что поймать момент закрытия страницы посреди работы
        совсем не редкость.
        """
        for attr in self._WORKER_ATTRS:
            worker = getattr(self, attr, None)
            setattr(self, attr, None)
            if worker is None:
                continue
            try:
                if worker.isRunning():
                    worker.quit()
                    # Ждём, а не убиваем: terminate() у QThread оставляет
                    # захваченные объекты в неопределённом состоянии.
                    worker.wait(3000)
            except Exception as exc:
                log(f"Остановка фонового потока VPN ({attr}): {exc}", "DEBUG")

    def _refresh_connection_state(self) -> None:
        """Запрашивает состояние службы туннеля в фоне.

        Раньше get_status() вызывался здесь напрямую, а внутри он ждёт
        awg.exe до десяти секунд. Метод дёргается при каждом открытии
        страницы и смене профиля — окно замирало на ровном месте.
        """
        profile = self._current_profile()
        tunnel_name = _profile_name(profile) if profile else ""

        def _collect():
            from vpn.tunnel import TunnelState
            from vpn.tunnel_runtime import get_stats, get_status

            status = get_status()
            state = status.state if status else TunnelState.DISCONNECTED
            stats = None
            if state is TunnelState.CONNECTED:
                try:
                    stats = get_stats(tunnel_name)
                except Exception:
                    stats = None
            return state, stats

        self._start_worker(
            "_status_worker",
            _collect,
            self._on_connection_state_ready,
            lambda message: log(f"Состояние туннеля: {message}", "DEBUG"),
        )

    def _on_connection_state_ready(self, payload) -> None:
        from vpn.tunnel import TunnelState, describe_state

        try:
            state, stats = payload
        except Exception:
            state, stats = TunnelState.DISCONNECTED, None

        self._tunnel_state = state
        self._last_stats = stats
        self._sync_stats_timer(state is TunnelState.CONNECTED)
        self.connect_btn.setText("Отключить" if state is TunnelState.CONNECTED else "Подключить")

        text = describe_state(state)
        if stats is not None:
            # Рукопожатие — единственный надёжный признак живого туннеля:
            # адаптер может существовать, а обмена не быть.
            try:
                from vpn.status import describe

                text = f"{text} · {describe(stats)}"
            except Exception as exc:
                log(f"Статистика туннеля: {exc}", "DEBUG")

        self.state_label.setText(text)

    def _update_details(self) -> None:
        profile = self._current_profile()
        has_profile = profile is not None

        for button in (self.ping_btn, self.export_btn, self.delete_btn, self.connect_btn):
            button.setEnabled(has_profile)

        self._refresh_connection_state()

        if not has_profile:
            # Общее «Профили не добавлены» врало: профили могли быть, но
            # на соседней вкладке.
            self.details_label.setText(empty_text(self._tab))
            self.ping_label.setText("")
            return

        protocol = getattr(profile, "protocol", "") or getattr(profile, "protocol_title", "")
        parts = [f"Протокол: {protocol}", f"Сервер: {profile.endpoint or 'не указан'}"]
        if profile.address:
            parts.append(f"Адрес в туннеле: {profile.address}")
        if profile.dns:
            parts.append(f"DNS: {profile.dns}")
        self.details_label.setText("\n".join(parts))
        self.ping_label.setText("")

    # ──────────────────────────────────────────────────────────────────
    # Действия
    # ──────────────────────────────────────────────────────────────────

    def _save_links(self, text: str) -> None:
        """Разбирает ссылку или подписку и добавляет серверы в список.

        Адрес подписки — отдельный случай: за списком надо сходить в
        сеть. Делаем это в потоке, иначе окно замирает на всё время
        ответа сервера, а ждать там можно до десяти секунд.
        """
        from vpn.links import parse_subscription
        from vpn.subscription import load_subscription, looks_like_subscription_url

        raw = str(text or "").strip()

        if looks_like_subscription_url(raw):
            self.state_label.setText("Загружаем подписку...")
            started = self._start_worker(
                "_subscription_worker",
                lambda url=raw: load_subscription(url),
                self._on_subscription_loaded,
                self._on_subscription_failed,
            )
            if started is None:
                self._error("Подписка уже загружается")
            return

        added, errors = parse_subscription(raw)
        self._apply_links(added, errors)

    def _on_subscription_loaded(self, result) -> None:
        added, errors = result
        self._refresh_connection_state()
        self._apply_links(added, errors)

    def _on_subscription_failed(self, message: str) -> None:
        self._refresh_connection_state()
        self._error(f"Не удалось загрузить подписку: {message}")

    def _apply_links(self, added, errors) -> None:
        """Кладёт разобранные серверы в хранилище и обновляет список."""
        from vpn.link_store import load_links, merge, save_links

        if not added:
            self._error(errors[0] if errors else "Не удалось разобрать ссылку")
            return

        root = _profiles_root()
        existing, _load_errors = load_links(root)
        merged = merge(existing, added)

        saved, message = save_links(root, merged)
        if not saved:
            self._error(message)
            return

        self.input_edit.clear()
        self._reload_profiles()

        # Об ошибках сообщаем, даже когда что-то добавилось: в подписке
        # из тридцати серверов молча потерять три — значит показать
        # неполный список и не сказать об этом.
        if errors:
            self._error(f"Добавлено серверов: {len(added)}. Не разобрано: {len(errors)}")

    def _on_pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл конфигурации",
            "",
            "Конфигурация VPN (*.conf);;Все файлы (*.*)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                self.input_edit.setPlainText(handle.read())
        except Exception as exc:
            self._error(f"Не удалось прочитать файл: {exc}")

    def _on_save_profile(self) -> None:
        text = self.input_edit.toPlainText()

        # Разборщик выбирается по содержимому, а не по вкладке.
        #
        # Сначала он выбирался вкладкой, и это оказалось ненадёжно:
        # человек стоял на вкладке «VPN», вставлял ссылку на подписку и
        # всё равно получал «поддерживаются только ключи, начинающиеся с
        # vpn://» — ответ разборщика WireGuard. Состояние вкладки и
        # состояние поля разошлись, а поймать этот разрыв на живом окне
        # не удалось.
        #
        # Содержимое однозначно: `[Interface]` не спутать с `vless://`,
        # и такая развилка не зависит от интерфейса вообще. Вкладка
        # осталась подсказкой для пустого поля.
        from vpn.links import looks_like_link

        if looks_like_link(text) or (self._tab == TAB_LINKS and text.strip()):
            self._save_links(text)
            return

        try:
            profile = parse_any(text)
        except VpnConfigError as exc:
            self._error(str(exc))
            return
        except Exception as exc:
            log(f"Разбор конфигурации VPN: {exc}", "ERROR")
            self._error("Не удалось разобрать конфигурацию")
            return

        self._profiles = upsert_profile(self._profiles, profile)
        saved, message = save_profiles(_profiles_root(), self._profiles)
        if not saved:
            self._error(message)
            return

        self.input_edit.clear()

        # Куда попал профиль, решает не вкладка, а сам конфиг: наличие
        # параметров маскировки. Вставили ключ AmneziaWG во вкладке
        # WireGuard — переводим туда, где он теперь лежит. Иначе человек
        # сохраняет профиль и видит пустой список.
        target_tab = tab_for_profile(profile)
        moved = target_tab != self._tab
        if moved:
            self._tab = target_tab
            self.hint_label.setText(TAB_HINTS[target_tab])
            self.input_edit.setPlaceholderText(TAB_PLACEHOLDERS[target_tab])
            try:
                self.tabs.setCurrentItem(target_tab)
            except Exception as exc:
                log(f"Переключение вкладки VPN: {exc}", "DEBUG")

        self._reload_profiles(select_endpoint=profile.endpoint)

        message = f"Профиль сохранён: {display_name(profile)} ({profile.protocol})"
        if moved:
            message = f"{message}. Открыта вкладка {TAB_TITLES[target_tab]}"
        self._success(message)

    def _on_profile_changed(self, _index: int) -> None:
        self._update_details()

    def _on_toggle_connection(self) -> None:
        from vpn.tunnel import TunnelState
        from vpn.tunnel_runtime import check_client_files

        profile = self._current_profile()
        if profile is None:
            return

        available, files_message = check_client_files()
        if not available:
            self._error(files_message)
            return

        disconnecting = self._tunnel_state is TunnelState.CONNECTED

        def _run():
            # Обе операции запускают amneziawg.exe и ждут его до 30 секунд.
            from vpn.tunnel_runtime import connect, disconnect

            if disconnecting:
                return disconnect(tunnel_name=_profile_name(profile))
            return connect(profile, tunnel_name=_profile_name(profile))

        started = self._start_worker(
            "_tunnel_worker",
            _run,
            lambda status: self._on_tunnel_result(status, profile),
            self._on_tunnel_failed,
        )
        if started is None:
            return

        self.connect_btn.setEnabled(False)
        self.state_label.setText("Отключение..." if disconnecting else "Подключение...")

    def _on_tunnel_result(self, status, profile) -> None:
        from vpn.tunnel import TunnelState, describe_state

        self.connect_btn.setEnabled(True)

        if status.state is TunnelState.ERROR:
            self._error(status.message or "Не удалось подключиться")
        elif status.state is TunnelState.CONNECTED:
            self._success(f"Туннель поднят: {profile.endpoint}")
        elif status.state is TunnelState.DISCONNECTED:
            self._success("Туннель отключён")

        self._refresh_connection_state()
        if status.state is TunnelState.ERROR:
            self.state_label.setText(describe_state(TunnelState.ERROR))

    def _on_tunnel_failed(self, message: str) -> None:
        log(f"Переключение туннеля: {message}", "ERROR")
        self.connect_btn.setEnabled(True)
        self._error(f"Не удалось выполнить операцию: {message}")
        self._refresh_connection_state()

    def _on_check_server(self) -> None:
        profile = self._current_profile()
        if profile is None:
            return

        host = getattr(profile, "endpoint_host", "") or getattr(profile, "host", "")
        port = profile.endpoint_port

        stats = self._last_stats
        started = self._start_worker(
            "_ping_worker",
            lambda: check_server(host, port, stats=stats),
            self._on_check_server_ready,
            self._on_check_server_failed,
        )
        if started is None:
            return

        self.ping_label.setText("Проверяем...")
        self.ping_btn.setEnabled(False)

    def _on_check_server_ready(self, result) -> None:
        self.ping_btn.setEnabled(True)

        if result is None:
            self.ping_label.setText("Не удалось выполнить проверку")
            return

        tokens = get_theme_tokens()
        color = tokens.accent_hex if result.ok else tokens.fg_muted
        self.ping_label.setStyleSheet(f"QLabel {{ color: {color}; }}")
        self.ping_label.setText(f"{format_latency(result)} — {result.message}")

    def _on_check_server_failed(self, message: str) -> None:
        log(f"Проверка сервера VPN: {message}", "ERROR")
        self.ping_btn.setEnabled(True)
        self.ping_label.setText("Не удалось выполнить проверку")

    def _on_export(self) -> None:
        profile = self._current_profile()
        if profile is None:
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить конфигурацию",
            f"{display_name(profile)}.conf",
            "Конфигурация VPN (*.conf)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(to_conf_text(profile))
        except Exception as exc:
            self._error(f"Не удалось сохранить файл: {exc}")
            return
        self._success("Файл конфигурации сохранён")

    def _on_delete(self) -> None:
        profile = self._current_profile()
        if profile is None:
            return

        self._profiles = remove_profile(self._profiles, profile.endpoint)
        saved, message = save_profiles(_profiles_root(), self._profiles)
        if not saved:
            self._error(message)
            return
        self._reload_profiles()
        self._success("Профиль удалён")

    # ──────────────────────────────────────────────────────────────────
    # Сообщения
    # ──────────────────────────────────────────────────────────────────

    def _error(self, text: str) -> None:
        InfoBar.error(
            title="Ошибка",
            content=str(text),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=6000,
        )

    def _success(self, text: str) -> None:
        InfoBar.success(
            title="Готово",
            content=str(text),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=4000,
        )


__all__ = ["VpnPage"]
