"""§D.0 — canonicalization & digest primitive (``canonical()`` / ``sha256_hex()``).

The single canonical-serialization and hashing primitive used by every digest, hash,
and ``*_hash``/``*_key``/``*_sha`` field in the spec (``idempotency_key`` §D.1, the
checkpoint epoch FR-7, ``params_hash`` §D.5, all sub-digests, and ``BlobRef.sha256``
§D.2). The load-bearing contract: **two correct implementations SHALL produce
byte-identical outputs** — so this module owns the exact serialization rules.

``canonical(X)`` is JCS / RFC-8785-style canonical JSON:
  * object keys sorted lexicographically **by UTF-16 code unit** (RFC-8785),
  * arrays preserve element order,
  * floats formatted with ``%.6g``, integers as bare decimal,
  * strings minimally escaped (ECMAScript ``JSON.stringify`` escaping; non-ASCII left
    as literal UTF-8),
  * no insignificant whitespace.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

__all__ = [
    "canonical",
    "sha256_hex",
    "output_schema_digest",
    "tool_schema_impl_digest",
    "resolved_input_digest",
]

# ECMAScript JSON.stringify short escapes (RFC-8785 §3.2.2.2). Lowercase \u hex.
_SHORT_ESCAPES = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}


def _escape_string(s: str) -> str:
    out = ['"']
    for ch in s:
        cp = ord(ch)
        short = _SHORT_ESCAPES.get(cp)
        if short is not None:
            out.append(short)
        elif cp < 0x20:
            out.append("\\u%04x" % cp)
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _format_float(x: float) -> str:
    if not math.isfinite(x):
        raise ValueError(f"canonical(): non-finite float not serializable: {x!r}")
    return "%.6g" % x


def _utf16_sort_key(key: str) -> bytes:
    # Sorting the UTF-16-BE encoding byte-lexicographically is equivalent to comparing
    # the sequence of UTF-16 code units numerically (each unit is 2 big-endian bytes).
    return key.encode("utf-16-be")


def _serialize(x: Any) -> str:
    if x is None:
        return "null"
    # bool is a subclass of int — must be checked first.
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        return _format_float(x)
    if isinstance(x, str):
        return _escape_string(x)
    if isinstance(x, (list, tuple)):
        return "[" + ",".join(_serialize(e) for e in x) + "]"
    if isinstance(x, dict):
        keys = list(x.keys())
        for k in keys:
            if not isinstance(k, str):
                raise TypeError(f"canonical(): dict keys must be str, got {type(k).__name__}")
        parts = [
            _escape_string(k) + ":" + _serialize(x[k]) for k in sorted(keys, key=_utf16_sort_key)
        ]
        return "{" + ",".join(parts) + "}"
    raise TypeError(f"canonical(): unsupported type {type(x).__name__}")


def canonical(x: Any) -> bytes:
    """Return the RFC-8785-style canonical JSON encoding of ``x`` as UTF-8 bytes."""
    return _serialize(x).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """SHA-256 of ``data`` as lowercase 64-char hex (§D.0)."""
    return hashlib.sha256(data).hexdigest()


# --- sub-digests (§D.0, consumed by idempotency_key §D.1) ------------------


def output_schema_digest(output_schema: Any) -> str:
    """``sha256_hex(canonical(output_schema))`` (§D.0)."""
    return sha256_hex(canonical(output_schema))


def resolved_input_digest(resolved_input_value: Any) -> str:
    """``sha256_hex(canonical(resolved_input_value))`` (§D.0)."""
    return sha256_hex(canonical(resolved_input_value))


def tool_schema_impl_digest(schema: Any, impl_source_sha256: str) -> str:
    """``sha256_hex(canonical(schema) ‖ impl_source_sha256)`` — byte concat (§D.0)."""
    return sha256_hex(canonical(schema) + impl_source_sha256.encode("ascii"))
