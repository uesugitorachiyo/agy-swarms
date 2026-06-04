from __future__ import annotations

import hashlib
from pathlib import Path
import pytest

from agy_swarms.governance.evidence import (
    EvidenceError,
    EvidenceRecord,
    ExternalEvidenceStore,
)


def test_evidence_record_round_trips_json():
    record = EvidenceRecord(
        run_id="run-123",
        artifact_digests={"src/app.py": "abc123sha"},
        changed_files=["src/app.py"],
        model_pins={"worker": "gemini-3.5-flash"},
        tool_pins={"git": "2.40.0"},
        policy_mode="auto",
        sandbox_root="/tmp/sandbox",
        replay_command=["agy", "run", "--replay", "run-123"],
        transcript_pointers={"worker_1": "/tmp/store/transcript_abc.log"},
    )

    serialized = record.to_json()
    deserialized = EvidenceRecord.from_json(serialized)

    assert deserialized.run_id == "run-123"
    assert deserialized.artifact_digests == {"src/app.py": "abc123sha"}
    assert deserialized.changed_files == ["src/app.py"]
    assert deserialized.model_pins == {"worker": "gemini-3.5-flash"}
    assert deserialized.policy_mode == "auto"
    assert deserialized.replay_command == ["agy", "run", "--replay", "run-123"]
    assert deserialized.transcript_pointers == {"worker_1": "/tmp/store/transcript_abc.log"}


def test_external_evidence_store_saves_transcripts_by_digest(tmp_path: Path):
    store_dir = tmp_path / "evidence_store"
    store = ExternalEvidenceStore(store_dir)

    content = "This is a very large transcript log that should never enter git."
    expected_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()

    pointer, digest = store.save_transcript("worker_run", content)

    assert digest == expected_digest
    assert Path(pointer).exists()
    assert Path(pointer).read_text() == content
    assert f"transcript_{digest}.log" in pointer


def test_verify_and_replay_validates_digests_successfully(tmp_path: Path):
    store_dir = tmp_path / "evidence_store"
    store = ExternalEvidenceStore(store_dir)

    # 1. Create a dummy artifact file in the workspace
    artifact_path = tmp_path / "my_artifact.json"
    artifact_content = b'{"ok": true}'
    artifact_path.write_bytes(artifact_content)
    artifact_digest = hashlib.sha256(artifact_content).hexdigest()

    # 2. Save a transcript externally
    transcript_content = "some log content"
    pointer, trans_digest = store.save_transcript("t1", transcript_content)

    record = EvidenceRecord(
        run_id="run-test",
        artifact_digests={str(artifact_path): artifact_digest},
        changed_files=[str(artifact_path)],
        model_pins={"worker": "gemini-3.5-flash"},
        tool_pins={"git": "2.40.0"},
        policy_mode="auto",
        sandbox_root=str(tmp_path),
        replay_command=["agy", "run", "--replay", "run-test"],
        transcript_pointers={"t1": pointer},
    )

    # Verify should succeed without error
    store.verify_and_replay(record)


def test_verify_and_replay_rejects_missing_artifact(tmp_path: Path):
    store_dir = tmp_path / "evidence_store"
    store = ExternalEvidenceStore(store_dir)

    record = EvidenceRecord(
        run_id="run-test",
        artifact_digests={"missing_artifact.json": "somefakehash"},
        changed_files=["missing_artifact.json"],
        model_pins={},
        tool_pins={},
        policy_mode="auto",
        sandbox_root=str(tmp_path),
        replay_command=[],
        transcript_pointers={},
    )

    with pytest.raises(EvidenceError, match="Missing artifact file: missing_artifact.json"):
        store.verify_and_replay(record)


def test_verify_and_replay_rejects_artifact_digest_mismatch(tmp_path: Path):
    store_dir = tmp_path / "evidence_store"
    store = ExternalEvidenceStore(store_dir)

    artifact_path = tmp_path / "my_artifact.json"
    artifact_path.write_bytes(b"content")

    record = EvidenceRecord(
        run_id="run-test",
        artifact_digests={str(artifact_path): "wrong_hash"},
        changed_files=[str(artifact_path)],
        model_pins={},
        tool_pins={},
        policy_mode="auto",
        sandbox_root=str(tmp_path),
        replay_command=[],
        transcript_pointers={},
    )

    with pytest.raises(EvidenceError, match="Artifact digest mismatch"):
        store.verify_and_replay(record)


def test_verify_and_replay_rejects_missing_external_transcript(tmp_path: Path):
    store_dir = tmp_path / "evidence_store"
    store = ExternalEvidenceStore(store_dir)

    record = EvidenceRecord(
        run_id="run-test",
        artifact_digests={},
        changed_files=[],
        model_pins={},
        tool_pins={},
        policy_mode="auto",
        sandbox_root=str(tmp_path),
        replay_command=[],
        transcript_pointers={"t1": str(store_dir / "nonexistent_transcript.log")},
    )

    with pytest.raises(EvidenceError, match="Missing external transcript pointer"):
        store.verify_and_replay(record)


def test_verify_and_replay_rejects_escaping_transcript_pointer(tmp_path: Path):
    store_dir = tmp_path / "evidence_store"
    store = ExternalEvidenceStore(store_dir)

    # Place a transcript outside the designated store
    outside_dir = tmp_path / "outside_store"
    outside_dir.mkdir()
    unsafe_pointer = outside_dir / "transcript_xyz.log"
    unsafe_pointer.write_text("compromised data")

    record = EvidenceRecord(
        run_id="run-test",
        artifact_digests={},
        changed_files=[],
        model_pins={},
        tool_pins={},
        policy_mode="auto",
        sandbox_root=str(tmp_path),
        replay_command=[],
        transcript_pointers={"t1": str(unsafe_pointer)},
    )

    with pytest.raises(EvidenceError, match="Security violation: transcript pointer escapes"):
        store.verify_and_replay(record)
