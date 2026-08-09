"""Добавление серверов ссылкой на подписку — как в Happ.

Человек вставил `https://sub.gsupport.support/XXxqV-mzg7R0rHVg` и
получил в ответ:

    неизвестный протокол «https». Поддерживаются: vless, vmess, trojan, ss

Формально верно: разборщик одной ссылки такого протокола не знает.
По сути — ответ не на тот вопрос. Это не адрес сервера, это адрес
списка серверов, и по нему надо сходить.

Разбор содержимого был готов давно: `parse_subscription` понимает и
список построчно, и base64 от него. Не хватало доставки.

## Что проверяется без сети

Всё, кроме самого запроса: распознавание адреса, разбор обоих форматов,
и главное — что недоступный сервер даёт человеческое сообщение, а не
исключение посреди интерфейса.
"""

from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


BODY = (
    "vless://11111111-2222-3333-4444-555555555555@a.example:443?security=tls#Берлин\n"
    "trojan://secret@b.example:8443#Прага"
)


class UrlRecognitionTests(unittest.TestCase):
    def test_http_and_https_are_subscriptions(self) -> None:
        from vpn.subscription import looks_like_subscription_url

        for url in ("https://sub.example.org/abc", "http://sub.example.org/abc"):
            with self.subTest(url=url):
                self.assertTrue(looks_like_subscription_url(url))

    def test_a_server_link_is_not_a_subscription(self) -> None:
        """Иначе одиночную ссылку понесло бы в сеть вместо разбора."""
        from vpn.subscription import looks_like_subscription_url

        for text in ("vless://x@h:1", "vmess://eyJ2IjoiMiJ9", "[Interface]", ""):
            with self.subTest(text=text):
                self.assertFalse(looks_like_subscription_url(text))


class ContentTests(unittest.TestCase):
    """Разбор скачанного — оба формата, которые раздают панели."""

    def test_plain_list(self) -> None:
        from vpn.links import parse_subscription

        profiles, errors = parse_subscription(BODY)

        self.assertEqual([item.title for item in profiles], ["Берлин", "Прага"])
        self.assertEqual(errors, [])

    def test_base64_list(self) -> None:
        from vpn.links import parse_subscription

        encoded = base64.b64encode(BODY.encode("utf-8")).decode("ascii")
        profiles, errors = parse_subscription(encoded)

        self.assertEqual([item.title for item in profiles], ["Берлин", "Прага"])
        self.assertEqual(errors, [])


class FetchTests(unittest.TestCase):
    def _response(self, *, status=200, chunks=(b"",)):
        class _Response:
            status_code = status

            def iter_content(self, _size):
                return iter(chunks)

            def close(self):
                return None

        return _Response()

    def test_downloaded_list_becomes_profiles(self) -> None:
        from vpn.subscription import load_subscription

        with patch(
            "requests.get", return_value=self._response(chunks=(BODY.encode("utf-8"),))
        ):
            profiles, errors = load_subscription("https://sub.example.org/abc")

        self.assertEqual([item.title for item in profiles], ["Берлин", "Прага"])
        self.assertEqual(errors, [])

    def test_base64_body_is_decoded(self) -> None:
        from vpn.subscription import load_subscription

        encoded = base64.b64encode(BODY.encode("utf-8"))
        with patch("requests.get", return_value=self._response(chunks=(encoded,))):
            profiles, _errors = load_subscription("https://sub.example.org/abc")

        self.assertEqual(len(profiles), 2)

    def test_unreachable_server_is_a_message_not_a_crash(self) -> None:
        """Страница показывает ошибки списком; исключение её обрушило бы."""
        from vpn.subscription import load_subscription

        with patch("requests.get", side_effect=OSError("нет сети")):
            profiles, errors = load_subscription("https://sub.example.org/abc")

        self.assertEqual(profiles, [])
        self.assertIn("не удалось открыть ссылку", errors[0])

    def test_server_error_is_reported_with_its_code(self) -> None:
        from vpn.subscription import load_subscription

        with patch("requests.get", return_value=self._response(status=404)):
            profiles, errors = load_subscription("https://sub.example.org/abc")

        self.assertEqual(profiles, [])
        self.assertIn("404", errors[0])

    def test_oversized_answer_is_refused(self) -> None:
        """По ссылке может лежать что угодно; читать это в память нельзя."""
        from vpn.subscription import MAX_BYTES, load_subscription

        huge = (b"x" * 8192 for _ in range((MAX_BYTES // 8192) + 2))
        with patch("requests.get", return_value=self._response(chunks=huge)):
            profiles, errors = load_subscription("https://sub.example.org/abc")

        self.assertEqual(profiles, [])
        self.assertIn("слишком много данных", errors[0])

    def test_empty_answer_is_reported(self) -> None:
        from vpn.subscription import load_subscription

        with patch("requests.get", return_value=self._response(chunks=())):
            profiles, errors = load_subscription("https://sub.example.org/abc")

        self.assertEqual(profiles, [])
        self.assertIn("пусто", errors[0])

    def test_only_http_schemes_are_fetched(self) -> None:
        """Адрес приходит от человека и уходит в сетевой запрос."""
        from vpn.subscription import load_subscription

        for url in ("ftp://host/list", "file:///etc/passwd", "vless://x@h:1"):
            with self.subTest(url=url):
                profiles, errors = load_subscription(url)
                self.assertEqual(profiles, [])
                self.assertIn("http", errors[0])


class PageWiringTests(unittest.TestCase):
    """Загрузка обязана идти в потоке: ответа ждут до десяти секунд."""

    def test_subscription_is_loaded_off_the_ui_thread(self) -> None:
        import inspect

        from vpn.ui import page

        source = inspect.getsource(page.VpnPage._save_links)

        self.assertIn("looks_like_subscription_url", source)
        self.assertIn("_start_worker", source)
        self.assertLess(source.index("_start_worker"), source.index("parse_subscription("))


if __name__ == "__main__":
    unittest.main()
