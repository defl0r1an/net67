"""Имена сайтов из сертификата сервера.

Сертификат HTTPS перечисляет домены, для которых он выдан (поле SAN). Это
честный способ узнать «кто ещё живёт на этом адресе», не обращаясь к внешним
сервисам. Проверка сертификата здесь выключена нарочно: интересен как раз
чужой или подменённый сертификат, а стандартный ``ssl`` отдаёт разобранные
поля только у проверенного. DER разбирается библиотекой cryptography: поиск
байтов OID в произвольном месте путал имя издателя с именем сайта.
"""

from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass
from ipaddress import ip_address

KIND_OK = "ok"
KIND_TIMEOUT = "timeout"
KIND_REFUSED = "refused"
KIND_TLS = "tls"
KIND_ERROR = "error"


@dataclass(frozen=True, slots=True)
class CertNames:
    kind: str
    names: tuple[str, ...] = ()
    common_name: str = ""
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.kind == KIND_OK


def subject_alt_names(der: bytes) -> tuple[str, ...]:
    from cryptography import x509

    try:
        cert = x509.load_der_x509_certificate(der)
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        names = [str(name).strip().lower() for name in san.get_values_for_type(x509.DNSName)]
        names.extend(str(address) for address in san.get_values_for_type(x509.IPAddress))
        return tuple(dict.fromkeys(names))
    except (ValueError, x509.ExtensionNotFound, x509.DuplicateExtension, x509.UnsupportedGeneralNameType):
        return ()


def common_name(der: bytes) -> str:
    from cryptography import x509
    from cryptography.x509.oid import NameOID

    try:
        cert = x509.load_der_x509_certificate(der)
        values = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        return str(values[0].value).strip() if values else ""
    except ValueError:
        return ""


def fetch_cert_names(ip: str, *, server_name: str | None = None, port: int = 443, timeout_s: float = 4.0) -> CertNames:
    """Подключается к адресу и читает имена из его сертификата. Исключений не бросает.

    ``server_name`` — имя сайта, которое называем серверу (SNI). Без него сервер
    отдаёт сертификат «по умолчанию» — он и показывает, чей это адрес.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        family = socket.AF_INET6 if ip_address(ip).version == 6 else socket.AF_INET
    except ValueError as exc:
        return CertNames(kind=KIND_ERROR, detail=str(exc))

    try:
        with socket.socket(family, socket.SOCK_STREAM) as raw:
            raw.settimeout(timeout_s)
            raw.connect((ip, port))
            with context.wrap_socket(raw, server_hostname=server_name or None) as tls:
                der = tls.getpeercert(binary_form=True) or b""
    except socket.timeout:
        return CertNames(kind=KIND_TIMEOUT, detail="сервер не ответил вовремя")
    except ConnectionRefusedError:
        return CertNames(kind=KIND_REFUSED, detail=f"порт {port} закрыт")
    except ssl.SSLError as exc:
        return CertNames(kind=KIND_TLS, detail=str(getattr(exc, "reason", "") or exc))
    except OSError as exc:
        return CertNames(kind=KIND_ERROR, detail=str(exc))

    if not der:
        return CertNames(kind=KIND_TLS, detail="сервер не прислал сертификат")
    return CertNames(kind=KIND_OK, names=subject_alt_names(der), common_name=common_name(der))


__all__ = [
    "KIND_ERROR",
    "KIND_OK",
    "KIND_REFUSED",
    "KIND_TIMEOUT",
    "KIND_TLS",
    "CertNames",
    "common_name",
    "fetch_cert_names",
    "subject_alt_names",
]
