"""Флаг страны по названию сервера.

В списке серверов вместо флага стояли двухбуквенные сокращения — «GB»,
«NL», «PT». Они пришли из имён в подписке и читаются хуже флага: чтобы
понять «GB», надо вспомнить, а флаг узнаётся сразу.

## Откуда берётся страна

Из самого названия. Подписки почти всегда пишут его человеку, а не
машине: «GB Великобритания N1», «NL Нидерланды N1». Значит, искать надо
двумя способами — по сокращению в начале и по русскому названию, — и
второй важнее: сокращение может отсутствовать, название есть всегда.

## Почему символы, а не картинки

Флаг собирается из двух символов-индикаторов Unicode: 🇳 + 🇱 даёт 🇳🇱.
Никаких файлов, никакой папки с картинками, ничего не надо класть в
сборку.

Оговорка: Windows такие пары **не рисует флагами** — системный шрифт
Segoe UI Emoji их не поддерживает, и на экране будут две буквы в
рамочках. Это лучше голого «NL», но до настоящего флага не дотягивает.
Настоящие потребуют набора картинок в приложении.
"""

from __future__ import annotations


#: Сдвиг от латинской буквы к её региональному индикатору.
_REGIONAL_INDICATOR_BASE = 0x1F1E6
_LATIN_A = ord("A")


#: Все коды стран по ISO 3166-1. Двести сорок девять штук — взяты из
#: системного справочника iso-codes, а не набраны руками.
#:
#: Нужны они для одного: отличить код страны от любых других двух букв
#: в начале имени сервера. «N1» и «V2» тоже двухбуквенные, и без этого
#: списка они бы притворялись странами.
ISO_COUNTRY_CODES: frozenset[str] = frozenset({
    "AD", "AE", "AF", "AG", "AI", "AL", "AM", "AO", "AQ", "AR", "AS", "AT",
    "AU", "AW", "AX", "AZ", "BA", "BB", "BD", "BE", "BF", "BG", "BH", "BI",
    "BJ", "BL", "BM", "BN", "BO", "BQ", "BR", "BS", "BT", "BV", "BW", "BY",
    "BZ", "CA", "CC", "CD", "CF", "CG", "CH", "CI", "CK", "CL", "CM", "CN",
    "CO", "CR", "CU", "CV", "CW", "CX", "CY", "CZ", "DE", "DJ", "DK", "DM",
    "DO", "DZ", "EC", "EE", "EG", "EH", "ER", "ES", "ET", "FI", "FJ", "FK",
    "FM", "FO", "FR", "GA", "GB", "GD", "GE", "GF", "GG", "GH", "GI", "GL",
    "GM", "GN", "GP", "GQ", "GR", "GS", "GT", "GU", "GW", "GY", "HK", "HM",
    "HN", "HR", "HT", "HU", "ID", "IE", "IL", "IM", "IN", "IO", "IQ", "IR",
    "IS", "IT", "JE", "JM", "JO", "JP", "KE", "KG", "KH", "KI", "KM", "KN",
    "KP", "KR", "KW", "KY", "KZ", "LA", "LB", "LC", "LI", "LK", "LR", "LS",
    "LT", "LU", "LV", "LY", "MA", "MC", "MD", "ME", "MF", "MG", "MH", "MK",
    "ML", "MM", "MN", "MO", "MP", "MQ", "MR", "MS", "MT", "MU", "MV", "MW",
    "MX", "MY", "MZ", "NA", "NC", "NE", "NF", "NG", "NI", "NL", "NO", "NP",
    "NR", "NU", "NZ", "OM", "PA", "PE", "PF", "PG", "PH", "PK", "PL", "PM",
    "PN", "PR", "PS", "PT", "PW", "PY", "QA", "RE", "RO", "RS", "RU", "RW",
    "SA", "SB", "SC", "SD", "SE", "SG", "SH", "SI", "SJ", "SK", "SL", "SM",
    "SN", "SO", "SR", "SS", "ST", "SV", "SX", "SY", "SZ", "TC", "TD", "TF",
    "TG", "TH", "TJ", "TK", "TL", "TM", "TN", "TO", "TR", "TT", "TV", "TW",
    "TZ", "UA", "UG", "UM", "US", "UY", "UZ", "VA", "VC", "VE", "VG", "VI",
    "VN", "VU", "WF", "WS", "YE", "YT", "ZA", "ZM", "ZW",
})


#: Названия стран, которые встречаются в именах серверов.
#:
#: Запасной путь, если кода в имени нет. Список короткий намеренно: он
#: покрывает то, что реально попадается в подписках, а полного перевода
#: двухсот сорока девяти стран здесь и не требуется.
COUNTRY_NAMES: dict[str, tuple[str, ...]] = {
    "GB": ("великобритания", "англия", "британия", "uk", "united kingdom"),
    "NL": ("нидерланды", "голландия", "netherlands", "holland"),
    "PT": ("португалия", "portugal"),
    "DE": ("германия", "germany", "deutschland"),
    "FR": ("франция", "france"),
    "US": ("сша", "америка", "usa", "united states"),
    "FI": ("финляндия", "finland"),
    "SE": ("швеция", "sweden"),
    "NO": ("норвегия", "norway"),
    "PL": ("польша", "poland"),
    "TR": ("турция", "turkey", "türkiye"),
    "JP": ("япония", "japan"),
    "SG": ("сингапур", "singapore"),
    "HK": ("гонконг", "hong kong"),
    "AE": ("оаэ", "эмираты", "dubai", "emirates"),
    "CH": ("швейцария", "switzerland"),
    "AT": ("австрия", "austria"),
    "ES": ("испания", "spain"),
    "IT": ("италия", "italy"),
    "CA": ("канада", "canada"),
    "LV": ("латвия", "latvia"),
    "LT": ("литва", "lithuania"),
    "EE": ("эстония", "estonia"),
    "CZ": ("чехия", "czech"),
    "RO": ("румыния", "romania"),
    "MD": ("молдова", "moldova"),
    "AM": ("армения", "armenia"),
    "KZ": ("казахстан", "kazakhstan"),
    "RU": ("россия", "russia"),
    "UA": ("украина", "ukraine"),
    "IN": ("индия", "india"),
    "BR": ("бразилия", "brazil"),
    "AU": ("австралия", "australia"),
    "IL": ("израиль", "israel"),
    "KR": ("корея", "korea"),
    "CN": ("китай", "china"),
}


def flag_for_code(code: str) -> str:
    """Флаг по двухбуквенному коду страны. Непонятный код — пусто."""
    text = str(code or "").strip().upper()
    if len(text) != 2 or not text.isalpha() or not text.isascii():
        return ""

    return "".join(chr(_REGIONAL_INDICATOR_BASE + ord(ch) - _LATIN_A) for ch in text)


def country_code(title: str) -> str:
    """Код страны из названия сервера. Не нашли — пустая строка.

    Сначала берём код из самой подписки — она его и пишет: «GB
    Великобритания N1», «NL Нидерланды N1». Это надёжнее перевода: код
    один на весь мир, а название страны каждый сервис пишет по-своему,
    да ещё на разных языках.

    Раньше порядок был обратный, и работали только те тридцать шесть
    стран, для которых у нас лежал перевод. Сервер «SG Node 3» флага не
    получал, хотя код был прямо в имени.

    Названия остались запасным путём: код в имени бывает не всегда.
    """
    text = str(title or "").strip()
    if not text:
        return ""

    # Код ищем не только в начале: подписки пишут его и как «[NL]», и
    # через дефис, и в скобках после имени.
    for token in _tokens(text):
        if token in ISO_COUNTRY_CODES:
            return token

    lowered = text.lower()
    for code, names in COUNTRY_NAMES.items():
        for name in names:
            if name in lowered:
                return code

    return ""


def _tokens(text: str) -> list[str]:
    """Двухбуквенные куски имени, приведённые к верхнему регистру.

    Разделителями считаем всё, кроме букв: скобки, дефисы, точки. Так
    «[NL]-1» и «NL Нидерланды» дают одно и то же.
    """
    import re

    return [part.upper() for part in re.split(r"[^A-Za-z]+", text) if len(part) == 2]


def strip_country_prefix(title: str) -> str:
    """Убирает двухбуквенное сокращение из начала названия.

    Флаг его заменяет, и оставлять оба — значит писать страну дважды.
    """
    text = str(title or "").strip()
    parts = text.split(None, 1)
    if len(parts) == 2 and len(parts[0]) == 2 and parts[0].isalpha() and parts[0].isascii():
        if parts[0].upper() in ISO_COUNTRY_CODES:
            return parts[1]
    return text


def decorate(title: str) -> str:
    """Название сервера с флагом вместо сокращения."""
    code = country_code(title)
    if not code:
        return str(title or "")

    flag = flag_for_code(code)
    if not flag:
        return str(title or "")

    return f"{flag}  {strip_country_prefix(title)}"


#: Где лежат картинки флагов. Имя файла — код страны в нижнем регистре:
#: `nl.png`, `gb.png`. Папки может не быть вовсе — тогда работает
#: запасной вариант из символов.
FLAGS_DIR_NAME = "flags"

#: Высота значка в списке. Ширина подбирается по пропорции картинки:
#: у флагов она разная, и растягивать их до квадрата нельзя.
FLAG_HEIGHT = 14

_ICON_CACHE: dict[str, object] = {}


def flags_dir():
    """Папка с картинками флагов."""
    from config.runtime_layout import APPLICATION_PATHS

    return APPLICATION_PATHS.ico_dir / FLAGS_DIR_NAME


def flag_image_path(code: str):
    """Путь к картинке флага. Нет файла — None."""
    text = str(code or "").strip().lower()
    if len(text) != 2 or not text.isalpha() or not text.isascii():
        return None

    for suffix in (".png", ".svg"):
        candidate = flags_dir() / f"{text}{suffix}"
        try:
            if candidate.is_file():
                return candidate
        except Exception:
            continue
    return None


def flag_icon(title: str):
    """Значок флага для строки списка. Нет картинки — None.

    Значки кэшируются: список перечитывается на каждое переключение
    вкладки, а чтение и масштабирование картинки на каждой строке — это
    десятки обращений к диску там, где хватает одного.
    """
    code = country_code(title)
    if not code:
        return None

    if code in _ICON_CACHE:
        return _ICON_CACHE[code]

    icon = None
    path = flag_image_path(code)
    if path is not None:
        try:
            from PyQt6.QtGui import QIcon, QPixmap

            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                from PyQt6.QtCore import Qt

                icon = QIcon(
                    pixmap.scaledToHeight(
                        FLAG_HEIGHT, Qt.TransformationMode.SmoothTransformation
                    )
                )
        except Exception:
            icon = None

    _ICON_CACHE[code] = icon
    return icon


def clear_icon_cache() -> None:
    """Сбрасывает кэш значков — нужен после подкладывания картинок."""
    _ICON_CACHE.clear()


__all__ = [
    "COUNTRY_NAMES",
    "FLAGS_DIR_NAME",
    "FLAG_HEIGHT",
    "clear_icon_cache",
    "country_code",
    "decorate",
    "flag_for_code",
    "flag_icon",
    "flag_image_path",
    "flags_dir",
    "strip_country_prefix",
]
