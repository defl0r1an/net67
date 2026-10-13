"""Что применить в системе после записи настроек из набора или файла.

settings.json — не вся правда. Автозапуск живёт задачей в планировщике
Windows, выбор сервисов hosts — строками системного файла. Раньше
«Применить» и «Загрузить из файла» писали только settings.json: на экране
сервис включён и автозапуск стоит, а в системе всё как было. Здесь
каждое такое изменение отдаётся тому же писателю, которым пользуется
своя страница, — второго писателя в hosts быть не должно.

Работает в фоне: запись hosts занимает заметное время.
"""

from __future__ import annotations

from log.log import log

from configsets.plans import PostApplyActions


def apply_post_actions(actions: PostApplyActions) -> list[str]:
    """Применяет действия. Возвращает человеческие строки о том, что не вышло."""
    problems: list[str] = []

    if actions.hosts_selection is not None:
        try:
            from hosts.commands import apply_hosts_draft

            result = apply_hosts_draft(dict(actions.hosts_selection))
            if not getattr(result, "success", False):
                problems.append(
                    "Сервисы hosts не записаны: " + (str(getattr(result, "message", "") or "") or "причина в журнале")
                )
        except Exception as exc:
            log(f"Конфигурации: hosts не применён: {exc}", "WARNING")
            problems.append("Сервисы hosts не записаны — подробности в журнале")

    if actions.gui_autostart is not None:
        try:
            from program_settings.commands import set_gui_autostart_enabled

            result = set_gui_autostart_enabled(bool(actions.gui_autostart))
            if str(getattr(result, "level", "")) != "success":
                problems.append(str(getattr(result, "content", "") or "Автозапуск не изменился"))
                # Настройка уже говорит «включено», а задачи нет: вернуть
                # правду, иначе тумблер на странице программы соврёт.
                from autostart import public as autostart_public

                autostart_public.save_gui_autostart_enabled(not bool(actions.gui_autostart))
        except Exception as exc:
            log(f"Конфигурации: автозапуск не применён: {exc}", "WARNING")
            problems.append("Автозапуск не изменился — подробности в журнале")

    return problems


__all__ = ["apply_post_actions"]
