"""Потоковый AES-CTR для MTProxy.

Реализаций две, и выбираются они по наличию, а не по настройке.

`tgcrypto` — самая быстрая, написана на C специально для протокола
Telegram. Но под Python 3.14 готовых колёс у неё нет, а сборка из
исходников требует компилятора C, которого на машине человека обычно не
стоит. Установка зависимостей падала прямо на ней:

    error: failed-wheel-build-for-install
    Failed to build TgCrypto

Хуже того, падение уносило с собой и все остальные пакеты из того же
запуска — приложение оставалось без `requests`.

`cryptography` — запасной путь и, по сути, основной. Она раздаётся
колёсами abi3: одно колесо собрано под Python 3.7 и работает на всех
последующих, включая 3.14. Компилятор не нужен.

Раньше запасного пути не было вовсе, и отсутствие tgcrypto роняло
MTProxy при первом же подключении Telegram — с трассировкой в пол-окна
и строчкой «Для Telegram Proxy нужен пакет tgcrypto», которую человеку
нечем было исполнить.
"""

from __future__ import annotations

from typing import Any


class AesCtrStream:
    """Потоковый AES-CTR. Состояние держится между вызовами update.

    Счётчик CTR обязан продолжаться от куска к куску: MTProxy шифрует
    поток, а не отдельные сообщения. Начни каждый кусок заново — выйдет
    мусор, который Telegram молча отвергнет.
    """

    __slots__ = ("_key", "_iv", "_state", "_encryptor")

    def __init__(self, key: bytes, iv: bytes):
        key_bytes = bytes(key)
        iv_bytes = bytes(iv)
        if len(key_bytes) != 32:
            raise ValueError("AES-CTR key must be exactly 32 bytes")
        if len(iv_bytes) != 16:
            raise ValueError("AES-CTR IV must be exactly 16 bytes")

        self._key = key_bytes
        # tgcrypto меняет IV и однобайтовое состояние прямо внутри
        # переданных буферов, поэтому держим их в bytearray и не даём
        # этому поведению расползтись по коду.
        self._iv = bytearray(iv_bytes)
        self._state = bytearray(b"\x00")
        self._encryptor: Any | None = None

    def update(self, data: bytes) -> bytes:
        chunk = bytes(data or b"")
        if not chunk:
            return b""

        module = _tgcrypto()
        if module is not None:
            return module.ctr256_encrypt(chunk, self._key, self._iv, self._state)

        if self._encryptor is None:
            self._encryptor = _new_cryptography_encryptor(self._key, bytes(self._iv))
        return self._encryptor.update(chunk)


def aes_ctr_crypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    return AesCtrStream(key, iv).update(data)


def aes_ctr_keystream(key: bytes, iv: bytes, size: int) -> bytes:
    if size <= 0:
        return b""
    return aes_ctr_crypt(key, iv, b"\x00" * int(size))


#: Разобранные реализации. None означает «ещё не смотрели»,
#: False — «смотрели, нет».
_TGCRYPTO: Any = None
_CRYPTOGRAPHY: Any = None


def _tgcrypto() -> Any:
    """Быстрая реализация, если она есть. Нет — None, не исключение."""
    global _TGCRYPTO
    if _TGCRYPTO is None:
        try:
            import tgcrypto

            _TGCRYPTO = tgcrypto
        except ImportError:
            _TGCRYPTO = False
    return _TGCRYPTO or None


def _new_cryptography_encryptor(key: bytes, iv: bytes) -> Any:
    global _CRYPTOGRAPHY
    if _CRYPTOGRAPHY is None:
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

            _CRYPTOGRAPHY = (Cipher, algorithms, modes)
        except ImportError:
            _CRYPTOGRAPHY = False

    if not _CRYPTOGRAPHY:
        raise ImportError(
            "Telegram Proxy не может шифровать поток: нет ни tgcrypto, ни cryptography. "
            "Установите cryptography: py -3.14 -m pip install cryptography"
        )

    cipher_cls, algorithms, modes = _CRYPTOGRAPHY
    return cipher_cls(algorithms.AES(key), modes.CTR(iv)).encryptor()


def available_backend() -> str:
    """Какая реализация будет работать: tgcrypto, cryptography или ничего.

    Нужна диагностике и журналу запуска: «работает, но медленнее» и «не
    работает вовсе» — разные новости, и человеку стоит знать, какая
    именно у него.
    """
    if _tgcrypto() is not None:
        return "tgcrypto"
    try:
        _new_cryptography_encryptor(b"\x00" * 32, b"\x00" * 16)
        return "cryptography"
    except ImportError:
        return ""


__all__ = [
    "AesCtrStream",
    "aes_ctr_crypt",
    "aes_ctr_keystream",
    "available_backend",
]
