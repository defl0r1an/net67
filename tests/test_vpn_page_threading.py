"""Страница VPN не должна блокировать интерфейс.

Все три её операции уходят в системные вызовы с большими таймаутами:

    connect()      amneziawg.exe /installtunnelservice   до 30 с
    get_status()   awg.exe show                          до 10 с
    check_server() три ICMP-пакета плюс TCP-проба        до 10 с

Изначально они выполнялись прямо в UI-потоке, и окно замирало: при
подключении, при проверке сервера и даже при простом открытии страницы —
состояние службы запрашивалось в _update_details().

Проверяем разбором исходника: поднять Qt в headless-окружении нельзя, а
дожидаться зависания в ручном тесте — плохой способ найти регрессию.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
PAGE = PROJECT_SRC / "vpn" / "ui" / "page.py"

#: Функции, которые нельзя звать из UI-потока.
BLOCKING_CALLS = frozenset(
    {"connect", "disconnect", "get_status", "get_stats", "check_server"}
)

#: Обработчики, которые пользователь дёргает кнопками.
UI_HANDLERS = (
    "_on_toggle_connection",
    "_on_check_server",
    "_refresh_connection_state",
)


def _method(name: str) -> ast.FunctionDef:
    tree = ast.parse(PAGE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"в page.py нет метода {name}")


def _direct_blocking_calls(function: ast.FunctionDef) -> list[str]:
    """Блокирующие вызовы вне вложенных функций и лямбд.

    Вложенные тела — это как раз то, что уходит в поток, их пропускаем.
    """
    nested: set[int] = set()
    for node in ast.walk(function):
        if node is function:
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            for inner in ast.walk(node):
                nested.add(id(inner))

    found: list[str] = []
    for node in ast.walk(function):
        if id(node) in nested or not isinstance(node, ast.Call):
            continue
        target = node.func
        name = ""
        if isinstance(target, ast.Name):
            name = target.id
        elif isinstance(target, ast.Attribute):
            name = target.attr
        if name in BLOCKING_CALLS:
            found.append(name)
    return sorted(set(found))


class VpnPageThreadingTests(unittest.TestCase):
    def test_ui_handlers_do_not_block(self) -> None:
        for handler in UI_HANDLERS:
            with self.subTest(handler):
                offenders = _direct_blocking_calls(_method(handler))
                self.assertEqual(
                    offenders,
                    [],
                    f"{handler} вызывает {offenders} в UI-потоке — окно зависнет",
                )

    def test_ui_handlers_use_background_worker(self) -> None:
        for handler in UI_HANDLERS:
            with self.subTest(handler):
                source = ast.unparse(_method(handler))
                self.assertIn(
                    "_start_worker",
                    source,
                    f"{handler} должен уходить в фоновый поток",
                )

    def test_worker_reports_failures(self) -> None:
        """Без сигнала об ошибке кнопка осталась бы выключенной навсегда."""
        worker = (PROJECT_SRC / "vpn" / "ui" / "workers.py").read_text(encoding="utf-8")

        self.assertIn("failed = pyqtSignal(str)", worker)
        self.assertIn("done = pyqtSignal(object)", worker)

    def test_page_keeps_worker_reference(self) -> None:
        """QThread без ссылки соберёт сборщик мусора прямо на ходу."""
        source = PAGE.read_text(encoding="utf-8")

        for attr in ("_status_worker", "_ping_worker", "_tunnel_worker"):
            self.assertIn(attr, source)

    def test_buttons_are_re_enabled_on_failure(self) -> None:
        source = ast.unparse(_method("_on_check_server_failed"))
        self.assertIn("setEnabled(True)", source)

        source = ast.unparse(_method("_on_tunnel_failed"))
        self.assertIn("setEnabled(True)", source)


class VpnPingTests(unittest.TestCase):
    """Проверка сервера должна быть честной насчёт UDP."""

    def test_check_server_has_bounded_timeout(self) -> None:
        import inspect
        import sys

        if str(PROJECT_SRC) not in sys.path:
            sys.path.insert(0, str(PROJECT_SRC))

        from vpn.ping import check_server

        signature = inspect.signature(check_server)
        self.assertIn("timeout", signature.parameters)
        self.assertIsNotNone(signature.parameters["timeout"].default)


if __name__ == "__main__":
    unittest.main()
