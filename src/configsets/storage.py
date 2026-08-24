"""Хранилище именованных наборов настроек.

Наборы лежат отдельными файлами в подпапке настроек: один файл — одна
конфигурация. Так проще переносить руками и чинить, если что-то пошло не
так, чем если бы всё лежало одним словарём.

Наборы сохраняются без секретов — как и обычная выгрузка. Смысл набора в
том, чтобы переключать режимы работы, а не хранить пароли.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from configsets.plans import ExportOptions, build_export, build_import_patch

CONFIGS_DIR_NAME = "configs"
CONFIG_FILE_SUFFIX = ".net67cfg.json"

_SAFE_NAME_RE = re.compile(r"[^\w \-]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class ConfigSet:
    name: str
    path: Path
    saved_at: float = 0.0
    sections: tuple[str, ...] = ()

    @property
    def saved_at_text(self) -> str:
        if not self.saved_at:
            return ""
        return time.strftime("%d.%m.%Y %H:%M", time.localtime(self.saved_at))


def configs_dir(root: Path | str) -> Path:
    return Path(root) / CONFIGS_DIR_NAME


def normalize_name(name: str) -> str:
    """Имя набора пригодное для имени файла."""
    cleaned = _SAFE_NAME_RE.sub("", str(name or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:48]


def config_path(root: Path | str, name: str) -> Path:
    return configs_dir(root) / f"{normalize_name(name)}{CONFIG_FILE_SUFFIX}"


def list_configs(root: Path | str) -> list[ConfigSet]:
    directory = configs_dir(root)
    if not directory.exists():
        return []

    items: list[ConfigSet] = []
    for path in sorted(directory.glob(f"*{CONFIG_FILE_SUFFIX}")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            # Битый файл не должен прятать остальные наборы.
            continue
        if not isinstance(raw, dict):
            continue

        sections = tuple(sorted((raw.get("sections") or {}).keys()))
        items.append(
            ConfigSet(
                name=str(raw.get("name") or path.name[: -len(CONFIG_FILE_SUFFIX)]),
                path=path,
                saved_at=float(raw.get("saved_at") or 0.0),
                sections=sections,
            )
        )
    return items


def save_config(
    root: Path | str,
    *,
    name: str,
    settings: dict,
    include_secrets: bool = False,
) -> tuple[bool, str]:
    """Сохраняет текущие настройки под именем."""
    clean = normalize_name(name)
    if not clean:
        return (False, "Введите название набора")

    document, report = build_export(
        settings,
        ExportOptions(include_secrets=include_secrets),
    )
    document["name"] = clean
    document["saved_at"] = time.time()

    path = config_path(root, clean)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        return (False, f"Не удалось сохранить набор: {exc}")

    suffix = ""
    if report.redacted:
        suffix = ", учётные данные не сохранялись"
    return (True, f"Набор «{clean}» сохранён{suffix}")


def load_config(path: Path | str) -> tuple[dict | None, str]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        return (None, f"Не удалось прочитать набор: {exc}")
    if not isinstance(raw, dict):
        return (None, "Файл набора повреждён")
    return (raw, "")


def apply_config(path: Path | str, *, current: dict) -> tuple[dict | None, str]:
    """Готовит новые настройки на основе набора."""
    document, message = load_config(path)
    if document is None:
        return (None, message)

    result, report = build_import_patch(document, current=current)
    if not report.ok:
        return (None, report.message or "Набор не удалось применить")

    return (result, f"Применено разделов: {len(report.sections)}")


def delete_config(path: Path | str) -> tuple[bool, str]:
    try:
        Path(path).unlink()
    except FileNotFoundError:
        return (True, "")
    except Exception as exc:
        return (False, f"Не удалось удалить набор: {exc}")
    return (True, "Набор удалён")


__all__ = [
    "CONFIGS_DIR_NAME",
    "CONFIG_FILE_SUFFIX",
    "ConfigSet",
    "apply_config",
    "config_path",
    "configs_dir",
    "delete_config",
    "list_configs",
    "load_config",
    "normalize_name",
    "save_config",
]
