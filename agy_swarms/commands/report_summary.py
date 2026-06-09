"""Run-report loading and summary helpers for inspect/resume commands."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def try_load_run_report(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict) and "status" in data and "states" in data:
        return data
    return None


def try_load_guard_rejection_report(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        isinstance(data, dict)
        and data.get("format") == "local-runner-guard-rejection"
        and data.get("schema_version") == "v1"
        and data.get("status") == "rejected"
    ):
        return data
    return None


def summarize_guard_rejection_report(report: dict[str, object]) -> dict[str, Any]:
    guard = report.get("review_bundle_guard")
    if not isinstance(guard, dict):
        guard = {}
    missing = guard.get("missing_command_reviews", [])
    mismatched = guard.get("mismatched_command_reviews", [])
    return {
        "format": "local-runner-guard-rejection",
        "schema_version": "v1",
        "status": "rejected",
        "reason_class": str(report.get("reason_class", "")),
        "commands_executed": report.get("commands_executed") is True,
        "guarded_run": guard.get("guarded_run") is True,
        "graph_sha256_match": guard.get("graph_sha256_match") is True,
        "review_complete": guard.get("review_complete") is True,
        "missing_command_review_count": len(missing) if isinstance(missing, list) else 0,
        "mismatched_command_review_count": len(mismatched) if isinstance(mismatched, list) else 0,
    }


def summarize_guarded_report(report: dict[str, object]) -> dict[str, Any] | None:
    guard = report.get("review_bundle_guard")
    if not isinstance(guard, dict):
        return None
    missing = guard.get("missing_command_reviews", [])
    mismatched = guard.get("mismatched_command_reviews", [])
    return {
        "has_review_bundle_guard": True,
        "guarded_run": guard.get("guarded_run") is True,
        "graph_sha256_match": guard.get("graph_sha256_match") is True,
        "review_complete": guard.get("review_complete") is True,
        "missing_command_review_count": len(missing) if isinstance(missing, list) else 0,
        "mismatched_command_review_count": len(mismatched) if isinstance(mismatched, list) else 0,
        "commands_executed": guard.get("commands_executed") is True,
    }


def summarize_run_report(report: dict[str, object]) -> dict[str, Any]:
    states = report.get("states", {})
    if not isinstance(states, dict):
        states = {}
    status_by_node = {str(node_id): str(status) for node_id, status in states.items()}
    counts = Counter(status_by_node.values())
    blockers = report.get("blockers", [])
    concerns = report.get("concerns", [])
    changed_files = report.get("changed_files", [])
    summary = {
        "total_nodes": len(status_by_node),
        "status_counts": dict(sorted(counts.items())),
        "failed_nodes": [
            node_id for node_id, status in status_by_node.items() if status == "failed"
        ],
        "skipped_nodes": [
            node_id for node_id, status in status_by_node.items() if status == "skipped"
        ],
        "blocker_count": len(blockers) if isinstance(blockers, list) else 0,
        "concern_count": len(concerns) if isinstance(concerns, list) else 0,
        "changed_files_count": len(changed_files) if isinstance(changed_files, list) else 0,
    }
    guarded_report = summarize_guarded_report(report)
    if guarded_report is not None:
        summary["guarded_report"] = guarded_report
    return summary


__all__ = [
    "summarize_guard_rejection_report",
    "summarize_guarded_report",
    "summarize_run_report",
    "try_load_guard_rejection_report",
    "try_load_run_report",
]
