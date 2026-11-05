"""Флаг страны по названию сервера.

В списке серверов вместо флага стояли двухбуквенные сокращения — «GB»,
«NL», «PT». Они пришли из имён в подписке и читаются хуже флага: чтобы
понять «GB», надо вспомнить, а флаг узнаётся сразу.

## Откуда берётся страна

Из самого названия. Подписки почти всегда пишут его человеку, а не
машине: «GB Великобритания N1», «NL Нидерланды N1». Значит, искать надо
двумя способами — по сокращению в начале и по русскому названию, — и
второй важнее: сокращение может отсутствовать, название есть всегда.

Флаги рисуются исходными изображениями Apple: Windows не поддерживает
региональные эмодзи в системном шрифте. Полный справочник названий нужен
подпискам, в которых вместо кода указаны Кипр, Антарктида или территория.
Страна берётся из названия профиля и не выдаётся за геолокацию сервера.
"""

from __future__ import annotations

import re
import unicodedata

from vpn.country_names import ALL_COUNTRY_NAMES, EXTRA_FLAG_CODES


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
    # Дописано по следам Албании: код в подписке был набран кириллицей,
    # а запасного пути по названию у страны не оказалось — в списке её
    # просто не было. Ниже страны, которые встречаются в подписках чаще
    # всего; полного перечня из двухсот сорока девяти здесь не нужно,
    # его заменяет поиск кода.
    "AL": ("албания", "albania"),
    "RS": ("сербия", "serbia"),
    "BG": ("болгария", "bulgaria"),
    "HU": ("венгрия", "hungary"),
    "SK": ("словакия", "slovakia"),
    "SI": ("словения", "slovenia"),
    "HR": ("хорватия", "croatia"),
    "GR": ("греция", "greece"),
    "CY": ("кипр", "cyprus"),
    "IE": ("ирландия", "ireland"),
    "DK": ("дания", "denmark"),
    "BE": ("бельгия", "belgium"),
    "LU": ("люксембург", "luxembourg"),
    "IS": ("исландия", "iceland"),
    "MD": ("молдавия", "молдова", "moldova"),
    "GE": ("грузия", "georgia"),
    "AZ": ("азербайджан", "azerbaijan"),
    "UZ": ("узбекистан", "uzbekistan"),
    "KG": ("киргизия", "кыргызстан", "kyrgyzstan"),
    "MX": ("мексика", "mexico"),
    "AR": ("аргентина", "argentina"),
    "CL": ("чили", "chile"),
    "ZA": ("юар", "южная африка", "south africa"),
    "EG": ("египет", "egypt"),
    "TH": ("таиланд", "thailand"),
    "VN": ("вьетнам", "vietnam"),
    "ID": ("индонезия", "indonesia"),
    "MY": ("малайзия", "malaysia"),
    "PH": ("филиппины", "philippines"),
    "TW": ("тайвань", "taiwan"),
    "NZ": ("новая зеландия", "new zealand"),
    "CD": ("демократическая республика конго", "др конго", "democratic republic of the congo", "dr congo"),
    "CG": ("республика конго", "republic of the congo"),
}


for _code, _aliases in ALL_COUNTRY_NAMES.items():
    COUNTRY_NAMES[_code] = tuple(dict.fromkeys((*COUNTRY_NAMES.get(_code, ()), *_aliases)))
for _code, _aliases in tuple(COUNTRY_NAMES.items()):
    COUNTRY_NAMES[_code] = tuple(dict.fromkeys((*_aliases, *(
        alias.replace("о-ва", "острова").replace("о-в", "остров") for alias in _aliases
    ))))

SUPPORTED_FLAG_CODES = ISO_COUNTRY_CODES | EXTRA_FLAG_CODES
_SUBDIVISION_TAGS = {"GB-ENG": "gbeng", "GB-SCT": "gbsct", "GB-WLS": "gbwls"}
_SUBDIVISION_EMOJI = {
    code: "\U0001f3f4" + "".join(chr(0xe0000 + ord(char)) for char in tag) + "\U000e007f"
    for code, tag in _SUBDIVISION_TAGS.items()
}


def _normal_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold().replace("ё", "е"))
    return "".join(char for char in text if not unicodedata.combining(char))


_NAME_RULES = [
    (re.compile(r"(?<!\w)" + r"[\W_]+".join(re.escape(word) for word in re.findall(r"\w+", _normal_name(alias))) + r"(?!\w)"), code)
    for alias, code in sorted(
        {(alias, code) for code, aliases in COUNTRY_NAMES.items() for alias in aliases if len(alias) > 2},
        key=lambda pair: (-len(pair[0]), -len(pair[1]), pair[1]),
    )
]


def flag_for_code(code: str) -> str:
    """Флаг по двухбуквенному коду страны. Непонятный код — пусто."""
    text = str(code or "").strip().upper()
    if text in _SUBDIVISION_EMOJI:
        return _SUBDIVISION_EMOJI[text]
    if text not in SUPPORTED_FLAG_CODES:
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

    for code, emoji in _SUBDIVISION_EMOJI.items():
        if emoji in text:
            return code
    for index in range(len(text) - 1):
        pair = text[index:index + 2]
        if all(0x1f1e6 <= ord(char) <= 0x1f1ff for char in pair):
            code = "".join(chr(ord(char) - 0x1f1e6 + ord("A")) for char in pair)
            if code in SUPPORTED_FLAG_CODES:
                return code

    subdivision = re.search(r"(?<!\w)(GB-(?:ENG|SCT|WLS))(?!\w)", text, re.I)
    if subdivision:
        return subdivision[1].upper()
    lowered = _normal_name(text)
    # St. Barthélemy начинается с сокращения Saint, а не с кода ST.
    for pattern, code in _NAME_RULES:
        if pattern.match(lowered):
            return code
    prefix = re.match(r"^[\[(\s]*([^\W\d_]{2})(?![^\W\d_])", text)
    if prefix:
        token = _tokens(prefix[1])[0]
        if token == "UK":
            return "GB"
        if token in SUPPORTED_FLAG_CODES:
            return token

    # Полное название точнее случайного двухбуквенного слова внутри него:
    # «о-ва» в названии территории не должно превращаться в код BA.
    for pattern, code in _NAME_RULES:
        if pattern.search(lowered):
            return code

    # Подписки также ставят код после имени или в скобках.
    for token in _tokens(text):
        if token == "UK":
            return "GB"
        if token in SUPPORTED_FLAG_CODES:
            return token

    return ""


#: Кириллические буквы, неотличимые на вид от латинских.
#:
#: Подписки пишут названия по-русски, и код страны в них нередко набран
#: тем же кириллическим раскладом: «АL Албания» вместо «AL Албания».
#: На экране разницы нет — «А» и «A» рисуются одинаково, — а для разбора
#: это разные символы.
#:
#: Так и терялась Албания: разделителем считалось всё, кроме латиницы,
#: кириллическая «А» съедалась вместе с пробелом, от кода оставалась
#: одна буква «L», и страна не опознавалась. Флага не было у неё одной —
#: у соседей по списку код был набран латиницей.
#: Буквы, которые выглядят латинскими, но ими не являются.
#:
#: Две беды, и обе встретились на живых подписках.
#:
#: Первая — кириллица: код страны набирают русской раскладкой, «АL
#: Албания» вместо «AL Албания». На экране разницы нет.
#:
#: Вторая — малые капители Unicode: подписка пишет код красиво, «ɢʙ»,
#: «ɴʟ», «ᴅᴇ». Это отдельные символы (U+0262, U+0274, U+1D05), и у них
#: нет верхнего регистра вовсе: `"ɢʙ".upper()` возвращает то же «ɢʙ».
#: Поэтому проверка на код страны их не узнавала, и рядом с флагом
#: оставались буквы, которые он и должен был заменить.
#:
#: Флаг при этом находился — но не по коду, а по названию страны, и это
#: сбивало с толку: выглядело так, будто код распознан.
_CYRILLIC_LOOKALIKES = str.maketrans({
    # Кириллица
    "А": "A", "В": "B", "С": "C", "Е": "E", "Н": "H", "К": "K",
    "М": "M", "О": "O", "Р": "P", "Т": "T", "У": "Y", "Х": "X",
    "а": "a", "в": "b", "с": "c", "е": "e", "н": "h", "к": "k",
    "м": "m", "о": "o", "р": "p", "т": "t", "у": "y", "х": "x",
    # Малые капители
    "ᴀ": "A", "ʙ": "B", "ᴄ": "C", "ᴅ": "D", "ᴇ": "E", "ꜰ": "F",
    "ɢ": "G", "ʜ": "H", "ɪ": "I", "ᴊ": "J", "ᴋ": "K", "ʟ": "L",
    "ᴍ": "M", "ɴ": "N", "ᴏ": "O", "ᴘ": "P", "ǫ": "Q", "ʀ": "R",
    "ꜱ": "S", "ᴛ": "T", "ᴜ": "U", "ᴠ": "V", "ᴡ": "W", "ʏ": "Y",
    "ᴢ": "Z",
})


def _tokens(text: str) -> list[str]:
    """Двухбуквенные слова имени, приведённые к верхнему регистру.

    Разделителями считаем всё, кроме букв: скобки, дефисы, точки. Так
    «[NL]-1» и «NL Нидерланды» дают одно и то же.

    Слово берётся целиком, вместе с кириллицей, и только потом похожие
    буквы заменяются латинскими. Порядок здесь важен и проверен ошибкой:
    сначала я резал строку по латинице, а кириллицу считал разделителем
    — тогда «Мой сервер» распадалось на куски, из которых складывалось
    «MO», и сервер получал флаг Макао. Целое слово такого не даёт:
    «Мой» и «сервер» длиннее двух букв и отсеиваются сразу.
    """
    import re

    parts = re.findall(r"[^\W\d_]+", str(text or ""), flags=re.UNICODE)
    return [
        part.translate(_CYRILLIC_LOOKALIKES).upper()
        for part in parts
        if len(part) == 2
    ]


#: Диапазон символов-индикаторов регионов. Пара таких символов — это и
#: есть флаг-эмодзи: 🇳🇱 состоит из U+1F1F3 и U+1F1F1.
_REGIONAL_INDICATOR_FIRST = 0x1F1E6
_REGIONAL_INDICATOR_LAST = 0x1F1FF

#: Что выбрасываем заодно с флагом: селектор начертания и «нулевой»
#: разделитель. Подписки вставляют их между символами вперемешку.
_INVISIBLE = {"️", "︎", "​", "‍"}


def _is_regional_indicator(char: str) -> bool:
    return _REGIONAL_INDICATOR_FIRST <= ord(char) <= _REGIONAL_INDICATOR_LAST


def _strip_leading_flag_emoji(text: str) -> str:
    """Срезает флаг-эмодзи в начале строки, если он там есть."""
    for emoji in _SUBDIVISION_EMOJI.values():
        if text.startswith(emoji):
            return text[len(emoji):].lstrip()
    index = 0
    length = len(text)
    found = 0

    while index < length:
        char = text[index]
        if char in _INVISIBLE:
            index += 1
            continue
        if _is_regional_indicator(char):
            found += 1
            index += 1
            continue
        break

    if found < 2:
        return text
    return text[index:].lstrip()


def _strip_leading_code(text: str) -> str:
    """Срезает двухбуквенное сокращение страны в начале строки."""
    parts = text.split(None, 1)
    if len(parts) != 2:
        return text

    normalized = parts[0].translate(_CYRILLIC_LOOKALIKES).upper()
    if normalized.isascii() and normalized in SUPPORTED_FLAG_CODES:
        return parts[1]
    return text


def strip_country_prefix(title: str) -> str:
    """Убирает из начала названия всё, что уже сказано флагом.

    Флаг рисуется значком слева от строки. Оставлять рядом ещё и код
    страны — значит писать её дважды.

    ## Почему одного правила мало

    Сокращение бывает трёх видов, и все три встречаются в одной подписке.

    Обычные латинские буквы — «NL Нидерланды». Кириллица в той же
    раскладке — «АL Албания», «СН Швейцария»: набирают вслепую, и «А»
    оказывается русской. И флаг-эмодзи — «🇳🇱 Нидерланды».

    Последний и остался на экране после первой правки. Обмануло то, как
    его рисует Windows: шрифта для флагов там нет, и пара
    символов-индикаторов выводится двумя буквами в рамочках. Выглядит как
    «ɴʟ» — то есть ровно как код, который мы вроде бы уже срезали.
    Поэтому я и проверял разбор кодов, а надо было — эмодзи.

    Разбор его не брал: символы-индикаторы не буквы, `isalpha()` на них
    отвечает False, и проверка выходила из функции на первой же строчке.

    ## Почему два прохода

    Подписки ставят и то, и другое сразу: «🇬🇧 GB Великобритания».
    Срезав только эмодзи, оставили бы код, а срезав только код — не
    тронули бы ничего, потому что первым в строке стоит эмодзи.
    """
    text = str(title or "").strip()

    # Порядок фиксирован: эмодзи всегда впереди кода, не наоборот.
    text = _strip_leading_flag_emoji(text)
    text = _strip_leading_code(text)

    return text.strip()


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
#: `nl.png`, `gb.png`. При неизвестной стране страница рисует глобус.
FLAGS_DIR_NAME = "flags"

#: Высота значка в списке. Ширина подбирается по пропорции картинки:
#: у флагов она разная, и растягивать их до квадрата нельзя.
#:
#: Держится в паре с SERVER_LIST_ICON_HEIGHT в vpn/ui/page.py: там под
#: значок отводится место в строке. Разойдутся — флаг обрежется или
#: повиснет в пустой рамке.
FLAG_HEIGHT = 24

_ICON_CACHE: dict[str, object] = {}


def flags_dir():
    """Папка с картинками флагов."""
    from config.runtime_layout import APPLICATION_PATHS

    return APPLICATION_PATHS.ico_dir / FLAGS_DIR_NAME


def flag_image_path(code: str):
    """Путь к картинке флага. Нет файла — None."""
    text = str(code or "").strip().lower()
    if text.upper() not in SUPPORTED_FLAG_CODES:
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

    # Молчаливый пропуск здесь уже стоил разбирательства: у одной страны
    # из десятка флаг не появлялся, а в журнале об этом не было ни
    # слова — ни про отсутствующий файл, ни про нечитаемую картинку.
    # Отличать эти случаи важно: первый лечится подкладыванием файла,
    # второй — заменой набора.
    if path is None:
        _log_missing_flag(code, "нет файла")
    else:
        try:
            from PyQt6.QtGui import QIcon, QPixmap

            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                _log_missing_flag(code, f"картинка не читается: {path.name}")
            else:
                # QIcon сам подберёт разрешение под DPI; раннее уменьшение
                # до 24 px размывало флаги на мониторах с масштабом 150–200 %.
                icon = QIcon(str(path))
        except Exception as exc:
            _log_missing_flag(code, f"{path.name}: {exc}")
            icon = None

    _ICON_CACHE[code] = icon
    return icon


def _log_missing_flag(code: str, reason: str) -> None:
    """Пишет в журнал, почему у страны нет флага. Раз на страну.

    Кэш значков и так хранит по одной записи на страну, но пишется
    сообщение только при первом промахе: список перечитывается на каждое
    переключение вкладки, и без этого журнал заполнился бы повторами.
    """
    try:
        from log.log import log

        log(f"Флаг {code}: {reason}", "DEBUG")
    except Exception:
        pass


def clear_icon_cache() -> None:
    """Сбрасывает кэш значков — нужен после подкладывания картинок."""
    _ICON_CACHE.clear()


__all__ = [
    "COUNTRY_NAMES",
    "FLAGS_DIR_NAME",
    "FLAG_HEIGHT",
    "SUPPORTED_FLAG_CODES",
    "clear_icon_cache",
    "country_code",
    "decorate",
    "flag_for_code",
    "flag_icon",
    "flag_image_path",
    "flags_dir",
    "strip_country_prefix",
]
