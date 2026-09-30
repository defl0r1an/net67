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
#:
#: Исходный проект переехал с GitHub Discussions на задачи Forgejo и
#: переименовал ссылки в *_ISSUES_URL. У net67 канал один и тот же
#: адрес из branding.py, поэтому новые имена — синонимы старых.
SUPPORT_DISCUSSIONS_URL = _BRAND_SUPPORT_URL
BLOCKCHECK_DISCUSSIONS_URL = _BRAND_SUPPORT_URL
PROFILE_REQUEST_FORM_URL = _BRAND_SUPPORT_URL
SUPPORT_ISSUES_URL = _BRAND_SUPPORT_URL
BLOCKCHECK_ISSUES_URL = _BRAND_SUPPORT_URL

#: Статьи к шагам обучающего тура — в нашей вики (wiki/content), не на сайте.
#:
#: Долго здесь было пусто: у исходного проекта шаги вели на его вики, а
#: она не про net67. Теперь статьи свои, и ссылка — страница вики с
#: якорем заголовка, как в самой вики: ``presets#фейки``. Адрес сервера
#: подставляет docs.local_site.page_url при показе карточки. Шаг без
#: записи кнопку «Подробнее» не показывает.
#:
#: Якорь — заголовок статьи строчными, без знаков препинания, пробелы
#: заменены дефисами. Сверяет их tests/test_onboarding_wiki_links.py:
#: переименуешь заголовок — тест назовёт шаг, который осиротел.
ONBOARDING_WIKI_URLS: dict[str, str] = {
    "welcome": "index",
    "how_it_works": "how-it-works",
    "oneclick": "first-run",
    "services": "not-working#4-сайт-закрыт-по-стране",
    "program_settings": "first-run#автозапуск",
    "view_switch": "first-run#простой-и-расширенный-вид",
    "building_blocks": "bypass#три-слова-которые-легко-перепутать",
    "preset": "bypass#как-выбирается-пресет",
    "menu_presets": "bypass",
    "presets_list": "presets#мои-пресеты",
    "preset_menu": "presets#меню-пресета",
    "preset_file": "presets#пресет-это-текстовый-файл",
    "preset_header": "presets#служебные-строки",
    "preset_lua_init": "presets#подключение-техник",
    "preset_engine_options": "presets#общие-настройки-движка",
    "preset_interception": "presets#какой-трафик-перехватывается",
    "preset_blobs": "presets#фейки",
    "preset_profile": "presets#профили",
    "preset_profile_name": "presets#имя-профиля",
    "preset_profile_match": "presets#когда-срабатывает-профиль",
    "preset_profile_packets": "presets#к-каким-пакетам-применять",
    "preset_profile_strategy": "presets#стратегия",
    "preset_profile_new": "presets#граница-профилей",
    "presets_toolbar": "presets#свои-пресеты",
    "profiles_list": "profiles",
    "profile_row": "profiles#профиль-и-его-стратегия",
    "profile_menu": "profiles#меню-профиля",
    "profiles_toolbar": "profiles#новые-профили",
    "profile_order": "profiles#порядок-профилей",
    "list_type": "profiles#hostlist-или-ipset",
    "ranges": "profiles#диапазоны-пакетов",
    "profile_tabs": "profiles#вкладки-профиля",
    "strategy_choice": "techniques#какую-стратегию-выбрать",
    "technique_fake": "techniques#fake",
    "technique_multisplit": "techniques#multisplit",
    "technique_multidisorder": "techniques#multidisorder",
    "technique_fakedsplit": "techniques#fakedsplit",
    "technique_hostfakesplit": "techniques#hostfakesplit",
    "technique_tcpseg": "techniques#tcpseg",
    "technique_oob": "techniques#oob",
    "technique_syndata": "techniques#syndata",
    "list_entries": "lists#свои-сайты",
    "dns": "dns",
    "hosts": "hosts",
    "telegram_proxy": "telegram",
    "vpn": "vpn",
    "menu_diagnostics": "diagnostics",
    "blockcheck": "diagnostics#blockcheck",
    "log_analyzer": "diagnostics#анализ-лога",
    "logs": "diagnostics#логи",
    "finish": "not-working",
    "bypass_welcome": "how-it-works",
    "bypass_practice": "techniques#какую-стратегию-выбрать",
    "bypass_finish": "how-it-works",
}


__all__ = [
    "ANDROID_URL",
    "BLOCKCHECK_DISCUSSIONS_URL",
    "BLOCKCHECK_ISSUES_URL",
    "BOLVAN_URL",
    "DOCS_URL",
    "INFO_URL",
    "ONBOARDING_WIKI_URLS",
    "PRESET_INFO_URL",
    "PROFILE_INFO_URL",
    "PROFILE_REQUEST_FORM_URL",
    "SUPPORT_DISCUSSIONS_URL",
    "SUPPORT_ISSUES_URL",
    "WINWS_LOG_ANALYZER_INFO_URL",
]
