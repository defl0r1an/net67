"""Прокси не поднимается вхолостую, когда Telegram не запущен.

Прокси нужен ради одного действия: открыть ссылку `tg://`, чтобы
мессенджер сам предложил подключиться. Без запущенного Telegram
обработать её некому — прокси висел на порту, человек считал, что всё
сработало, а мессенджер о прокси не знал.

Важна и вторая половина: незапущенный Telegram не должен отменять всё
включение. Обход соединения работает и без него, и откатывать hosts,
DNS и сам движок из-за мессенджера — несоразмерно.
"""

from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class ProcessNameTests(unittest.TestCase):
    def test_official_build_is_recognized(self) -> None:
        from telegram_proxy.presence import is_telegram_process

        self.assertTrue(is_telegram_process("Telegram.exe"))

    def test_case_and_path_do_not_matter(self) -> None:
        """Перечисление процессов отдаёт имена в разном виде."""
        from telegram_proxy.presence import is_telegram_process

        for value in (
            "TELEGRAM.EXE",
            r"C:\Users\user\AppData\Roaming\Telegram Desktop\Telegram.exe",
            '  "Telegram.exe"  ',
        ):
            with self.subTest(value=value):
                self.assertTrue(is_telegram_process(value))

    def test_forks_are_recognized_too(self) -> None:
        """Люди пользуются не только официальной сборкой."""
        from telegram_proxy.presence import is_telegram_process

        for value in ("AyuGram.exe", "64Gram.exe", "Unigram.exe"):
            with self.subTest(value=value):
                self.assertTrue(is_telegram_process(value))

    def test_other_programs_are_not_telegram(self) -> None:
        from telegram_proxy.presence import is_telegram_process

        for value in ("chrome.exe", "winws.exe", "", "telegram"):
            with self.subTest(value=value):
                self.assertFalse(is_telegram_process(value))


class DetectionTests(unittest.TestCase):
    def _running(self, names) -> bool:
        from telegram_proxy.presence import is_telegram_running

        return is_telegram_running(
            iter_processes=lambda: [(index, name) for index, name in enumerate(names)]
        )

    def test_found_among_other_processes(self) -> None:
        self.assertTrue(self._running(["chrome.exe", "Telegram.exe", "winws.exe"]))

    def test_absent_is_absent(self) -> None:
        self.assertFalse(self._running(["chrome.exe", "winws.exe"]))

    def test_empty_process_list_means_not_running(self) -> None:
        self.assertFalse(self._running([]))

    def test_broken_enumeration_assumes_running(self) -> None:
        """Неизвестность трактуем в пользу попытки.

        Если перечислить процессы не удалось, честнее поднять прокси и
        дать человеку увидеть результат, чем отказать со ссылкой на сбой,
        которого он не совершал.
        """
        from telegram_proxy.presence import is_telegram_running

        def broken():
            raise OSError("нет доступа к списку процессов")

        self.assertTrue(is_telegram_running(iter_processes=broken))


@dataclass
class _Deps:
    """Заглушки шагов оркестратора с записью вызовов."""

    calls: list = field(default_factory=list)
    telegram_ready: tuple = (True, "")

    def _op(self, name: str):
        def run(*_args, **_kwargs):
            self.calls.append(name)
            return (True, "")

        return run

    def build(self):
        from oneclick.runner import OneClickDeps

        return OneClickDeps(
            check_conflicts=self._op("check_conflicts"),
            start_dpi=self._op("start_dpi"),
            stop_dpi=self._op("stop_dpi"),
            check_telegram_ready=lambda: self.telegram_ready,
            start_telegram_proxy=self._op("start_telegram_proxy"),
            stop_telegram_proxy=self._op("stop_telegram_proxy"),
            backup_hosts=self._op("backup_hosts"),
            apply_hosts=self._op("apply_hosts"),
            restore_hosts=self._op("restore_hosts"),
            check_dns_integrity=lambda: [],
            apply_dns=self._op("apply_dns"),
            restore_dns=self._op("restore_dns"),
            probe_domains=lambda: (0, ()),
        )


class OrchestratorTests(unittest.TestCase):
    def _run(self, deps: _Deps):
        from oneclick.plans import OneClickRequest
        from oneclick.runner import OneClickRunner

        request = OneClickRequest(needs_telegram_proxy=True, hosts_entries={})
        return OneClickRunner(deps.build()).enable(request)

    def test_proxy_is_not_started_without_telegram(self) -> None:
        deps = _Deps(telegram_ready=(False, "Telegram Desktop не запущен"))

        self._run(deps)

        self.assertNotIn("start_telegram_proxy", deps.calls)

    def test_bypass_still_starts_without_telegram(self) -> None:
        """Мессенджер не должен отменять весь обход."""
        from oneclick.state import OneClickState

        deps = _Deps(telegram_ready=(False, "Telegram Desktop не запущен"))

        outcome = self._run(deps)

        self.assertIs(outcome.state, OneClickState.RUNNING)
        self.assertIn("start_dpi", deps.calls)

    def test_nothing_is_rolled_back(self) -> None:
        """Откат из-за незапущенного мессенджера снял бы и hosts, и DNS."""
        deps = _Deps(telegram_ready=(False, "Telegram Desktop не запущен"))

        self._run(deps)

        for call in ("stop_dpi", "restore_hosts", "restore_dns"):
            with self.subTest(call=call):
                self.assertNotIn(call, deps.calls)

    def test_person_is_told_why(self) -> None:
        """Иначе на экране «Работает», а Telegram по-прежнему не открывается."""
        deps = _Deps(telegram_ready=(False, "Telegram Desktop не запущен"))

        outcome = self._run(deps)

        self.assertIn("Telegram Desktop не запущен", outcome.message)

    def test_redirect_is_announced_before_it_happens(self) -> None:
        """Telegram выпрыгивает поверх работы — предупредить обязаны."""
        from telegram_proxy.presence import REDIRECT_NOTICE

        deps = _Deps(telegram_ready=(True, REDIRECT_NOTICE))
        reported: list[str] = []
        built = deps.build()
        built.report = lambda _state, message: reported.append(str(message))

        from oneclick.plans import OneClickRequest
        from oneclick.runner import OneClickRunner

        OneClickRunner(built).enable(
            OneClickRequest(needs_telegram_proxy=True, hosts_entries={})
        )

        self.assertIn(REDIRECT_NOTICE, reported)

    def test_routine_skips_stay_out_of_the_message(self) -> None:
        """«Подмена DNS не обнаружена» — это в лог, а не на экран.

        Поэтому у шага есть отдельное поле note: в него попадает только
        то, ради чего человек мог нажать кнопку и чего не произошло.
        """
        deps = _Deps(telegram_ready=(True, ""))

        outcome = self._run(deps)

        self.assertEqual(outcome.message, "Работает")


if __name__ == "__main__":
    unittest.main()
