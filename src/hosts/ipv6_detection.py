from __future__ import annotations

import ctypes
import ipaddress
import os
import socket
from functools import lru_cache


_IPV6_PROBE_TARGETS: tuple[tuple[str, int], ...] = (
    ("2001:4860:4860::8888", 53),
    ("2606:4700:4700::1111", 53),
    ("2620:119:35::35", 53),
)

_AF_INET6 = 23
_ERROR_BUFFER_OVERFLOW = 111
_ERROR_SUCCESS = 0
_IF_OPER_STATUS_UP = 1
_IF_TYPE_SOFTWARE_LOOPBACK = 24
_GAA_FLAGS = 0x0002 | 0x0004 | 0x0008 | 0x0080


class _SocketAddress(ctypes.Structure):
    _fields_ = [
        ("lpSockaddr", ctypes.c_void_p),
        ("iSockaddrLength", ctypes.c_int),
    ]


class _IpAdapterUnicastAddress(ctypes.Structure):
    pass


_IpAdapterUnicastAddressPtr = ctypes.POINTER(_IpAdapterUnicastAddress)
_IpAdapterUnicastAddress._fields_ = [
    ("Length", ctypes.c_ulong),
    ("Flags", ctypes.c_ulong),
    ("Next", _IpAdapterUnicastAddressPtr),
    ("Address", _SocketAddress),
    ("PrefixOrigin", ctypes.c_int),
    ("SuffixOrigin", ctypes.c_int),
    ("DadState", ctypes.c_int),
    ("ValidLifetime", ctypes.c_ulong),
    ("PreferredLifetime", ctypes.c_ulong),
    ("LeaseLifetime", ctypes.c_ulong),
    ("OnLinkPrefixLength", ctypes.c_ubyte),
]


class _IpAdapterGatewayAddress(ctypes.Structure):
    pass


_IpAdapterGatewayAddressPtr = ctypes.POINTER(_IpAdapterGatewayAddress)
_IpAdapterGatewayAddress._fields_ = [
    ("Length", ctypes.c_ulong),
    ("Reserved", ctypes.c_ulong),
    ("Next", _IpAdapterGatewayAddressPtr),
    ("Address", _SocketAddress),
]


class _IpAdapterAddresses(ctypes.Structure):
    pass


_IpAdapterAddressesPtr = ctypes.POINTER(_IpAdapterAddresses)
_IpAdapterAddresses._fields_ = [
    ("Length", ctypes.c_ulong),
    ("IfIndex", ctypes.c_ulong),
    ("Next", _IpAdapterAddressesPtr),
    ("AdapterName", ctypes.c_char_p),
    ("FirstUnicastAddress", _IpAdapterUnicastAddressPtr),
    ("FirstAnycastAddress", ctypes.c_void_p),
    ("FirstMulticastAddress", ctypes.c_void_p),
    ("FirstDnsServerAddress", ctypes.c_void_p),
    ("DnsSuffix", ctypes.c_wchar_p),
    ("Description", ctypes.c_wchar_p),
    ("FriendlyName", ctypes.c_wchar_p),
    ("PhysicalAddress", ctypes.c_ubyte * 8),
    ("PhysicalAddressLength", ctypes.c_ulong),
    ("Flags", ctypes.c_ulong),
    ("Mtu", ctypes.c_ulong),
    ("IfType", ctypes.c_ulong),
    ("OperStatus", ctypes.c_int),
    ("Ipv6IfIndex", ctypes.c_ulong),
    ("ZoneIndices", ctypes.c_ulong * 16),
    ("FirstPrefix", ctypes.c_void_p),
    ("TransmitLinkSpeed", ctypes.c_ulonglong),
    ("ReceiveLinkSpeed", ctypes.c_ulonglong),
    ("FirstWinsServerAddress", ctypes.c_void_p),
    ("FirstGatewayAddress", _IpAdapterGatewayAddressPtr),
]


class _SockaddrIn6(ctypes.Structure):
    _fields_ = [
        ("sin6_family", ctypes.c_ushort),
        ("sin6_port", ctypes.c_ushort),
        ("sin6_flowinfo", ctypes.c_ulong),
        ("sin6_addr", ctypes.c_ubyte * 16),
        ("sin6_scope_id", ctypes.c_ulong),
    ]


def is_ipv6_address(value: str) -> bool:
    try:
        return ipaddress.ip_address(str(value or "").strip()).version == 6
    except ValueError:
        return False


def _is_usable_local_ipv6(value: str) -> bool:
    try:
        addr = ipaddress.ip_address(str(value or "").strip())
    except ValueError:
        return False
    return (
        addr.version == 6
        and not addr.is_unspecified
        and not addr.is_loopback
        and not addr.is_link_local
        and not addr.is_multicast
    )


def _socket_address_to_ipv6(address: _SocketAddress) -> str:
    if not address.lpSockaddr or address.iSockaddrLength < ctypes.sizeof(_SockaddrIn6):
        return ""
    sockaddr = ctypes.cast(address.lpSockaddr, ctypes.POINTER(_SockaddrIn6)).contents
    if sockaddr.sin6_family != _AF_INET6:
        return ""
    return str(ipaddress.IPv6Address(bytes(sockaddr.sin6_addr)))


def _has_gateway_ipv6(adapter: _IpAdapterAddresses) -> bool:
    gateway = adapter.FirstGatewayAddress
    while gateway:
        ip = _socket_address_to_ipv6(gateway.contents.Address)
        if _is_usable_local_ipv6(ip):
            return True
        gateway = gateway.contents.Next
    return False


def _has_unicast_ipv6(adapter: _IpAdapterAddresses) -> bool:
    unicast = adapter.FirstUnicastAddress
    while unicast:
        ip = _socket_address_to_ipv6(unicast.contents.Address)
        if _is_usable_local_ipv6(ip):
            return True
        unicast = unicast.contents.Next
    return False


def _is_ipv6_available_winapi() -> bool:
    """Проверяет IPv6 через Windows IP Helper API без внешнего сетевого запроса."""
    try:
        get_adapters_addresses = ctypes.windll.iphlpapi.GetAdaptersAddresses
    except Exception:
        return False

    size = ctypes.c_ulong(15 * 1024)
    buffer = ctypes.create_string_buffer(size.value)
    result = get_adapters_addresses(
        _AF_INET6,
        _GAA_FLAGS,
        None,
        ctypes.cast(buffer, _IpAdapterAddressesPtr),
        ctypes.byref(size),
    )
    if result == _ERROR_BUFFER_OVERFLOW:
        buffer = ctypes.create_string_buffer(size.value)
        result = get_adapters_addresses(
            _AF_INET6,
            _GAA_FLAGS,
            None,
            ctypes.cast(buffer, _IpAdapterAddressesPtr),
            ctypes.byref(size),
        )
    if result != _ERROR_SUCCESS:
        return False

    adapter = ctypes.cast(buffer, _IpAdapterAddressesPtr)
    while adapter:
        current = adapter.contents
        if (
            current.OperStatus == _IF_OPER_STATUS_UP
            and current.IfType != _IF_TYPE_SOFTWARE_LOOPBACK
            and _has_gateway_ipv6(current)
            and _has_unicast_ipv6(current)
        ):
            return True
        adapter = current.Next
    return False


def _is_ipv6_available_socket_probe() -> bool:
    """Запасная проверка для среды разработки вне Windows."""
    for host, port in _IPV6_PROBE_TARGETS:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
            sock.settimeout(0.7)
            sock.connect((host, port))
            local_addr = sock.getsockname()[0]
            if _is_usable_local_ipv6(local_addr):
                return True
        except OSError:
            continue
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
    return False


@lru_cache(maxsize=1)
def is_ipv6_available() -> bool:
    """Проверяет, есть ли рабочий IPv6 у пользователя."""
    if os.name == "nt":
        return _is_ipv6_available_winapi()
    return _is_ipv6_available_socket_probe()


def reset_ipv6_detection_cache() -> None:
    is_ipv6_available.cache_clear()
