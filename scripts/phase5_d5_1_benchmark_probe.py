#!/usr/bin/env python3
"""Run D5.1 benchmark manifest and blinded-run evidence."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import asdict
from pathlib import Path

from agy_swarms.eval.benchmark import (
    BenchmarkValidationError,
    build_blinded_run_record,
    load_benchmark_manifest,
    manifest_hash,
    validate_benchmark_manifest_pin,
    validate_blinded_run_record,
)


def run_probe(
    *,
    root: Path = Path("."),
    output_path: Path = Path(".planning/spikes/d5.1-benchmark-manifest.json"),
    write_output: bool = True,
) -> dict:
    manifest_path = root / "benchmarks" / "phase5_benchmark_manifest.json"
    manifest = load_benchmark_manifest(manifest_path)
    lock = tomllib.loads((root / "agy.lock").read_text())
    pinned_hash = lock["benchmarks"]["phase5_benchmark_manifest_sha"]
    blinding_seed = lock["phase0"]["blinding_seed"]

    current_hash = manifest_hash(manifest)
    validate_benchmark_manifest_pin(manifest, pinned_hash)
    record = build_blinded_run_record(
        manifest,
        run_id="phase5-d5.1-smoke",
        blinding_seed=blinding_seed,
        candidate_arm_id="agy-swarms",
        baseline_arm_id="opus-4.8",
    )
    validate_blinded_run_record(manifest, record)

    task_ids = {task.id for task in manifest.tasks}
    missing_maps = sorted(task_ids.difference(record.item_arm_position_map))
    provider_labels_stripped = _provider_labels_stripped(record, ("agy-swarms", "opus-4.8"))
    result = {
        "gate": "D5.1/benchmark-manifest",
        "passed": not missing_maps and provider_labels_stripped,
        "manifest": {
            "path": str(manifest_path),
            "hash": current_hash,
            "pinned_hash": pinned_hash,
            "pinned": current_hash == pinned_hash,
            "rubric_sha": manifest.rubric_sha,
            "task_ids": sorted(task_ids),
        },
        "run_record": {
            "valid": True,
            "run_id": record.run_id,
            "blinding_seed": record.blinding_seed,
            "task_count": len(record.judge_items),
            "missing_per_item_arm_maps": missing_maps,
            "item_arm_position_map": record.item_arm_position_map,
        },
        "judge_packet": {
            "provider_labels_stripped": provider_labels_stripped,
            "items": [asdict(item) for item in record.judge_items],
        },
    }
    if write_output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def _provider_labels_stripped(record, provider_labels: tuple[str, ...]) -> bool:
    forbidden = set(provider_labels) | {"Candidate", "Baseline"}
    return all(
        all(label not in item.judge_prompt for label in forbidden) for item in record.judge_items
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".planning/spikes/d5.1-benchmark-manifest.json"),
    )
    args = parser.parse_args()
    try:
        result = run_probe(root=args.root, output_path=args.output)
    except BenchmarkValidationError as exc:
        print(json.dumps({"gate": "D5.1/benchmark-manifest", "passed": False, "error": str(exc)}))
        return 1
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "manifest_hash": result["manifest"]["hash"],
                "pinned": result["manifest"]["pinned"],
                "task_count": result["run_record"]["task_count"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
