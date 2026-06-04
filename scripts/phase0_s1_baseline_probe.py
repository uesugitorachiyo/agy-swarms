#!/usr/bin/env python3
"""Run the Phase-0 S1/G0.1 baseline/compression bootstrap probe.

This is a deterministic bootstrap for the S1 evidence package. It does not claim
the final S1 gate because live single-agent token accounting and external
comparand wall-clock baselines still need S2/owner evidence. It does pin:

- the reference task hash from `benchmarks/reference_task.md`
- a concrete runnable fixture shape for that task
- a full-context baseline packet
- a compressed handoff packet
- a deterministic token estimate and candidate compression ratio
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from agy_swarms.canonical import canonical, sha256_hex


FIXTURE_FILES: dict[str, str] = {
    "pyproject.toml": """[project]
name = "merge-fixture"
version = "0.0.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
""",
    "src/merge_fixture/__init__.py": """from .merge import MergeConflict, merge_results

__all__ = ["MergeConflict", "merge_results"]
""",
    "src/merge_fixture/merge.py": '''class MergeConflict(ValueError):
    """Raised when two scalar result values conflict."""


def merge_results(left, right):
    """Merge two structured result dictionaries.

    BUG: conflicting scalar values are silently overwritten, and output ordering
    follows insertion history instead of a deterministic sorted-key rule.
    """
    merged = dict(left)
    for key, value in right.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = merge_results(merged[key], value)
        else:
            merged[key] = value
    return merged
''',
    "tests/test_merge.py": """import pytest

from merge_fixture import MergeConflict, merge_results


def test_happy_path_merges_disjoint_keys():
    assert merge_results({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_nested_merge_preserves_nested_values():
    assert merge_results({"a": {"x": 1}}, {"a": {"y": 2}}) == {"a": {"x": 1, "y": 2}}


def test_scalar_conflict_raises_typed_error():
    with pytest.raises(MergeConflict):
        merge_results({"a": 1}, {"a": 2})


def test_output_keys_are_sorted_deterministically():
    assert list(merge_results({"b": 2}, {"a": 1}).keys()) == ["a", "b"]
""",
}


def token_estimate(text: str) -> int:
    """Deterministic bootstrap estimate: ceil(UTF-8 bytes / 4).

    This is explicitly not provider billing. S1 remains pending until the live
    agy accounting path records actual billable-equivalent tokens.
    """
    return math.ceil(len(text.encode("utf-8")) / 4)


def build_full_context(reference_task: str) -> str:
    parts = [
        "# Task\n",
        reference_task,
        "\n# Full Repository Context\n",
    ]
    for path in sorted(FIXTURE_FILES):
        parts.extend([f"\n## {path}\n```text\n", FIXTURE_FILES[path], "\n```\n"])
    return "".join(parts)


def build_compressed_packet(reference_task: str) -> str:
    return "\n".join(
        [
            "# Task",
            reference_task.strip(),
            "",
            "# Scoped Handoff",
            "- Target file: `src/merge_fixture/merge.py`.",
            "- Current behavior: recursive dict merge, but scalar conflicts overwrite and key order follows insertion history.",
            "- Required change: preserve deterministic sorted-key output and raise `MergeConflict` on conflicting scalar values.",
            "- Verification: add/run tests for disjoint merge, nested merge, scalar conflict, and deterministic key ordering.",
            "- Repository files available by pointer: `pyproject.toml`, `src/merge_fixture/__init__.py`, `src/merge_fixture/merge.py`, `tests/test_merge.py`.",
            "",
        ]
    )


def run_probe(reference_task_path: Path) -> dict[str, Any]:
    reference_task = reference_task_path.read_text()
    full_context = build_full_context(reference_task)
    compressed_packet = build_compressed_packet(reference_task)
    full_tokens = token_estimate(full_context)
    compressed_tokens = token_estimate(compressed_packet)
    reduction_fraction = 1.0 - (compressed_tokens / full_tokens)
    ratio = full_tokens / compressed_tokens
    fixture_sha = sha256_hex(canonical(FIXTURE_FILES))
    return {
        "gate": "S1/G0.1-bootstrap",
        "final_s1_gate": False,
        "reference_task_path": str(reference_task_path),
        "reference_task_sha": sha256_hex(reference_task_path.read_bytes()),
        "fixture_sha": fixture_sha,
        "fixture_file_count": len(FIXTURE_FILES),
        "estimator": "ceil(utf8_bytes/4)",
        "full_context": {
            "bytes": len(full_context.encode("utf-8")),
            "estimated_tokens": full_tokens,
        },
        "compressed_packet": {
            "bytes": len(compressed_packet.encode("utf-8")),
            "estimated_tokens": compressed_tokens,
        },
        "compression": {
            "ratio_full_over_compressed": ratio,
            "reduction_fraction": reduction_fraction,
            "reduction_percent": reduction_fraction * 100,
            "g0_1_go_floor_percent": 40.0,
            "g0_1_no_go_floor_percent": 25.0,
            "candidate_x_target_ratio": ratio,
        },
        "passed_bootstrap": reduction_fraction >= 0.40,
        "remaining_for_final_s1": [
            "live single-agent agy run on the pinned reference fixture",
            "actual billable-equivalent token baseline from agy accounting",
            "ao2 serial-repair wall-clock comparand on the same reference task",
            "factory-v3 wall-clock comparand for M3 two-way speed gate",
            "owner ratification of X_target after real baseline harvest",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-task", type=Path, default=Path("benchmarks/reference_task.md"))
    parser.add_argument(
        "--output", type=Path, default=Path(".planning/spikes/s1-g0.1-baseline-bootstrap.json")
    )
    args = parser.parse_args()

    result = run_probe(args.reference_task)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed_bootstrap": result["passed_bootstrap"],
                "reference_task_sha": result["reference_task_sha"],
                "full_estimated_tokens": result["full_context"]["estimated_tokens"],
                "compressed_estimated_tokens": result["compressed_packet"]["estimated_tokens"],
                "reduction_percent": result["compression"]["reduction_percent"],
                "candidate_x_target_ratio": result["compression"]["candidate_x_target_ratio"],
            },
            indent=2,
        )
    )
    return 0 if result["passed_bootstrap"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
