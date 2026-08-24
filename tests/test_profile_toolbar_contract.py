from __future__ import annotations

import inspect
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from profile.ui import shell as profile_shell
from profile.ui import preset_setup_page
from presets.ui.common import user_presets_build
from presets.ui.common import user_presets_page


class ProfileToolbarContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PyQt6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def test_profile_toolbar_has_no_manual_refresh_button(self) -> None:
        source = inspect.getsource(profile_shell)

        self.assertNotIn("RefreshButton", source)
        self.assertNotIn("reload_btn", source)
        self.assertNotIn("on_reload", source)

    def test_no_buttons_lead_to_the_upstream_repository(self) -> None:
        """Кнопки на GitHub исходного проекта убраны, и вернуться не должны.

        Раньше здесь проверялось обратное — что кнопки есть и берут
        значок GITHUB напрямую. Обе вели в репозиторий автора исходного
        проекта: «заявка на добавление сайта» и «получить конфиги». В
        корпоративной сборке net67 они отправляли двадцать руководителей
        к постороннему проекту, поэтому удалены.

        Проверка не ослаблена, а перевёрнута: раньше стерегли наличие,
        теперь — отсутствие.
        """
        profile_source = inspect.getsource(profile_shell.build_profile_shell)
        presets_source = inspect.getsource(user_presets_build.build_user_presets_page_shell)

        for source, name in ((profile_source, "профили"), (presets_source, "пресеты")):
            with self.subTest(page=name):
                self.assertNotIn("FluentIcon.GITHUB", source)
                self.assertNotIn("PrimaryPushButton(", source)

    def test_removed_button_field_stays_but_holds_nothing(self) -> None:
        """Поле request_btn читают страница и модуль доступности.

        Убрать его целиком значило бы править оба места ради кнопки,
        которой больше нет; оба и так проверяют значение на None.
        """
        profile_source = inspect.getsource(profile_shell.build_profile_shell)

        self.assertIn("request_btn = None", profile_source)

    def test_profile_request_button_opens_github_form_not_info_popup(self) -> None:
        source = inspect.getsource(preset_setup_page.PresetSetupPageBase._build_content)

        self.assertIn("on_open_profile_request_form=self._open_profile_request_form", source)
        self.assertIn("on_show_info_popup=self._show_profile_info", source)
        self.assertNotIn("on_open_profile_request_form=self._show_profile_info", source)

    def test_user_presets_list_reserves_space_for_visible_fluent_scrollbar(self) -> None:
        presets_source = inspect.getsource(user_presets_build.build_user_presets_page_shell)

        self.assertIn("reserve_vertical_space=True", presets_source)

    def test_user_presets_status_icon_is_next_to_title_not_in_toolbar(self) -> None:
        source = inspect.getsource(user_presets_page.UserPresetsPageBase._build_ui)
        install_source = inspect.getsource(user_presets_page.UserPresetsPageBase._install_title_status_icon)

        self.assertIn("self._install_title_status_icon()", source)
        self.assertIn("title_layout.addWidget(self._preset_status_icon", install_source)
        self.assertNotIn("set_inline_widget(self._preset_status", source)
        self.assertNotIn("self.add_widget(self._preset_status_bar)", source)


if __name__ == "__main__":
    unittest.main()
