"""Документация открывается из программы, без интернета.

Раздел «Документация» был убран вместе со ссылками прежнего автора:
адрес вики в branding.py опустел, и карточка перестала показываться.
Своей документации тогда не было, показывать было нечего.

Теперь вики едет вместе с программой — папка `docs` рядом с
исполняемым файлом. Открыть её файлом в браузере нельзя: генератор
рассчитан на веб-сервер, ссылки внутри ведут на `./vpn`, а не на
`./vpn.html`, и по протоколу `file://` подставлять расширение некому.
Поэтому программа поднимает свой сервер на 127.0.0.1.

Здесь закреплено то, что легко потерять при следующей правке: сервер
слушает только себя, наружу ничего не отдаёт, расширение подставляет,
и повторное открытие не плодит серверы.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class AvailabilityTests(unittest.TestCase):
    """Раздел показывает себя рабочим только когда есть что открыть."""

    def test_missing_folder_is_not_available(self) -> None:
        import docs.local_site as site

        original = site.docs_root
        site.docs_root = lambda: Path("/nonexistent-docs-folder")
        try:
            self.assertFalse(site.is_available())
        finally:
            site.docs_root = original

    def test_empty_folder_is_not_available(self) -> None:
        """Пустая папка остаётся после неудачной сборки.

        По ней раздел выглядел бы рабочим, а открывал бы пустоту —
        поэтому проверяется не папка, а главная страница в ней.
        """
        import tempfile

        import docs.local_site as site

        with tempfile.TemporaryDirectory() as tmp:
            original = site.docs_root
            site.docs_root = lambda: Path(tmp)
            try:
                self.assertFalse(site.is_available())
            finally:
                site.docs_root = original

    def test_folder_with_index_is_available(self) -> None:
        import tempfile

        import docs.local_site as site

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "index.html").write_text("<h1>вики</h1>", encoding="utf-8")
            original = site.docs_root
            site.docs_root = lambda: Path(tmp)
            try:
                self.assertTrue(site.is_available())
            finally:
                site.docs_root = original

    def test_open_reports_the_reason_when_there_is_nothing(self) -> None:
        """Молчаливое ничего человек читает как поломку кнопки."""
        import docs.local_site as site

        original = site.docs_root
        site.docs_root = lambda: Path("/nonexistent-docs-folder")
        try:
            ok, message = site.open_in_browser()
        finally:
            site.docs_root = original

        self.assertFalse(ok)
        self.assertTrue(message.strip())


class ServerTests(unittest.TestCase):
    """Поведение поднятого сервера — на живой папке и живых запросах."""

    @classmethod
    def setUpClass(cls) -> None:
        import tempfile

        cls._prepare_mimetypes()

        import docs.local_site as site

        cls.site = site
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / "index.html").write_text("<h1>Главная</h1>", encoding="utf-8")
        (root / "vpn.html").write_text("<h1>VPN по ссылке</h1>", encoding="utf-8")
        (root / "sub").mkdir()
        (root / "sub" / "page.html").write_text("<h1>Вложенная</h1>", encoding="utf-8")

        cls._original_root = site.docs_root
        site.docs_root = lambda: root
        cls.url = site.start()

    @staticmethod
    def _prepare_mimetypes() -> None:
        """Готовит определение типов файлов заранее.

        Не про сервер, а про песочницу, где идут проверки. В `src` лежит
        заглушка модуля `winreg` — она нужна, чтобы код с обращениями к
        реестру Windows вообще импортировался вне Windows.

        Стандартный `mimetypes` при первом обращении видит этот модуль,
        принимает систему за Windows и лезет в реестр за списком типов.
        Заглушка таких имён не знает, обработчик падает, а браузер видит
        оборванное соединение.

        На самой Windows проблемы нет: там `winreg` встроен в
        интерпретатор и заглушку не перекрывает.
        """
        import mimetypes

        if getattr(mimetypes, "_winreg", None) is not None:
            mimetypes._winreg = None
        mimetypes.init()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.site.stop()
        cls.site.docs_root = cls._original_root
        cls.tmp.cleanup()

    def _get(self, path: str):
        import urllib.request

        return urllib.request.urlopen(self.url.rstrip("/") + path, timeout=5)

    def test_server_started(self) -> None:
        self.assertTrue(self.url.startswith("http://127.0.0.1:"))

    def test_listens_on_loopback_only(self) -> None:
        """Наружу вики отдавать незачем — она внутренняя."""
        self.assertIn("127.0.0.1", self.url)
        self.assertNotIn("0.0.0.0", self.url)

    def test_index_is_served(self) -> None:
        with self._get("/") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("Главная", response.read().decode("utf-8"))

    def test_extension_is_added(self) -> None:
        """Ссылки внутри сайта расширения не содержат."""
        with self._get("/vpn") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("VPN по ссылке", response.read().decode("utf-8"))

    def test_nested_page_without_extension(self) -> None:
        with self._get("/sub/page") as response:
            self.assertEqual(response.status, 200)

    def test_missing_page_is_a_honest_404(self) -> None:
        import urllib.error

        with self.assertRaises(urllib.error.HTTPError) as caught:
            self._get("/there-is-no-such-page")

        self.assertEqual(caught.exception.code, 404)

    def test_second_start_reuses_the_same_server(self) -> None:
        """Иначе каждое нажатие кнопки поднимало бы ещё один сервер."""
        self.assertEqual(self.site.start(), self.url)


class ShutdownTests(unittest.TestCase):
    def test_stop_is_wired_into_closing(self) -> None:
        """Иначе порт остаётся занятым до конца сеанса Windows."""
        root = Path(__file__).resolve().parents[1]
        source = (root / "src/main/window_lifecycle_cleanup.py").read_text(encoding="utf-8")

        self.assertIn("from docs.local_site import stop as stop_docs_site", source)
        self.assertIn("stop_docs_site()", source)

    def test_stop_without_start_is_not_an_error(self) -> None:
        import docs.local_site as site

        site.stop()
        site.stop()


class WiringTests(unittest.TestCase):
    def _read(self, relative: str) -> str:
        """Читаем исходник файлом, а не импортом.

        Импорт этих модулей тянет за собой Qt, а проверяется здесь
        расстановка вызовов — она видна и в тексте.
        """
        root = Path(__file__).resolve().parents[1]
        return (root / relative).read_text(encoding="utf-8")

    def test_card_opens_the_local_site(self) -> None:
        source = self._read("src/presets/ui/control/shared_builders.py")

        self.assertIn("def build_docs_card(", source)
        self.assertIn("from docs.local_site import open_in_browser", source)

    def test_card_is_added_to_the_page(self) -> None:
        source = self._read("src/presets/ui/control/zapret2/sections_build.py")

        self.assertIn("build_docs_card(", source)
        self.assertIn("extra_card.addSettingCard(wiki_card)", source)

    def test_build_scripts_ship_the_site(self) -> None:
        """Без копирования папки кнопка открывала бы пустоту."""
        root = Path(__file__).resolve().parents[1]

        for relative in ("scripts/build_local.ps1", ".github/workflows/windows-release.yml"):
            with self.subTest(script=relative):
                text = (root / relative).read_text(encoding="utf-8")
                self.assertIn("wiki\\site", text)
                self.assertIn('"docs"', text)

    def test_paths_know_about_the_docs_folder(self) -> None:
        from config.runtime_layout import ApplicationPaths

        paths = ApplicationPaths.from_root("/opt/net67")

        self.assertEqual(paths.docs_dir.name, "docs")
        self.assertEqual(paths.docs_dir.parent, paths.root)


if __name__ == "__main__":
    unittest.main()
