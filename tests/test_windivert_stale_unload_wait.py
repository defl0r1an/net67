"""Драйвер WinDivert нужно дождаться, а не стартовать поверх него.

Симптом со стороны человека: включил защиту, выключил, включил снова —
и «нихуя не работает». В логе при этом всё хорошо: процесс запущен,
PID выдан, «Пресет успешно запущен».

Причина: после остановки служба драйвера какое-то время висит в
состоянии DELETE_PENDING. Проверка готовности это видела и на первой же
итерации возвращала ready=True со словами «allowing winws2 to perform
the real driver open». winws стартовал поверх ещё живого драйвера,
получал бесполезный дескриптор и трафик не фильтровал.

DELETE_PENDING — состояние временное, его надо переждать. Обход остаётся
только на случай, когда драйвер завис по-настоящему: отказать в запуске
нельзя, иначе кнопка «Включить» перестанет работать совсем.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class _Harness:
    """Подменяет пробы и сон, чтобы тест не ходил в SCM и не ждал."""

    def __init__(self, module, *, stale_for: int, ready_after: int, extra_wait: float = 0.05):
        self.module = module
        self.stale_for = stale_for
        self.ready_after = ready_after
        # Настоящая добавка — 12 секунд. В тесте столько ждать незачем:
        # проверяется сам факт ожидания, а не его длительность.
        self.extra_wait = extra_wait
        self.calls = 0
        self.slept = 0.0
        self._saved = {}

    def __enter__(self):
        m = self.module
        self._saved = {
            "probe": m.probe_windivert_state_runtime,
            "stale": m.find_stale_windivert_delete_pending_services_runtime,
            "sleep": m.time.sleep,
            "extra": m.STALE_DRIVER_UNLOAD_EXTRA_WAIT_SECONDS,
        }
        m.STALE_DRIVER_UNLOAD_EXTRA_WAIT_SECONDS = self.extra_wait

        def probe():
            return m.WinDivertRuntimeProbeResult(
                installed=True,
                ready=self.calls >= self.ready_after,
                error_code=None,
                stage="test",
            )

        def stale():
            self.calls += 1
            return ["Monkey"] if self.calls <= self.stale_for else []

        def sleep(seconds):
            self.slept += float(seconds)

        m.probe_windivert_state_runtime = probe
        m.find_stale_windivert_delete_pending_services_runtime = stale
        m.time.sleep = sleep
        return self

    def __exit__(self, *_exc):
        m = self.module
        m.probe_windivert_state_runtime = self._saved["probe"]
        m.find_stale_windivert_delete_pending_services_runtime = self._saved["stale"]
        m.time.sleep = self._saved["sleep"]
        m.STALE_DRIVER_UNLOAD_EXTRA_WAIT_SECONDS = self._saved["extra"]
        return False


class StaleDriverWaitTests(unittest.TestCase):
    def test_waits_until_the_driver_finishes_unloading(self) -> None:
        import winws_runtime.runtime.system_ops as ops

        with _Harness(ops, stale_for=3, ready_after=3, extra_wait=5.0) as harness:
            result = ops.wait_for_windivert_spawn_ready_runtime(
                max_wait_seconds=5.0,
                poll_interval=0.001,
            )

        self.assertTrue(result.ready)
        self.assertGreater(harness.calls, 1, "проверка вышла на первой же итерации")
        self.assertNotIn("bypassed", str(result.stage), "обход вместо ожидания")

    def test_gives_up_and_starts_anyway_after_the_deadline(self) -> None:
        """Отказать в запуске нельзя — кнопка «Включить» перестанет работать."""
        import winws_runtime.runtime.system_ops as ops

        with _Harness(ops, stale_for=10**6, ready_after=10**6) as harness:
            result = ops.wait_for_windivert_spawn_ready_runtime(
                max_wait_seconds=0.05,
                poll_interval=0.01,
            )

        self.assertTrue(result.ready)
        self.assertIn("stale_delete_pending_bypassed", str(result.stage))
        self.assertGreater(harness.calls, 1)

    def test_clean_driver_returns_immediately(self) -> None:
        import winws_runtime.runtime.system_ops as ops

        with _Harness(ops, stale_for=0, ready_after=0) as harness:
            result = ops.wait_for_windivert_spawn_ready_runtime(
                max_wait_seconds=5.0,
                poll_interval=0.1,
            )

        self.assertTrue(result.ready)
        self.assertEqual(harness.calls, 1)
        self.assertEqual(harness.slept, 0.0)

    def test_extra_wait_is_long_enough_to_be_useful(self) -> None:
        """Пара секунд — обычный срок, но на нагруженной машине бывает дольше."""
        import winws_runtime.runtime.system_ops as ops

        self.assertGreaterEqual(ops.STALE_DRIVER_UNLOAD_EXTRA_WAIT_SECONDS, 5.0)


class WhatsAppPresetCoverageTests(unittest.TestCase):
    """WhatsApp должен работать без VPN от главной кнопки.

    Переписка ходит по TCP с именем в SNI — её ловил профиль по hostlist.
    Но у мессенджера много соединений вообще без SNI, а звонки и медиа
    идут по UDP. Без профилей по списку адресов и по UDP включение
    защиты чинило только чат.
    """

    PRESET = PROJECT_SRC / "presets" / "builtin" / "winws2" / "Стандартный 1.txt"

    def _text(self) -> str:
        return self.PRESET.read_text(encoding="utf-8")

    def test_preset_exists(self) -> None:
        self.assertTrue(self.PRESET.is_file())

    def test_hostlist_profile_is_there(self) -> None:
        self.assertIn("--hostlist=lists/whatsapp.txt", self._text())

    def test_ipset_profile_covers_connections_without_sni(self) -> None:
        text = self._text()

        self.assertIn("--ipset=lists/ipset-whatsapp.txt", text)
        # Имя профиля берётся из каталога, иначе страница «Профили
        # пресета» не сопоставит его со стратегией.
        blocks = [b for b in text.split("--new") if "ipset-whatsapp.txt" in b and "--filter-tcp" in b]
        self.assertTrue(blocks, "нет TCP-профиля WhatsApp по адресам")

    def test_udp_profile_covers_calls_and_media(self) -> None:
        text = self._text()
        blocks = text.split("--new")
        udp = [b for b in blocks if "--name=WhatsApp UDP wide" in b]

        self.assertTrue(udp, "нет UDP-профиля WhatsApp — звонки не заработают")
        block = udp[0]
        self.assertIn("--filter-udp=", block)
        self.assertIn("--ipset=lists/ipset-whatsapp.txt", block)

    def test_udp_ports_are_inside_the_windivert_filter(self) -> None:
        """Профиль не увидит ни пакета, если порты не открыты в заголовке."""
        text = self._text()

        self.assertIn("--wf-udp-out=443-65535", text)

    def test_referenced_lists_are_shipped(self) -> None:
        import re

        repo_root = PROJECT_SRC.parent
        for name in re.findall(r"--(?:hostlist|ipset)=lists/([^\s]+)", self._text()):
            with self.subTest(list=name):
                self.assertTrue(
                    (repo_root / "lists" / name).is_file(),
                    f"список {name} не входит в поставку",
                )


if __name__ == "__main__":
    unittest.main()
