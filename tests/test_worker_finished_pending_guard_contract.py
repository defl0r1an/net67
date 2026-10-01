from __future__ import annotations

import ast
from pathlib import Path
import unittest


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"

FRESHNESS_GUARD_MARKERS = (
    "_is_current_worker_finish",
    "_accept_current",
    "_is_current_request_finish",
    ".is_current(",
    "accept_worker_finish",
    "current_worker",
    "_runtime_worker",
    "request_id !=",
    "_schedule_next_profile_setup_write_operation_after_finish",
    "_schedule_next_user_profile_write_operation_after_finish",
)


def _finish_handlers_guarded_by_runtime(tree: ast.AST) -> set[str]:
    """Имена обработчиков, переданных в start_qthread_worker(on_finished=...).

    OneShotWorkerRuntime зовёт их только для текущего воркера
    (_finish_qthread_worker сверяет self.worker is worker): проверка
    свежести у них есть, просто живёт уровнем ниже, а не в теле обработчика.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "start_qthread_worker"):
            continue
        for keyword in node.keywords:
            value = keyword.value
            if keyword.arg == "on_finished" and isinstance(value, ast.Attribute):
                names.add(value.attr)
    return names


class WorkerFinishedPendingGuardContractTests(unittest.TestCase):
    def test_pending_finished_handlers_check_current_worker_or_request(self) -> None:
        offenders: list[str] = []
        for path in SRC_ROOT.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "_pending" not in text or "finished" not in text:
                continue

            tree = ast.parse(text)
            guarded_by_runtime = _finish_handlers_guarded_by_runtime(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                if not node.name.startswith("_on_"):
                    continue
                if "finished" not in node.name:
                    continue
                if node.name in guarded_by_runtime:
                    continue

                source = ast.get_source_segment(text, node) or ""
                if "_pending" not in source:
                    continue
                if any(marker in source for marker in FRESHNESS_GUARD_MARKERS):
                    continue

                rel_path = path.relative_to(SRC_ROOT).as_posix()
                offenders.append(f"{rel_path}:{node.lineno}:{node.name}")

        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
