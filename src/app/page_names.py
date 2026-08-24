"""
Именованные константы для страниц окна.
Используй этот Enum вместо числовых индексов.
"""

from enum import Enum, auto


class PageName(Enum):
    """Имена страниц в pages_stack (QStackedWidget)

    Порядок значений НЕ ВАЖЕН - это просто уникальные идентификаторы.
    Фактический индекс в стеке определяется порядком добавления виджетов.
    """

    # === Основные страницы ===
    # net67 v2: управление -> мои пресеты/raw preset или настройка preset-а через profiles
    ZAPRET2_MODE_CONTROL = auto()
    ZAPRET2_USER_PRESETS = auto()
    ZAPRET2_PRESET_RAW_EDITOR = auto()
    ZAPRET2_PRESET_SETUP = auto()
    ZAPRET2_PROFILE_SETUP = auto()
    ZAPRET2_PROFILE_ORDER = auto()

    # net67 v1: зеркальный путь, отличается только strategy внутри profile

    # === Настройки системы ===
    NETWORK = auto()                 # Сеть
    HOSTS = auto()                   # Разблокировка сервисов
    BLOCKCHECK = auto()              # BlockCheck
    WINWS_LOG_ANALYZER = auto()      # Анализ debug-лога winws2
    LOGS = auto()                    # Логи
    SERVERS = auto()                 # Серверы обновлений
    ABOUT = auto()                   # О программе
    SUPPORT = auto()                 # Поддержка (GitHub Discussions и каналы сообщества)

    # === Telegram Proxy ===
    TELEGRAM_PROXY = auto()          # Telegram WebSocket Proxy

    # === VPN ===
    VPN = auto()                     # Профили AmneziaWG и WireGuard

    # === Конфигурации ===
    CONFIGS = auto()                 # Наборы настроек, перенос и правка файла

    # === Оркестратор (автообучение) ===
