from __future__ import annotations

import hashlib
from pathlib import Path


def path_stat_signature(path: Path) -> tuple[object, ...]:
    try:
        stat = path.stat()
        mtime_ns = int(getattr(stat, "st_mtime_ns", 0) or 0)
        size = int(getattr(stat, "st_size", 0) or 0)
    except Exception:
        return (0, 0)

    return (mtime_ns, size)


def path_cache_signature(path: Path) -> tuple[object, ...]:
    try:
        stat = path.stat()
        mtime_ns = int(getattr(stat, "st_mtime_ns", 0) or 0)
        size = int(getattr(stat, "st_size", 0) or 0)
    except Exception:
        return (0, 0, "")

    digest = ""
    try:
        if path.is_file():
            digest = hashlib.blake2b(path.read_bytes(), digest_size=16).hexdigest()
    except Exception:
        digest = ""

    return (mtime_ns, size, digest)
