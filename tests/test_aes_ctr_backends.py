"""MTProxy шифрует поток и без tgcrypto.

tgcrypto под Python 3.14 не собирается без компилятора C, и установка
падала прямо на нём, унося весь остальной список пакетов. Приложение
при этом роняло MTProxy на первом же подключении Telegram — с
трассировкой в пол-окна и советом «нужен пакет tgcrypto», который
человеку нечем было исполнить.

Теперь tgcrypto — необязательный ускоритель, а работу делает
cryptography: она раздаётся колёсами abi3 и ставится на 3.14 без
компилятора.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

KEY = bytes(range(32))
IV = bytes(range(16))


class AesCtrBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        from telegram_proxy.proxy import aes_ctr

        self.aes_ctr = aes_ctr

    def test_some_backend_is_available(self) -> None:
        self.assertIn(self.aes_ctr.available_backend(), ("tgcrypto", "cryptography"))

    def test_matches_reference_aes_ctr(self) -> None:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        plain = b"MTProxy handshake payload " * 10
        expected = Cipher(algorithms.AES(KEY), modes.CTR(IV)).encryptor().update(plain)

        self.assertEqual(self.aes_ctr.aes_ctr_crypt(KEY, IV, plain), expected)

    def test_counter_continues_between_chunks(self) -> None:
        # Ради этого и нужен поток: MTProxy шифрует не отдельные
        # сообщения, а непрерывную ленту. Начни каждый кусок заново —
        # выйдет мусор, который Telegram молча отвергнет.
        plain = b"a" * 37 + b"b" * 63 + b"c" * 100
        whole = self.aes_ctr.aes_ctr_crypt(KEY, IV, plain)

        stream = self.aes_ctr.AesCtrStream(KEY, IV)
        chunked = stream.update(plain[:37]) + stream.update(plain[37:100]) + stream.update(plain[100:])

        self.assertEqual(chunked, whole)

    def test_decrypts_back_to_source(self) -> None:
        plain = b"init packet payload"
        encrypted = self.aes_ctr.aes_ctr_crypt(KEY, IV, plain)

        self.assertEqual(self.aes_ctr.AesCtrStream(KEY, IV).update(encrypted), plain)

    def test_key_and_iv_lengths_are_checked(self) -> None:
        with self.assertRaises(ValueError):
            self.aes_ctr.AesCtrStream(b"\x00" * 31, IV)
        with self.assertRaises(ValueError):
            self.aes_ctr.AesCtrStream(KEY, b"\x00" * 15)

    def test_tgcrypto_is_optional_not_required(self) -> None:
        # Проверка стережёт саму суть правки: отсутствие tgcrypto не
        # должно превращаться в исключение.
        saved = self.aes_ctr._TGCRYPTO
        self.aes_ctr._TGCRYPTO = False
        self.addCleanup(setattr, self.aes_ctr, "_TGCRYPTO", saved)

        self.assertEqual(self.aes_ctr.available_backend(), "cryptography")
        self.assertTrue(self.aes_ctr.aes_ctr_crypt(KEY, IV, b"payload"))


if __name__ == "__main__":
    unittest.main()
