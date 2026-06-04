"""D5.1 benchmark manifest and blinded run-record schema."""

import json
from pathlib import Path

import pytest

from agy_swarms.eval.benchmark import (
    BenchmarkManifest,
    BenchmarkTask,
    BenchmarkValidationError,
    build_blinded_run_record,
    load_benchmark_manifest,
    manifest_hash,
    validate_benchmark_manifest_pin,
    validate_blinded_run_record,
)


def test_manifest_hash_is_stable_for_same_tasks_and_rubric():
    manifest = BenchmarkManifest(
        rubric_sha="sha256:rubric",
        tasks=(
            BenchmarkTask(id="task-b", prompt="Second task", source_ref="bench:b"),
            BenchmarkTask(id="task-a", prompt="First task", source_ref="bench:a"),
        ),
    )

    assert manifest_hash(manifest) == manifest_hash(manifest)
    assert manifest_hash(manifest) == (
        "8aa18990a8dc64a25aef89b0dc6f5eb3276b5a7ad41a50b0e030e89a1c65d5c7"
    )


def test_blinded_arm_order_is_deterministic_from_seed():
    manifest = BenchmarkManifest(
        rubric_sha="sha256:rubric",
        tasks=(BenchmarkTask(id="task-a", prompt="First task", source_ref="bench:a"),),
    )

    first = build_blinded_run_record(
        manifest,
        run_id="run-1",
        blinding_seed="seed-1",
        candidate_arm_id="agy-swarms",
        baseline_arm_id="opus-4.8",
    )
    second = build_blinded_run_record(
        manifest,
        run_id="run-1",
        blinding_seed="seed-1",
        candidate_arm_id="agy-swarms",
        baseline_arm_id="opus-4.8",
    )

    assert first.item_arm_position_map == second.item_arm_position_map
    assert first.judge_items[0].presented_arms == second.judge_items[0].presented_arms
    assert first.judge_items[0].presented_arms in (("A", "B"), ("B", "A"))


def test_judge_inputs_strip_arm_labels():
    manifest = BenchmarkManifest(
        rubric_sha="sha256:rubric",
        tasks=(BenchmarkTask(id="task-a", prompt="First task", source_ref="bench:a"),),
    )

    record = build_blinded_run_record(
        manifest,
        run_id="run-1",
        blinding_seed="seed-1",
        candidate_arm_id="agy-swarms",
        baseline_arm_id="opus-4.8",
    )

    assert "agy-swarms" not in record.judge_items[0].judge_prompt
    assert "opus-4.8" not in record.judge_items[0].judge_prompt
    assert "Candidate" not in record.judge_items[0].judge_prompt
    assert "Baseline" not in record.judge_items[0].judge_prompt


def test_missing_per_item_arm_map_blocks_m1():
    manifest = BenchmarkManifest(
        rubric_sha="sha256:rubric",
        tasks=(BenchmarkTask(id="task-a", prompt="First task", source_ref="bench:a"),),
    )
    record = build_blinded_run_record(
        manifest,
        run_id="run-1",
        blinding_seed="seed-1",
        candidate_arm_id="agy-swarms",
        baseline_arm_id="opus-4.8",
    )
    invalid = record.__class__(
        run_id=record.run_id,
        manifest_hash=record.manifest_hash,
        rubric_sha=record.rubric_sha,
        blinding_seed=record.blinding_seed,
        item_arm_position_map={},
        judge_items=record.judge_items,
    )

    with pytest.raises(BenchmarkValidationError, match="per-item arm map"):
        validate_blinded_run_record(manifest, invalid)


def test_manifest_pin_rejects_task_or_rubric_drift_without_lockfile_bump():
    manifest = BenchmarkManifest(
        rubric_sha="sha256:rubric",
        tasks=(BenchmarkTask(id="task-a", prompt="First task", source_ref="bench:a"),),
    )
    pinned_hash = manifest_hash(manifest)
    drifted = BenchmarkManifest(
        rubric_sha="sha256:changed",
        tasks=(BenchmarkTask(id="task-a", prompt="First task", source_ref="bench:a"),),
    )

    with pytest.raises(BenchmarkValidationError, match="manifest hash mismatch"):
        validate_benchmark_manifest_pin(drifted, pinned_hash)


def test_current_repo_benchmark_manifest_matches_lockfile_pin():
    manifest = load_benchmark_manifest(Path("benchmarks/phase5_benchmark_manifest.json"))
    lock_text = Path("agy.lock").read_text()
    pinned_hash = _extract_lock_value(lock_text, "phase5_benchmark_manifest_sha")

    assert validate_benchmark_manifest_pin(manifest, pinned_hash) == pinned_hash


def _extract_lock_value(text: str, key: str) -> str:
    for line in text.splitlines():
        if line.startswith(f"{key} = "):
            return json.loads(line.split(" = ", 1)[1])
    raise AssertionError(f"missing {key}")
