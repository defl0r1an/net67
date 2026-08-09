from __future__ import annotations

from typing import Any


class AesCtrStream:
    """Потоковый AES-CTR поверх tgcrypto.

    tgcrypto меняет IV и однобайтовое состояние прямо внутри переданных буферов,
    поэтому держим их в bytearray и не даём этому поведению расползтись по коду.
    """

    __slots__ = ("_key", "_iv", "_state")

    def __init__(self, key: bytes, iv: bytes):
        key_bytes = bytes(key)
        iv_bytes = bytes(iv)
        if len(key_bytes) != 32:
            raise ValueError("AES-CTR key must be exactly 32 bytes")
        if len(iv_bytes) != 16:
            raise ValueError("AES-CTR IV must be exactly 16 bytes")
        self._key = key_bytes
        self._iv = bytearray(iv_bytes)
        self._state = bytearray(b"\x00")

    def update(self, data: bytes) -> bytes:
        chunk = bytes(data or b"")
        if not chunk:
            return b""
        return _tgcrypto().ctr256_encrypt(chunk, self._key, self._iv, self._state)


def aes_ctr_crypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    return AesCtrStream(key, iv).update(data)


def aes_ctr_keystream(key: bytes, iv: bytes, size: int) -> bytes:
    if size <= 0:
        return b""
    return aes_ctr_crypt(key, iv, b"\x00" * int(size))


_TGCRYPTO: Any | None = None


def _tgcrypto() -> Any:
    global _TGCRYPTO
    if _TGCRYPTO is None:
        try:
            import tgcrypto
        except ImportError as exc:
            raise ImportError("Для Telegram Proxy нужен пакет tgcrypto") from exc
        _TGCRYPTO = tgcrypto
    return _TGCRYPTO


__all__ = ["AesCtrStream", "aes_ctr_crypt", "aes_ctr_keystream"]
