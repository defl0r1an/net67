from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PostStartupHost:
    _window: Any
    # Выбор пресета фасада пресетов: туру первого запуска нужен для
    # ответа о провайдере. Окно фасадов не держит.
    _select_preset: Any = None

    @property
    def close_state(self):
        return self._window.close_state

    @property
    def startup_state(self):
        return self._window.startup_state

    @property
    def startup_interactive_ready(self):
        return self._window.startup_interactive_ready

    @property
    def startup_post_init_ready(self):
        return self._window.startup_post_init_ready

    def install_idle_memory_trim(self) -> None:
        """Чистит память, пока окно долго скрыто в трее или свёрнуто."""
        from ui.idle_memory_trim import install_idle_memory_trim

        install_idle_memory_trim(self._window)

    def is_alive(self) -> bool:
        close_state = self.close_state
        return not bool(close_state.is_exiting or close_state.closing_completely)

    def ask_update(self, version: str, details: dict | None = None) -> tuple[str, list[dict]]:
        """Окно «Доступно обновление»: (что нажали, показанная история).

        Раньше здесь было окошко в одну строку: «Выпущена версия X.
        Установить?» — что в ней нового, узнать было негде, а отказаться
        можно было только до следующего запуска.

        Хозяин окна только показывает и возвращает ответ: "install",
        "skip" или "later". Что с ним делать — запомнить пропуск, сохранить
        текст «Что нового», начать установку, — решает тот, кто спросил:
        у него есть фасад обновлятора.
        """
        from updater.ui.update_dialog import ask_update

        details = dict(details or {})
        release = details.get("release_info") if isinstance(details.get("release_info"), dict) else {}
        history = [item for item in (details.get("history") or ()) if isinstance(item, dict)]
        if not history:
            # Источник не дал историю — показываем хотя бы сам выпуск.
            history = [{"version": version, "notes": str(details.get("release_notes") or ""), "is_new": True}]
        action = ask_update(
            self._window,
            current_version=str(details.get("current_version") or ""),
            target_version=version,
            history=history,
            source=str(details.get("source") or ""),
            release_url=str(details.get("release_url") or ""),
            file_name=str(release.get("file_name") or ""),
            file_size=release.get("file_size") or 0,
        )
        return str(action), history

    def is_window_shown(self) -> bool:
        """Окно сейчас на экране: не свёрнуто и не убрано в трей."""
        window = self._window
        if window is None:
            return False
        return bool(window.isVisible()) and not bool(window.isMinimized())

    def show_whats_new(self, version: str, history) -> None:
        """Окно «Что нового» после установки новой версии."""
        from updater.ui.update_dialog import show_whats_new

        show_whats_new(self._window, version=version, history=history)

    def show_page(self, page_name) -> None:
        from ui.window_adapter import show_page

        show_page(self._window, page_name)

    def ensure_page(self, page_name):
        from ui.window_adapter import ensure_page

        return ensure_page(self._window, page_name)

    def start_onboarding_tour(self, *, setup: bool = False) -> bool:
        """Пробует показать обучающий тур. False — окно пока не готово."""
        from ui.onboarding import start_onboarding_tour

        return bool(
            start_onboarding_tour(self._window, automatic=True, setup=setup, select_preset=self._select_preset)
        )

    def get_loaded_page(self, page_name):
        from ui.window_adapter import get_loaded_page

        return get_loaded_page(self._window, page_name)


def build_post_startup_host(window, *, select_preset=None) -> PostStartupHost:
    return PostStartupHost(window, select_preset)


__all__ = ["PostStartupHost", "build_post_startup_host"]
