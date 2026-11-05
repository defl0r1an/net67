"""Полный набор флагов нужен серверам за пределами нескольких популярных стран."""
import json
from pathlib import Path

import pytest

from vpn.flags import ISO_COUNTRY_CODES, SUPPORTED_FLAG_CODES, country_code, flag_for_code, strip_country_prefix

ROOT = Path(__file__).resolve().parents[1]


def test_every_supported_country_and_territory_has_a_real_image():
    from PyQt6.QtGui import QImage
    manifest = json.loads((ROOT / 'ico/flags/source.json').read_text(encoding='utf-8'))
    assert set(manifest['flags']) == SUPPORTED_FLAG_CODES
    assert len(ISO_COUNTRY_CODES) == 249
    for code in SUPPORTED_FLAG_CODES:
        image = QImage(str(ROOT / 'ico/flags' / manifest['flags'][code]['file']))
        assert not image.isNull(), code
        assert image.hasAlphaChannel(), code


@pytest.mark.parametrize(('title', 'expected'), [
    ('Кипр', 'CY'), ('Антарктида 2', 'AQ'), ('🇨🇾 Fast 1', 'CY'),
    ('Сервер 🇦🇶', 'AQ'), ('Zimbabwe', 'ZW'), ('Уганда 3', 'UG'),
    ('French Polynesia', 'PF'), ('Демократическая Республика Конго', 'CD'),
    ('🇪🇺 Europe', 'EU'), ('Косово', 'XK'), ('Scotland', 'GB-SCT'),
    ('Остров Буве', 'BV'), ('Мой сервер', ''), ('Node 3', ''),
    ('О-ва Кайман', 'KY'), ('Англия', 'GB-ENG'), ('GB-SCT Node', 'GB-SCT'),
])
def test_names_and_emoji_are_recognized(title, expected):
    assert country_code(title) == expected


@pytest.mark.parametrize('code', ['GB-ENG', 'GB-SCT', 'GB-WLS'])
def test_subdivision_emoji_is_recognized_and_not_repeated_in_the_title(code):
    emoji = flag_for_code(code)
    assert emoji
    assert country_code(emoji + ' Node') == code
    assert strip_country_prefix(emoji + ' Node') == 'Node'


def test_all_canonical_russian_and_english_territory_names_are_recognized():
    from vpn.country_names import ALL_COUNTRY_NAMES
    for code, names in ALL_COUNTRY_NAMES.items():
        for name in names:
            assert country_code(name + " · 1") == code, (code, name, country_code(name))
