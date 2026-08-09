"""Шаг прокси Telegram в «одной кнопке».

Кнопка «Включить» стабильно показывала «Не удалось запустить прокси для
Telegram», а после нажатия «Повторить» прокси оказывался поднят. Причин
было две, и обе в том, как читался результат:

* start_proxy_if_enabled_async только ставит запуск в отдельный поток —
  её True означает «отправлено», а не «работает»;
* она возвращает False, если прокси уже запущен, и это принималось за
  неудачу.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

DEPS = PROJECT_SRC / "oneclick" / "deps.py"


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(DEPS.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"в deps.py нет функции {name}")


class TelegramProxyStepTests(unittest.TestCase):
    def test_step_checks_real_state_not_dispatch_result(self) -> None:
        source = ast.unparse(_function("_start_telegram_proxy"))

        self.assertIn("_is_telegram_proxy_running", source)
        self.assertNotIn(
            "started = bool(start_proxy_if_enabled_async())",
            source,
            "результат постановки в очередь снова принимается за успех",
        )

    def test_already_running_is_success(self) -> None:
        """Работающий прокси — не повод для ошибки."""
        source = ast.unparse(_function("_start_telegram_proxy"))

        # Запуск и ожидание идут только когда прокси ещё не поднят.
        self.assertIn("if not _is_telegram_proxy_running():", source)
        # А ссылка Telegram открывается в обоих случаях.
        self.assertIn("_open_telegram_proxy_deeplink()", source)

    def test_deeplink_is_offered_after_start(self) -> None:
        """Прокси без ссылки бесполезен: Telegram о нём не узнает."""
        source = ast.unparse(_function("_open_telegram_proxy_deeplink"))

        self.assertIn("build_proxy_url", source)
        self.assertIn("consume_auto_deeplink_request", source)

    def test_wait_is_bounded(self) -> None:
        """Ждём поднятия слушателя, но не бесконечно."""
        source = ast.unparse(_function("_start_telegram_proxy"))

        self.assertIn("monotonic", source)
        self.assertIn("5.0", source)


class HostsStepTypeTests(unittest.TestCase):
    """Блок hosts переписывает тот, кто знает полный список.

    Сначала шаг отдавал «домен -> адрес» в apply_service_profiles: домены
    принимались за имена сервисов, адреса за названия профилей, и
    включение падало с «Не найдено записей hosts для выбранных сервисов».
    Поле переименовали в hosts_entries, а вызов заменили на парный.

    Потом выяснилось, что и это не то. Запись в hosts не дописывает, а
    заменяет управляемый блок целиком, поэтому «Включить» с его 501
    записью стирал полторы тысячи, поставленных при установке. Теперь шаг
    переприменяет сохранённый выбор сервисов — ровно то, что показано
    тумблерами на странице «Сервисы».
    """

    def test_apply_hosts_reapplies_saved_selection(self) -> None:
        source = ast.unparse(_function("_apply_hosts"))

        self.assertIn("load_user_selection", source)
        self.assertIn("apply_service_profiles", source)
        self.assertNotIn("apply_domain_ip_entries", source)

    def test_request_field_is_named_after_its_content(self) -> None:
        from oneclick.plans import OneClickRequest

        request = OneClickRequest()
        self.assertTrue(hasattr(request, "hosts_entries"))
        self.assertFalse(
            hasattr(request, "hosts_profiles"),
            "старое имя вернулось — оно и приглашало перепутать типы",
        )

    def test_hosts_command_exists_and_is_exported(self) -> None:
        from hosts.public import apply_domain_ip_entries

        self.assertTrue(callable(apply_domain_ip_entries))

    def test_wizard_builds_domain_to_ip_pairs(self) -> None:
        """Значения должны быть адресами, а не именами профилей."""
        from wizard.plans import build_hosts_entries

        entries = build_hosts_entries(["ai"])
        if not entries:
            self.skipTest("каталог hosts недоступен")

        for host, ip in entries.items():
            with self.subTest(host):
                self.assertIn(".", host)
                # Адрес: цифры и точки либо двоеточия IPv6.
                self.assertTrue(
                    all(ch.isdigit() or ch in ".:abcdefABCDEF" for ch in ip),
                    f"{ip} не похож на адрес",
                )


if __name__ == "__main__":
    unittest.main()
