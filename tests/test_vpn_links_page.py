"""Страница VPN: ссылка разбирается своим разборщиком, серверы — списком.

Обе проверки родились из снимка экрана.

На вкладке «VPN» человек вставил ссылку на подписку и получил ответ
«Поддерживаются только ключи, начинающиеся с vpn://». Ошибка была
честной: её и правда выдал разборщик WireGuard, потому что разборщик был
один на обе вкладки.

Второе — выбор сервера выпадающим списком. У подписки бывает тридцать
серверов, и выбирать из них по одному, каждый раз раскрывая список, —
мучение. Просьба была прямой: список, а не выпадающий.
"""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class ParserRoutingTests(unittest.TestCase):
    """Разборщик выбирается вкладкой."""

    def setUp(self) -> None:
        from vpn.ui import page

        self.source = inspect.getsource(page.VpnPage._on_save_profile)

    def test_links_tab_goes_to_the_link_parser(self) -> None:
        self.assertIn("TAB_LINKS", self.source)
        self.assertIn("_save_links", self.source)

    def test_link_branch_comes_before_the_wireguard_parser(self) -> None:
        """Иначе ссылка успевает получить чужую ошибку."""
        self.assertLess(
            self.source.index("_save_links"), self.source.index("parse_any")
        )

    def test_subscription_is_parsed_whole(self) -> None:
        """Ссылка на подписку — это список серверов, а не один сервер."""
        from vpn.ui import page

        source = inspect.getsource(page.VpnPage._save_links)

        self.assertIn("parse_subscription", source)

    def test_partial_failures_are_reported(self) -> None:
        """Потерять три сервера из тридцати и промолчать нельзя.

        Складывание в хранилище переехало в _apply_links: у подписки по
        ссылке результат приходит из потока, и общий на оба пути шаг
        оказался удобнее продублированного.
        """
        from vpn.ui import page

        source = inspect.getsource(page.VpnPage._apply_links)

        self.assertIn("errors", source)
        self.assertIn("Не разобрано", source)

    def test_links_are_merged_not_replaced(self) -> None:
        """Вторая подписка не должна стирать первую."""
        from vpn.ui import page

        source = inspect.getsource(page.VpnPage._apply_links)

        self.assertIn("merge", source)


class ServerListTests(unittest.TestCase):
    def test_page_shows_a_list_not_a_dropdown(self) -> None:
        from vpn.ui import page

        source = inspect.getsource(page.VpnPage._build_ui)

        self.assertIn("QListWidget", source)
        self.assertIn("profile_list", source)

    def test_dropdown_stays_hidden_for_the_old_handlers(self) -> None:
        """На него смотрят существующие обработчики страницы.

        Переписывать их все ради смены вида значило бы трогать логику
        вместе с оформлением.
        """
        from vpn.ui import page

        source = inspect.getsource(page.VpnPage._build_ui)

        self.assertIn("self.profile_combo.hide()", source)

    def test_selection_is_read_from_the_list(self) -> None:
        """В списке человек и выбирает строку — спрашивать надо его."""
        from vpn.ui import page

        source = inspect.getsource(page.VpnPage._current_profile)

        self.assertIn("profile_list.currentRow()", source)

    def test_list_height_leaves_room_for_the_rest_of_the_page(self) -> None:
        from vpn.ui.page import SERVER_LIST_HEIGHT

        self.assertLessEqual(SERVER_LIST_HEIGHT, 260)

    def test_list_is_styled_by_the_shell(self) -> None:
        """Иначе он выглядел бы системным списком Windows среди своих карточек."""
        from shell.theme import DARK, shell_qss

        qss = shell_qss(DARK)

        self.assertIn("QListWidget#net67ServerList", qss)
        self.assertIn("net67ServerList::item:selected", qss)


class StorageTests(unittest.TestCase):
    def test_page_reads_both_stores(self) -> None:
        """Конфиги поднимает служба, ссылки — ядро Xray. Список один."""
        from vpn.ui import page

        source = inspect.getsource(page.VpnPage._reload_profiles)

        self.assertIn("load_profiles", source)
        self.assertIn("load_links", source)

    def test_broken_records_go_to_the_log_not_to_a_popup(self) -> None:
        """Ошибка в файле не повод не открыть страницу."""
        from vpn.ui import page

        source = inspect.getsource(page.VpnPage._reload_profiles)

        self.assertIn("log(", source)


if __name__ == "__main__":
    unittest.main()
