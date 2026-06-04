"""Stable operator-facing JSON reports for completed runs."""

from __future__ import annotations

from typing import Any

from .conductor import RunReport


def report_to_json(report: RunReport) -> dict[str, Any]:
    """Convert a RunReport into the stable v0.2 local-runner JSON shape."""
    return {
        "status": report.status.value,
        "states": {node_id: status.value for node_id, status in report.states.items()},
        "blockers": list(report.blockers),
        "spent_tokens": report.spent_tokens,
        "spent_usd": report.spent_usd,
        "concerns": [
            concern for envelope in report.results.values() for concern in envelope.concerns
        ],
        "changed_files": sorted(
            {
                changed_file
                for envelope in report.results.values()
                for changed_file in envelope.changed_files
            }
        ),
        "results": {
            node_id: {
                "status": envelope.status,
                "error_class": envelope.error_class.value,
                "artifact": envelope.artifact,
                "stdout": envelope.artifact.get("stdout", envelope.stdout_ref or ""),
                "stderr": envelope.artifact.get("stderr", ""),
                "exit_code": envelope.artifact.get("exit_code"),
            }
            for node_id, envelope in report.results.items()
        },
    }
