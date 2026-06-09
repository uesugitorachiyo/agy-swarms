"""Inspect command handler."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .inspect_bundle import inspect_review_bundle, inspect_review_bundle_diff
from .report_summary import (
    summarize_guard_rejection_report,
    summarize_run_report,
    try_load_guard_rejection_report,
    try_load_run_report,
)
from .resume import cmd_resume


def cmd_inspect(args: argparse.Namespace) -> int:
    """Inspect a checkpoint, run report, or review bundle."""
    try:
        if args.review_bundle_diff:
            return inspect_review_bundle_diff(args.review_bundle_diff)
        if args.review_bundle:
            return inspect_review_bundle(args.review_bundle)

        path = Path(args.checkpoint)
        if not path.exists():
            print(f"Error: File not found: {path}", file=sys.stderr)
            return 1

        report = try_load_run_report(path)
        if report is not None:
            print(
                json.dumps(
                    {
                        "kind": "run_report",
                        "path": str(path),
                        "size_bytes": path.stat().st_size,
                        "status": report.get("status"),
                        "states": report.get("states", {}),
                        "blockers": report.get("blockers", []),
                        "summary": summarize_run_report(report),
                    },
                    indent=2,
                )
            )
            return 0

        rejection_report = try_load_guard_rejection_report(path)
        if rejection_report is not None:
            print(
                json.dumps(
                    {
                        "kind": "guard_rejection_report",
                        "path": str(path),
                        "size_bytes": path.stat().st_size,
                        "status": rejection_report.get("status"),
                        "reason_class": rejection_report.get("reason_class"),
                        "summary": summarize_guard_rejection_report(rejection_report),
                    },
                    indent=2,
                )
            )
            return 0

        print(json.dumps({"kind": "file", "path": str(path), "size_bytes": path.stat().st_size}))
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


__all__ = ["cmd_inspect", "cmd_resume"]
