"""Execution-time guard for binding saved review bundles to local graph runs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .graph_io import load_graph
from .review_bundle_inspection import load_review_bundle


GUARD_REJECTION_SCHEMA = "schemas/local-runner-guard-rejection-v1.schema.json"


class ReviewBundleGuardError(ValueError):
    """Raised when a saved review bundle cannot authorize a local graph run."""

    def __init__(
        self,
        message: str,
        *,
        reason_class: str,
        summary: dict[str, Any],
    ) -> None:
        super().__init__(message)
        self.reason_class = reason_class
        self.summary = dict(summary)


def validate_review_bundle_for_graph(
    graph_path: str | Path,
    bundle_path: str | Path,
) -> dict[str, Any]:
    """Validate saved bundle evidence before local graph command execution."""
    graph = load_graph(graph_path)
    bundle = load_review_bundle(bundle_path)
    graph_sha256 = _graph_sha256(graph_path)
    command_digests = {
        node.id: _command_sha256(node.command) for node in graph.nodes if node.command is not None
    }
    review = bundle.get("preflight", {}).get("command_review", {})
    reviewed_digests = _reviewed_command_digests(review)
    command_ids = set(command_digests)
    reviewed_ids = set(reviewed_digests)
    missing = sorted(command_ids - reviewed_ids)
    mismatched = sorted(
        node_id
        for node_id in command_ids & reviewed_ids
        if command_digests[node_id] != reviewed_digests[node_id]
    )
    graph_match = graph_sha256 == bundle.get("graph_sha256")
    review_complete = bool(bundle.get("review_bundle", {}).get("review_complete"))

    summary = {
        "kind": "review_bundle_run_guard",
        "graph_path": str(graph_path),
        "bundle_path": str(bundle_path),
        "graph_sha256": graph_sha256,
        "bundle_graph_sha256": bundle.get("graph_sha256"),
        "graph_sha256_match": graph_match,
        "review_complete": review_complete,
        "missing_command_reviews": missing,
        "mismatched_command_reviews": mismatched,
        "commands_executed": False,
    }
    if not graph_match:
        raise ReviewBundleGuardError(
            (
                "review bundle does not match graph; repair: regenerate the review "
                "bundle for this graph"
            ),
            reason_class="graph_digest_mismatch",
            summary=summary,
        )
    if not review_complete or missing or mismatched:
        raise ReviewBundleGuardError(
            (
                "review bundle command review is incomplete; repair: regenerate "
                "with preflight --review-bundle"
            ),
            reason_class="command_review_incomplete",
            summary=summary,
        )
    return summary


def build_guard_rejection_report(
    *, reason_class: str, summary: dict[str, Any], message: str | None = None
) -> dict[str, Any]:
    """Build a stable report for pre-execution review-bundle guard rejections."""
    diagnostic, repair_hint = _split_diagnostic(message)
    return {
        "format": "local-runner-guard-rejection",
        "schema_version": "v1",
        "schema": GUARD_REJECTION_SCHEMA,
        "status": "rejected",
        "reason_class": reason_class,
        "diagnostic": diagnostic,
        "repair_hint": repair_hint,
        "commands_executed": False,
        "review_bundle_guard": {
            **summary,
            "guarded_run": False,
            "commands_executed": False,
        },
    }


def write_guard_rejection_report(
    output_path: str | Path,
    *,
    reason_class: str,
    summary: dict[str, Any],
    message: str | None = None,
) -> dict[str, Any]:
    """Write a byte-stable guard rejection report and return the payload."""
    payload = build_guard_rejection_report(
        reason_class=reason_class,
        summary=summary,
        message=message,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def build_malformed_review_bundle_guard_summary(
    graph_path: str | Path,
    bundle_path: str | Path,
) -> dict[str, Any]:
    """Build safe guard evidence when the saved review bundle cannot be loaded."""
    return {
        "kind": "review_bundle_run_guard",
        "graph_path": str(graph_path),
        "bundle_path": str(bundle_path),
        "graph_sha256": _graph_sha256(graph_path),
        "bundle_graph_sha256": "",
        "graph_sha256_match": False,
        "review_complete": False,
        "missing_command_reviews": [],
        "mismatched_command_reviews": [],
        "commands_executed": False,
    }


def _split_diagnostic(message: str | None) -> tuple[str, str]:
    if not message:
        return (
            "review bundle guard rejected local command execution",
            "regenerate the review bundle for this graph",
        )
    diagnostic, separator, repair = message.partition("; repair: ")
    if not separator:
        return diagnostic, "regenerate the review bundle for this graph"
    return diagnostic, repair


def _graph_sha256(graph_path: str | Path) -> str:
    return hashlib.sha256(Path(graph_path).read_bytes()).hexdigest()


def _command_sha256(command: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(command, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _reviewed_command_digests(review: object) -> dict[str, str]:
    if not isinstance(review, dict):
        return {}
    return {
        str(node_id): str(item.get("argv_sha256", ""))
        for node_id, item in review.items()
        if isinstance(item, dict)
    }
