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

    def test_list_is_tall_enough_to_choose_from(self) -> None:
        """Подписка приносит десятки серверов, и выбирать надо глазами.

        Потолок был 260 — шесть строк. На подписке из двадцати пяти это
        превращалось в возню с полосой прокрутки в крошечном окошке.
        Нижняя граница теперь важнее верхней: список должен показывать
        хотя бы десяток.

        Верхнюю оставляем, но с запасом: страница не должна становиться
        одним сплошным списком, под ним ещё кнопки и подробности.
        """
        from vpn.ui.page import SERVER_LIST_HEIGHT

        self.assertGreaterEqual(SERVER_LIST_HEIGHT, 300)
        self.assertLessEqual(SERVER_LIST_HEIGHT, 460)

    def test_list_is_styled_by_the_shell(self) -> None:
        """Иначе он выглядел бы системным списком Windows среди своих карточек."""
        from shell.theme import DARK, shell_qss

        qss = shell_qss(DARK)

        self.assertIn("QListWidget#net67ServerList", qss)
        self.assertIn("net67ServerList::item:selected", qss)


class ExportButtonLabelTests(unittest.TestCase):
    """Кнопка сохранения обязана обещать то, что делает.

    Она одна на два рода профилей. У AmneziaWG сохраняется настоящий
    `.conf` формата WireGuard; у сервера из ссылки такого файла нет
    вовсе — сохраняется настройка ядра Xray, то есть JSON.

    Сначала я поправил поведение и оставил прежнюю подпись: человек
    нажимал «Сохранить как .conf» и получал .json. Заметил это он, а не
    я, — поэтому здесь проверка.
    """

    class _Button:
        def __init__(self) -> None:
            self.text_value = ""

        def setText(self, value: str) -> None:  # noqa: N802 (Qt API)
            self.text_value = str(value)

    def _label_for(self, profile) -> str:
        """Зовём метод несвязанным, на заглушке вместо страницы.

        Настоящую VpnPage здесь не построить: это QWidget, ему нужны
        приложение Qt и десяток зависимостей страницы. А правило
        касается двух строк и одной кнопки.
        """
        from types import SimpleNamespace

        from vpn.ui.page import VpnPage

        stub = SimpleNamespace(export_btn=self._Button())
        VpnPage._apply_export_button_label(stub, profile)
        return stub.export_btn.text_value

    def test_link_profile_does_not_promise_a_conf_file(self) -> None:
        from vpn.ui.page import EXPORT_LINK_TITLE

        label = self._label_for(_LinkProfileDouble())

        self.assertEqual(label, EXPORT_LINK_TITLE)
        self.assertNotIn(".conf", label)

    def test_wireguard_profile_still_says_conf(self) -> None:
        from vpn.ui.page import EXPORT_CONF_TITLE

        label = self._label_for(_ConfProfileDouble())

        self.assertEqual(label, EXPORT_CONF_TITLE)
        self.assertIn(".conf", label)

    def test_no_selection_falls_back_to_the_conf_label(self) -> None:
        """Кнопка в этот момент выключена — подпись просто не должна пустеть."""
        from vpn.ui.page import EXPORT_CONF_TITLE

        self.assertEqual(self._label_for(None), EXPORT_CONF_TITLE)

    def test_labels_differ(self) -> None:
        from vpn.ui.page import EXPORT_CONF_TITLE, EXPORT_LINK_TITLE

        self.assertNotEqual(EXPORT_CONF_TITLE, EXPORT_LINK_TITLE)

    def test_details_update_applies_the_label(self) -> None:
        """Иначе подпись меняется только при первом построении страницы."""
        from vpn.ui import page as page_module

        source = inspect.getsource(page_module.VpnPage._update_details)

        self.assertIn("_apply_export_button_label", source)


class _LinkProfileDouble:
    """Сервер из подписки: есть raw, нет ключей WireGuard."""

    raw = "vless://uuid@example.org:443?security=tls#NL"
    scheme = "vless"
    endpoint = "example.org:443"


class _ConfProfileDouble:
    """Профиль AmneziaWG: есть приватный ключ и адрес в туннеле."""

    private_key = "aGVsbG8="
    address = "10.8.0.2/32"
    endpoint = "vpn.example.org:51820"


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
