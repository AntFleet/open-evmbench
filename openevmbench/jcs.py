"""RFC 8785 (JCS) canonicalization.

The acceptance signature and acceptance_record_hash are computed over
JCS-canonical bytes (SPEC §4). We delegate to the `rfc8785` package rather
than approximating with sorted-keys json.dumps, because JCS number
serialization follows ECMAScript formatting, which differs from Python's
for some values (e.g. 1e16).
"""

from __future__ import annotations

from typing import Any

import rfc8785


def canonicalize(obj: Any) -> bytes:
    return rfc8785.dumps(obj)
