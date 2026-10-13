# configsets/ui/page.py
"""Страница «Конфигурации»: наборы настроек, перенос и правка файла.

После любой записи настроек — набор, файл или редактор — страница отдаёт
системе то, что живёт вне settings.json (hosts, автозапуск), и сообщает в
колокольчик, что остальное вступит в силу после перезапуска, с кнопкой
«Перезапустить» (app/restart.py).
"""

from __future__ import annotations

import json
import threading

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CheckBox,
    ComboBox,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    TextEdit,
)

from log.log import log
from ui.accessibility import set_control_accessibility
from ui.pages.base_page import BasePage
from ui.theme import get_theme_tokens

from configsets.plans import (
    ExportOptions,
    build_export,
    build_import_patch,
    describe_export,
    plan_preset_import,
    post_apply_actions,
    validate_document,
)
from configsets.storage import (
    apply_config,
    delete_config,
    list_configs,
    read_preset_files,
    save_config,
    user_presets_dir,
    write_preset_files,
)


from configsets import CONFIGS_READY


def _settings_root():
    from config.runtime_layout import APPLICATION_PATHS

    return APPLICATION_PATHS.settings_dir


#: Что читается один раз при запуске и потому ждёт перезапуска.
RESTART_NOTE = "Оформление, поведение трея и выбранный пресет вступят в силу после перезапуска net67."


class _EffectsBridge(QObject):
    """Доставляет итог фонового применения обратно в поток окна."""

    finished = pyqtSignal(str, list)


class ConfigsPage(BasePage):
    """Именованные наборы, экспорт-импорт и редактор настроек."""

    def __init__(self, parent=None):
        super().__init__(
            "Конфигурации",
            "Наборы настроек, перенос на другие компьютеры и правка файла",
            parent,
            title_key="page.configs.title",
            subtitle_key="page.configs.subtitle",
        )
        self._items = []
        self._effects_bridge = _EffectsBridge(self)
        self._effects_bridge.finished.connect(self._on_effects_finished)
        if not CONFIGS_READY:
            # Честная надпись дешевле, чем человек, решивший, что сохранил
            # настройки, которых нет.
            wip = StrongBodyLabel("Раздел в разработке и пока не работает.")
            wip.setWordWrap(True)
            self.add_widget(wip)
            return
        self._build_ui()
        self._reload()

    # ──────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        tokens = get_theme_tokens()

        # ── Наборы ────────────────────────────────────────────────────
        self.add_widget(StrongBodyLabel("Наборы настроек"))

        hint = BodyLabel(
            "Сохраните текущие настройки под именем и переключайтесь между "
            "ними — например «офис» и «мобильный интернет»."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"QLabel {{ color: {tokens.fg_muted}; }}")
        self.add_widget(hint)

        save_row = QHBoxLayout()
        save_row.setSpacing(8)
        self.name_edit = LineEdit()
        self.name_edit.setPlaceholderText("Название набора")
        set_control_accessibility(
            self.name_edit,
            name="Название набора настроек",
            description="Под этим именем будут сохранены текущие настройки",
        )
        save_row.addWidget(self.name_edit, 1)

        self.save_btn = PrimaryPushButton("Сохранить текущие")
        self.save_btn.clicked.connect(self._on_save)
        save_row.addWidget(self.save_btn)
        self._add_row(save_row)

        apply_row = QHBoxLayout()
        apply_row.setSpacing(8)
        self.sets_combo = ComboBox()
        set_control_accessibility(
            self.sets_combo,
            name="Сохранённые наборы",
            description="Выбор набора для применения",
        )
        apply_row.addWidget(self.sets_combo, 1)

        self.apply_btn = PushButton("Применить")
        self.apply_btn.clicked.connect(self._on_apply)
        apply_row.addWidget(self.apply_btn)

        self.delete_btn = PushButton("Удалить")
        self.delete_btn.clicked.connect(self._on_delete)
        apply_row.addWidget(self.delete_btn)
        self._add_row(apply_row)

        self.sets_info = BodyLabel("")
        self.sets_info.setWordWrap(True)
        self.sets_info.setStyleSheet(f"QLabel {{ color: {tokens.fg_faint}; font-size: 12px; }}")
        self.add_widget(self.sets_info)

        self.add_spacing(20)

        # ── Перенос ───────────────────────────────────────────────────
        self.add_widget(StrongBodyLabel("Перенос на другой компьютер"))

        transfer_hint = BodyLabel(
            "Настройте один компьютер, выгрузите файл и примените его на "
            "остальных. Настройки этого компьютера — размер окна и "
            "состояние файла hosts — в файл не попадают."
        )
        transfer_hint.setWordWrap(True)
        transfer_hint.setStyleSheet(f"QLabel {{ color: {tokens.fg_muted}; }}")
        self.add_widget(transfer_hint)

        self.secrets_box = CheckBox("Включить пароли и секреты прокси")
        set_control_accessibility(
            self.secrets_box,
            name="Включить пароли в файл",
            description="По умолчанию учётные данные вырезаются из файла",
        )
        self.add_widget(self.secrets_box)

        secrets_warning = BodyLabel(
            "Без этой галочки пароль апстрим-прокси и секрет MTProxy в файл "
            "не попадут. Включайте только если файл никуда не уйдёт."
        )
        secrets_warning.setWordWrap(True)
        secrets_warning.setStyleSheet(f"QLabel {{ color: {tokens.fg_faint}; font-size: 12px; }}")
        self.add_widget(secrets_warning)

        transfer_row = QHBoxLayout()
        transfer_row.setSpacing(8)
        self.export_btn = PushButton("Выгрузить в файл")
        self.export_btn.clicked.connect(self._on_export)
        transfer_row.addWidget(self.export_btn)

        self.import_btn = PushButton("Загрузить из файла")
        self.import_btn.clicked.connect(self._on_import)
        transfer_row.addWidget(self.import_btn)
        transfer_row.addStretch()
        self._add_row(transfer_row)

        self.add_spacing(20)

        # ── Редактор ──────────────────────────────────────────────────
        self.add_widget(StrongBodyLabel("Файл настроек"))

        editor_hint = BodyLabel(
            "Прямая правка. Перед сохранением проверяется формат JSON, а "
            "значения проходят ту же проверку, что и обычные настройки: "
            "недопустимое будет заменено на значение по умолчанию."
        )
        editor_hint.setWordWrap(True)
        editor_hint.setStyleSheet(f"QLabel {{ color: {tokens.fg_muted}; }}")
        self.add_widget(editor_hint)

        self.editor = TextEdit(self.content)
        self.editor.setMinimumHeight(260)
        set_control_accessibility(
            self.editor,
            name="Файл настроек",
            description="Содержимое settings.json в формате JSON",
        )
        self.add_widget(self.editor)

        editor_row = QHBoxLayout()
        editor_row.setSpacing(8)
        self.reload_btn = PushButton("Перечитать")
        self.reload_btn.clicked.connect(self._load_editor)
        editor_row.addWidget(self.reload_btn)

        self.save_editor_btn = PushButton("Сохранить изменения")
        self.save_editor_btn.clicked.connect(self._on_save_editor)
        editor_row.addWidget(self.save_editor_btn)
        editor_row.addStretch()
        self._add_row(editor_row)

    def _add_row(self, layout: QHBoxLayout) -> None:
        holder = QWidget(self.content)
        wrapper = QVBoxLayout(holder)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.addLayout(layout)
        self.add_widget(holder)

    # ──────────────────────────────────────────────────────────────────

    def _current_settings(self) -> dict:
        from settings.store import read_settings

        return read_settings()

    def _write_settings(self, data: dict) -> tuple[bool, str]:
        """Записывает настройки через нормализацию.

        Прямая запись в файл недопустима: кривой или враждебный конфиг
        испортил бы состояние приложения. Нормализация выбрасывает
        лишнее и подставляет значения по умолчанию.
        """
        try:
            from settings.normalize import normalize_settings
            from settings.store import replace_settings

            normalize_settings(data)
        except Exception as exc:
            return (False, f"Настройки не прошли проверку: {exc}")

        try:
            replace_settings(data)
        except Exception as exc:
            return (False, f"Не удалось сохранить настройки: {exc}")
        return (True, "")

    def _reload(self) -> None:
        self._items = list_configs(_settings_root())
        self.sets_combo.blockSignals(True)
        self.sets_combo.clear()
        for item in self._items:
            self.sets_combo.addItem(item.name)
        self.sets_combo.blockSignals(False)

        has = bool(self._items)
        self.apply_btn.setEnabled(has)
        self.delete_btn.setEnabled(has)
        self.sets_info.setText(
            "Наборы не сохранены" if not has else f"Сохранено наборов: {len(self._items)}"
        )
        self._load_editor()

    def _selected(self):
        index = self.sets_combo.currentIndex()
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def _load_editor(self) -> None:
        try:
            text = json.dumps(self._current_settings(), ensure_ascii=False, indent=2)
        except Exception as exc:
            text = f"Не удалось прочитать настройки: {exc}"
        self.editor.setPlainText(text)

    # ──────────────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        ok, message = save_config(
            _settings_root(),
            name=self.name_edit.text(),
            settings=self._current_settings(),
            include_secrets=self.secrets_box.isChecked(),
        )
        if not ok:
            self._error(message)
            return
        self.name_edit.clear()
        self._reload()
        self._success(message)

    def _on_apply(self) -> None:
        item = self._selected()
        if item is None:
            return

        before = self._current_settings()
        result, message = apply_config(item.path, current=before)
        if result is None:
            self._error(message)
            return

        written, write_message = self._write_settings(result)
        if not written:
            self._error(write_message)
            return

        self._load_editor()
        self._apply_in_system(before, message)

    def _on_delete(self) -> None:
        item = self._selected()
        if item is None:
            return
        ok, message = delete_config(item.path)
        if not ok:
            self._error(message)
            return
        self._reload()
        self._success(message or "Набор удалён")

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить конфигурацию",
            "net67-config.json",
            "Конфигурация net67 (*.json)",
        )
        if not path:
            return

        document, report = build_export(
            self._current_settings(),
            ExportOptions(include_secrets=self.secrets_box.isChecked()),
            presets=read_preset_files(user_presets_dir()),
        )
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            self._error(f"Не удалось сохранить файл: {exc}")
            return

        self._success(describe_export(report))

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл конфигурации",
            "",
            "Конфигурация net67 (*.json);;Все файлы (*.*)",
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as handle:
                document = json.load(handle)
        except Exception as exc:
            self._error(f"Не удалось прочитать файл: {exc}")
            return

        valid, message = validate_document(document)
        if not valid:
            self._error(message)
            return

        before = self._current_settings()
        presets_dir = user_presets_dir()
        plan = plan_preset_import(document, existing=read_preset_files(presets_dir))
        result, report = build_import_patch(document, current=before, renamed_presets=plan.renamed)
        if not report.ok:
            self._error(report.message)
            return

        # Пресеты — раньше настроек: настройки могут указывать на пресет из
        # файла, и в момент записи он уже должен лежать в папке.
        failed = write_preset_files(presets_dir, plan.writes)
        written, write_message = self._write_settings(result)
        if not written:
            self._error(write_message)
            return

        self._reload()
        parts = [f"Применено разделов: {len(report.sections)}"]
        if plan.writes:
            parts.append(f"своих пресетов: {len(plan.writes) - len(failed)}")
        if plan.renamed:
            names = ", ".join(f"«{new}»" for new in plan.renamed.values())
            parts.append(f"пресеты с теми же именами здесь не тронуты, файловые легли рядом: {names}")
        if failed or plan.rejected:
            parts.append(f"не записаны: {', '.join(sorted(set(failed) | set(plan.rejected)))}")
        if report.ignored:
            parts.append(f"пропущено: {', '.join(report.ignored)}")
        self._apply_in_system(before, ". ".join(parts))

    def _on_save_editor(self) -> None:
        raw = self.editor.toPlainText()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            self._error(f"Ошибка в JSON, строка {exc.lineno}: {exc.msg}")
            return

        if not isinstance(data, dict):
            self._error("Настройки должны быть объектом JSON")
            return

        before = self._current_settings()
        written, message = self._write_settings(data)
        if not written:
            self._error(message)
            return

        self._load_editor()
        self._apply_in_system(before, "Настройки сохранены")

    # ── применение в системе и перезапуск ─────────────────────────────

    def _apply_in_system(self, before: dict, summary: str) -> None:
        """Отдаёт системе то, что живёт вне settings.json, потом сообщает итог.

        Запись hosts занимает заметное время, поэтому в фоне. Итог
        приходит в поток окна сигналом.
        """
        actions = post_apply_actions(before, self._current_settings())
        if not actions.any:
            self._notify_applied(summary, [])
            return

        def run() -> None:
            from configsets.effects import apply_post_actions

            try:
                problems = apply_post_actions(actions)
            except Exception as exc:
                log(f"Конфигурации: применение в системе упало: {exc}", "ERROR")
                problems = ["Часть настроек не применилась в системе — подробности в журнале"]
            self._effects_bridge.finished.emit(summary, list(problems))

        threading.Thread(target=run, name="ConfigsApplyEffects", daemon=True).start()

    def _on_effects_finished(self, summary: str, problems: list) -> None:
        self._notify_applied(summary, problems)

    def _notify_applied(self, summary: str, problems: list) -> None:
        content = ". ".join(part for part in (summary, *problems, RESTART_NOTE) if part)
        factory = InfoBar.warning if problems else InfoBar.success
        bar = factory(
            title="Настройки применены" if not problems else "Настройки применены не целиком",
            content=content,
            parent=self,
            position=InfoBarPosition.TOP,
            duration=8000,
        )
        if bar is None:
            return
        # Плашка уходит в колокольчик, кнопка — вместе с ней
        # (ui/infobar_inbox_capture.py).
        button = PushButton("Перезапустить", bar)
        button.clicked.connect(self._restart)
        bar.addWidget(button)

    def _restart(self) -> None:
        from app.restart import restart_application

        if not restart_application(self.window()):
            self._error("Не удалось перезапустить net67 — закройте программу и откройте снова.")

    # ──────────────────────────────────────────────────────────────────

    def _error(self, text: str) -> None:
        InfoBar.error(
            title="Ошибка",
            content=str(text),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=6000,
        )

    def _success(self, text: str) -> None:
        InfoBar.success(
            title="Готово",
            content=str(text),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=5000,
        )


__all__ = ["ConfigsPage"]
