"""Внешние ссылки приложения.

Раньше здесь были ресурсы автора исходного проекта: документация на
publish.obsidian.md, GitHub Discussions и формы заявок в репозитории
youtubediscord/zapret. Они убраны вместе с остальными упоминаниями автора.

Теперь адреса приходят из branding.py. Пока там пусто, соответствующие
кнопки и карточки не показываются — код проверяет ссылку на пустоту
перед созданием виджета.

Чтобы вернуть раздел справки, достаточно заполнить DOCS_URL или
SUPPORT_URL в branding.py.
"""

from branding import DOCS_URL as _BRAND_DOCS_URL
from branding import SUPPORT_URL as _BRAND_SUPPORT_URL

#: Основная документация.
DOCS_URL = _BRAND_DOCS_URL
INFO_URL = _BRAND_DOCS_URL

#: Справочные страницы отдельных разделов. Пустая строка гасит
#: соответствующую кнопку «Подробнее».
PRESET_INFO_URL = ""
PROFILE_INFO_URL = ""
WINWS_LOG_ANALYZER_INFO_URL = ""
ANDROID_URL = ""

#: Апстрим движка. Это не автор GUI, а сторонний компонент winws,
#: на котором всё построено. Ссылку оставляем: так требует его лицензия.
BOLVAN_URL = "https://github.com/bol-van/zapret-win-bundle"

#: Каналы обращения в поддержку.
SUPPORT_DISCUSSIONS_URL = _BRAND_SUPPORT_URL
BLOCKCHECK_DISCUSSIONS_URL = _BRAND_SUPPORT_URL
PROFILE_REQUEST_FORM_URL = _BRAND_SUPPORT_URL


__all__ = [
    "ANDROID_URL",
    "BLOCKCHECK_DISCUSSIONS_URL",
    "BOLVAN_URL",
    "DOCS_URL",
    "INFO_URL",
    "PRESET_INFO_URL",
    "PROFILE_INFO_URL",
    "PROFILE_REQUEST_FORM_URL",
    "SUPPORT_DISCUSSIONS_URL",
    "WINWS_LOG_ANALYZER_INFO_URL",
]
