"""Выключить в браузере ECH или QUIC одной кнопкой — и вернуть как было.

ECH — расширение, которым браузер прячет имя сайта; QUIC (HTTP/3) — быстрый
способ соединения поверх UDP. Проверка после «Применить» доказывает, когда
сайт не открывается именно с ними (``browser_diagnosis``, проверка с QUIC).
Совет «выключите» человеку трудно выполнить руками: в Edge и Chrome
переключателей в настройках нет. Поэтому программа делает это сама, только по
кнопке и только в одном браузере:

* Edge и Chrome — правило браузера текущего пользователя
  (``HKCU\\Software\\Policies\\…``): ``EncryptedClientHelloEnabled = 0`` или
  ``QuicAllowed = 0``. На Edge 156 оба проверены по журналу сети (win10). Отмена
  удаляет только это значение, а пустой раздел, созданный программой, — целиком;
* Firefox — строки в ``user.js`` каждого профиля (настройки Mozilla). Строки
  помечены своей меткой, отмена убирает только их.

Браузер читает правила и ``user.js`` при запуске — его нужно перезапустить.
Реестр и файлы передаются снаружи, поэтому всё проверяется без Windows.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass

from blockcheck.default_browser import BROWSER_CHROME, BROWSER_EDGE, BROWSER_FIREFOX

__all__ = ["ECH", "FEATURES", "POLICY_KEYS", "QUIC", "SwitchResult", "can_switch", "is_disabled", "restore", "turn_off"]

ECH = "ech"
QUIC = "quic"


@dataclass(frozen=True, slots=True)
class Feature:
    name: str
    # Правило Edge и Chrome, которое её выключает (значение 0).
    policy: str
    # Настройки Firefox, которые её выключают (false).
    firefox_prefs: tuple[str, ...]

    @property
    def firefox_mark(self) -> str:
        # Пометка строк, которые дописала программа: по ней отмена убирает только их.
        return f"// net67: {self.name} выключен кнопкой в программе"


FEATURES = {
    ECH: Feature("ECH", "EncryptedClientHelloEnabled", ("network.dns.echconfig.enabled", "network.dns.http3_echconfig.enabled")),
    QUIC: Feature("QUIC", "QuicAllowed", ("network.http.http3.enable",)),
}
POLICY_KEYS = {
    BROWSER_EDGE: r"Software\Policies\Microsoft\Edge",
    BROWSER_CHROME: r"Software\Policies\Google\Chrome",
}


def _backup_key(what: str, family: str) -> str:
    return rf"Software\net67\BrowserSwitch\{family}\{what}"


def _disable_policy(reg, what: str, family: str) -> None:
    feature = FEATURES[what]
    path = POLICY_KEYS[family]
    backup = _backup_key(what, family)
    if reg.get(backup, "Owned") != 1:
        previous = reg.get(path, feature.policy)
        if previous is not None and (type(previous) is not int or not 0 <= previous <= 0xFFFFFFFF):
            raise OSError("У правила браузера неожиданный формат; измените его вручную")
        # Копия должна пережить перезапуск программы и появиться до изменения правила.
        reg.set_dword(backup, "HadKey", int(reg.key_exists(path)))
        reg.set_dword(backup, "HadValue", int(previous is not None))
        if previous is not None:
            reg.set_dword(backup, "Previous", previous)
        reg.set_dword(backup, "Owned", 1)
    reg.set_dword(path, feature.policy, 0)


def _restore_policy(reg, what: str, family: str) -> bool:
    feature = FEATURES[what]
    path = POLICY_KEYS[family]
    backup = _backup_key(what, family)
    if reg.get(backup, "Owned") != 1:
        return False
    # После нашей кнопки правило мог изменить человек или администратор.
    if reg.get(path, feature.policy) == 0:
        if reg.get(backup, "HadValue"):
            reg.set_dword(path, feature.policy, reg.get(backup, "Previous"))
        else:
            reg.delete_value(path, feature.policy)
        if not reg.get(backup, "HadKey") and reg.key_is_empty(path):
            reg.delete_key(path)
    reg.delete_key(backup)
    return True


@dataclass(frozen=True, slots=True)
class SwitchResult:
    ok: bool
    text: str


def can_switch(family: str) -> bool:
    return family in POLICY_KEYS or family == BROWSER_FIREFOX


# --- реестр -----------------------------------------------------------------


class _Registry:
    """Раздел правил браузера в HKCU. Подменяется в тестах."""

    def get(self, path: str, name: str):
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                return winreg.QueryValueEx(key, name)[0]
        except FileNotFoundError:
            return None

    def key_exists(self, path: str) -> bool:
        import winreg

        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, path))
            return True
        except FileNotFoundError:
            return False

    def set_dword(self, path: str, name: str, value: int) -> None:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, int(value))

    def delete_value(self, path: str, name: str) -> None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass

    def key_is_empty(self, path: str) -> bool:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                subkeys, values, _modified = winreg.QueryInfoKey(key)
            return subkeys == 0 and values == 0
        except FileNotFoundError:
            return False

    def delete_key(self, path: str) -> None:
        import winreg

        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except FileNotFoundError:
            pass


# --- Firefox ----------------------------------------------------------------


def firefox_profile_dirs(appdata: str | None = None) -> list[str]:
    """Папки профилей Firefox из ``%APPDATA%\\Mozilla\\Firefox\\profiles.ini``."""
    import configparser

    root = os.path.join(appdata or os.environ.get("APPDATA", ""), "Mozilla", "Firefox")
    parser = configparser.ConfigParser()
    try:
        with open(os.path.join(root, "profiles.ini"), encoding="utf-8", errors="replace") as source:
            parser.read_file(source)
    except OSError:
        return []
    found = []
    for section in parser.sections():
        if not section.startswith("Profile") or not parser.has_option(section, "Path"):
            continue
        path = parser.get(section, "Path").replace("/", os.sep)
        relative = parser.get(section, "IsRelative", fallback="1") == "1"
        full = os.path.join(root, path) if relative else path
        if os.path.isdir(full):
            found.append(full)
    return found


def _firefox_lines(feature: Feature) -> list[str]:
    return [f'user_pref("{name}", false); {feature.firefox_mark}' for name in feature.firefox_prefs]


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", newline="") as source:
            return source.read()
    except FileNotFoundError:
        return ""


def _write(path: str, text: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".net67-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as target:
            target.write(text)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


# --- действия ---------------------------------------------------------------


def is_disabled(what: str, family: str, *, registry=None, profiles: Callable[[], list[str]] = firefox_profile_dirs) -> bool:
    """Выключено этой кнопкой; чужое правило не считается нашим изменением."""
    feature = FEATURES[what]
    if family in POLICY_KEYS:
        reg = registry or _Registry()
        return reg.get(_backup_key(what, family), "Owned") == 1 and reg.get(POLICY_KEYS[family], feature.policy) == 0
    if family == BROWSER_FIREFOX:
        dirs = profiles()
        return bool(dirs) and all(feature.firefox_mark in _read(os.path.join(folder, "user.js")) for folder in dirs)
    return False


def turn_off(what: str, family: str, title: str, *, registry=None, profiles: Callable[[], list[str]] = firefox_profile_dirs) -> SwitchResult:
    feature = FEATURES[what]
    restart = f"Закройте все окна {title} и откройте снова — тогда это заработает."
    try:
        if family in POLICY_KEYS:
            _disable_policy(registry or _Registry(), what, family)
            return SwitchResult(True, f"{feature.name} в {title} выключен. {restart}")
        if family == BROWSER_FIREFOX:
            dirs = profiles()
            if not dirs:
                manual = ", ".join(f"{name} = false" for name in feature.firefox_prefs)
                return SwitchResult(False, f"Не нашёл профилей Firefox. Выключите {feature.name} сами: about:config → {manual}.")
            for folder in dirs:
                path = os.path.join(folder, "user.js")
                text = _read(path)
                if feature.firefox_mark in text:
                    continue
                _write(path, text + ("" if not text or text.endswith("\n") else "\n") + "\n".join(_firefox_lines(feature)) + "\n")
            return SwitchResult(True, f"{feature.name} в {title} выключен. {restart}")
    except (OSError, UnicodeError) as error:
        return SwitchResult(False, f"Не вышло выключить {feature.name} в {title}: {error}")
    return SwitchResult(False, f"В {title} программа {feature.name} выключить не умеет.")


def restore(what: str, family: str, title: str, *, registry=None, profiles: Callable[[], list[str]] = firefox_profile_dirs) -> SwitchResult:
    """Вернуть как было: убрать только то, что добавила кнопка."""
    feature = FEATURES[what]
    try:
        if family in POLICY_KEYS:
            reg = registry or _Registry()
            if not _restore_policy(reg, what, family):
                return SwitchResult(True, f"Правило {feature.name} в {title} не менялось через net67 и сохранено.")
            return SwitchResult(True, f"{feature.name} в {title} снова как раньше. Перезапустите {title}.")
        if family == BROWSER_FIREFOX:
            for folder in profiles():
                path = os.path.join(folder, "user.js")
                text = _read(path)
                if feature.firefox_mark not in text:
                    continue
                own = set(_firefox_lines(feature))
                kept = [line for line in text.splitlines(keepends=True) if line.rstrip("\r\n") not in own]
                if any(line.strip() for line in kept):
                    _write(path, "".join(kept))
                else:
                    os.remove(path)
            return SwitchResult(True, f"{feature.name} в {title} снова как раньше. Перезапустите {title}.")
    except (OSError, UnicodeError) as error:
        return SwitchResult(False, f"Не вышло вернуть {feature.name} в {title}: {error}")
    return SwitchResult(False, f"В {title} программа {feature.name} не меняла.")
