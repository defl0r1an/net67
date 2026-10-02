"""
updater/startup_update_check.py
────────────────────────────────────────────────────────────────
Синхронная проверка обновлений при запуске приложения.
Не содержит Qt-импортов — безопасно вызывать из фонового потока.
"""
from __future__ import annotations

from log.log import log



def _is_skipped_by_user(version: str) -> bool:
    try:
        from settings.store import get_skipped_update_version
        from updater.release_notes import version_key

        skipped = get_skipped_update_version()
        return bool(skipped) and version_key(skipped) == version_key(version)
    except Exception:
        return False


def _release_url(version: str) -> str:
    from updater.release_notes import release_page_url
    from updater.server_config import GITHUB_REPO

    return release_page_url(version, GITHUB_REPO)


def _source_title(release_info: dict) -> str:
    """Откуда пришло известие об обновлении — словом для окна."""
    source = str((release_info or {}).get("source") or "").strip()
    return source or "GitHub"


def release_history_for(release_info: dict, *, current_version: str) -> list[dict]:
    """Изменения всех пропущенных версий и пара предыдущих — для окна обновления.

    Список выпусков берётся у GitHub (он кэшируется). Если его не достать,
    в истории остаётся один предлагаемый выпуск: окно всё равно покажет,
    что в нём нового.
    """
    from updater.release_notes import build_history
    from updater.server_config import GITHUB_REPO

    target = str((release_info or {}).get("version") or "")
    releases: list[dict] = [dict(release_info or {})]
    try:
        from updater.github_release import get_all_releases_with_exe

        releases.extend(item for item in (get_all_releases_with_exe() or ()) if isinstance(item, dict))
    except Exception as exc:
        log(f"История выпусков недоступна: {exc}", "🔁 UPDATE")
    return list(build_history(releases, current_version=current_version, target_version=target, repo=GITHUB_REPO))


def check_for_update_sync() -> dict:
    """
    Проверяет наличие обновлений синхронно.

    Возвращает dict:
        has_update   : bool      — найдено ли новое обновление
        version      : str|None  — версия обновления (если has_update) или текущая
        release_notes: str       — заметки к релизу
        error        : str|None  — текст ошибки (если проверка не удалась)
        release_info : dict|None — полные метаданные найденного выпуска
    """
    try:
        from config.build_info import CHANNEL, APP_VERSION

        from updater.release_manager import get_latest_release
        from updater.github_release import normalize_version
        from updater.update import compare_versions
        from updater.rate_limiter import UpdateRateLimiter
        from updater.update_cache import UpdateCache

        log("Проверка обновлений при запуске...", "🔁 UPDATE")

        try:
            app_ver_norm = normalize_version(APP_VERSION)
        except Exception:
            app_ver_norm = APP_VERSION

        release_info = UpdateCache.get_cached_release(CHANNEL)
        if release_info:
            log("Стартовая проверка обновлений использует кэш", "🔁 UPDATE")
        else:
            can_check, skip_reason = UpdateRateLimiter.can_check_update(is_auto=True)
            if not can_check:
                log(f"Автопроверка обновлений при запуске пропущена: {skip_reason}", "🔁 UPDATE")
                return {
                    'has_update': False,
                    'version': app_ver_norm,
                    'release_notes': '',
                    'error': None,
                    'release_info': None,
                    'skipped': True,
                    'skip_reason': skip_reason,
                    'checked_at': UpdateRateLimiter.get_last_check_time(is_auto=True),
                }

            release_info = get_latest_release(CHANNEL, use_cache=True)
            UpdateRateLimiter.record_check(is_auto=True)

        if not release_info:
            return {
                'has_update': False,
                'version': None,
                'release_notes': '',
                'error': 'Не удалось получить информацию о релизах',
                'release_info': None,
            }

        new_ver = release_info.get('version', '')
        release_notes = release_info.get('release_notes', '')

        cmp = compare_versions(app_ver_norm, new_ver)
        if cmp < 0:
            if _is_skipped_by_user(new_ver):
                # «Пропустить версию»: при запуске о ней не напоминаем. На
                # странице «Серверы» она по-прежнему видна и ставится.
                log(f"Обновление v{new_ver} пропущено по просьбе пользователя", "🔁 UPDATE")
                return {
                    'has_update': False,
                    'version': app_ver_norm,
                    'release_notes': '',
                    'error': None,
                    'release_info': None,
                    'skipped': True,
                    'skip_reason': f"Версия {new_ver} пропущена. Установить её можно на странице «Серверы»",
                }
            log(f"Найдено обновление v{new_ver} (текущая v{app_ver_norm})", "🔁 UPDATE")
            return {
                'has_update': True,
                'version': new_ver,
                'release_notes': release_notes,
                'error': None,
                'release_info': release_info,
                'current_version': app_ver_norm,
                'history': release_history_for(release_info, current_version=app_ver_norm),
                'release_url': _release_url(new_ver),
                'source': _source_title(release_info),
            }
        else:
            log(f"Обновлений нет (v{app_ver_norm})", "🔁 UPDATE")
            return {
                'has_update': False,
                'version': app_ver_norm,
                'release_notes': '',
                'error': None,
                'release_info': None,
            }

    except Exception as e:
        log(f"Ошибка проверки обновлений при запуске: {e}", "❌ ERROR")
        return {
            'has_update': False,
            'version': None,
            'release_notes': '',
            'error': str(e),
            'release_info': None,
        }
