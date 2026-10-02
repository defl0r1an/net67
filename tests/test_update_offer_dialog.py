"""Окно «Доступно обновление», история выпусков и «Что нового».

Об обновлении спрашивало окошко в одну строку. Владелец показал окно
исходного проекта и попросил такое же: что нового в каждой пропущенной
версии, «Пропустить версию», «Позже», «Обновить».

Слои: история и её текст (без Qt и сети), проверка при запуске, само
окно и показ «Что нового» после установки.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from updater import release_notes  # noqa: E402

RELEASES = [
    {"version": "0.14.67", "published_at": "2026-10-20T10:00:00Z", "release_notes": "- новый движок\n- новое окно"},
    {"version": "0.13.67", "published_at": "2026-10-02T08:19:51Z", "release_notes": "- кнопка проверки"},
    {"version": "0.12.67", "published_at": "2026-09-30T09:52:18Z", "release_notes": "- меньше памяти"},
    {"version": "0.11.67", "published_at": "2026-09-02T05:46:00Z", "release_notes": "- без Steam"},
    {"version": "0.10.67", "published_at": "2026-08-24T13:56:59Z", "release_notes": "- пресеты 2.39"},
    {"version": "0.9.67", "published_at": "2026-08-10T00:00:00Z", "release_notes": "- старое"},
]


class HistoryTests(unittest.TestCase):
    def _history(self, current: str, target: str, **kwargs):
        return release_notes.build_history(RELEASES, current_version=current, target_version=target, **kwargs)

    def test_skipped_versions_are_new_and_a_few_earlier_follow(self) -> None:
        history = self._history("0.12.67", "0.14.67")

        self.assertEqual([item["version"] for item in history], ["0.14.67", "0.13.67", "0.12.67", "0.11.67", "0.10.67"])
        self.assertEqual([item["is_new"] for item in history], [True, True, False, False, False])
        self.assertEqual(release_notes.count_new_versions(history), 2)

    def test_versions_newer_than_the_offered_one_are_not_shown(self) -> None:
        # Окно про то обновление, которое сейчас поставится.
        history = self._history("0.11.67", "0.13.67")

        self.assertNotIn("0.14.67", [item["version"] for item in history])
        self.assertEqual(history[0]["version"], "0.13.67")

    def test_all_skipped_versions_are_kept_whatever_the_limit(self) -> None:
        history = self._history("0.9.67", "0.14.67", earlier_limit=1)

        self.assertEqual(release_notes.count_new_versions(history), 5)
        self.assertEqual([item["version"] for item in history if not item["is_new"]], ["0.9.67"])

    def test_versions_compare_as_numbers(self) -> None:
        releases = [{"version": "0.9.67"}, {"version": "0.10.67"}]
        history = release_notes.build_history(releases, current_version="0.9.67", target_version="0.10.67")

        self.assertEqual(history[0]["version"], "0.10.67")
        self.assertTrue(history[0]["is_new"])

    def test_junk_is_ignored(self) -> None:
        releases = [{"version": "мусор"}, None, {"version": "v0.14.67"}, {"version": "0.14.67"}]
        history = release_notes.build_history(releases, current_version="0.13.67", target_version="0.14.67")

        self.assertEqual([item["version"] for item in history], ["0.14.67"])

    def test_release_page_address(self) -> None:
        history = self._history("0.13.67", "0.14.67", repo="defl0r1an/net67")

        self.assertEqual(history[0]["url"], "https://github.com/defl0r1an/net67/releases/tag/v0.14.67")
        self.assertEqual(release_notes.release_page_url("0.14.67", ""), "")


class NotesTextTests(unittest.TestCase):
    def test_lines_github_adds_itself_are_dropped(self) -> None:
        notes = "- важное\n\n**Full Changelog**: https://github.com/a/b/compare/v1...v2"

        self.assertEqual(release_notes.clean_release_notes(notes), "- важное")
        self.assertEqual(release_notes.clean_release_notes("**Full Changelog**: https://x/y"), "")

    def test_list_headings_bold_and_links(self) -> None:
        html = release_notes.notes_html(
            "# Обновления\n- можно **пропустить**\n- сайт https://example.com/doc.\nпросто строка", accent_hex="#00aaff"
        )

        self.assertIn("<b>Обновления</b>", html)
        self.assertIn("<li", html)
        self.assertIn("<b>пропустить</b>", html)
        self.assertIn('<a href="https://example.com/doc"', html)
        self.assertIn("просто строка", html)

    def test_text_from_the_network_cannot_inject_markup(self) -> None:
        html = release_notes.notes_html("- <script>alert(1)</script> <img src=x>", accent_hex="#00aaff")

        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;script&gt;", html)

    def test_date_and_word_forms(self) -> None:
        self.assertEqual(release_notes.format_release_date("2026-10-02T08:19:51Z"), "2 октября 2026")
        self.assertEqual(release_notes.format_release_date("чепуха"), "")
        self.assertEqual([release_notes.versions_word(n) for n in (1, 2, 5, 11, 21)], ["версию", "версии", "версий", "версий", "версию"])

    def test_new_and_earlier_are_told_apart(self) -> None:
        history = release_notes.build_history(RELEASES, current_version="0.13.67", target_version="0.14.67")
        html = release_notes.history_html(history, accent_hex="#00aaff", muted_hex="#888888")

        self.assertIn("Ранее", html)
        self.assertIn("новое", html)
        self.assertLess(html.index("v0.14.67"), html.index("Ранее"))
        self.assertLess(html.index("Ранее"), html.index("v0.13.67"))


class StartupCheckTests(unittest.TestCase):
    def _check(self, *, skipped: str = ""):
        from updater import startup_update_check

        release = dict(RELEASES[0], file_name="net67-setup-0.14.67.exe", file_size=65_000_000)
        with (
            patch("config.build_info.APP_VERSION", "0.12.67"),
            patch("updater.update_cache.UpdateCache.get_cached_release", return_value=release),
            patch("updater.github_release.get_all_releases_with_exe", return_value=RELEASES),
            patch("settings.store.get_skipped_update_version", return_value=skipped),
            patch.object(startup_update_check, "log"),
        ):
            return startup_update_check.check_for_update_sync()

    def test_found_update_carries_everything_the_window_needs(self) -> None:
        result = self._check()

        self.assertTrue(result["has_update"])
        self.assertEqual(result["current_version"], "0.12.67")
        self.assertEqual([item["version"] for item in result["history"]][:2], ["0.14.67", "0.13.67"])
        self.assertEqual(result["source"], "GitHub")
        self.assertTrue(result["release_url"].endswith("/releases/tag/v0.14.67"))

    def test_skipped_version_is_not_offered_at_startup(self) -> None:
        result = self._check(skipped="0.14.67")

        self.assertFalse(result["has_update"])
        self.assertTrue(result["skipped"])
        self.assertIn("пропущена", result["skip_reason"])

    def test_skipping_an_older_version_does_not_hide_a_newer_one(self) -> None:
        self.assertTrue(self._check(skipped="0.13.67")["has_update"])

    def test_history_survives_a_failed_release_list(self) -> None:
        from updater import startup_update_check

        with (
            patch("updater.github_release.get_all_releases_with_exe", side_effect=RuntimeError("нет сети")),
            patch.object(startup_update_check, "log"),
        ):
            history = startup_update_check.release_history_for(RELEASES[0], current_version="0.13.67")

        self.assertEqual([item["version"] for item in history], ["0.14.67"])


class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PyQt6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication(sys.argv)

    def _dialog(self, **kwargs):
        from PyQt6.QtWidgets import QWidget

        from updater.ui.update_dialog import UpdateOfferDialog

        host = QWidget()
        host.resize(1200, 800)
        self.addCleanup(host.deleteLater)
        history = release_notes.build_history(RELEASES, current_version="0.12.67", target_version="0.14.67")
        options = dict(
            current_version="0.12.67",
            target_version="0.14.67",
            history=history,
            source="GitHub",
            release_url="https://github.com/defl0r1an/net67/releases/tag/v0.14.67",
            file_name="net67-setup-0.14.67.exe",
            file_size=65_000_000,
        )
        options.update(kwargs)
        dialog = UpdateOfferDialog(host, **options)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_header_says_what_changes_and_how_many_versions(self) -> None:
        dialog = self._dialog()

        self.assertEqual(dialog.title_label.text(), "Доступно обновление")
        subtitle = dialog.subtitle_label.text()
        self.assertIn("v0.12.67", subtitle)
        self.assertIn("v0.14.67", subtitle)
        self.assertIn("версий в обновлении: 2", subtitle)
        self.assertIn("источник: GitHub", subtitle)
        self.assertIn("новый движок", dialog.browser.toPlainText())

    def test_each_button_gives_its_own_answer(self) -> None:
        from updater.ui.update_dialog import RESULT_INSTALL, RESULT_LATER, RESULT_SKIP

        for button_name, expected in (("install_btn", RESULT_INSTALL), ("later_btn", RESULT_LATER), ("skip_btn", RESULT_SKIP)):
            dialog = self._dialog()
            getattr(dialog, button_name).click()
            with self.subTest(button=button_name):
                self.assertEqual(dialog.result_action, expected)

    def test_closing_without_a_choice_means_later(self) -> None:
        from updater.ui.update_dialog import RESULT_LATER

        dialog = self._dialog()
        dialog.reject()

        self.assertEqual(dialog.result_action, RESULT_LATER)

    def test_details_tab_names_file_and_size(self) -> None:
        dialog = self._dialog()
        details = dialog.details_label.text()

        self.assertIn("net67-setup-0.14.67.exe", details)
        self.assertIn("62.0 МБ", details)

    def test_browser_button_hides_without_an_address(self) -> None:
        self.assertTrue(self._dialog(release_url="").browser_btn.isHidden())
        self.assertFalse(self._dialog().browser_btn.isHidden())

    def test_whats_new_counts_versions(self) -> None:
        from PyQt6.QtWidgets import QWidget

        from updater.ui.update_dialog import WhatsNewDialog

        host = QWidget()
        self.addCleanup(host.deleteLater)
        history = release_notes.build_history(RELEASES, current_version="0.12.67", target_version="0.14.67")
        dialog = WhatsNewDialog(host, version="0.14.67", history=history)
        self.addCleanup(dialog.deleteLater)

        self.assertEqual(dialog.title_label.text(), "Что нового в v0.14.67")
        self.assertEqual(dialog.subtitle_label.text(), "Изменения за 2 версии")


class HostWindowTests(unittest.TestCase):
    """Хозяин окна только показывает окно и возвращает ответ."""

    def test_answer_comes_back_with_the_shown_history(self) -> None:
        from main.post_startup_host import PostStartupHost

        host = PostStartupHost(SimpleNamespace())
        details = {"current_version": "0.12.67", "history": [{"version": "0.14.67", "notes": "x", "is_new": True}]}
        with patch("updater.ui.update_dialog.ask_update", return_value="skip") as ask:
            action, history = host.ask_update("0.14.67", details)

        self.assertEqual(action, "skip")
        self.assertEqual(history, details["history"])
        self.assertEqual(ask.call_args.kwargs["current_version"], "0.12.67")
        self.assertEqual(ask.call_args.kwargs["target_version"], "0.14.67")

    def test_release_without_history_still_shows_its_own_notes(self) -> None:
        from main.post_startup_host import PostStartupHost

        host = PostStartupHost(SimpleNamespace())
        with patch("updater.ui.update_dialog.ask_update", return_value="later") as ask:
            _action, history = host.ask_update("0.14.67", {"release_notes": "- одно изменение"})

        self.assertEqual(history[0]["notes"], "- одно изменение")
        self.assertEqual(ask.call_args.kwargs["history"], history)


class StartupFlowTests(unittest.TestCase):
    """Что делает программа с ответом из окна при запуске."""

    def _run(self, action: str):
        from unittest.mock import Mock

        from main import post_startup_update

        history = [{"version": "0.14.67", "notes": "x", "is_new": True}]
        feature = Mock()
        feature.is_auto_update_enabled.return_value = True
        feature.begin_update_check.return_value = 1
        feature.finish_update_check.return_value = True
        feature.run_startup_update_check.return_value = {
            "has_update": True,
            "version": "0.14.67",
            "release_notes": "x",
            "error": None,
            "history": history,
        }
        page = Mock()
        host = SimpleNamespace(
            startup_post_init_ready=object(),
            startup_state=SimpleNamespace(post_init_ready=True),
            is_alive=Mock(return_value=True),
            ask_update=Mock(return_value=(action, history)),
            show_page=Mock(),
            get_loaded_page=Mock(return_value=page),
        )
        with (
            patch.object(post_startup_update, "bind_startup_gate", side_effect=lambda _signal, callback, **_kwargs: callback()),
            patch.object(post_startup_update, "schedule_after", side_effect=lambda _delay_ms, callback: callback()),
            patch.object(post_startup_update, "enqueue_subsystem_task", side_effect=lambda _queue, _name, target: target()),
            patch.object(post_startup_update, "log"),
        ):
            post_startup_update.install_update_check(host, updater_feature=feature, notify=Mock(), set_status=Mock())
        return feature, host, page, history

    def test_install_remembers_the_changes_and_starts_the_update(self) -> None:
        feature, host, page, history = self._run("install")

        feature.remember_whats_new.assert_called_once_with("0.14.67", history)
        feature.remember_skipped_update.assert_not_called()
        host.show_page.assert_called_once()
        page.present_startup_update.assert_called_once()

    def test_skip_is_remembered_and_nothing_is_installed(self) -> None:
        feature, host, page, _history = self._run("skip")

        feature.remember_skipped_update.assert_called_once_with("0.14.67")
        feature.remember_whats_new.assert_not_called()
        host.show_page.assert_not_called()
        page.present_startup_update.assert_not_called()

    def test_later_changes_nothing(self) -> None:
        feature, host, _page, _history = self._run("later")

        feature.remember_skipped_update.assert_not_called()
        feature.remember_whats_new.assert_not_called()
        host.show_page.assert_not_called()

    def test_whats_new_is_shown_only_when_something_is_pending(self) -> None:
        from unittest.mock import Mock

        from main import post_startup_update

        for pending, expected_calls in ((("0.14.67", [{"version": "0.14.67"}]), 1), (("", []), 0)):
            feature = Mock()
            feature.pending_whats_new.return_value = pending
            host = SimpleNamespace(
                startup_post_init_ready=object(),
                startup_state=SimpleNamespace(post_init_ready=True),
                is_alive=Mock(return_value=True),
                show_whats_new=Mock(),
            )
            with (
                patch.object(post_startup_update, "bind_startup_gate", side_effect=lambda _signal, callback, **_kwargs: callback()),
                patch.object(post_startup_update, "schedule_after", side_effect=lambda _delay_ms, callback: callback()),
                patch.object(post_startup_update, "log"),
            ):
                post_startup_update.install_whats_new(host, updater_feature=feature)
            with self.subTest(pending=pending[0]):
                self.assertEqual(host.show_whats_new.call_count, expected_calls)


class WhatsNewOnceTests(unittest.TestCase):
    def _pending(self, *, app_version: str, pending_version: str):
        from updater import commands

        state = {"pending_version": pending_version, "pending_history": [{"version": pending_version, "notes": "x"}]}
        with (
            patch("config.build_info.APP_VERSION", app_version),
            patch("settings.store.get_whats_new_state", return_value=state),
            patch("settings.store.set_whats_new_seen_version") as seen,
            patch.object(commands, "_in_background", side_effect=lambda _name, target: target()),
        ):
            return commands.pending_whats_new(), seen

    def test_shown_once_for_the_installed_version(self) -> None:
        (version, history), seen = self._pending(app_version="0.14.67", pending_version="0.14.67")

        self.assertEqual(version, "0.14.67")
        self.assertEqual(len(history), 1)
        seen.assert_called_once_with("0.14.67")

    def test_not_shown_while_the_old_version_is_still_running(self) -> None:
        # Нажали «Обновить», но установка не прошла: текст ждёт своей версии.
        (version, history), seen = self._pending(app_version="0.13.67", pending_version="0.14.67")

        self.assertEqual((version, history), ("", []))
        seen.assert_not_called()

    def test_settings_keep_only_well_formed_state(self) -> None:
        from settings.normalize import normalize_updater

        updater = normalize_updater(
            {"skipped_version": " 0.14.67 ", "whats_new": {"pending_version": "0.14.67", "pending_history": [{"a": 1}, "мусор"]}}
        )

        self.assertEqual(updater["skipped_version"], "0.14.67")
        self.assertEqual(updater["whats_new"]["pending_history"], [{"a": 1}])
        self.assertEqual(normalize_updater(None)["whats_new"], {"seen_version": "", "pending_version": "", "pending_history": []})


if __name__ == "__main__":
    unittest.main()
