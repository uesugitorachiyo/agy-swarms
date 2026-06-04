#!/usr/bin/env python3
"""Run the Phase-0 S5/G0.5 end-to-end scoped-read/compression probe.

This is a zero-token, replayable harness over the existing Phase-1 substrate:

- a tiny conductor graph runs planner -> compression-first worker -> closer;
- a blackboard section can only be read through the worker's declared scope;
- an undeclared full-context read is rejected;
- the worker artifact keeps a dense summary plus pointers, not raw context.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agy_swarms.adapters.scripted import CannedResult, ScriptedAdapter
from agy_swarms.blackboard import Blackboard, ScopedReadError
from agy_swarms.budget import Dims
from agy_swarms.canonical import canonical, sha256_hex
from agy_swarms.conductor import Conductor
from agy_swarms.types import Caps, Epoch, NodeSpec, RunStatus, TaskGraph


def token_estimate(value: Any) -> int:
    return math.ceil(len(canonical(value)) / 4)


def build_full_context() -> dict[str, Any]:
    repeated_noise = "\n".join(
        f"irrelevant module {index}: generated scaffolding and unrelated notes"
        for index in range(1, 81)
    )
    return {
        "task": "Fix merge_results so scalar conflicts raise and keys are sorted.",
        "repo_dump": repeated_noise,
        "files": {
            "src/merge_fixture/merge.py": "buggy implementation: overwrites scalar conflicts",
            "tests/test_merge.py": "tests require MergeConflict and deterministic key order",
            "README.md": "not needed for this worker",
            "docs/history.md": "not needed for this worker",
        },
    }


def build_scope_packet() -> dict[str, Any]:
    return {
        "objective": "Fix merge_results deterministic merge behavior.",
        "allowed_files": ["src/merge_fixture/merge.py", "tests/test_merge.py"],
        "acceptance": [
            "raise MergeConflict on unequal scalar conflicts",
            "recursively merge dictionaries",
            "return dictionaries with sorted keys",
            "pytest passes",
        ],
        "pointers": [
            "benchmarks/reference_task.md",
            "src/merge_fixture/merge.py",
            "tests/test_merge.py",
        ],
    }


def build_worker_artifact(scope_packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": "Merge worker should edit merge.py and tests only.",
        "obligations": list(scope_packet["acceptance"]),
        "pointers": list(scope_packet["pointers"]),
        "omitted": ["raw repo dump", "unrelated docs"],
    }


def run_probe() -> dict[str, Any]:
    epoch = Epoch(epoch_seq=5, epoch_id="S5-G0.5")
    blackboard = Blackboard(epoch)
    full_context = build_full_context()
    scope_packet = build_scope_packet()

    blackboard.write("context.full", "planner", full_context)
    blackboard.write("context.scope", "planner", scope_packet)

    allowed = {"context.scope"}
    scoped_value = blackboard.read_scoped("context.scope", allowed)
    undeclared_rejected = False
    try:
        blackboard.read_scoped("context.full", allowed)
    except ScopedReadError:
        undeclared_rejected = True

    worker_artifact = build_worker_artifact(scoped_value)
    worker_text = canonical(worker_artifact).decode()
    full_text = canonical(full_context).decode()
    raw_context_leaked = full_text in worker_text

    full_tokens = token_estimate(full_context)
    scoped_tokens = token_estimate(scoped_value)
    artifact_tokens = token_estimate(worker_artifact)

    graph = TaskGraph(
        seed=505,
        nodes=[
            NodeSpec(
                id="planner",
                role="planner",
                objective="Produce scoped worker packet.",
                outputs=["scope_packet"],
                caps=Caps(max_output_tokens=64, max_thinking_tokens=0),
            ),
            NodeSpec(
                id="worker",
                role="worker",
                objective="Return compressed artifact from declared scope only.",
                dependencies=["planner"],
                inputs=["scope_packet"],
                outputs=["compressed_artifact"],
                boundaries="read_scope=context.scope",
                caps=Caps(max_output_tokens=128, max_thinking_tokens=0),
            ),
            NodeSpec(
                id="closer",
                role="closer",
                objective="Verify compressed worker artifact contains obligations and pointers.",
                dependencies=["worker"],
                inputs=["compressed_artifact"],
                outputs=["closure"],
                caps=Caps(max_output_tokens=64, max_thinking_tokens=0),
            ),
        ],
        edges=[("planner", "worker"), ("worker", "closer")],
    )
    adapter = ScriptedAdapter(
        {
            "planner": CannedResult(artifact={"scope_packet": scoped_value}),
            "worker": CannedResult(artifact={"compressed_artifact": worker_artifact}),
            "closer": CannedResult(
                artifact={
                    "closure": {
                        "passed": True,
                        "artifact_has_pointers": bool(worker_artifact["pointers"]),
                        "artifact_has_obligations": bool(worker_artifact["obligations"]),
                    }
                }
            ),
        }
    )
    report = Conductor(
        graph,
        adapter,
        limit=Dims(tokens=10_000, usd=0.0),
        epoch=epoch,
        cap=2,
    ).run()
    report_hash = sha256_hex(canonical(asdict(report)))
    compression_ratio = full_tokens / artifact_tokens
    passed = (
        report.status == RunStatus.SUCCEEDED
        and undeclared_rejected
        and not raw_context_leaked
        and artifact_tokens < scoped_tokens < full_tokens
        and bool(worker_artifact["pointers"])
    )

    return {
        "gate": "S5/G0.5",
        "passed": passed,
        "zero_token": True,
        "end_to_end": {
            "status": report.status.value,
            "nodes": sorted(report.results),
            "spent_tokens": report.spent_tokens,
            "spent_usd": report.spent_usd,
            "report_hash": report_hash,
        },
        "scoped_read": {
            "allowed_sections": sorted(allowed),
            "declared_read_ok": scoped_value == scope_packet,
            "undeclared_full_context_rejected": undeclared_rejected,
        },
        "compression": {
            "full_context_estimated_tokens": full_tokens,
            "scoped_packet_estimated_tokens": scoped_tokens,
            "compressed_artifact_estimated_tokens": artifact_tokens,
            "ratio_full_over_artifact": compression_ratio,
            "artifact_keeps_pointers": bool(worker_artifact["pointers"]),
            "raw_context_leaked": raw_context_leaked,
        },
        "artifacts": {
            "worker_artifact_sha": sha256_hex(canonical(worker_artifact)),
            "worker_artifact": worker_artifact,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path(".planning/spikes/s5-g0.5-e2e-scoped-compression.json")
    )
    args = parser.parse_args()

    result = run_probe()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "report_hash": result["end_to_end"]["report_hash"],
                "full_tokens": result["compression"]["full_context_estimated_tokens"],
                "artifact_tokens": result["compression"]["compressed_artifact_estimated_tokens"],
                "compression_ratio": result["compression"]["ratio_full_over_artifact"],
                "undeclared_full_context_rejected": result["scoped_read"][
                    "undeclared_full_context_rejected"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
