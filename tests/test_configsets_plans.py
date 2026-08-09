from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))


def _settings() -> dict:
    return {
        "version": 1,
        "program": {"dpi_autostart": True},
        "appearance": {"theme": "dark"},
        "telegram_proxy": {
            "enabled": True,
            "upstream_user": "operator",
            "upstream_pass": "s3cret",
            "mtproxy_secret": "deadbeef",
        },
        "hosts": {"selection": {"a": "b"}, "bootstrap_signature": "v3", "active_domains": ["x"]},
        "dns": {"force_dns_enabled": True, "dns_crash_count": 7},
        "window": {"geometry": "1920x1080"},
        "premium": {"device_id": "ABC-123"},
    }


class ExportSecretTests(unittest.TestCase):
    def test_secrets_are_redacted_by_default(self) -> None:
        """Выгрузка настроек не должна рассылать пароли."""
        from configsets.plans import build_export

        document, report = build_export(_settings())
        proxy = document["sections"]["telegram_proxy"]

        self.assertEqual(proxy["upstream_pass"], "")
        self.assertEqual(proxy["mtproxy_secret"], "")
        self.assertTrue(report.has_redactions)
        self.assertIn("telegram_proxy.upstream_pass", report.redacted)

    def test_secrets_can_be_included_explicitly(self) -> None:
        from configsets.plans import ExportOptions, build_export

        document, report = build_export(_settings(), ExportOptions(include_secrets=True))

        self.assertEqual(document["sections"]["telegram_proxy"]["upstream_pass"], "s3cret")
        self.assertFalse(report.has_redactions)

    def test_document_marks_whether_it_holds_secrets(self) -> None:
        """Получатель файла должен понимать, что внутри."""
        from configsets.plans import ExportOptions, build_export

        plain, _ = build_export(_settings())
        secret, _ = build_export(_settings(), ExportOptions(include_secrets=True))

        self.assertFalse(plain["contains_secrets"])
        self.assertTrue(secret["contains_secrets"])

    def test_non_secret_fields_survive_redaction(self) -> None:
        from configsets.plans import build_export

        document, _ = build_export(_settings())

        self.assertTrue(document["sections"]["telegram_proxy"]["enabled"])


class ExportScopeTests(unittest.TestCase):
    def test_machine_specific_sections_are_dropped(self) -> None:
        from configsets.plans import build_export

        document, report = build_export(_settings())

        self.assertNotIn("window", document["sections"])
        self.assertNotIn("premium", document["sections"])
        self.assertIn("window", report.skipped_sections)

    def test_machine_specific_fields_are_dropped(self) -> None:
        """Подпись hosts и счётчик сбоев DNS относятся к этой машине."""
        from configsets.plans import build_export

        document, _ = build_export(_settings())

        self.assertNotIn("bootstrap_signature", document["sections"]["hosts"])
        self.assertNotIn("dns_crash_count", document["sections"]["dns"])
        self.assertIn("selection", document["sections"]["hosts"])

    def test_selected_sections_only(self) -> None:
        from configsets.plans import ExportOptions, build_export

        document, _ = build_export(_settings(), ExportOptions(sections=frozenset({"appearance"})))

        self.assertEqual(list(document["sections"]), ["appearance"])

    def test_portable_sections_exclude_machine_specific(self) -> None:
        from configsets.plans import portable_sections

        names = portable_sections(_settings())

        self.assertNotIn("window", names)
        self.assertNotIn("version", names)
        self.assertIn("program", names)


class ValidationTests(unittest.TestCase):
    def test_foreign_file_is_rejected(self) -> None:
        from configsets.plans import validate_document

        ok, message = validate_document({"format": "something-else"})

        self.assertFalse(ok)
        self.assertIn("не файл конфигурации", message)

    def test_non_dict_is_rejected(self) -> None:
        from configsets.plans import validate_document

        self.assertFalse(validate_document(["не словарь"])[0])

    def test_newer_format_is_refused_with_explanation(self) -> None:
        from configsets.plans import CONFIG_FORMAT_VERSION, validate_document

        ok, message = validate_document(
            {"format": "net67-config", "format_version": CONFIG_FORMAT_VERSION + 5, "sections": {}}
        )

        self.assertFalse(ok)
        self.assertIn("более новой версией", message)

    def test_missing_sections_is_rejected(self) -> None:
        from configsets.plans import validate_document

        self.assertFalse(validate_document({"format": "net67-config", "format_version": 1})[0])

    def test_own_export_passes_validation(self) -> None:
        from configsets.plans import build_export, validate_document

        document, _ = build_export(_settings())

        self.assertTrue(validate_document(document)[0])


class ImportTests(unittest.TestCase):
    def test_import_applies_sections(self) -> None:
        from configsets.plans import build_export, build_import_patch

        document, _ = build_export(_settings())
        current = _settings()
        current["appearance"]["theme"] = "light"

        result, report = build_import_patch(document, current=current)

        self.assertTrue(report.ok)
        self.assertEqual(result["appearance"]["theme"], "dark")

    def test_redacted_secret_does_not_erase_working_password(self) -> None:
        """Главная ловушка: импорт обезличенного файла затёр бы пароль."""
        from configsets.plans import build_export, build_import_patch

        document, _ = build_export(_settings())
        result, _ = build_import_patch(document, current=_settings())

        self.assertEqual(result["telegram_proxy"]["upstream_pass"], "s3cret")

    def test_explicit_secret_is_applied(self) -> None:
        from configsets.plans import ExportOptions, build_export, build_import_patch

        document, _ = build_export(_settings(), ExportOptions(include_secrets=True))
        current = _settings()
        current["telegram_proxy"]["upstream_pass"] = "старый"

        result, _ = build_import_patch(document, current=current)

        self.assertEqual(result["telegram_proxy"]["upstream_pass"], "s3cret")

    def test_machine_specific_sections_are_not_imported(self) -> None:
        from configsets.plans import ExportOptions, build_export, build_import_patch

        document, _ = build_export(_settings(), ExportOptions(include_machine_specific=True))
        current = _settings()
        current["window"]["geometry"] = "800x600"

        result, report = build_import_patch(document, current=current)

        self.assertEqual(result["window"]["geometry"], "800x600")
        self.assertIn("window", report.ignored)

    def test_unknown_sections_are_reported_not_applied(self) -> None:
        from configsets.plans import build_import_patch

        document = {
            "format": "net67-config",
            "format_version": 1,
            "sections": {"выдуманный": {"a": 1}, "appearance": {"theme": "dark"}},
        }
        result, report = build_import_patch(document, current=_settings())

        self.assertNotIn("выдуманный", result)
        self.assertIn("выдуманный", report.ignored)

    def test_invalid_document_leaves_settings_untouched(self) -> None:
        from configsets.plans import build_import_patch

        current = _settings()
        result, report = build_import_patch({"format": "чужой"}, current=current)

        self.assertFalse(report.ok)
        self.assertEqual(result, current)

    def test_empty_import_is_reported_as_failure(self) -> None:
        from configsets.plans import build_import_patch

        document = {"format": "net67-config", "format_version": 1, "sections": {}}
        _result, report = build_import_patch(document, current=_settings())

        self.assertFalse(report.ok)
        self.assertIn("нет разделов", report.message)


class DescribeTests(unittest.TestCase):
    def test_description_mentions_redaction(self) -> None:
        from configsets.plans import build_export, describe_export

        _document, report = build_export(_settings())

        self.assertIn("вырезан", describe_export(report).lower())


if __name__ == "__main__":
    unittest.main()
