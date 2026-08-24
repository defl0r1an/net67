"""Пути внутри файла параметров winws2 не должны содержать пробелов.

Движок разбирает файл параметров по пробелам и кавычек не понимает. При
установке в `C:\\Program Files\\net67` абсолютный путь разваливается на
два куска, и запуск падает с «failed to split command line options from
file» — ровно это и происходило при каждой диагностике.
"""

from __future__ import annotations

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from profile.winws2_preset_source import preset_path_value  # noqa: E402


BASE = r"C:\Program Files\net67"


def test_path_inside_install_dir_becomes_relative():
    value = preset_path_value(BASE + r"\blockcheck_probe_hosts.txt", BASE)
    assert value == "blockcheck_probe_hosts.txt"
    assert " " not in value


def test_nested_path_keeps_folders_but_loses_the_space():
    value = preset_path_value(BASE + r"\lists\ipset-all.txt", BASE)
    assert value == "lists/ipset-all.txt"
    assert " " not in value


def test_backslashes_become_slashes_like_in_builtin_presets():
    # Встроенные пресеты пишут `lists/...` — тот же вид и здесь.
    assert "\\" not in preset_path_value(BASE + r"\lists\ipset-steam.txt", BASE)


def test_path_outside_install_dir_stays_as_is():
    # Уйти вверх по дереву в файле параметров нельзя ничем лучше
    # абсолютного пути, поэтому его и оставляем.
    outside = r"C:\Users\User\Desktop\my-hosts.txt"
    assert preset_path_value(outside, BASE) == outside


def test_empty_value_survives():
    assert preset_path_value("", BASE) == ""
    assert preset_path_value(None, BASE) == ""


def test_probe_preset_has_no_spaces_in_option_values():
    """Сам пробный пресет диагностики: ни одной строки с пробелом в пути."""
    scanner = pytest.importorskip("blockcheck.strategy_scanner")

    class _Fake:
        _work_dir = BASE

    value = scanner.StrategyScanner._preset_path_value(
        _Fake(), os.path.join(BASE, "blockcheck_probe_hosts.txt")
    )

    assert value == "blockcheck_probe_hosts.txt"
