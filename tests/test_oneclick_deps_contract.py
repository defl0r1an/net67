"""Контракт обвязки «одной кнопки» с реальными API приложения.

Смысл теста: oneclick/deps.py — единственное место, где оркестратор
встречается с системой, и проверить его вживую нельзя (нужны Windows,
права администратора и настоящая сеть). Поэтому сверяем хотя бы то, что
вызываемые функции и методы вообще существуют и принимают те аргументы,
которые мы передаём.

Именно так был пойман вызов несуществующего manager.stop() вместо
stop_proxy().
"""

from __future__ import annotations

import ast
import inspect
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_SRC = PROJECT_ROOT / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

DEPS_PATH = PROJECT_SRC / "oneclick" / "deps.py"


def _accepts(func, *names: str) -> bool:
    """Принимает ли функция такие именованные аргументы."""
    signature = inspect.signature(func)
    params = signature.parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return True
    return all(name in params for name in names)


class OneClickDepsBuildTests(unittest.TestCase):
    def test_deps_cover_every_runner_field(self) -> None:
        """Ни одно поле OneClickDeps не должно остаться незаполненным."""
        import dataclasses

        from oneclick.deps import build_oneclick_deps
        from oneclick.runner import OneClickDeps

        class _FakeRuntime:
            def is_any_running(self, *, silent: bool = True) -> bool:
                return False

            def start(self, *_a, **_kw) -> bool:
                return True

            def stop(self, *_a, **_kw) -> bool:
                return True

        deps = build_oneclick_deps(runtime_feature=_FakeRuntime())

        for field in dataclasses.fields(OneClickDeps):
            value = getattr(deps, field.name)
            if field.name == "report":
                continue
            self.assertTrue(callable(value), f"{field.name} не заполнено вызываемым объектом")


class OneClickDepsSignatureTests(unittest.TestCase):
    def test_runtime_feature_supports_used_calls(self) -> None:
        from app.feature_facades.runtime import RuntimeFeature

        self.assertTrue(_accepts(RuntimeFeature.start, "skip_conflict_prompt"))
        self.assertTrue(hasattr(RuntimeFeature, "stop"))
        self.assertTrue(_accepts(RuntimeFeature.is_any_running, "silent"))

    def test_hosts_api_exposes_used_functions(self) -> None:
        import hosts.public as hosts_public

        for name in ("read_hosts_file", "write_hosts_file", "apply_service_profiles", "create_hosts_runtime"):
            self.assertTrue(hasattr(hosts_public, name), f"hosts.public.{name} отсутствует")

    def test_telegram_proxy_api_exposes_used_functions(self) -> None:
        import telegram_proxy.public as proxy_public

        self.assertTrue(hasattr(proxy_public, "set_enabled"))
        self.assertTrue(hasattr(proxy_public, "start_proxy_if_enabled_async"))

    def test_proxy_manager_has_stop_proxy_not_stop(self) -> None:
        """Регрессия: обвязка звала manager.stop(), которого нет."""
        from telegram_proxy.manager import TelegramProxyManager

        self.assertTrue(hasattr(TelegramProxyManager, "stop_proxy"))

    @unittest.skipUnless(
        sys.platform == "win32",
        "dns.dns_core использует ctypes.windll и импортируется только на Windows",
    )
    def test_dns_manager_supports_used_calls(self) -> None:
        from dns.dns_force import DNSForceManager

        self.assertTrue(_accepts(DNSForceManager.get_network_adapters, "include_disconnected"))
        self.assertTrue(_accepts(DNSForceManager.disable_force_dns, "reset_to_auto", "adapters"))
        self.assertTrue(hasattr(DNSForceManager, "set_dns_for_adapter"))

    def test_probe_and_integrity_helpers_exist(self) -> None:
        from blockcheck.dns_integrity import check_dns_integrity
        from blockcheck.tcp_test import probe_tcp_target_health

        self.assertTrue(callable(check_dns_integrity))
        self.assertTrue(_accepts(probe_tcp_target_health, "timeout"))


class OneClickDepsIsolationTests(unittest.TestCase):
    def test_pure_modules_do_not_import_system_apis(self) -> None:
        """plans.py и runner.py обязаны оставаться тестируемыми без Windows."""
        forbidden = ("hosts", "dns", "telegram_proxy", "blockcheck", "app", "PyQt6")

        for name in ("plans.py", "runner.py", "state.py"):
            source = (PROJECT_SRC / "oneclick" / name).read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                module = ""
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                elif isinstance(node, ast.Import):
                    module = node.names[0].name
                root = module.split(".")[0]
                self.assertNotIn(
                    root,
                    forbidden,
                    f"{name} импортирует {module} — чистый слой должен остаться без системных зависимостей",
                )


if __name__ == "__main__":
    unittest.main()
