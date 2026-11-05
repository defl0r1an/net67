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
from ui.widgets.fluent_item_tooltip import install_fluent_item_tooltips, set_fluent_item_tooltip

from vpn.parser import VpnConfigError, parse_any, to_conf_text
from vpn.tabs import (
    TAB_HINTS,
    TAB_INPUT_TITLES,
    TAB_LINKS,
    TAB_NOTES,
    TAB_ORDER,
    TAB_PLACEHOLDERS,
    TAB_SUBTITLES,
    TAB_TITLES,
    TAB_WARNINGS,
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


#: Высота списка серверов.
#:
#: Было 190 — шесть строк, и в подписке из двадцати пяти серверов
#: приходилось скроллить крошечное окошко. Стало вдвое больше: видно
#: десяток, и выбор перестал быть вознёй с полосой прокрутки.
SERVER_LIST_HEIGHT = 380

#: Наибольшая ширина списка серверов.
#:
#: Список тянулся во всю страницу — на широком мониторе это полоса в
#: полтора метра, где название сервера жмётся к левому краю, а справа
#: полтора экрана пустоты. Поэтому ширина ограничена.
#:
#: Прежние 560 оказались малы. В них не влезали ни длинные названия
#: («Великобритания N1 (YouTube без рекламы)»), ни заголовок группы с
#: трафиком, и обрезалось всё подряд: «GruVPN · 24 серверов · 314…».
#: Многоточие вместо остатка трафика — ровно то место, ради которого
#: трафик и показывают.
SERVER_LIST_MAX_WIDTH = 760

#: Наименьшая ширина списка. Ниже названия начинают обрезаться уже у
#: коротких стран, и список перестаёт быть списком серверов.
SERVER_LIST_MIN_WIDTH = 420

#: Высота значка флага в строке списка.
#:
#: Держится в паре с FLAG_HEIGHT из vpn/flags.py: там картинка
#: масштабируется, здесь под неё отводится место. Разойдутся — флаг
#: обрежется или повиснет в пустой рамке.
SERVER_LIST_ICON_HEIGHT = 24

#: Подписи кнопки сохранения — по одной на род профиля.
#:
#: Профиль AmneziaWG сохраняется настоящим файлом `.conf` формата
#: WireGuard. У сервера из ссылки такого файла нет: сохраняется
#: настройка ядра Xray, то есть JSON. Одна подпись на оба случая
#: обязательно врёт в одном из них.
EXPORT_CONF_TITLE = "Сохранить как .conf"
EXPORT_LINK_TITLE = "Сохранить настройки сервера"


def _profiles_root():
    from config.runtime_layout import APPLICATION_PATHS

    return APPLICATION_PATHS.settings_dir


def _profile_key(profile) -> tuple[str, str]:
    """Чем отличаем выбранный профиль от остальных.

    Одного адреса мало: в подписке у нескольких серверов бывает общий
    адрес и разные имена. Одного имени тоже мало — имена повторяются
    между подписками.
    """
    if profile is None:
        return ("", "")
    return (str(getattr(profile, "endpoint", "") or ""), _profile_name(profile))


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


#: В этой роли у строки-заголовка лежит адрес подписки. По ней же
#: заголовок отличается от строки сервера: у сервера роль пустая.
_GROUP_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 1

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
        #: Свёрнутые группы — по адресу подписки. Пустая строка значит
        #: группу «Мои серверы».
        self._collapsed_groups: set[str] = set()
        #: Кто выбран, независимо от того, видно ли его сейчас.
        #:
        #: Раньше выбор жил в строке списка, и свернуть группу с текущим
        #: сервером значило потерять выбор: строка исчезала, страница
        #: считала, что не выбрано ничего, и гасила кнопку подключения.
        #: Свернуть список — не то же самое, что передумать.
        self._selected_key: tuple[str, str] = ("", "")
        #: Какой профиль лежит в какой строке списка.
        #:
        #: Список делится на группы по подпискам, и строки-заголовки
        #: занимают в нём место наравне с серверами. Совпадение «номер
        #: строки = номер профиля» на этом кончилось, поэтому связь
        #: держится здесь: в строке-заголовке лежит -1.
        self._row_profiles: list[int] = []
        self._tab = TAB_ORDER[0]
        #: Замок на разделе подключения по ссылке снят.
        #:
        #: Его ставили, пока раздел дорабатывался: вкладка писала «Раздел
        #: в разработке» и открывалась десятью нажатиями. Со стороны это
        #: неотличимо от поломки — вкладка не переключается, и всё.
        #: Правило и его проверки остались в vpn/tabs.py: понадобится
        #: закрыть снова — достаточно поставить здесь False.
        self._links_unlocked = True
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

        from vpn.ui.experience import VpnExperience
        self._closing = False
        self._experience = VpnExperience(self, _profiles_root())
        self._build_ui()
        self._sync_warning_label(self._tab)
        self._sync_refresh_button()
        self._clear_stale_system_proxy()
        self._clear_stale_tunnel()
        self._reload_profiles()

    def _clear_stale_tunnel(self) -> None:
        """Снимает следы туннеля, оставшиеся от прошлого запуска.

        Рядом с уборкой системного прокси и по той же причине: сеанс,
        который не попрощался, оставляет за собой работающий tun2socks и
        постоянный маршрут в исчезнувший шлюз.

        Место не идеальное. Уборка случается при построении страницы VPN,
        то есть только если человек на неё зашёл, — а брошенный процесс
        мешает и тому, кто туда не заходит: он держит файлы поставки и
        не даёт обновиться. Правильное место — стартовый контур
        приложения, но там уборки прокси тоже нет, и разносить их по
        разным местам хуже, чем оставить обе здесь.
        """
        try:
            from vpn.link_runtime import clear_stale_tunnel

            clear_stale_tunnel()
        except Exception as exc:
            log(f"Проверка следов туннеля при запуске: {exc}", "DEBUG")

    def _clear_stale_system_proxy(self) -> None:
        """Снимает прокси, оставшийся от прошлого запуска.

        Приложение можно закрыть не по-людски — снять задачу, обесточить
        машину. Тогда в реестре остаётся указание ходить через порт,
        которого больше нет, и Windows слушается: сайты перестают
        открываться у всей системы, а виноватым выглядит net67.
        """
        try:
            from vpn import system_proxy
            from vpn.link_runtime import local_proxy_address

            if system_proxy.clear_stale(local_proxy_address()):
                log("Снят системный прокси, оставшийся от прошлого запуска", "INFO")
        except Exception as exc:
            log(f"Проверка системного прокси при запуске: {exc}", "DEBUG")

    # ──────────────────────────────────────────────────────────────────
    # Фоновые вызовы
    # ──────────────────────────────────────────────────────────────────

    def _start_worker(self, attr: str, call, on_done, on_failed=None):
        from vpn.ui.workers import VpnJob
        if getattr(self, "_closing", False) or getattr(self, attr, None) is not None:
            return None
        job = VpnJob(self, attr, call, on_done, on_failed)
        setattr(self, attr, job.worker)
        job.worker.start()
        return job.worker

    # ──────────────────────────────────────────────────────────────────
    # Построение
    # ──────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        from vpn.ui.page_build import build_vpn_page
        build_vpn_page(self)

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

    def _wireguard_profiles(self) -> list:
        """Только конфигурации WireGuard — то, что живёт в файле профилей.

        `self._profiles` собран для показа: в нём и конфигурации, и
        серверы из ссылок, потому что список на экране один. Файл же у
        каждого рода свой, и отдавать этот общий список в `save_profiles`
        нельзя — ссылки записывались в файл конфигураций и возвращались
        оттуда пустыми строчками «Профиль без имени».
        """
        from vpn.tabs import TAB_AMNEZIA, tab_for_profile

        return [p for p in self._profiles if tab_for_profile(p) == TAB_AMNEZIA]

    def _refill_combo(self, *, select_endpoint: str = "") -> None:
        """Наполняет список профилями активной вкладки.

        Хранилище общее: вкладка решает только, что показать. Поэтому
        фильтруем при показе, а не режем файл профилей на два.
        """
        self._visible_profiles = profiles_for_tab(self._profiles, self._tab)

        motion = getattr(self, "_list_motion", None)
        if motion is not None:
            # Номера строк после пересборки указывают уже на другие строки.
            motion.reset()
        self.profile_combo.blockSignals(True)
        self.profile_list.blockSignals(True)
        self.profile_combo.clear()
        self.profile_list.clear()
        # В списке — с флагом вместо двухбуквенного сокращения: «GB» надо
        # вспоминать, флаг узнаётся сразу. В выпадающем оставляем как
        # есть: его не видно, он живёт ради старых обработчиков.
        #
        # Картинка предпочтительнее символов: пара символов-индикаторов
        # рисуется флагом не везде, Windows их не поддерживает и рисует
        # две буквы в рамочках. Есть картинка — берём её, нет — остаётся
        # символьный вариант.
        from PyQt6.QtWidgets import QListWidgetItem

        from vpn.flags import flag_icon, strip_country_prefix

        for profile in self._visible_profiles:
            self.profile_combo.addItem(display_name(profile))

        self._row_profiles = []
        for key, header, members in self._grouped_profiles():
            collapsed = key in self._collapsed_groups
            if header:
                self.profile_list.addItem(self._group_header_item(key, header, collapsed))
                self._row_profiles.append(-1)

            if collapsed:
                continue

            for position in members:
                profile = self._visible_profiles[position]
                name = display_name(profile)
                icon = flag_icon(name)
                if icon is None:
                    item = QListWidgetItem(name)
                    import qtawesome as qta
                    from ui.theme import token_to_qcolor
                    item.setIcon(qta.icon("fa5s.globe", color=token_to_qcolor(get_theme_tokens().fg_muted)))
                else:
                    item = QListWidgetItem(strip_country_prefix(name))
                    item.setIcon(icon)
                self._experience.decorate_item(item, profile)
                self.profile_list.addItem(item)
                self._row_profiles.append(position)

        index = -1
        if select_endpoint:
            for position, profile in enumerate(self._visible_profiles):
                if profile.endpoint == select_endpoint:
                    index = position
                    break
        if index < 0:
            # Список перестраивается на каждое сворачивание группы, и
            # сбрасывать выбор на первый сервер каждый раз значило бы
            # менять сервер за человека.
            index = self._index_for_key(self._selected_key)
        if index < 0 and self._visible_profiles:
            index = 0

        if 0 <= index < len(self._visible_profiles):
            self.profile_combo.setCurrentIndex(index)
            self._selected_key = _profile_key(self._visible_profiles[index])
            row = self._row_for_profile(index)
            # Строки может не быть: выбранный сервер спрятан в свёрнутой
            # группе. Подсветки тогда нет, но выбор остаётся, и кнопка
            # подключения продолжает работать.
            self.profile_list.setCurrentRow(row if row >= 0 else -1)
        self.profile_combo.blockSignals(False)
        self.profile_list.blockSignals(False)
        self._sync_tab_labels()
        self._update_details()

    def _index_for_key(self, key: tuple[str, str]) -> int:
        """Где сейчас лежит профиль с этим ключом. -1 — нигде."""
        if not any(key):
            return -1
        for position, profile in enumerate(self._visible_profiles):
            if _profile_key(profile) == key:
                return position
        return -1

    # ── группировка списка ────────────────────────────────────────────

    def _group_header_item(self, key: str, text: str, collapsed: bool):
        """Строка-заголовок группы: нажимается, но не выбирается.

        Флаг ровно один — «включён». Без `ItemIsSelectable` щелчок по
        заголовку не сдвигает выбор сервера и стрелки его перескакивают,
        а сигнал о нажатии всё равно приходит — по нему группа и
        сворачивается.

        Раньше стояло `NoItemFlags`, и заголовок был мёртвым: нажатия по
        выключенным элементам Qt не отдаёт вовсе. Оттого сворачивание и
        «не работало».
        """
        # QtGui подтягивается здесь, а не наверху файла: модуль страницы
        # читают проверки, которым окно не нужно, а QtGui тянет за собой
        # графические библиотеки системы и падает там, где их нет.
        from PyQt6.QtCore import QSize
        from PyQt6.QtCore import Qt as _Qt
        from PyQt6.QtWidgets import QListWidgetItem

        from ui.theme import token_to_qcolor

        tokens = get_theme_tokens()

        item = QListWidgetItem(f"{'▸' if collapsed else '▾'}   {text}")
        item.setFlags(_Qt.ItemFlag.ItemIsEnabled)
        item.setData(_GROUP_KEY_ROLE, key)

        # Заголовок группы — не строка списка, а полка над строками.
        # Поэтому он крупнее соседей, а не только жирнее: одной жирности
        # мало, когда под ним два десятка пунктов такого же размера.
        font = item.font()
        font.setBold(True)
        size = font.pointSizeF()
        if size > 0:
            font.setPointSizeF(size + 0.5)
        item.setFont(font)

        # Цвет получается разбором токена, а не QColor(строка).
        #
        # Токены темы написаны для таблиц стилей и выглядят как
        # `rgba(255, 255, 255, 0.65)`. QColor такую запись не понимает,
        # молчит и отдаёт недействительный цвет, который рисуется чёрным.
        # На светлой теме это сходило с рук, на тёмной заголовок
        # подписки исчезал совсем: чёрный по чёрному.
        #
        # Берём `fg`, а не `fg_muted`: приглушать стоит подробности, а не
        # название подписки с остатком трафика и сроком. Ради них сюда и
        # смотрят.
        item.setForeground(token_to_qcolor(tokens.fg))

        # Тонкая подложка вместо разделительной черты: она отделяет
        # группу от предыдущей, не добавляя в список лишний элемент.
        item.setBackground(token_to_qcolor(tokens.surface_bg))

        # Воздух сверху и снизу. Без него полка липнет к первой строке
        # под собой, и разделение пропадает.
        hint = item.sizeHint()
        if hint.isValid():
            item.setSizeHint(QSize(hint.width(), hint.height() + 14))

        set_fluent_item_tooltip(item, "Нажмите, чтобы свернуть или развернуть группу")
        return item

    def _on_list_item_clicked(self, item) -> None:
        """Щелчок по заголовку сворачивает и разворачивает группу."""
        if item is None:
            return
        key = item.data(_GROUP_KEY_ROLE)
        if key is None:
            return  # строка сервера, а не заголовок

        key = str(key)
        collapsing = key not in self._collapsed_groups
        # Состояние меняем сразу, а не в конце движения: пересоберись список
        # по другой причине посреди ухода — он соберётся уже свёрнутым.
        self._collapsed_groups.symmetric_difference_update({key})
        motion = getattr(self, "_list_motion", None)
        if collapsing:
            header_row = self.profile_list.row(item)
            item.setText(item.text().replace("▾", "▸", 1))
            if motion is not None and motion.leave(self._group_member_rows(header_row), on_finished=self._refill_combo):
                return
            self._refill_combo()
            return
        self._refill_combo()
        if motion is not None:
            motion.appear(self._group_member_rows(self._group_header_row(key)))

    def _group_header_row(self, key: str) -> int:
        """Строка заголовка группы с этим ключом; -1 — такой нет."""
        for row in range(self.profile_list.count()):
            item = self.profile_list.item(row)
            if item is not None and item.data(_GROUP_KEY_ROLE) == key:
                return row
        return -1

    def _group_member_rows(self, header_row: int) -> list[int]:
        """Строки серверов под заголовком — до следующего заголовка."""
        if header_row < 0:
            return []
        rows = []
        for row in range(header_row + 1, len(self._row_profiles)):
            if self._row_profiles[row] < 0:
                break
            rows.append(row)
        return rows

    def _grouped_profiles(self):
        """Делит видимые профили на группы по подпискам."""
        from vpn.subscriptions import group_by_subscription, load_subscriptions

        try:
            subscriptions = load_subscriptions(_profiles_root())
        except Exception:
            # Подписки — сведения вспомогательные: без них список просто
            # останется одной группой, ронять из-за них страницу нельзя.
            subscriptions = []

        groups = group_by_subscription(self._visible_profiles, subscriptions)
        filtered = []
        for key, header, members in groups:
            accepted = [position for position in members
                        if self._experience.accepts(self._visible_profiles[position])]
            if accepted:
                filtered.append((key, header, accepted))
        return filtered

    def _row_for_profile(self, index: int) -> int:
        """Строка списка, в которой лежит профиль с этим номером."""
        try:
            return self._row_profiles.index(int(index))
        except ValueError:
            return -1

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
        self.hint_label.setText("Вставьте ссылку на сервер, подписку, ключ vpn:// или текст .conf.")
        self.input_title_label.setText(TAB_INPUT_TITLES[tab])
        section = getattr(self, "add_section", None)
        if section is not None:
            section.set_title("Ключ, подписка или конфигурация")
        subtitle = getattr(self, "subtitle_label", None)
        if subtitle is not None:
            subtitle.setText(TAB_SUBTITLES[tab])
        self.input_edit.setPlaceholderText("vless://, trojan://, ss://, https://, vpn:// или [Interface]…")
        note = getattr(self, "note_label", None)
        if note is not None:
            note.setText(TAB_NOTES[tab])
        self._sync_warning_label(tab)
        self._sync_refresh_button()
        self._refill_combo()
        # Новая вкладка — новое содержимое: оно приходит волной, а не
        # подменяется за кадр (ui/reveal.py, vpn/ui/server_list_motion.py).
        motion = getattr(self, "_list_motion", None)
        if motion is not None and self.isVisible():
            motion.appear(range(self.profile_list.count()))
        if self.isVisible():
            self.profile_list.viewport().update()

    def _sync_warning_label(self, tab: str) -> None:
        self.warning_label.setText(TAB_WARNINGS.get(tab, ""))
        self.warning_label.hide()

    def _show_block(self, widget) -> None:
        from ui.reveal import cancel_dismiss, reveal_widgets

        cancel_dismiss(widget)
        # Слой движения есть — строка как раз уходила: проявляем её с того
        # места, где застали, а не с нуля.
        moving = widget.isHidden() or widget.graphicsEffect() is not None
        widget.setVisible(True)
        if moving and self.isVisible():
            reveal_widgets([widget])

    def _hide_block(self, widget) -> None:
        from ui.reveal import cancel_dismiss, dismiss_row

        if widget.isHidden():
            return
        if self.isVisible() and dismiss_row(widget, on_finished=lambda w=widget: cancel_dismiss(w, keep_hidden=True)):
            return
        widget.setVisible(False)

    def _sync_refresh_button(self) -> None:
        """Подписки бывают только у серверов по ссылке.

        На вкладке AmneziaWG обновлять нечего: там конфигурации, которые
        человек приносит файлом. Кнопка, которая на половине вкладок
        отвечает «нет сохранённых подписок», — это кнопка-обманка.
        """
        button = getattr(self, "refresh_subs_btn", None)
        if button is None:
            return
        wanted = self._tab == TAB_LINKS
        if not self.isVisible():
            button.setVisible(wanted)
            return
        from ui.reveal import conceal_widgets, reveal_widgets

        if wanted:
            # Кнопка могла как раз уходить — тогда проявление подхватит её
            # с того места, где застало, и уход не спрячет её в конце.
            moving = button.isHidden() or button.graphicsEffect() is not None
            button.setVisible(True)
            if moving:
                reveal_widgets([button])
        elif not button.isHidden() and not conceal_widgets([button]):
            button.setVisible(False)

    def _current_profile(self):
        # Спрашиваем список: он на экране, и именно в нём человек выбрал
        # строку. Выпадающий держим в согласии с ним ради обработчиков,
        # которые на него смотрят.
        row = self.profile_list.currentRow()
        index = -1
        if 0 <= row < len(self._row_profiles):
            index = self._row_profiles[row]
        if index < 0:
            # Строки нет — сервер спрятан в свёрнутой группе. Выбор от
            # этого не пропал, он просто не подсвечен.
            index = self._index_for_key(self._selected_key)
        if index >= 0 and index != self.profile_combo.currentIndex():
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
    _WORKER_ATTRS = ("_status_worker", "_ping_worker", "_tunnel_worker", "_subscription_worker")

    def cleanup(self) -> None:
        self._sync_stats_timer(False)
        self._stop_workers()
        super().cleanup()

    def _stop_workers(self) -> None:
        self._closing = True
        self._experience.close()
        for attr in self._WORKER_ATTRS:
            worker = getattr(self, attr, None)
            setattr(self, attr, None)
            if worker is not None:
                job = getattr(worker, "_vpn_job", None)
                if job is not None:
                    job.detach()

    def _sync_connect_button(self, *, connected: bool = False, busy: bool = False,
                             disconnecting: bool = False) -> None:
        """Приводит круглую кнопку к текущему состоянию соединения.

        Кнопка и подпись под ней ведутся вместе: подпись повторяет то,
        что кнопка означает сейчас, и человеку не приходится гадать по
        цвету круга.
        """
        button = getattr(self, "connect_button", None)
        if button is None:
            return

        from vpn.ui.connect_button import VpnButtonState

        if busy:
            state = VpnButtonState.DISCONNECTING if disconnecting else VpnButtonState.CONNECTING
        elif connected:
            state = VpnButtonState.CONNECTED
        else:
            state = VpnButtonState.DISCONNECTED

        button.set_state(state)
        caption = getattr(self, "connect_caption", None)
        if caption is not None:
            caption.setText(button.title())

    def _refresh_connection_state(self) -> None:
        if self._closing or self._experience.operation is not None:
            return
        profile = self._current_profile()
        tunnel_name = _profile_name(profile) if profile else ""
        generation = self._experience.generation

        def collect():
            from vpn.link_runtime import active_connection, is_connected
            from vpn.tunnel import TunnelState
            from vpn.tunnel_runtime import get_stats, get_status, active_connection as active_tunnel
            from vpn.operation import connection_marker
            marker = connection_marker()
            active, scope = active_connection()
            link_connected = is_connected()
            if link_connected:
                state, stats = TunnelState.DISCONNECTED, None
            else:
                tunnel_profile, active_name = active_tunnel()
                name = active_name or tunnel_name
                status = get_status(name)
                state = status.state if status else TunnelState.DISCONNECTED
                stats = get_stats(name) if state is TunnelState.CONNECTED else None
                active = tunnel_profile or profile
            return state, stats, active, scope, link_connected, generation, marker

        self._start_worker("_status_worker", collect, self._on_connection_state_ready,
                           lambda message: log(f"Состояние VPN: {message}", "DEBUG"))

    def _on_connection_state_ready(self, payload) -> None:
        self._experience.status_ready(payload)

    def _apply_page_theme(self, tokens=None, force=False) -> None:
        if not hasattr(self, "scope_label") or self._closing:
            return
        tokens = tokens or get_theme_tokens()
        self.scope_label.setStyleSheet(f"QLabel {{ color: {tokens.fg_muted}; }}")
        self._experience.sync()

    def _apply_export_button_label(self, profile) -> None:
        """Подписывает кнопку сохранения под выбранный сервер.

        Кнопка одна, а сохраняет она разное. У профиля AmneziaWG это
        настоящий файл `.conf` — формат WireGuard, его понимает любой
        клиент. У сервера из ссылки такого файла не бывает вовсе: там нет
        ни приватного ключа, ни адреса в туннеле, всё это задаёт ядро
        Xray само. Сохраняется настройка ядра, то есть JSON.

        Подпись «Сохранить как .conf» на вкладке со ссылками поэтому
        просто врала: нажимаешь — получаешь .json. Сначала я поправил то,
        что кнопка делает, и забыл про то, что она обещает.
        """
        from vpn.link_runtime import is_link_profile

        try:
            link = profile is not None and is_link_profile(profile)
        except Exception:
            link = False

        self.export_btn.setText(EXPORT_LINK_TITLE if link else EXPORT_CONF_TITLE)

    def _update_details(self) -> None:
        profile = self._current_profile()
        has_profile = profile is not None

        for button in (self.ping_btn, self.export_btn, self.delete_btn):
            button.setEnabled(has_profile)
        self.connect_button.setEnabled(has_profile)

        self._apply_export_button_label(profile)

        self._experience.sync()
        self._refresh_connection_state()

        if not has_profile:
            # Общее «Профили не добавлены» врало: профили могли быть, но
            # на соседней вкладке.
            self.details_label.setText(empty_text(self._tab))
            return

        # Поля тут разные у двух родов профилей, и у сервера из ссылки
        # половины из них нет вовсе: ни адреса в туннеле, ни DNS — их
        # задаёт ядро Xray само. Обращение напрямую роняло страницу на
        # каждом выборе сервера и на каждой проверке.
        protocol = getattr(profile, "protocol", "") or getattr(profile, "protocol_title", "")
        parts = [f"Протокол: {protocol}", f"Сервер: {profile.endpoint or 'не указан'}"]

        address = getattr(profile, "address", "")
        if address:
            parts.append(f"Адрес в туннеле: {address}")

        dns = getattr(profile, "dns", "")
        if dns:
            parts.append(f"DNS: {dns}")

        usage = self._subscription_line(profile)
        if usage:
            parts.append(usage)

        self.details_label.setText("\n".join(parts))

    def _subscription_line(self, profile) -> str:
        """Остаток трафика подписки, из которой пришёл этот сервер.

        В заголовке группы он тоже есть, но заголовок остаётся вверху и
        уезжает за край при прокрутке. Здесь — рядом с выбранным
        сервером, где на него и смотрят перед подключением.
        """
        source = str(getattr(profile, "source", "") or "").strip()
        if not source:
            return ""

        try:
            from vpn.subscriptions import find, load_subscriptions

            info = find(load_subscriptions(_profiles_root()), source)
        except Exception:
            return ""

        if info is None:
            return ""

        usage = info.usage.describe()
        if not usage:
            return f"Подписка: {info.display_title()}"
        return f"Подписка: {info.display_title()} — {usage}"

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
        from vpn.subscription import load_subscription_with_info, looks_like_subscription_url

        raw = str(text or "").strip()

        if looks_like_subscription_url(raw):
            self.import_status_label.setText("Загружаем подписку…")
            self.import_status_label.show()
            self.save_btn.setEnabled(False)
            started = self._start_worker(
                "_subscription_worker",
                lambda url=raw: load_subscription_with_info(url),
                self._on_subscription_loaded,
                self._on_subscription_failed,
            )
            if started is None:
                self._error("Подписка уже загружается")
            return

        added, errors = parse_subscription(raw)
        self._apply_links(added, errors)

    def _on_subscription_loaded(self, result) -> None:
        self.save_btn.setEnabled(True)
        self.import_status_label.hide()
        # Форма результата зависит от того, кто загружал: добавление
        # подписки отдаёт ещё и сведения о ней, обновление — тоже.
        if isinstance(result, tuple) and len(result) == 3:
            added, errors, info = result
        else:
            added, errors, info = (*result, None)

        self._refresh_connection_state()

        if info is not None:
            self._remember_subscription(info)
            # Серверы помечаем подпиской: по этой метке список делится
            # на группы, и по ней же подписка обновляется целиком.
            import dataclasses

            added = [dataclasses.replace(p, source=info.url) for p in added]

        self._apply_links(added, errors, sources=[info.url] if info is not None else None)

    def _remember_subscription(self, info) -> None:
        """Сохраняет подписку: адрес, имя, трафик, время обновления."""
        from vpn.subscriptions import load_subscriptions, save_subscriptions, upsert

        root = _profiles_root()
        try:
            items = upsert(load_subscriptions(root), info)
            saved, message = save_subscriptions(root, items)
            if not saved:
                log(f"Подписка не сохранена: {message}", "⚠ WARNING")
        except Exception as exc:
            # Подписка — сведения вспомогательные: серверы уже добавлены
            # и работают без неё. Ронять из-за этого добавление нельзя.
            log(f"Подписка не сохранена: {exc}", "⚠ WARNING")

    def _on_refresh_subscriptions(self) -> None:
        """Перезагружает все подписки и обновляет списки серверов."""
        from vpn.subscriptions import load_subscriptions

        subscriptions = load_subscriptions(_profiles_root())
        if not subscriptions:
            self._error("Нет сохранённых подписок — добавьте ссылку на подписку")
            return

        urls = [item.url for item in subscriptions]

        def _reload():
            from vpn.subscription import load_subscription_with_info

            collected, problems, infos = [], [], []
            for url in urls:
                from PyQt6.QtCore import QThread
                if QThread.currentThread().isInterruptionRequested():
                    break
                profiles, errors, info = load_subscription_with_info(url)
                problems.extend(errors)
                if info is not None:
                    infos.append(info)
                collected.extend(
                    __import__("dataclasses").replace(p, source=url) for p in profiles
                )
            return collected, problems, infos

        started = self._start_worker(
            "_subscription_worker",
            _reload,
            self._on_subscriptions_refreshed,
            self._on_subscription_failed,
        )
        if started is None:
            self._error("Подписка уже загружается")
            return

        self.state_label.setText(f"Обновляем подписки ({len(urls)})...")

    def _on_subscriptions_refreshed(self, result) -> None:
        from vpn.link_store import load_links, replace_source, save_links

        added, errors, infos = result
        for info in infos:
            self._remember_subscription(info)

        if not added:
            self._error(errors[0] if errors else "Подписки не вернули ни одного сервера")
            return

        root = _profiles_root()
        existing, _load_errors = load_links(root)
        # Именно замена: сервер, убранный из подписки, должен исчезнуть и
        # у нас, иначе в списке копится мёртвое.
        merged = replace_source(existing, added, [info.url for info in infos])

        saved, message = save_links(root, merged)
        if not saved:
            self._error(message)
            return

        self._reload_profiles()

        if errors:
            self._error(f"Серверов обновлено: {len(added)}. Не разобрано: {len(errors)}")
            return
        self._success(f"Подписки обновлены: серверов {len(added)}")

    def _on_subscription_failed(self, message: str) -> None:
        self.save_btn.setEnabled(True)
        self.import_status_label.setText("Не удалось загрузить. Попробуйте ещё раз.")
        self.import_status_label.show()
        self._refresh_connection_state()
        self._error(f"Не удалось загрузить подписку: {message}")

    def _apply_links(self, added, errors, *, sources=None) -> None:
        """Кладёт разобранные серверы в хранилище и обновляет список.

        `sources` — адреса подписок, серверы которых пришли заново. Их
        прежние серверы выбрасываются: вставить ту же ссылку второй раз
        человек может только чтобы обновить список, а не чтобы получить
        рядом со свежими тридцатью ещё тридцать вчерашних.
        """
        from vpn.link_store import load_links, merge, replace_source, save_links

        if not added:
            self._error(errors[0] if errors else "Не удалось разобрать ссылку")
            return

        root = _profiles_root()
        existing, _load_errors = load_links(root)
        if sources:
            merged = replace_source(existing, added, sources)
        else:
            merged = merge(existing, added)

        saved, message = save_links(root, merged)
        if not saved:
            self._error(message)
            return

        self.input_edit.clear()
        self.add_section.hide()
        if self._tab != TAB_LINKS:
            self.tabs.setCurrentItem(TAB_LINKS)
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

        is_config = text.lstrip().casefold().startswith("vpn://") or "[interface]" in text.casefold()
        if looks_like_link(text) or (self._tab == TAB_LINKS and text.strip() and not is_config):
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
        saved, message = save_profiles(_profiles_root(), self._wireguard_profiles())
        if not saved:
            self._error(message)
            return

        self.input_edit.clear()
        self.add_section.hide()

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

    def _export_link_config(self, profile) -> None:
        """Сохраняет конфигурацию ядра Xray для выбранного сервера."""
        import json

        from vpn.xray import build_config

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить конфигурацию сервера",
            f"{_profile_name(profile) or 'server'}.json",
            "Конфигурация Xray (*.json)",
        )
        if not path:
            return

        try:
            text = json.dumps(build_config(profile), ensure_ascii=False, indent=2)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except Exception as exc:
            self._error(f"Не удалось сохранить файл: {exc}")
            return

        self._success(f"Конфигурация сохранена: {path}")

    def _on_profile_changed(self, _index: int) -> None:
        self._selected_key = _profile_key(self._current_profile())
        self._update_details()
        from vpn.link_runtime import is_link_profile
        from vpn.view_state import profile_id
        experience = self._experience
        profile = self._current_profile()
        if (profile is not None and experience.active is not None and experience.connected
                and is_link_profile(profile) and is_link_profile(experience.active)
                and profile_id(profile) != profile_id(experience.active)):
            self._switch_link_server(profile)

    def _switch_link_server(self, profile) -> None:
        self._experience.start(profile)

    def _on_tun_mode_toggled(self, enabled: bool) -> None:
        """Переключает охват соединения.

        На лету не переключаем: туннель поднимается поверх уже
        работающего ядра и правит маршруты, а менять их под идущим
        соединением — верный способ оборвать его на середине. Настройка
        применится при следующем подключении, о чём и говорим.
        """
        from vpn.link_runtime import is_connected, set_tun_mode_enabled
        from vpn.tun_mode import check_available

        if enabled:
            available, message = check_available()
            if not available:
                self.tun_mode_toggle.setChecked(False, block_signals=True)
                self._error(message)
                return

        set_tun_mode_enabled(bool(enabled))
        self._experience.sync()

        if is_connected():
            self._success(
                "Режим сохранён. Он применится при следующем подключении — "
                "переключите сервер или отключитесь и подключитесь снова."
            )

    def _on_toggle_connection(self) -> None:
        self._experience.toggle()

    def _toggle_link_connection(self, profile) -> None:
        self._experience.toggle()

    def _on_link_result(self, result) -> None:
        self._experience.finished(result)

    def _on_tunnel_result(self, status, profile) -> None:
        self._experience.finished(status)

    def _on_tunnel_failed(self, message: str) -> None:
        self._experience.failed(message)

    def _on_check_server(self) -> None:
        self._experience.check()

    def _on_check_server_ready(self, result) -> None:
        self._experience.checked(result)

    def _on_check_server_failed(self, message: str) -> None:
        self._experience.check_failed(message)

    def _on_export(self) -> None:
        profile = self._current_profile()
        if profile is None:
            return

        # У сервера из ссылки никакого .conf не бывает: это формат
        # WireGuard, с приватным ключом и адресом в туннеле. Сохранять
        # его для ссылки было нечем, и кнопка стояла просто так.
        #
        # Для ссылки сохраняем то, что имеет смысл, — конфигурацию ядра
        # Xray. Её можно скормить xray напрямую, показать в поддержку
        # или сравнить с рабочей.
        from vpn.link_runtime import is_link_profile

        if is_link_profile(profile):
            self._export_link_config(profile)
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

        from vpn.link_runtime import is_link_profile
        from vpn.view_state import profile_id
        if is_link_profile(profile):
            from vpn.link_store import load_links, save_links
            links, errors = load_links(_profiles_root())
            if errors:
                self._error("Не удалось прочитать список серверов; удаление отменено")
                return
            saved, message = save_links(_profiles_root(), [item for item in links
                                        if profile_id(item) != profile_id(profile)])
        else:
            remaining = remove_profile(self._wireguard_profiles(), profile.endpoint)
            saved, message = save_profiles(_profiles_root(), remaining)
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
