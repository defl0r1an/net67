"""Во время проверки стратегий запуск обхода отклоняется.

Сканер стратегий снимает все процессы winws перед проверкой и поднимает
свои по ходу — движок на это время принадлежит ему. Кнопка «Включить»
при этом оставалась доступной, и поднятый ею процесс сканер убивал через
несколько секунд. В журнале это выглядело так:

    14:46:34  Starting: пресет Ростелеком
    14:46:38  Завершено 1 процессов winws2.exe
    14:46:38  winws2 завершился сразу (код 1)

Человеку показывали «winws2 завершился сразу» или «обход не запустился
за 40 секунд» — оба сообщения уводят в сторону: и пресет, и движок были
исправны. Проверка стережёт, что запуск отклоняется сразу и с понятным
объяснением.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class _Owner:
    """Заглушка владельца запуска: интересен только исход подготовки."""

    def __init__(self) -> None:
        self._dpi_start_thread = None
        self._pending_launch_warnings = None
        self.failed_with: str | None = None

    def _mark_runtime_failed(self, text: str) -> None:
        self.failed_with = text


class StartFlowScanGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        import winws_runtime.runtime.start_flow as start_flow
        from winws_runtime.runtime.scan_guard import mark_external_winws_scan_active

        self.start_flow = start_flow
        self.mark_scan = mark_external_winws_scan_active

        # Сообщения человеку и разбор конфликтов к этой проверке не
        # относятся: они требуют окна.
        self._saved = (
            start_flow.set_runtime_owner_status,
            start_flow.show_launch_error_top,
            start_flow.handle_conflicting_processes_before_start,
        )
        start_flow.set_runtime_owner_status = lambda *a, **k: None
        start_flow.show_launch_error_top = lambda *a, **k: None
        start_flow.handle_conflicting_processes_before_start = lambda *a, **k: True

        self.addCleanup(self._restore)
        self.addCleanup(mark_external_winws_scan_active, False)

    def _restore(self) -> None:
        (
            self.start_flow.set_runtime_owner_status,
            self.start_flow.show_launch_error_top,
            self.start_flow.handle_conflicting_processes_before_start,
        ) = self._saved

    def test_start_is_refused_while_strategy_scan_runs(self) -> None:
        self.mark_scan(True, ttl_seconds=30)
        owner = _Owner()

        accepted = self.start_flow.prepare_start_preflight(owner)

        self.assertFalse(accepted)
        # Текст важен не меньше отказа: прежние сообщения винили движок.
        self.assertIn("проверка стратегий", owner.failed_with or "")

    def test_start_is_allowed_when_no_scan_runs(self) -> None:
        self.mark_scan(False)
        owner = _Owner()

        self.assertTrue(self.start_flow.prepare_start_preflight(owner))
        self.assertIsNone(owner.failed_with)


if __name__ == "__main__":
    unittest.main()
