from __future__ import annotations

import re


WINWS2_LUA_INIT_PATHS: tuple[str, ...] = (
    "lua/zapret-lib.lua",
    "lua/zapret-antidpi.lua",
    "lua/zapret-auto.lua",
    "lua/custom_funcs.lua",
    "lua/custom_diag.lua",
    "lua/zapret-multishake.lua",
    "lua/fakemultisplit.lua",
    "lua/fakemultidisorder.lua",
)

CORE_LUA_INITS: tuple[str, ...] = WINWS2_LUA_INIT_PATHS[:5]
WINWS2_LUA_INIT_LINES: tuple[str, ...] = tuple(
    f"--lua-init=@{lua_path}" for lua_path in WINWS2_LUA_INIT_PATHS
)

EXTENSION_LUA_INITS: dict[str, set[str]] = {
    WINWS2_LUA_INIT_PATHS[5]: {
        "hostfakesplit_stealth",
        "hostfakesplit_chaos",
        "hostfakesplit_multi",
        "hostfakesplit_gradual",
        "hostfakesplit_decoy",
    },
    WINWS2_LUA_INIT_PATHS[6]: {
        "fakemultisplit",
    },
    WINWS2_LUA_INIT_PATHS[7]: {
        "fakemultidisorder",
    },
}

def preset_path_value(path, base_dir=None) -> str:
    """Путь в том виде, в каком его переживёт файл параметров winws2.

    Движок разбирает файл параметров по пробелам и кавычек не понимает.
    Абсолютный путь вида `C:\\Program Files\\net67\\lists\\ipset-all.txt`
    разваливается на два куска, и запуск падает с «failed to split command
    line options from file». Встроенные пресеты поэтому и пишут `lists/...`
    — относительно каталога программы, откуда движок и запускается.

    Путь приводится к относительному от base_dir (по умолчанию — корень
    установки). Если это невозможно (другой диск, каталог вне программы),
    возвращается исходный путь: сломать его сильнее нельзя, а на путях без
    пробелов он работает.
    """
    text = str(path or "")
    if not text:
        return text

    if base_dir is None:
        try:
            from config.runtime_layout import APPLICATION_PATHS

            base_dir = str(APPLICATION_PATHS.root)
        except Exception:
            return text

    # Разбор путей берётся под стиль самого пути, а не под систему, где
    # выполняется код. Программа живёт на Windows, но тесты гоняются и на
    # Linux, где posixpath не видит в `C:\...\lists` ни разделителей, ни
    # диска и возвращает путь целиком — вместе с пробелом, ради которого
    # всё и затевалось.
    import ntpath
    import posixpath

    module = ntpath if ("\\" in text or ntpath.splitdrive(text)[0]) else posixpath

    try:
        relative = module.relpath(text, str(base_dir))
    except ValueError:
        return text

    if relative.startswith(".."):
        return text

    return relative.replace("\\", "/")


_LUA_DESYNC_FUNC_RE = re.compile(r"--lua-desync=([a-z0-9_]+)", re.IGNORECASE)
_LUA_INIT_RE = re.compile(r"--lua-init=@?(.+)", re.IGNORECASE)
_STRATEGY_TAG_RE = re.compile(r":strategy=\d+", re.IGNORECASE)
_CIRCULAR_LUA_DESYNC_RE = re.compile(r"(?<!\S)--lua-desync=circular(?::\S*)?(?=\s|$)", re.IGNORECASE)


def is_winws2_circular_preset_source(source_text: str) -> bool:
    for raw in str(source_text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _CIRCULAR_LUA_DESYNC_RE.search(stripped):
            return True
    return False


def has_winws2_strategy_tags(source_text: str) -> bool:
    for raw in str(source_text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.lower().startswith("--lua-desync=") and _STRATEGY_TAG_RE.search(stripped):
            return True
    return False


def ensure_winws2_lua_init_lines(source_text: str) -> str:
    text = str(source_text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    existing_inits: set[str] = set()
    used_funcs: set[str] = set()
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        init_match = _LUA_INIT_RE.match(stripped)
        if init_match:
            existing_inits.add(init_match.group(1).strip().replace("\\", "/").lower())
        for func_match in _LUA_DESYNC_FUNC_RE.finditer(stripped):
            used_funcs.add(func_match.group(1).strip().lower())

    if not used_funcs:
        return text

    needed: list[str] = []
    for lua_path in CORE_LUA_INITS:
        if lua_path.lower() not in existing_inits:
            needed.append(lua_path)

    for lua_path, funcs in EXTENSION_LUA_INITS.items():
        if lua_path.lower() not in existing_inits and used_funcs & funcs:
            needed.append(lua_path)

    if not needed:
        return text

    insert_idx = 0
    for idx, raw in enumerate(lines):
        stripped = raw.strip()
        if stripped.lower().startswith("--lua-init="):
            insert_idx = idx + 1
        elif insert_idx == 0 and (stripped.startswith("#") or stripped == ""):
            insert_idx = idx + 1

    new_lines = [f"--lua-init=@{lua_path}" for lua_path in needed]
    lines = [*lines[:insert_idx], *new_lines, *lines[insert_idx:]]
    return "\n".join(lines)


__all__ = [
    "CORE_LUA_INITS",
    "EXTENSION_LUA_INITS",
    "WINWS2_LUA_INIT_LINES",
    "WINWS2_LUA_INIT_PATHS",
    "ensure_winws2_lua_init_lines",
    "has_winws2_strategy_tags",
    "is_winws2_circular_preset_source",
]
