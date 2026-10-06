from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class _ImmediateIdleTasks:
    """Очередь пауз пользователя, которая в тесте выполняет задачу сразу."""

    def add(self, _name, callback, *, delay_ms=0, needs_shown_window=True) -> None:
        callback()


class _RecordingIdleTasks:
    """Очередь пауз пользователя, которая только записывает задачи."""

    def __init__(self) -> None:
        self.tasks: list[tuple[str, object, int, bool]] = []

    def add(self, name, callback, *, delay_ms=0, needs_shown_window=True) -> None:
        self.tasks.append((name, callback, int(delay_ms), bool(needs_shown_window)))


class _UpdaterFeature:
    finished_result = None

    def __init__(self, result: dict, *, whats_new=("", ())) -> None:
        self._result = dict(result)
        self._whats_new = whats_new

    def is_auto_update_enabled(self) -> bool:
        return True

    def begin_update_check(self, *, source: str) -> int:
        self.begin_source = source
        return 7

    def finish_update_check(self, result: dict, *, source: str, token: int) -> bool:
        self.finished_result = dict(result)
        self.finish_source = source
        self.finish_token = token
        return True

    def run_startup_update_check(self) -> dict:
        return dict(self._result)

    def pending_whats_new(self):
        return self._whats_new


def _host():
    return SimpleNamespace(
        startup_post_init_ready=object(),
        startup_state=SimpleNamespace(post_init_ready=True),
        is_alive=Mock(return_value=True),
        ask_update=Mock(return_value=("later", [])),
        show_page=Mock(),
        get_loaded_page=Mock(),
        show_whats_new=Mock(),
    )


def _patched(post_startup_update):
    return (
        patch.object(post_startup_update, "bind_startup_gate", side_effect=lambda _signal, callback, **_kwargs: callback()),
        patch.object(post_startup_update, "schedule_after", side_effect=lambda _delay_ms, callback: callback()),
        patch.object(post_startup_update, "enqueue_subsystem_task", side_effect=lambda _queue, _name, target: target()),
        patch.object(post_startup_update, "log"),
    )


class PostStartupUpdateContractTests(unittest.TestCase):
    def test_skipped_startup_update_check_clears_checking_status(self) -> None:
        from main import post_startup_update

        startup_host = _host()
        statuses: list[str] = []
        updater_feature = _UpdaterFeature(
            {
                "has_update": False,
                "version": "1.2.3",
                "release_notes": "",
                "error": None,
                "skipped": True,
                "skip_reason": "Следующая автоматическая проверка возможна через 5 мин",
            }
        )

        bind, after, enqueue, log = _patched(post_startup_update)
        with bind, after, enqueue, log:
            post_startup_update.install_update_check(
                startup_host,
                updater_feature=updater_feature,
                notify=Mock(),
                set_status=statuses.append,
                idle_tasks=_ImmediateIdleTasks(),
            )

        self.assertEqual(statuses[0], "Проверка обновлений...")
        self.assertNotEqual(statuses[-1], "Проверка обновлений...")
        self.assertIn("Следующая автоматическая проверка", statuses[-1])
        self.assertEqual(updater_feature.begin_source, "startup")
        self.assertEqual(updater_feature.finish_source, "startup")
        self.assertEqual(updater_feature.finish_token, 7)
        self.assertTrue(updater_feature.finished_result["skipped"])


class PostStartupUpdateIdleQueueTests(unittest.TestCase):
    """Окна после запуска ждут паузы пользователя, а не срабатывают по таймеру."""

    def test_update_offer_waits_for_user_pause_even_in_tray(self) -> None:
        from main import post_startup_update

        startup_host = _host()
        idle_tasks = _RecordingIdleTasks()
        feature = _UpdaterFeature({"has_update": True, "version": "9.9.9", "release_notes": "новое", "error": None})

        bind, after, enqueue, log = _patched(post_startup_update)
        with bind, after, enqueue, log:
            post_startup_update.install_update_check(
                startup_host,
                updater_feature=feature,
                notify=Mock(),
                set_status=Mock(),
                idle_tasks=idle_tasks,
            )

        # Окно обновления забирает фокус: посреди клика оно мешало. При окне в
        # трее ждать нечего — показывается, как и раньше.
        startup_host.ask_update.assert_not_called()
        self.assertEqual([(name, needs) for name, _cb, _delay, needs in idle_tasks.tasks], [("UpdateOfferDialog", False)])

        idle_tasks.tasks[0][1]()
        startup_host.ask_update.assert_called_once()
        self.assertEqual(startup_host.ask_update.call_args.args[0], "9.9.9")

    def test_update_offer_is_not_shown_after_app_started_closing(self) -> None:
        from main import post_startup_update

        startup_host = _host()
        idle_tasks = _RecordingIdleTasks()
        feature = _UpdaterFeature({"has_update": True, "version": "9.9.9", "release_notes": "", "error": None})

        bind, after, enqueue, log = _patched(post_startup_update)
        with bind, after, enqueue, log:
            post_startup_update.install_update_check(
                startup_host,
                updater_feature=feature,
                notify=Mock(),
                set_status=Mock(),
                idle_tasks=idle_tasks,
            )
        startup_host.is_alive.return_value = False
        idle_tasks.tasks[0][1]()

        startup_host.ask_update.assert_not_called()

    def test_whats_new_waits_for_user_pause_and_shown_window(self) -> None:
        from main import post_startup_update

        startup_host = _host()
        idle_tasks = _RecordingIdleTasks()
        history = ({"version": "9.9.9", "notes": "новое"},)
        feature = _UpdaterFeature({}, whats_new=("9.9.9", history))

        bind, after, enqueue, log = _patched(post_startup_update)
        with bind, after, enqueue, log:
            post_startup_update.install_whats_new(startup_host, updater_feature=feature, idle_tasks=idle_tasks)

        startup_host.show_whats_new.assert_not_called()
        self.assertEqual(
            [(name, delay, needs) for name, _cb, delay, needs in idle_tasks.tasks],
            [("WhatsNewDialog", post_startup_update._WHATS_NEW_DELAY_MS, True)],
        )

        idle_tasks.tasks[0][1]()
        startup_host.show_whats_new.assert_called_once_with("9.9.9", history)


if __name__ == "__main__":
    unittest.main()
