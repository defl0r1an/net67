"""Ядро Xray: запуск, ожидание, остановка.

Ссылки vless, vmess, trojan и ss поднимает не AmneziaWG, а отдельное
ядро. Тесты держат три решения, каждое из которых стоило бы дорого,
если бы его приняли иначе.

Локальный прокси вместо системного туннеля: туннель — это драйвер,
права администратора и конфликт с WinDivert, который в то же время
держит обход DPI.

Конфигурация файлом, а не аргументами командной строки: половина
параметров приходит в самой ссылке, и разбирать их в аргументы значило
бы поддерживать чужой формат целиком.

Ожидание порта, а не «процесс создан»: Popen возвращает объект сразу, а
слушатель поднимается позже. Ровно на этом уже обжигался прокси
Telegram — на экране «работает», в действительности ничего.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


class _Profile:
    """Подделка LinkProfile. Поля те же, что у настоящего.

    Адрес и порт добавлены не для удобства: конфиг ядра берёт их
    оттуда, и без них подделка перестала бы изображать то, что
    изображает.
    """

    def __init__(
        self,
        scheme: str = "vless",
        raw: str = "vless://uuid@example.org:443",
        host: str = "example.org",
        port: int = 443,
    ):
        self.scheme = scheme
        self.raw = raw
        self.host = host
        self.port = port


class ConfigTests(unittest.TestCase):
    def _config(self, profile=None, **kwargs):
        from vpn.xray import build_config

        return build_config(profile or _Profile(), **kwargs)

    def test_proxy_listens_only_on_loopback(self) -> None:
        """Слушать наружу значило бы отдать прокси всей сети."""
        inbound = self._config()["inbounds"][0]

        self.assertEqual(inbound["listen"], "127.0.0.1")

    def test_port_is_not_a_common_one(self) -> None:
        """1080 и 8080 заняты половиной программ.

        Попасть в чужой слушающий порт значило бы считать чужую службу
        своим ядром и рапортовать о подключении, которого нет.
        """
        from vpn.xray import LOCAL_PORT

        self.assertNotIn(LOCAL_PORT, {1080, 8080, 8888, 9050})

    def test_link_parameters_reach_the_core(self) -> None:
        """Раньше ссылка уходила в конфиг целиком, полем _link.

        Так и было задумано — «пересобирать из частей значит потерять
        неизвестный параметр», — но ядро такого поля не знает и просто
        его игнорирует. Конфиг без адреса и идентификатора не поднимает
        соединение вообще, а на странице это выглядит как «ядро
        запустилось и тут же умерло».

        Поэтому параметры теперь разбираются: reality с именем сервера,
        flow для vless, адрес и порт узла.
        """
        link = "vless://uuid@example.org:443?security=reality&sni=a.b&flow=xtls-rprx-vision"
        outbound = self._config(_Profile(raw=link, scheme="vless", host="example.org", port=443))["outbounds"][0]

        self.assertEqual(outbound["protocol"], "vless")

        server = outbound["settings"]["vnext"][0]
        self.assertEqual(server["address"], "example.org")
        self.assertEqual(server["port"], 443)
        self.assertEqual(server["users"][0]["id"], "uuid")
        self.assertEqual(server["users"][0]["flow"], "xtls-rprx-vision")

        stream = outbound["streamSettings"]
        self.assertEqual(stream["security"], "reality")
        self.assertEqual(stream["realitySettings"]["serverName"], "a.b")

    def test_udp_is_allowed(self) -> None:
        """Без него не работают ни звонки, ни игры."""
        self.assertTrue(self._config()["inbounds"][0]["settings"]["udp"])

    def test_core_log_is_quiet(self) -> None:
        """На уровне info ядро пишет каждое соединение — десятки строк в секунду."""
        self.assertEqual(self._config()["log"]["loglevel"], "warning")

    def test_config_is_written_as_readable_json(self) -> None:
        from vpn.xray import write_config

        with TemporaryDirectory() as directory:
            path = write_config(_Profile(), Path(directory))

            self.assertTrue(path.is_file())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["inbounds"][0]["protocol"], "socks")


class WaitTests(unittest.TestCase):
    def test_returns_as_soon_as_the_port_answers(self) -> None:
        from vpn.xray import wait_until_listening

        self.assertTrue(wait_until_listening(probe=lambda: True))

    def test_gives_up_after_the_deadline(self) -> None:
        """Не поднялось за полторы секунды — не поднимется."""
        from vpn.xray import wait_until_listening

        self.assertFalse(wait_until_listening(timeout_s=0.15, probe=lambda: False))

    def test_deadline_is_short_enough_to_not_feel_like_a_freeze(self) -> None:
        from vpn.xray import STARTUP_TIMEOUT_S

        self.assertLessEqual(STARTUP_TIMEOUT_S, 3.0)

    def test_port_probe_survives_a_closed_port(self) -> None:
        from vpn.xray import is_port_open

        # Порт заведомо свободен: проверка обязана ответить «нет», а не
        # уронить приложение исключением сокета.
        self.assertFalse(is_port_open(59999))


class RuntimeTests(unittest.TestCase):
    def _runtime(self, root=None):
        from vpn.xray import XrayRuntime

        return XrayRuntime(root=root)

    class _Process:
        def __init__(self):
            self.terminated = False
            self.killed = False
            self._alive = True

        def poll(self):
            return None if self._alive else 0

        def terminate(self):
            self.terminated = True
            self._alive = False

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self.killed = True
            self._alive = False

    def test_missing_core_says_where_to_put_it(self) -> None:
        """«Ошибка запуска» без адреса — это тупик для человека."""
        from vpn.xray import XrayError

        runtime = self._runtime(root=Path("/несуществующая/папка"))

        with TemporaryDirectory() as directory:
            with self.assertRaises(XrayError) as caught:
                runtime.start(_Profile(), settings_dir=Path(directory))

        self.assertIn("bin", str(caught.exception))

    def test_start_writes_config_and_spawns(self) -> None:
        process = self._Process()
        spawned = []

        def spawn(core, config):
            spawned.append((core, config))
            return process

        runtime = self._runtime(root=Path("/любая"))
        with TemporaryDirectory() as directory:
            runtime.start(_Profile(), settings_dir=Path(directory), spawn=spawn)

            self.assertTrue(runtime.is_running)
            self.assertEqual(len(spawned), 1)
            self.assertTrue(Path(spawned[0][1]).is_file())

    def test_stop_terminates_the_process(self) -> None:
        process = self._Process()
        runtime = self._runtime(root=Path("/любая"))

        with TemporaryDirectory() as directory:
            runtime.start(_Profile(), settings_dir=Path(directory), spawn=lambda *_: process)
            runtime.stop()

        self.assertTrue(process.terminated)
        self.assertFalse(runtime.is_running)

    def test_second_start_replaces_the_first(self) -> None:
        """Два ядра на одном порту — второе просто не поднимется."""
        first, second = self._Process(), self._Process()
        processes = [first, second]
        runtime = self._runtime(root=Path("/любая"))

        with TemporaryDirectory() as directory:
            runtime.start(
                _Profile(), settings_dir=Path(directory), spawn=lambda *_: processes.pop(0)
            )
            runtime.start(
                _Profile(), settings_dir=Path(directory), spawn=lambda *_: processes.pop(0)
            )

        self.assertTrue(first.terminated)
        self.assertTrue(runtime.is_running)

    def test_stop_without_start_is_not_an_error(self) -> None:
        self._runtime().stop()


class AvailabilityTests(unittest.TestCase):
    def test_core_is_looked_for_next_to_the_program(self) -> None:
        from vpn.xray import core_path

        path = core_path(Path("/корень"))

        self.assertEqual(path.parts[-3:], ("bin", "xray", "xray.exe"))

    def test_missing_core_is_reported_not_raised(self) -> None:
        """Страница VPN обязана открыться и без ядра, просто без подключения."""
        from vpn.xray import is_core_available

        self.assertFalse(is_core_available(Path("/нет/такой/папки")))


if __name__ == "__main__":
    unittest.main()
