"""D5.1 benchmark manifest and blinded run-record schema."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

__all__ = [
    "BenchmarkManifest",
    "BenchmarkTask",
    "BenchmarkValidationError",
    "BlindedJudgeItem",
    "BlindedRunRecord",
    "build_blinded_run_record",
    "load_benchmark_manifest",
    "manifest_hash",
    "validate_benchmark_manifest_pin",
    "validate_blinded_run_record",
]


class BenchmarkValidationError(ValueError):
    """Raised when benchmark provenance is incomplete or drifts from pins."""


@dataclass(frozen=True)
class BenchmarkTask:
    """One fixed benchmark task."""

    id: str
    prompt: str
    source_ref: str


@dataclass(frozen=True)
class BenchmarkManifest:
    """Pinned task set and scoring rubric for Phase-5 M1."""

    rubric_sha: str
    tasks: tuple[BenchmarkTask, ...]


@dataclass(frozen=True)
class BlindedJudgeItem:
    """Judge-facing item without provider arm labels."""

    task_id: str
    judge_prompt: str
    presented_arms: tuple[str, str]


@dataclass(frozen=True)
class BlindedRunRecord:
    """Provenance needed to unblind judge results after M1 scoring."""

    run_id: str
    manifest_hash: str
    rubric_sha: str
    blinding_seed: str
    item_arm_position_map: dict[str, dict[str, str]]
    judge_items: tuple[BlindedJudgeItem, ...]


def load_benchmark_manifest(path: Path) -> BenchmarkManifest:
    """Load a Phase-5 benchmark manifest from JSON."""
    data = json.loads(path.read_text())
    tasks = tuple(
        BenchmarkTask(
            id=str(item["id"]),
            prompt=str(item["prompt"]),
            source_ref=str(item["source_ref"]),
        )
        for item in data["tasks"]
    )
    return BenchmarkManifest(rubric_sha=str(data["rubric_sha"]), tasks=tasks)


def manifest_hash(manifest: BenchmarkManifest) -> str:
    """Return the canonical SHA-256 for the task set and rubric."""
    return hashlib.sha256(_canonical_manifest_bytes(manifest)).hexdigest()


def validate_benchmark_manifest_pin(
    manifest: BenchmarkManifest,
    pinned_manifest_hash: str,
) -> str:
    """Fail closed when the current task set or rubric differs from the lockfile pin."""
    current_hash = manifest_hash(manifest)
    if not pinned_manifest_hash:
        raise BenchmarkValidationError("manifest hash pin is missing")
    if current_hash != pinned_manifest_hash:
        raise BenchmarkValidationError(
            "manifest hash mismatch: lockfile bump required for task or rubric drift"
        )
    return current_hash


def build_blinded_run_record(
    manifest: BenchmarkManifest,
    *,
    run_id: str,
    blinding_seed: str,
    candidate_arm_id: str,
    baseline_arm_id: str,
) -> BlindedRunRecord:
    """Create a deterministic A/B map and judge packet for a candidate-vs-baseline run."""
    if not run_id:
        raise BenchmarkValidationError("run_id is required")
    if not blinding_seed:
        raise BenchmarkValidationError("blinding_seed is required")
    if candidate_arm_id == baseline_arm_id:
        raise BenchmarkValidationError("candidate and baseline arm ids must differ")

    item_arm_position_map: dict[str, dict[str, str]] = {}
    judge_items: list[BlindedJudgeItem] = []
    for task in _sorted_tasks(manifest):
        candidate_first = _candidate_first(
            seed=blinding_seed,
            run_id=run_id,
            task_id=task.id,
        )
        if candidate_first:
            arm_map = {candidate_arm_id: "A", baseline_arm_id: "B"}
            presented_arms = ("A", "B")
        else:
            arm_map = {candidate_arm_id: "B", baseline_arm_id: "A"}
            presented_arms = ("B", "A")
        item_arm_position_map[task.id] = arm_map
        judge_items.append(
            BlindedJudgeItem(
                task_id=task.id,
                judge_prompt=_judge_prompt(task, presented_arms),
                presented_arms=presented_arms,
            )
        )

    return BlindedRunRecord(
        run_id=run_id,
        manifest_hash=manifest_hash(manifest),
        rubric_sha=manifest.rubric_sha,
        blinding_seed=blinding_seed,
        item_arm_position_map=item_arm_position_map,
        judge_items=tuple(judge_items),
    )


def validate_blinded_run_record(
    manifest: BenchmarkManifest,
    record: BlindedRunRecord,
) -> BlindedRunRecord:
    """Validate that a blinded record contains all M1 blocking provenance."""
    expected_hash = manifest_hash(manifest)
    if record.manifest_hash != expected_hash:
        raise BenchmarkValidationError("manifest hash mismatch")
    if record.rubric_sha != manifest.rubric_sha:
        raise BenchmarkValidationError("rubric hash mismatch")
    if not record.blinding_seed:
        raise BenchmarkValidationError("blinding_seed is required")

    task_ids = {task.id for task in manifest.tasks}
    if set(record.item_arm_position_map) != task_ids:
        raise BenchmarkValidationError("per-item arm map is required for every task")
    for task_id, arm_map in record.item_arm_position_map.items():
        labels = set(arm_map.values())
        if labels != {"A", "B"}:
            raise BenchmarkValidationError(f"per-item arm map for {task_id} must map to A/B")
    judge_task_ids = {item.task_id for item in record.judge_items}
    if judge_task_ids != task_ids:
        raise BenchmarkValidationError("judge items must match benchmark tasks")
    return record


def _canonical_manifest_bytes(manifest: BenchmarkManifest) -> bytes:
    payload = {
        "rubric_sha": manifest.rubric_sha,
        "tasks": [asdict(task) for task in _sorted_tasks(manifest)],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _sorted_tasks(manifest: BenchmarkManifest) -> tuple[BenchmarkTask, ...]:
    return tuple(sorted(manifest.tasks, key=lambda task: task.id))


def _candidate_first(*, seed: str, run_id: str, task_id: str) -> bool:
    digest = hashlib.sha256(f"{seed}\0{run_id}\0{task_id}".encode()).digest()
    return digest[0] % 2 == 0


def _judge_prompt(task: BenchmarkTask, presented_arms: tuple[str, str]) -> str:
    arms = " and ".join(f"Response {label}" for label in presented_arms)
    return (
        f"Task: {task.prompt}\n"
        f"Source: {task.source_ref}\n"
        f"Compare {arms} using the pinned rubric. Return only the winning response label "
        "and concise rationale."
    )
