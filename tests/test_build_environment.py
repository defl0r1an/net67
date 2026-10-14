"""Проверяет защиту сборки от чужих DLL в PATH."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_build_environment", ROOT / "scripts/prepare_build_environment.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_system_libraries_precede_foreign_tools():
    value = module.build_path(r"C:\Tools\Poppler;C:\Windows\System32;C:\Tools\Git", r"C:\Windows", r"C:\Python\python.exe")
    assert value.split(";") == [r"C:\Windows\System32", r"C:\Python", r"C:\Windows", r"C:\Tools\Poppler", r"C:\Tools\Git"]


def test_path_deduplicates_case_and_quotes():
    value = module.build_path('"c:\\windows\\system32";;C:\\Python', r"C:\Windows", r"C:\Python\python.exe")
    assert value.split(";") == [r"C:\Windows\System32", r"C:\Python", r"C:\Windows"]


def test_both_builds_prepare_library_search():
    for path in ("scripts/build_local.ps1", ".github/workflows/windows-release.yml"):
        source = (ROOT / path).read_text(encoding="utf-8-sig")
        assert "$env:PATH =" in source
        assert "scripts\\prepare_build_environment.py" in source


def test_local_build_remains_readable_by_powershell_5():
    assert (ROOT / "scripts/build_local.ps1").read_text(encoding="utf-8-sig").isascii()
