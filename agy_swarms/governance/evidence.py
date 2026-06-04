"""External evidence and replay record (FR-12/FR-15/D6.3)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path


class EvidenceError(Exception):
    """Raised when evidence verification or replay fails."""


@dataclass
class EvidenceRecord:
    run_id: str
    artifact_digests: dict[str, str]  # relative_path -> sha256
    changed_files: list[str]
    model_pins: dict[str, str]
    tool_pins: dict[str, str]
    policy_mode: str
    sandbox_root: str
    replay_command: list[str]
    transcript_pointers: dict[str, str]  # transcript_id -> external_pointer_path

    def to_json(self) -> str:
        """Serialize the evidence record to a JSON string."""
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, data: str) -> EvidenceRecord:
        """Deserialize an evidence record from a JSON string."""
        parsed = json.loads(data)
        return cls(**parsed)


class ExternalEvidenceStore:
    """Manages large run artifacts and transcript logs outside git history."""

    def __init__(self, store_dir: Path | str) -> None:
        self.store_dir = Path(store_dir).resolve()
        # Ensure the external store is created (should be git-ignored like .agy/evidence or artifacts/)
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def save_transcript(self, transcript_id: str, transcript_content: str) -> tuple[str, str]:
        """Externalize a raw transcript, referencing and saving it by digest.

        Returns:
            (pointer_path, sha256_digest)
        """
        content_bytes = transcript_content.encode("utf-8")
        digest = hashlib.sha256(content_bytes).hexdigest()

        # Save to the external git-ignored directory named by its digest
        pointer_path = self.store_dir / f"transcript_{digest}.log"
        pointer_path.write_bytes(content_bytes)

        return str(pointer_path), digest

    def save_large_artifact(self, artifact_name: str, content: bytes) -> tuple[str, str]:
        """Externalize a large artifact, saving it by digest.

        Returns:
            (pointer_path, sha256_digest)
        """
        digest = hashlib.sha256(content).hexdigest()
        pointer_path = self.store_dir / f"artifact_{digest}.bin"
        pointer_path.write_bytes(content)

        return str(pointer_path), digest

    def verify_and_replay(self, record: EvidenceRecord) -> None:
        """Verify the integrity of a run's evidence record before replay.

        Raises:
            EvidenceError if any pointer is missing or digest mismatches.
        """
        # 1. Verify artifact digests
        for rel_path_str, expected_digest in record.artifact_digests.items():
            path = Path(rel_path_str)
            if not path.exists():
                raise EvidenceError(f"Missing artifact file: {rel_path_str}")

            actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_digest != expected_digest:
                raise EvidenceError(
                    f"Artifact digest mismatch for '{rel_path_str}': expected {expected_digest}, got {actual_digest}"
                )

        # 2. Verify external transcripts/pointers
        for trans_id, pointer_str in record.transcript_pointers.items():
            pointer_path = Path(pointer_str)
            if not pointer_path.exists():
                raise EvidenceError(
                    f"Missing external transcript pointer for '{trans_id}': {pointer_str}"
                )

            # Assert transcript file is inside the designated external store_dir for security
            resolved_pointer = pointer_path.resolve()
            try:
                resolved_pointer.relative_to(self.store_dir)
            except ValueError:
                raise EvidenceError(
                    f"Security violation: transcript pointer escapes external store: {pointer_str}"
                )
