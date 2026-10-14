"""Не даёт DLL сторонних инструментов подменять системные зависимости Qt."""
import ntpath
import os
import sys


def build_path(path: str, windows_dir: str, python_executable: str) -> str:
    preferred = [ntpath.join(windows_dir, "System32"), ntpath.dirname(python_executable), windows_dir]
    result = []
    seen = set()
    for item in [*preferred, *path.split(";")]:
        item = item.strip().strip('"')
        key = ntpath.normcase(ntpath.normpath(item))
        if item and key not in seen:
            seen.add(key)
            result.append(item)
    return ";".join(result)


if __name__ == "__main__":
    print(build_path(os.environ.get("PATH", ""), os.environ.get("SystemRoot", r"C:\Windows"), sys.executable))
