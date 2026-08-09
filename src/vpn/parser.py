"""Разбор конфигураций AmneziaWG и WireGuard.

Поддерживаются два формата ввода:

* Текст ``.conf`` — обычный WireGuard-INI, при необходимости с
  расширенными полями AmneziaWG (Jc, Jmin, Jmax, S1..S4, H1..H4, I*, J*).
* Ссылка ``vpn://`` — как её выдаёт AmneziaVPN. Внутри base64, а под
  ним встречается и сжатый JSON, и голый JSON, и просто текст .conf.

Модуль чистый: ни сети, ни файловой системы, ни Qt.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import zlib
from dataclasses import dataclass, field, replace


class VpnConfigError(ValueError):
    """Понятная пользователю ошибка разбора конфигурации."""


#: Ключи WireGuard — 32 байта в base64, то есть 44 символа с '=' на конце.
_KEY_RE = re.compile(r"^[A-Za-z0-9+/]{42}[A-Za-z0-9+/=]{2}$")

#: Расширенные параметры обфускации AmneziaWG.
#:
#: Порядок важен только для вывода в .conf. S3, S4 и семейства I*/J*
#: появились в AmneziaWG 1.5 — реальные конфигурации AmneziaVPN их
#: содержат, и без них разбор падал.
AWG_FIELDS = (
    "Jc", "Jmin", "Jmax",
    "S1", "S2", "S3", "S4",
    "H1", "H2", "H3", "H4",
    "I1", "I2", "I3", "I4", "I5",
    "J1", "J2", "J3",
    "Itime",
)

#: Поля, которые обязаны быть целым числом.
_AWG_INT_FIELDS = frozenset({"Jc", "Jmin", "Jmax", "S1", "S2", "S3", "S4", "Itime"})

#: Поля-заголовки. Могут быть числом либо диапазоном "мин-макс":
#: AmneziaVPN выдаёт, например, ``H1 = 1429615376-1775318475``.
_AWG_RANGE_FIELDS = frozenset({"H1", "H2", "H3", "H4"})

#: Целое число или диапазон двух целых через дефис.
_AWG_RANGE_RE = re.compile(r"^\d+(?:-\d+)?$")


@dataclass(frozen=True, slots=True)
class AmneziaParams:
    """Параметры обфускации AmneziaWG.

    Именно они отличают AmneziaWG от обычного WireGuard: пакеты
    маскируются мусорными байтами и подменёнными заголовками.
    """

    #: Значения хранятся строками: заголовки H1..H4 бывают диапазонами,
    #: а поля I1..I5 в AmneziaWG 1.5 — это шаблоны пакетов, не числа.
    values: dict[str, str] = field(default_factory=dict)

    @property
    def enabled(self) -> bool:
        return bool(self.values)

    def as_conf_lines(self) -> list[str]:
        return [f"{name} = {self.values[name]}" for name in AWG_FIELDS if name in self.values]


@dataclass(frozen=True, slots=True)
class VpnProfile:
    """Разобранный профиль подключения."""

    name: str = ""
    private_key: str = ""
    address: str = ""
    dns: str = ""
    mtu: int | None = None

    public_key: str = ""
    preshared_key: str = ""
    endpoint_host: str = ""
    endpoint_port: int = 0
    allowed_ips: str = "0.0.0.0/0, ::/0"
    keepalive: int | None = None

    awg: AmneziaParams = field(default_factory=AmneziaParams)
    source: str = "conf"

    @property
    def endpoint(self) -> str:
        if not self.endpoint_host:
            return ""
        return f"{self.endpoint_host}:{self.endpoint_port}" if self.endpoint_port else self.endpoint_host

    @property
    def protocol(self) -> str:
        return "AmneziaWG" if self.awg.enabled else "WireGuard"


def _is_key(value: str) -> bool:
    return bool(_KEY_RE.match(str(value or "").strip()))


def _split_endpoint(value: str) -> tuple[str, int]:
    raw = str(value or "").strip()
    if not raw:
        return ("", 0)

    # IPv6 в квадратных скобках: [2001:db8::1]:51820
    if raw.startswith("["):
        host, _, port = raw.partition("]")
        host = host[1:]
        port = port.lstrip(":")
    else:
        host, _, port = raw.rpartition(":")
        if not host:
            host, port = raw, ""

    try:
        port_number = int(port) if port else 0
    except ValueError:
        raise VpnConfigError(f"Некорректный порт в адресе сервера: {raw}") from None

    if port_number and not (0 < port_number < 65536):
        raise VpnConfigError(f"Порт вне допустимого диапазона: {port_number}")

    return (host.strip(), port_number)


def _validate_awg_value(name: str, raw_value: str) -> str:
    """Проверяет значение параметра обфускации и возвращает его как есть.

    Числа не приводятся к int намеренно: заголовки H1..H4 бывают
    диапазонами вида ``1429615376-1775318475``, а шаблоны пакетов
    I1..I5 вообще не числа. Клиент AmneziaWG ждёт исходную запись.
    """
    value = str(raw_value or "").strip()
    if not value:
        raise VpnConfigError(f"Параметр {name} пуст")

    if name in _AWG_INT_FIELDS:
        try:
            int(value)
        except ValueError:
            raise VpnConfigError(f"Параметр {name} должен быть числом") from None
        return value

    if name in _AWG_RANGE_FIELDS:
        if not _AWG_RANGE_RE.match(value):
            raise VpnConfigError(
                f"Параметр {name} должен быть числом или диапазоном вида 100-200"
            )
        return value

    # I1..I5, J1..J3 — произвольные шаблоны, передаём без проверки.
    return value


def parse_wireguard_conf(text: str, *, name: str = "") -> VpnProfile:
    """Разбирает текст .conf в профиль."""
    raw = str(text or "").strip()
    if not raw:
        raise VpnConfigError("Конфигурация пуста")

    section = ""
    interface: dict[str, str] = {}
    peer: dict[str, str] = {}

    for line in raw.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if section == "interface":
            interface[key] = value
        elif section == "peer":
            peer[key] = value

    if not interface and not peer:
        raise VpnConfigError("Не найдены секции [Interface] и [Peer]")
    if not interface.get("PrivateKey"):
        raise VpnConfigError("В секции [Interface] нет PrivateKey")
    if not peer.get("PublicKey"):
        raise VpnConfigError("В секции [Peer] нет PublicKey")

    private_key = interface["PrivateKey"]
    public_key = peer["PublicKey"]
    if not _is_key(private_key):
        raise VpnConfigError("PrivateKey не похож на ключ WireGuard")
    if not _is_key(public_key):
        raise VpnConfigError("PublicKey не похож на ключ WireGuard")

    host, port = _split_endpoint(peer.get("Endpoint", ""))
    if not host:
        raise VpnConfigError("В секции [Peer] не указан Endpoint")

    awg_values: dict[str, str] = {}
    for field_name in AWG_FIELDS:
        if field_name not in interface:
            continue
        awg_values[field_name] = _validate_awg_value(field_name, interface[field_name])

    def _optional_int(source: dict[str, str], key: str) -> int | None:
        if key not in source:
            return None
        try:
            return int(source[key])
        except ValueError:
            return None

    return VpnProfile(
        name=str(name or "").strip(),
        private_key=private_key,
        address=interface.get("Address", ""),
        dns=interface.get("DNS", ""),
        mtu=_optional_int(interface, "MTU"),
        public_key=public_key,
        preshared_key=peer.get("PresharedKey", ""),
        endpoint_host=host,
        endpoint_port=port,
        allowed_ips=peer.get("AllowedIPs", "0.0.0.0/0, ::/0"),
        keepalive=_optional_int(peer, "PersistentKeepalive"),
        awg=AmneziaParams(values=awg_values),
        source="conf",
    )


def _decode_vpn_payload(payload: str) -> bytes:
    """Достаёт из ссылки vpn:// исходные байты.

    Формат встречается в нескольких вариантах, поэтому пробуем по
    очереди: сжатие Qt (4 байта длины + zlib), голый zlib и просто
    base64 без сжатия.
    """
    cleaned = payload.strip().replace("\n", "").replace("\r", "")
    # AmneziaVPN использует url-safe алфавит, но встречается и обычный.
    cleaned = cleaned.replace("-", "+").replace("_", "/")
    padding = (-len(cleaned)) % 4
    try:
        blob = base64.b64decode(cleaned + "=" * padding)
    except (binascii.Error, ValueError) as exc:
        raise VpnConfigError("Ключ повреждён: не удалось раскодировать base64") from exc

    if not blob:
        raise VpnConfigError("Ключ пуст")

    # Вариант Qt qCompress: спереди 4 байта размера, дальше zlib.
    for candidate in (blob[4:], blob):
        try:
            return zlib.decompress(candidate)
        except zlib.error:
            continue

    return blob


def parse_vpn_key(text: str, *, name: str = "") -> VpnProfile:
    """Разбирает ссылку вида vpn://..."""
    raw = str(text or "").strip()
    if not raw:
        raise VpnConfigError("Ключ пуст")

    lowered = raw.lower()
    if lowered.startswith("vpn://"):
        raw = raw[len("vpn://") :]
    elif "://" in raw:
        raise VpnConfigError("Поддерживаются только ключи, начинающиеся с vpn://")

    decoded = _decode_vpn_payload(raw)

    try:
        text = decoded.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise VpnConfigError("Ключ не содержит читаемой конфигурации") from exc

    stripped = text.strip()

    # Порядок важен. JSON пробуем первым: он тоже содержит подстроки
    # "[Interface]" и "[Peer]" — но внутри экранированной строки, и как
    # INI такой текст не читается.
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        data = None

    if data is None:
        # Часть ключей — просто base64 от текста .conf, без JSON и без
        # сжатия. Именно такие выдаёт AmneziaVPN для готового профиля
        # AmneziaWG, и разбор их как JSON падал на «нет читаемой
        # конфигурации», хотя конфиг лежал прямо внутри.
        if "[Interface]" in stripped and "[Peer]" in stripped:
            return replace(parse_wireguard_conf(stripped, name=name), source="key")
        raise VpnConfigError("Ключ не содержит читаемой конфигурации")

    if not isinstance(data, dict):
        raise VpnConfigError("Ключ не содержит читаемой конфигурации")

    config_text = _find_wireguard_config(data)
    if not config_text:
        raise VpnConfigError(
            "В ключе нет конфигурации WireGuard или AmneziaWG. "
            "Возможно, это ключ другого протокола."
        )

    profile = parse_wireguard_conf(config_text, name=name or str(data.get("description") or ""))
    return replace(profile, source="key")


def _find_wireguard_config(data: object, *, depth: int = 0) -> str:
    """Ищет в JSON текст конфигурации.

    Структура ключа AmneziaVPN менялась между версиями, поэтому не
    полагаемся на конкретный путь, а обходим дерево и берём первое
    значение, похожее на WireGuard-конфиг.
    """
    if depth > 6:
        return ""

    if isinstance(data, str):
        text = data.strip()
        if "[Interface]" in text and "[Peer]" in text:
            return text
        return ""

    if isinstance(data, dict):
        # Наиболее вероятные ключи проверяем первыми.
        for key in ("last_config", "config", "wireguard_config_data", "awg_config_data"):
            found = _find_wireguard_config(data.get(key), depth=depth + 1)
            if found:
                return found
        for value in data.values():
            found = _find_wireguard_config(value, depth=depth + 1)
            if found:
                return found
        return ""

    if isinstance(data, list):
        for item in data:
            found = _find_wireguard_config(item, depth=depth + 1)
            if found:
                return found

    return ""


def parse_any(text: str, *, name: str = "") -> VpnProfile:
    """Определяет формат сам: ссылка или содержимое .conf."""
    raw = str(text or "").strip()
    if not raw:
        raise VpnConfigError("Введите ключ или содержимое файла конфигурации")

    if raw.lower().startswith("vpn://"):
        return parse_vpn_key(raw, name=name)
    if "[Interface]" in raw or "[Peer]" in raw:
        return parse_wireguard_conf(raw, name=name)
    if "://" in raw.split()[0]:
        raise VpnConfigError("Поддерживаются только ключи, начинающиеся с vpn://")

    raise VpnConfigError(
        "Не удалось распознать формат. Вставьте ключ vpn://... "
        "или содержимое файла .conf"
    )


def to_conf_text(profile: VpnProfile) -> str:
    """Собирает обратно текст .conf — для экспорта и передачи клиенту."""
    lines = ["[Interface]", f"PrivateKey = {profile.private_key}"]
    if profile.address:
        lines.append(f"Address = {profile.address}")
    if profile.dns:
        lines.append(f"DNS = {profile.dns}")
    if profile.mtu:
        lines.append(f"MTU = {profile.mtu}")
    lines.extend(profile.awg.as_conf_lines())

    lines.extend(["", "[Peer]", f"PublicKey = {profile.public_key}"])
    if profile.preshared_key:
        lines.append(f"PresharedKey = {profile.preshared_key}")
    if profile.allowed_ips:
        lines.append(f"AllowedIPs = {profile.allowed_ips}")
    if profile.endpoint:
        lines.append(f"Endpoint = {profile.endpoint}")
    if profile.keepalive:
        lines.append(f"PersistentKeepalive = {profile.keepalive}")

    return "\n".join(lines) + "\n"


__all__ = [
    "AWG_FIELDS",
    "AmneziaParams",
    "VpnConfigError",
    "VpnProfile",
    "parse_any",
    "parse_vpn_key",
    "parse_wireguard_conf",
    "to_conf_text",
]
