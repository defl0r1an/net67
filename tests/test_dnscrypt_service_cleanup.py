"""Службу шифрованного DNS снимают сборка и удаление — по одному имени и в одном порядке.

Служба net67DnsCrypt работает из папки программы (user\\dnscrypt) и держит
свой файл. Первая сборка после выбора DNSCrypt упала на «Artifact folder is
locked»: build_local.ps1 о службе не знал. Снять одну службу мало — адаптер
останется на 127.0.0.1, где никто не отвечает, и компьютер потеряет
интернет. Поэтому и сборка, и удаление зовут installer\\remove_dnscrypt.ps1:
сначала автоматический DNS адаптерам, потом служба.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


class DnsCryptServiceCleanupTests(unittest.TestCase):
    def test_service_name_is_the_same_everywhere(self) -> None:
        from dns.local_proxy import SERVICE_NAME

        script = (ROOT / "installer" / "remove_dnscrypt.ps1").read_text(encoding="ascii")
        build = (ROOT / "scripts" / "build_local.ps1").read_text(encoding="ascii")
        self.assertIn(f'$ServiceName = "{SERVICE_NAME}"', script)
        self.assertIn(f"Name='{SERVICE_NAME}'", build)

    def test_build_removes_the_service_before_wiping_the_artifact(self) -> None:
        build = (ROOT / "scripts" / "build_local.ps1").read_text(encoding="ascii")
        cleanup = build.index("installer\\remove_dnscrypt.ps1")
        wipe = build.index("Remove-Item -Recurse -Force $Artifact")
        self.assertLess(cleanup, wipe)
        # Чужая служба с тем же именем (другая папка программы) не трогается.
        self.assertIn("Test-InsideArtifact $dnsService.PathName", build)

    def test_adapters_are_reset_before_the_service_goes(self) -> None:
        script = (ROOT / "installer" / "remove_dnscrypt.ps1").read_text(encoding="ascii")
        self.assertLess(script.index("Set-DnsClientServerAddress"), script.index("delete $ServiceName"))

    def test_uninstaller_runs_the_same_script(self) -> None:
        iss = (ROOT / "installer" / "net67.iss").read_text(encoding="utf-8")
        self.assertIn("remove_dnscrypt.ps1", iss)


if __name__ == "__main__":
    unittest.main()
