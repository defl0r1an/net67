import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from shell.network_pulse import NetworkPulseWidget
from utils.windows_icmp import WindowsPingResult


class NetworkPulseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_pulse_updates_label_and_color_on_success(self) -> None:
        pulse = NetworkPulseWidget()
        self.addCleanup(pulse.deleteLater)
        self.addCleanup(pulse.cleanup)

        pulse._on_check_finished(True, 32.4)
        self.assertEqual(pulse._label.text(), "32 мс")
        self.assertIn("32 мс", pulse.toolTip())
        self.assertEqual(pulse._dot._color.name().lower(), "#52c477")

    def test_pulse_updates_label_and_color_on_failure(self) -> None:
        pulse = NetworkPulseWidget()
        self.addCleanup(pulse.deleteLater)
        self.addCleanup(pulse.cleanup)

        pulse._on_check_finished(False, 0.0)
        # Не «нет сети»: проверены два адреса, а не вся сеть.
        self.assertEqual(pulse._label.text(), "нет ответа")
        self.assertIn("1.1.1.1 и 8.8.8.8", pulse.toolTip())
        self.assertEqual(pulse._dot._color.name().lower(), "#ff4d4f")

    def test_pulse_monitor_signals_status_change(self) -> None:
        from shell.network_pulse import NetworkPulseMonitor

        monitor = NetworkPulseMonitor(initial_delay_ms=0)
        self.addCleanup(monitor.cleanup)
        events = []
        monitor.statusChanged.connect(lambda ok, rtt: events.append((ok, rtt)))

        monitor._on_check_finished(True, 28.5)
        self.assertTrue(monitor.is_connected)
        self.assertEqual(monitor.latency_ms, 28.5)
        self.assertEqual(events, [(True, 28.5)])

        monitor._on_check_finished(False, 0.0)
        self.assertFalse(monitor.is_connected)
        self.assertEqual(events[-1], (False, 0.0))


class MeasureNetworkPulseTests(unittest.TestCase):
    def test_closed_icmp_falls_back_to_tcp(self) -> None:
        from shell.network_pulse import measure_network_pulse

        calls = []

        def connect(host):
            calls.append(host)
            return 41.0 if host == "8.8.8.8" else None

        # Пинг закрыт, как в корпоративной сети, а соединение проходит.
        self.assertEqual(measure_network_pulse(ping=lambda host: None, connect=connect), (True, 41.0))
        self.assertEqual(calls, ["1.1.1.1", "8.8.8.8"])

    def test_no_answer_only_when_every_probe_failed(self) -> None:
        from shell.network_pulse import measure_network_pulse

        def broken(host):
            raise OSError("сеть недоступна")

        self.assertEqual(measure_network_pulse(ping=lambda host: None, connect=broken), (False, 0.0))
        self.assertEqual(measure_network_pulse(ping=lambda host: 12.0, connect=broken), (True, 12.0))


class TrayNetworkTextTests(unittest.TestCase):
    def _tray(self):
        import tray

        manager = tray.SystemTrayManager.__new__(tray.SystemTrayManager)
        manager.app_version = "0.20.67"
        manager._icon_handle = None
        manager._message_window = None
        manager._network_ok = None
        manager._network_latency_ms = 0.0
        return tray, manager

    def test_before_first_measurement_no_latency_is_shown(self) -> None:
        tray, manager = self._tray()
        self.assertEqual(manager._network_status_text(), "Сеть: проверка…")
        tip = manager._build_notify_icon_data(tray.NIF_TIP).szTip
        self.assertNotIn("мс", tip)

    def test_after_measurement(self) -> None:
        _tray, manager = self._tray()
        manager._network_ok, manager._network_latency_ms = True, 32.4
        self.assertEqual(manager._network_status_text(), "Сеть: 32 мс")
        manager._network_ok = False
        self.assertEqual(manager._network_status_text(), "Сеть: нет ответа от 1.1.1.1 и 8.8.8.8")
