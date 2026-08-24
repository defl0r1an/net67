"""Ошибка загрузки подписки объясняется человеку, а не пересказывается.

Человек вставлял ссылку на подписку и получал в окне полотно от
requests: HTTPSConnectionPool, Max retries exceeded, ConnectTimeoutError
и адрес объекта в памяти. Три повтора одного факта и ни слова о том, что
делать — полезных слов там ровно два, «timed out».

Разбор идёт по типу исключения, а не по его тексту: тексты requests
меняются от версии к версии и переводу не поддаются.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

URL = "https://sub.example.org/XXxqV-mzg7R0rHVg"


class SubscriptionErrorTextTests(unittest.TestCase):
    def setUp(self) -> None:
        from vpn.subscription import _explain_network_error

        self.explain = _explain_network_error

    def test_connect_timeout_names_host_and_suggests_bypass(self) -> None:
        import requests

        exc = requests.exceptions.ConnectTimeout(
            "HTTPSConnectionPool(host='sub.example.org', port=443): Max retries "
            "exceeded with url: /XXxqV (Caused by ConnectTimeoutError("
            "<HTTPSConnection object at 0x19cb18d5e50>, 'Connection to "
            "sub.example.org timed out. (connect timeout=10)'))"
        )

        text = self.explain(exc, URL, 10)

        self.assertIn("sub.example.org", text)
        self.assertIn("10 секунд", text)
        # Подписка часто и лежит за блокировкой — подсказка про обход
        # полезнее любого пересказа стека.
        self.assertIn("обход", text)
        # Внутренностей библиотеки в сообщении быть не должно.
        self.assertNotIn("HTTPSConnectionPool", text)
        self.assertNotIn("0x", text)

    def test_ssl_error_warns_about_substitution(self) -> None:
        import requests

        text = self.explain(requests.exceptions.SSLError("verify failed"), URL, 10)

        self.assertIn("сертификат", text)

    def test_unknown_error_still_says_something(self) -> None:
        # Запасной путь обязан остаться: неизвестная ошибка лучше
        # тишины, даже если её текст неказист.
        text = self.explain(ValueError("нечто своё"), URL, 10)

        self.assertIn("нечто своё", text)


if __name__ == "__main__":
    unittest.main()
