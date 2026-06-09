"""Resume command handler."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .report_summary import (
    summarize_guard_rejection_report,
    summarize_run_report,
    try_load_guard_rejection_report,
    try_load_run_report,
)


def cmd_resume(args: argparse.Namespace) -> int:
    """Resume execution from an existing checkpoint path."""
    try:
        checkpoint_path = Path(args.checkpoint)
        if not checkpoint_path.exists():
            print(f"Error: Checkpoint path does not exist: {checkpoint_path}", file=sys.stderr)
            return 1

        report = try_load_run_report(checkpoint_path)
        if report is not None:
            print(
                json.dumps(
                    {
                        "status": "resume_loaded",
                        "checkpoint": str(checkpoint_path),
                        "source_status": report.get("status"),
                        "states": report.get("states", {}),
                        "blockers": report.get("blockers", []),
                        "summary": summarize_run_report(report),
                    },
                    indent=2,
                )
            )
            return 0

        rejection_report = try_load_guard_rejection_report(checkpoint_path)
        if rejection_report is not None:
            print(
                json.dumps(
                    {
                        "status": "resume_loaded",
                        "checkpoint": str(checkpoint_path),
                        "source_status": rejection_report.get("status"),
                        "reason_class": rejection_report.get("reason_class"),
                        "summary": summarize_guard_rejection_report(rejection_report),
                    },
                    indent=2,
                )
            )
            return 0

        print(json.dumps({"status": "resumed", "checkpoint": str(checkpoint_path)}))
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


__all__ = ["cmd_resume"]
