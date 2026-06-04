"""FR-23 judge-panel soft evidence records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "JudgeEvidenceReport",
    "JudgeModel",
    "JudgePanelConfig",
    "JudgePanelError",
    "JudgeTransport",
    "JudgeVerdict",
    "record_judge_verdict",
    "summarize_judge_evidence",
    "validate_judge_panel",
]


class JudgeTransport(StrEnum):
    """Transport boundary for recorded judge evidence."""

    AGY_OAUTH = "agy_oauth"
    GEMINI_SDK_API = "gemini_sdk_api"


@dataclass(frozen=True)
class JudgeModel:
    """One configured judge model."""

    id: str
    model_id: str
    transport: JudgeTransport


@dataclass(frozen=True)
class JudgePanelConfig:
    """Judge panel configuration with the default worker route for comparison."""

    default_worker_model_id: str
    default_worker_transport: JudgeTransport
    judges: tuple[JudgeModel, ...]


@dataclass(frozen=True)
class JudgeVerdict:
    """Recorded temperature-0 LLM judge verdict."""

    judge_id: str
    model_id: str
    transport: JudgeTransport
    temperature: float
    rubric_sha: str
    artifact_pointer: str
    passed: bool
    defects: tuple[str, ...] = ()


@dataclass(frozen=True)
class JudgeEvidenceReport:
    """Soft evidence summary; judge-only defects are never code-owned gates."""

    evidence_type: str
    deterministic_gate: bool
    ground_truth_preferred: bool
    judge_only_defects: tuple[str, ...] = ()
    verdicts: tuple[JudgeVerdict, ...] = ()


class JudgePanelError(ValueError):
    """Raised when judge-panel evidence violates FR-23 constraints."""


def validate_judge_panel(config: JudgePanelConfig) -> JudgePanelConfig:
    """Require at least one model-diverse judge on a model-configurable transport."""
    if not config.judges:
        raise JudgePanelError("judge panel must include at least one judge")

    diverse_judges = tuple(
        judge for judge in config.judges if judge.model_id != config.default_worker_model_id
    )
    if not diverse_judges:
        raise JudgePanelError("judge panel must include at least one judge on a different model")
    if any(judge.transport != JudgeTransport.GEMINI_SDK_API for judge in diverse_judges):
        raise JudgePanelError("different-model judge must use a model-configurable transport")
    return config


def record_judge_verdict(
    judge: JudgeModel,
    *,
    rubric_sha: str,
    artifact_pointer: str,
    passed: bool,
    defects: tuple[str, ...] = (),
    temperature: float = 0.0,
) -> JudgeVerdict:
    """Create a recorded judge verdict; D4.2 only accepts temperature=0 evidence."""
    if temperature != 0.0:
        raise JudgePanelError("judge verdicts must record temperature=0")
    if not rubric_sha.strip():
        raise JudgePanelError("rubric_sha is required")
    if not artifact_pointer.strip():
        raise JudgePanelError("artifact_pointer is required")
    return JudgeVerdict(
        judge_id=judge.id,
        model_id=judge.model_id,
        transport=judge.transport,
        temperature=temperature,
        rubric_sha=rubric_sha,
        artifact_pointer=artifact_pointer,
        passed=passed,
        defects=tuple(defects),
    )


def summarize_judge_evidence(
    verdicts: tuple[JudgeVerdict, ...],
    *,
    ground_truth_available: bool,
) -> JudgeEvidenceReport:
    """Summarize LLM judge-only defects as soft, never deterministic, evidence."""
    judge_only_defects = tuple(
        defect for verdict in verdicts if not verdict.passed for defect in verdict.defects
    )
    return JudgeEvidenceReport(
        evidence_type="secondary_soft" if ground_truth_available else "soft",
        deterministic_gate=False,
        ground_truth_preferred=ground_truth_available,
        judge_only_defects=judge_only_defects,
        verdicts=tuple(verdicts),
    )
