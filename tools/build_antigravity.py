"""Пересобирает контроллер и проверяет поставляемый сетевой движок."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = "2.22.0"
PAYLOAD_SHA = "cb0a5c7c77a3e24dbb4e7f696c40d2b757355d51c772ea861d7471d028307f3a"
URL = f"https://github.com/confeden/Antigravity/releases/download/v{VERSION}/AG_{VERSION}.exe"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cargo", default=str(Path.home() / ".cargo/bin/cargo.exe"))
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    destination = ROOT / "bin/antigravity"
    destination.mkdir(parents=True, exist_ok=True)
    payload = destination / "ag_network.exe"
    if not payload.exists():
        if args.offline:
            raise SystemExit("Сетевой движок отсутствует; снимите --offline для загрузки.")
        request = urllib.request.Request(URL, headers={"User-Agent": "net67-build"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read(20 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != PAYLOAD_SHA:
            raise SystemExit("Сетевой движок не прошёл проверку SHA-256.")
        payload.write_bytes(data)
    if hashlib.sha256(payload.read_bytes()).hexdigest() != PAYLOAD_SHA:
        raise SystemExit("Сетевой движок повреждён; замените ag_network.exe.")
    # Системные линковщики спотыкаются о кириллицу в папке target.
    target = Path(tempfile.gettempdir()) / "net67-ag-msvc"
    command = [args.cargo, "+stable-x86_64-pc-windows-msvc", "test" if args.test else "build",
               "--release", "--locked", "--target-dir", str(target)]
    if args.offline:
        command.append("--offline")
    subprocess.run(command, cwd=ROOT / "vendor/antigravity_core", check=True)
    if args.test:
        return
    controller = destination / "net67_antigravity.exe"
    shutil.copy2(target / "release/net67_antigravity.exe", controller)
    manifest = {
        "version": VERSION,
        "source_tag": f"v{VERSION}",
        "source_commit": "94663a7",
        "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (controller, payload)},
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    check = subprocess.run([str(controller), "--check"], capture_output=True, check=True)
    print(check.stdout.decode("utf-8").strip())


if __name__ == "__main__":
    main()
