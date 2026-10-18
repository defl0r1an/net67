"""Без curl_cffi пробы не падают: сайт открывается прежним запросом OpenSSL.

Если libcurl не попал в сборку или его DLL убрал антивирус, каждая проба
BlockCheck и подбора падала бы исключением — у человека «не работает ничего».
"""

import unittest
from unittest.mock import patch

from diagnostics import tls_probe
from utils import chrome_https


class ChromeHttpsFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        chrome_https._CURL_MISSING_LOGGED = False

    def test_missing_curl_falls_back_to_openssl_request(self) -> None:
        seen = {}

        def fake_https_get(host, ip, path, **kwargs):
            seen.update(host=host, ip=ip, path=path, **kwargs)
            return tls_probe.ProbeResult(ip=ip, kind=tls_probe.KIND_OK, status=200)

        with patch.object(chrome_https, "_curl_api", side_effect=ImportError("нет curl_cffi")), \
             patch.object(tls_probe, "https_get", side_effect=fake_https_get), \
             patch("log.log.log") as log:
            result = chrome_https.chrome_get("example.com", "192.0.2.1", "/x", timeout=3.0, read_limit=10)
            chrome_https.chrome_get("example.com", "192.0.2.1", "/x", timeout=3.0)

        self.assertEqual(result.kind, tls_probe.KIND_OK)
        self.assertEqual((seen["host"], seen["ip"], seen["path"], seen["read_limit"]), ("example.com", "192.0.2.1", "/x", 0))
        # В журнал — одна строка на запуск, а не на каждую пробу.
        self.assertEqual(log.call_count, 1)

    def test_body_done_gets_body_without_headers(self) -> None:
        bodies = []

        def fake_https_get(host, ip, path, *, body_done=None, **_kwargs):
            body_done(b"HTTP/1.1 200 OK\r\nX: 1\r\n\r\nbody")
            return tls_probe.ProbeResult(ip=ip, kind=tls_probe.KIND_OK, status=200)

        with patch.object(chrome_https, "_curl_api", side_effect=OSError("DLL")), \
             patch.object(tls_probe, "https_get", side_effect=fake_https_get), \
             patch("log.log.log"):
            chrome_https.chrome_get("a.example", "192.0.2.1", timeout=1.0, body_done=lambda body: bodies.append(body) or True)

        self.assertEqual(bodies, [b"body"])



if __name__ == "__main__":
    unittest.main()
