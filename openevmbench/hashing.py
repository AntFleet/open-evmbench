"""SHA256 helpers. All submission hashes use the `sha256:<hex>` form (SPEC §4)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_prefixed(data: bytes) -> str:
    return f"sha256:{sha256_hex(data)}"


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def is_sha256_ref(value: str) -> bool:
    return bool(SHA256_RE.match(value))
