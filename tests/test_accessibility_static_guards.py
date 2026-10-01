from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

IMPORTANT_CONTROL_MARKERS = (
    "PushButton(",
    "PrimaryPushButton(",
    "ToolButton(",
    "PrimaryToolButton(",
    "TransparentToolButton(",
    "LineEdit(",
    "SearchLineEdit(",
    "ComboBox(",
    "CheckBox(",
    "SwitchButton(",
    "PlainTextEdit(",
    "TextEdit(",
    "QListWidget(",
    "QTableWidget(",
)

ACCESSIBILITY_MARKERS = (
    "set_control_accessibility",
    "set_state_text",
    "set_item_accessible_text",
    "set_segmented_items_accessibility",
    "enable_keyboard_click",
    "enable_keyboard_toggle",
    "accessibility",
)

KEYBOARD_COLLECTION_WIDGET_MARKERS = (
    "QListWidget(",
    "(QListWidget):",
    "ListView(",
    "(ListView):",
    "QTableWidget(",
    "(QTableWidget):",
    "TableWidget(",
    "(TableWidget):",
    "SegmentedWidget(",
)

KEYBOARD_COLLECTION_ACCESS_MARKERS = (
    "keyPressEvent",
    "focusInEvent",
    "currentItemChanged",
    "currentChanged",
    "currentCellChanged",
    "set_segmented_items_accessibility",
    "AccessibleTextRole",
    "setFocusPolicy(Qt.FocusPolicy.StrongFocus)",
    "screenReaderStateText",
    "enable_keyboard_click",
    "enable_keyboard_toggle",
    "set_item_accessible_text",
)

CUSTOM_MOUSE_ACTION_MARKERS = (
    "def mousePressEvent",
    "def mouseReleaseEvent",
    "def mouseDoubleClickEvent",
    ".mousePressEvent =",
    ".mouseReleaseEvent =",
    ".mouseDoubleClickEvent =",
)

CUSTOM_KEYBOARD_ACTION_MARKERS = (
    "def keyPressEvent",
    ".keyPressEvent =",
    "enable_keyboard_click",
    "enable_keyboard_toggle",
)

ALLOWED_NO_FOCUS_SOURCES = {
    "src/hosts/ui/services_build.py",
    "src/ui/accessibility.py",
    "src/ui/segmented_accessibility.py",
    "src/ui/widgets/fluent_scrollbar.py",
    "src/ui/widgets/win11_controls.py",
    # Точка состояния из zapret 21.1.6.45: NoFocus — пока она лишь
    # украшение; выключателем (set_clickable) она берёт StrongFocus.
    "src/ui/pulsing_dot.py",
}


#: Файлы, пришедшие из исходного проекта, на которых эти же проверки
#: падают и у него самого (проверено прогоном его набора тестов). Список
#: закрытый: новый файл сюда не попадает сам, его надо внести руками и
#: объяснить.
#:
#: - winws2_language/* и code_editor/language.py — языковая модель
#:   редактора пресетов; имена виджетов в них — текст подсказок, а не
#:   элементы управления;
#: - code_editor/completion_popup.py — всплывающий список дополнений,
#:   клавиатурой им управляет сам редактор;
#: - button_motion.py — ловит нажатия мыши только ради анимации кнопки,
#:   своего действия у него нет, клавиатурой кнопку жмут как раньше;
#: - onboarding/overlay.py — обучающий тур; переделывается под net67, и
#:   доступность для диктора добавляется вместе с ним.
UPSTREAM_KNOWN_GAPS = {
    "src/profile/winws2_language/diagnostics.py",
    "src/profile/winws2_language/hover.py",
    "src/profile/winws2_language/model.py",
    "src/ui/code_editor/language.py",
    "src/ui/code_editor/completion_popup.py",
    "src/ui/button_motion.py",
    "src/ui/onboarding/overlay.py",
}

#: Свои файлы net67, где мышь включает только украшение. Действия, до
#: которого клавиатуре надо дотянуться, у них нет.
#:
#: - widgets/fun/mascot.py — значок на карточках проверок: по щелчку
#:   крутится, и всё; в Tab-порядок украшение не ставим.
DECORATIVE_MOUSE_ONLY = {
    "src/ui/widgets/fun/mascot.py",
}


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_ui_files_with_important_controls_keep_accessibility_wiring() -> None:
    missing: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        rel_path = path.relative_to(ROOT).as_posix()
        if rel_path.startswith("src/themes/cache/"):
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        if not any(marker in source for marker in IMPORTANT_CONTROL_MARKERS):
            continue
        if any(marker in source for marker in ACCESSIBILITY_MARKERS):
            continue
        if rel_path in UPSTREAM_KNOWN_GAPS:
            continue
        missing.append(rel_path)

    assert missing == []


def test_collection_controls_keep_keyboard_or_row_accessibility() -> None:
    missing: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        rel_path = path.relative_to(ROOT).as_posix()
        if rel_path.startswith("src/themes/cache/"):
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        if not any(marker in source for marker in KEYBOARD_COLLECTION_WIDGET_MARKERS):
            continue
        if any(marker in source for marker in KEYBOARD_COLLECTION_ACCESS_MARKERS):
            continue
        if rel_path in UPSTREAM_KNOWN_GAPS:
            continue
        missing.append(rel_path)

    assert missing == []


def test_custom_mouse_actions_keep_keyboard_activation() -> None:
    missing: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        rel_path = path.relative_to(ROOT).as_posix()
        if rel_path.startswith("src/themes/cache/"):
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        if not any(marker in source for marker in CUSTOM_MOUSE_ACTION_MARKERS):
            continue
        if any(marker in source for marker in CUSTOM_KEYBOARD_ACTION_MARKERS):
            continue
        if rel_path in UPSTREAM_KNOWN_GAPS or rel_path in DECORATIVE_MOUSE_ONLY:
            continue
        missing.append(rel_path)

    assert missing == []


def test_no_focus_usage_stays_limited_to_decorative_helpers() -> None:
    unexpected: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        rel_path = path.relative_to(ROOT).as_posix()
        if rel_path.startswith("src/themes/cache/"):
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        if "FocusPolicy.NoFocus" not in source:
            continue
        if rel_path in ALLOWED_NO_FOCUS_SOURCES or rel_path in UPSTREAM_KNOWN_GAPS:
            continue
        unexpected.append(rel_path)

    assert unexpected == []


def test_profile_shell_keeps_toolbar_accessibility_helper() -> None:
    source = _source("src/profile/ui/shell.py")

    assert "from profile.ui.shell_accessibility import apply_profile_shell_accessibility" in source
    assert "apply_profile_shell_accessibility(" in source
    for control_name in (
        "add_profile_btn",
        "request_btn",
        "view_menu_btn",
        "order_btn",
        "info_btn",
        "profile_search_input",
    ):
        assert f"{control_name}={control_name}" in source


def test_user_presets_build_keeps_accessibility_helper_for_toolbar_and_list() -> None:
    source = _source("src/presets/ui/common/user_presets_build.py")

    assert (
        "from presets.ui.common.user_presets_accessibility import apply_user_presets_accessibility"
        in source
    )
    assert source.count("apply_user_presets_accessibility(") >= 2
    # get_configs_btn убрана вместе с карточкой «Получить конфиги»:
    # она вела на пост автора исходного проекта.
    for control_name in (
        "create_btn",
        "import_btn",
        "open_folder_btn",
        "reset_all_btn",
        "presets_info_btn",
        "info_btn",
        "preset_search_input",
        "presets_list",
    ):
        assert f"{control_name}={control_name}" in source


def test_the_donation_page_is_gone_from_the_tree() -> None:
    """Здесь проверялась доступность кнопок страницы доната.

    Страницы больше нет: подписок в net67 не бывает, а пакет donater
    вёл переписку с чужим Telegram-ботом и хранил привязку устройства.
    Проверка перевёрнута — она сторожит, чтобы пакет не вернулся
    случайным откатом ветки.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]

    for removed in (
        "src/donater",
        "src/app/feature_facades/premium.py",
        "src/ui/theme_subscription_manager.py",
    ):
        assert not (root / removed).exists(), removed


def test_notification_infobar_keeps_accessibility_for_dynamic_actions() -> None:
    source = _source("src/ui/window_notification_center.py")

    assert "self._set_infobar_accessibility(bar" in source
    assert "self._set_infobar_action_button_accessibility(btn, action, button_text)" in source
    assert 'name = f"Действие уведомления: {button_text}"' in source
