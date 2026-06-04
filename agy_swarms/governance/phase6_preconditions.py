"""D6.0 Phase-6 precondition and existing-surface audit."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

__all__ = [
    "Phase6EntryIssue",
    "Phase6EntryReport",
    "Phase6EntryStatus",
    "Phase6Surface",
    "Phase6SurfaceStatus",
    "evaluate_phase6_preconditions",
]


class Phase6EntryStatus(StrEnum):
    """Whether Phase 6 implementation may start."""

    PASSED = "passed"
    BLOCKED = "blocked"


class Phase6SurfaceStatus(StrEnum):
    """Implementation status of one AC-6 surface."""

    PASSED = "passed"
    PARTIAL = "partial"
    MISSING = "missing"


@dataclass(frozen=True)
class Phase6Surface:
    """One audited AC-6 implementation surface."""

    id: str
    status: Phase6SurfaceStatus
    message: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class Phase6EntryIssue:
    """One issue that blocks Phase-6 entry."""

    id: str
    message: str
    evidence: str = ""


@dataclass(frozen=True)
class Phase6EntryReport:
    """D6.0 report over Phase-6 prerequisites and implementation surfaces."""

    status: Phase6EntryStatus
    blockers: tuple[Phase6EntryIssue, ...]
    surfaces: dict[str, Phase6Surface]

    @property
    def blocking_issue_ids(self) -> tuple[str, ...]:
        return tuple(issue.id for issue in self.blockers)


def evaluate_phase6_preconditions(root: Path | str = Path(".")) -> Phase6EntryReport:
    """Classify AC-6 surfaces and fail closed if Phase-5 exit evidence is absent."""
    root_path = Path(root)
    blockers: list[Phase6EntryIssue] = []
    surfaces = {
        "phase5_exit": _phase5_exit_surface(root_path, blockers),
        "planning_contract": _planning_contract_surface(root_path),
        "sandbox_patch_promotion": _sandbox_patch_surface(root_path),
        "evidence_replay": _paired_module_surface(
            root_path,
            surface_id="evidence_replay",
            module_path="agy_swarms/governance/evidence.py",
            test_path="tests/test_evidence.py",
            passed_message="external evidence/replay module and tests exist",
            missing_message="external evidence/replay module is missing",
        ),
        "lockfile_pins": _lockfile_surface(root_path),
        "policy_engine": _paired_module_surface(
            root_path,
            surface_id="policy_engine",
            module_path="agy_swarms/governance/policy.py",
            test_path="tests/test_policy.py",
            passed_message="declarative policy engine and tests exist",
            missing_message="declarative policy engine is missing",
        ),
        "thin_cli": _paired_module_surface(
            root_path,
            surface_id="thin_cli",
            module_path="agy_swarms/main.py",
            test_path="tests/test_cli.py",
            passed_message="thin CLI module and tests exist",
            missing_message="thin CLI module is missing",
        ),
        "footprint_gate": _footprint_surface(root_path),
        "ac_con7": _con7_surface(root_path),
    }
    return Phase6EntryReport(
        status=Phase6EntryStatus.BLOCKED if blockers else Phase6EntryStatus.PASSED,
        blockers=tuple(blockers),
        surfaces=surfaces,
    )


def _phase5_exit_surface(root: Path, blockers: list[Phase6EntryIssue]) -> Phase6Surface:
    path = root / ".planning" / "spikes" / "ac5-phase5-exit.json"
    if not path.exists():
        blockers.append(
            Phase6EntryIssue(
                id="phase6.ac5_exit_evidence",
                message="Phase-5 AC-5 exit evidence is required before Phase 6 entry",
                evidence=str(path),
            )
        )
        return Phase6Surface(
            id="phase5_exit",
            status=Phase6SurfaceStatus.MISSING,
            message="Phase-5 AC-5 exit evidence is missing",
            evidence=(str(path),),
        )
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        blockers.append(
            Phase6EntryIssue(
                id="phase6.ac5_exit_evidence",
                message="Phase-5 AC-5 exit evidence is not valid JSON",
                evidence=str(exc),
            )
        )
        return Phase6Surface(
            id="phase5_exit",
            status=Phase6SurfaceStatus.MISSING,
            message="Phase-5 AC-5 exit evidence is unreadable",
            evidence=(str(path),),
        )
    provenance = payload.get("provenance_check", {})
    provenance_ok = all(
        provenance.get(key) is True
        for key in (
            "blinding_seed_consistent",
            "judge_rubric_consistent",
            "measurement_environment_verified",
        )
    )
    if payload.get("passed") is not True or payload.get("status") != "PHASE-5 EXIT READY":
        blockers.append(
            Phase6EntryIssue(
                id="phase6.ac5_exit_evidence",
                message="Phase-5 AC-5 exit evidence is not passed",
                evidence=str(path),
            )
        )
        return Phase6Surface(
            id="phase5_exit",
            status=Phase6SurfaceStatus.MISSING,
            message="Phase-5 AC-5 exit evidence is stale or failed",
            evidence=(str(path),),
        )
    if not provenance_ok:
        blockers.append(
            Phase6EntryIssue(
                id="phase6.ac5_exit_evidence",
                message="Phase-5 AC-5 provenance check is incomplete",
                evidence=str(path),
            )
        )
        return Phase6Surface(
            id="phase5_exit",
            status=Phase6SurfaceStatus.PARTIAL,
            message="Phase-5 AC-5 evidence passed but provenance is incomplete",
            evidence=(str(path),),
        )
    return Phase6Surface(
        id="phase5_exit",
        status=Phase6SurfaceStatus.PASSED,
        message="Phase-5 AC-5 exit evidence is green",
        evidence=(str(path),),
    )


def _planning_contract_surface(root: Path) -> Phase6Surface:
    spec = root / ".planning" / "SPEC.md"
    roadmap = root / ".planning" / "ROADMAP.md"
    if spec.exists() and roadmap.exists() and "AC-CON7" in spec.read_text():
        return Phase6Surface(
            id="planning_contract",
            status=Phase6SurfaceStatus.PASSED,
            message="SPEC and ROADMAP define AC-6/AC-CON7",
            evidence=(str(spec), str(roadmap)),
        )
    return Phase6Surface(
        id="planning_contract",
        status=Phase6SurfaceStatus.MISSING,
        message="SPEC/ROADMAP Phase-6 contract is missing or incomplete",
        evidence=(str(spec), str(roadmap)),
    )


def _sandbox_patch_surface(root: Path) -> Phase6Surface:
    sandbox = root / "agy_swarms" / "governance" / "sandbox.py"
    sandbox_test = root / "tests" / "test_sandbox.py"
    patch = root / "agy_swarms" / "governance" / "patch.py"
    patch_test = root / "tests" / "test_patch_promotion.py"
    if sandbox.exists() and sandbox_test.exists() and patch.exists() and patch_test.exists():
        return Phase6Surface(
            id="sandbox_patch_promotion",
            status=Phase6SurfaceStatus.PASSED,
            message="worktree sandbox and patch-promotion gate exist",
            evidence=tuple(_existing_paths(sandbox, sandbox_test, patch, patch_test)),
        )
    if sandbox.exists() and sandbox_test.exists():
        return Phase6Surface(
            id="sandbox_patch_promotion",
            status=Phase6SurfaceStatus.PARTIAL,
            message="worktree sandbox exists; patch-promotion gate is missing",
            evidence=tuple(_existing_paths(sandbox, sandbox_test, patch, patch_test)),
        )
    return Phase6Surface(
        id="sandbox_patch_promotion",
        status=Phase6SurfaceStatus.MISSING,
        message="sandbox and patch-promotion gate are missing",
        evidence=tuple(_existing_paths(sandbox, sandbox_test, patch, patch_test)),
    )


def _lockfile_surface(root: Path) -> Phase6Surface:
    module = root / "agy_swarms" / "lockfile.py"
    test = root / "tests" / "test_lockfile.py"
    drift_test = root / "tests" / "test_lockfile_drift_ac6.py"
    probe = root / "scripts" / "phase6_d6_4_lockfile_probe.py"
    if module.exists() and test.exists() and (probe.exists() or drift_test.exists()):
        return Phase6Surface(
            id="lockfile_pins",
            status=Phase6SurfaceStatus.PASSED,
            message="lockfile pin enforcement and AC-6 drift evidence exist",
            evidence=tuple(_existing_paths(module, test, drift_test, probe)),
        )
    if module.exists() and test.exists():
        return Phase6Surface(
            id="lockfile_pins",
            status=Phase6SurfaceStatus.PARTIAL,
            message="lockfile helpers exist; Phase-6 lockfile probe is missing",
            evidence=tuple(_existing_paths(module, test, drift_test, probe)),
        )
    return Phase6Surface(
        id="lockfile_pins",
        status=Phase6SurfaceStatus.MISSING,
        message="lockfile pin enforcement is missing",
        evidence=tuple(_existing_paths(module, test, probe)),
    )


def _footprint_surface(root: Path) -> Phase6Surface:
    ac6 = _ac6_exit_payload(root)
    if ac6.get("passed") is True and ac6.get("footprint_gate", {}).get("passed") is True:
        return Phase6Surface(
            id="footprint_gate",
            status=Phase6SurfaceStatus.PASSED,
            message="footprint gate passed in aggregate AC-6 exit evidence",
            evidence=tuple(
                _existing_paths(
                    root / "agy_swarms/governance/footprint.py",
                    root / "tests/test_footprint.py",
                    root / "scripts/phase6_ac6_exit_probe.py",
                    root / ".planning/spikes/ac6-phase6-exit.json",
                )
            ),
        )
    return _module_test_probe_surface(
        root,
        surface_id="footprint_gate",
        module_path="agy_swarms/governance/footprint.py",
        test_path="tests/test_footprint.py",
        probe_path="scripts/phase6_d6_6_footprint_probe.py",
        passed_message="footprint gate module, tests, and probe exist",
        partial_message="footprint module/tests exist; probe is missing",
        missing_message="footprint gate is missing",
    )


def _con7_surface(root: Path) -> Phase6Surface:
    ac6 = _ac6_exit_payload(root)
    if ac6.get("passed") is True and ac6.get("con7_clean_checkout", {}).get("passed") is True:
        return Phase6Surface(
            id="ac_con7",
            status=Phase6SurfaceStatus.PASSED,
            message="AC-CON7 passed in aggregate AC-6 exit evidence",
            evidence=tuple(
                _existing_paths(
                    root / "agy_swarms/governance/vendored_runtime.py",
                    root / "tests/test_vendored_runtime.py",
                    root / "scripts/phase6_ac6_exit_probe.py",
                    root / ".planning/spikes/ac6-phase6-exit.json",
                )
            ),
        )
    return _module_test_probe_surface(
        root,
        surface_id="ac_con7",
        module_path="agy_swarms/governance/vendored_runtime.py",
        test_path="tests/test_vendored_runtime.py",
        probe_path="scripts/phase6_d6_7_con7_probe.py",
        passed_message="AC-CON7 vendored-runtime module, tests, and probe exist",
        partial_message="AC-CON7 module/tests exist; probe is missing",
        missing_message="AC-CON7 no-sibling/vendored-runtime check is missing",
    )


def _paired_module_surface(
    root: Path,
    *,
    surface_id: str,
    module_path: str,
    test_path: str,
    passed_message: str,
    missing_message: str,
) -> Phase6Surface:
    module = root / module_path
    test = root / test_path
    if module.exists() and test.exists():
        status = Phase6SurfaceStatus.PASSED
        message = passed_message
    elif module.exists() or test.exists():
        status = Phase6SurfaceStatus.PARTIAL
        message = f"{missing_message}; only one side exists"
    else:
        status = Phase6SurfaceStatus.MISSING
        message = missing_message
    return Phase6Surface(
        id=surface_id,
        status=status,
        message=message,
        evidence=tuple(_existing_paths(module, test)),
    )


def _module_test_probe_surface(
    root: Path,
    *,
    surface_id: str,
    module_path: str,
    test_path: str,
    probe_path: str,
    passed_message: str,
    partial_message: str,
    missing_message: str,
) -> Phase6Surface:
    module = root / module_path
    test = root / test_path
    probe = root / probe_path
    if module.exists() and test.exists() and probe.exists():
        status = Phase6SurfaceStatus.PASSED
        message = passed_message
    elif module.exists() and test.exists():
        status = Phase6SurfaceStatus.PARTIAL
        message = partial_message
    else:
        status = Phase6SurfaceStatus.MISSING
        message = missing_message
    return Phase6Surface(
        id=surface_id,
        status=status,
        message=message,
        evidence=tuple(_existing_paths(module, test, probe)),
    )


def _existing_paths(*paths: Path) -> list[str]:
    return [str(path) for path in paths if path.exists()]


def _ac6_exit_payload(root: Path) -> dict:
    path = root / ".planning" / "spikes" / "ac6-phase6-exit.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
