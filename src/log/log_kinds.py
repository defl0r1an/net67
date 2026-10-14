"""Какие файлы в папке журналов какого вида — одно место для всех, кто их ищет.

Журнал отладки winws пишется под стабильным именем ``<пресет>_debug.log``
(``profile.settings._build_stable_debug_log_file``); раньше имя было
``zapret_winws2_debug_<время>.log``. Страница журналов, очистка, разбор журнала
winws и обращения в поддержку искали каждый свой набор шаблонов, и четверо из
пяти знали только старое имя: журнал winws, ради которого собирают обращение,
в архив не попадал. Теперь шаблоны берутся только отсюда.
"""

from __future__ import annotations

__all__ = [
    "APP_LOG_PATTERNS",
    "BLOCKCHECK_RUN_LOG_PATTERNS",
    "LEGACY_APP_LOG_PATTERNS",
    "ORCHESTRA_LOG_PATTERNS",
    "STRATEGY_SCAN_LOG_PATTERNS",
    "WINWS_DEBUG_LOG_PATTERNS",
]

# Журнал самой программы: net67_log_<дата>_<время>.txt. Под zapret_log_*.txt он
# писался до переименования — такие файлы уже лежат в logs/ у всех, кто ставил
# прежние версии: их по-прежнему показываем и чистим по лимиту, иначе они пропали
# бы со страницы «Логи» и копились бы вечно.
APP_LOG_PATTERNS = ("net67_log_*.txt", "zapret_log_*.txt")
LEGACY_APP_LOG_PATTERNS = ("zapret_[0-9]*.log",)
# Вывод winws2/winws: нынешнее имя по пресету и старое имя по времени запуска.
WINWS_DEBUG_LOG_PATTERNS = ("*_debug.log", "zapret_winws2_debug_*.log")
# Журнал запуска BlockCheck; под тем же именем пишет и подбор стратегий.
BLOCKCHECK_RUN_LOG_PATTERNS = ("blockcheck_run_*.log",)
STRATEGY_SCAN_LOG_PATTERNS = BLOCKCHECK_RUN_LOG_PATTERNS
ORCHESTRA_LOG_PATTERNS = ("orchestra_*.log",)
