"""Read-only inspection summaries for saved local review bundles."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class ReviewBundleInspectionError(ValueError):
    """Raised when a saved review bundle cannot be inspected safely."""


_REQUIRED_KEYS = {
    "format",
    "schema_version",
    "graph_path",
    "graph_sha256",
    "schemas",
    "commands_executed",
    "preflight",
    "review_bundle",
}
_SENSITIVE_TEXT = re.compile(
    r"(api[_-]?key|auth|bearer|credential|oauth|pass(word)?|secret|token)"
    r"|[\\/]"
    r"|[$@]"
    r"|[A-Za-z0-9_./+=:-]{32,}",
    re.IGNORECASE,
)


def load_review_bundle(path: str | Path) -> dict[str, Any]:
    """Load and validate a saved local review bundle envelope."""
    bundle_path = Path(path)
    try:
        payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReviewBundleInspectionError(
            f"review bundle unreadable: {_redact(str(exc))}; repair: provide a readable saved bundle JSON"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ReviewBundleInspectionError(
            f"review bundle is not valid JSON: line {exc.lineno} column {exc.colno}; repair: regenerate the review bundle"
        ) from exc

    if not isinstance(payload, dict):
        raise ReviewBundleInspectionError(
            "review bundle must be a JSON object; repair: regenerate with preflight --review-bundle"
        )

    missing = sorted(_REQUIRED_KEYS - set(payload))
    if missing:
        raise ReviewBundleInspectionError(
            "missing required keys: "
            + ", ".join(missing)
            + "; repair: regenerate with preflight --review-bundle --output"
        )

    if payload.get("format") != "local-review-bundle":
        raise ReviewBundleInspectionError(
            "unsupported review bundle format; repair: provide a local-review-bundle v1 file"
        )
    if payload.get("schema_version") != "v1":
        raise ReviewBundleInspectionError(
            "unsupported review bundle schema_version; repair: provide a v1 bundle"
        )
    if payload.get("commands_executed") is not False:
        raise ReviewBundleInspectionError(
            "review bundle commands_executed must be false; repair: regenerate before command execution"
        )

    preflight = payload.get("preflight")
    if not isinstance(preflight, dict):
        raise ReviewBundleInspectionError(
            "preflight evidence must be an object; repair: regenerate the review bundle"
        )
    if preflight.get("commands_executed") is not False:
        raise ReviewBundleInspectionError(
            "preflight commands_executed must be false; repair: regenerate before command execution"
        )

    review = payload.get("review_bundle")
    if not isinstance(review, dict):
        raise ReviewBundleInspectionError(
            "review_bundle evidence must be an object; repair: regenerate the review bundle"
        )
    schemas = payload.get("schemas")
    if not isinstance(schemas, dict):
        raise ReviewBundleInspectionError(
            "schemas evidence must be an object; repair: regenerate the review bundle"
        )

    return payload


def summarize_review_bundle(path: str | Path) -> dict[str, Any]:
    """Return a stable JSON-safe inspection summary without loading graph nodes."""
    payload = load_review_bundle(path)
    review = payload["review_bundle"]
    return {
        "kind": "review_bundle",
        "path": str(path),
        "format": payload["format"],
        "schema_version": payload["schema_version"],
        "graph_path": payload["graph_path"],
        "graph_sha256": payload["graph_sha256"],
        "command_node_count": int(review.get("command_node_count", 0)),
        "review_node_count": int(review.get("review_node_count", 0)),
        "review_complete": bool(review.get("review_complete", False)),
        "schemas": dict(sorted(payload["schemas"].items())),
        "commands_executed": False,
    }


def _redact(text: str) -> str:
    return _SENSITIVE_TEXT.sub("<redacted>", text)
