#!/usr/bin/env python3
"""Run D4.2 judge-panel soft-evidence probe."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from agy_swarms.quality.judges import (
    JudgeEvidenceReport,
    JudgeModel,
    JudgePanelConfig,
    JudgePanelError,
    JudgeTransport,
    JudgeVerdict,
    record_judge_verdict,
    summarize_judge_evidence,
    validate_judge_panel,
)


DEFAULT_MODEL = "gemini-3.5-flash-high"


def _validation_record(config: JudgePanelConfig) -> dict:
    try:
        validate_judge_panel(config)
    except JudgePanelError as exc:
        return {"accepted": False, "error": str(exc)}
    return {"accepted": True, "error": ""}


def _verdict_record(verdict: JudgeVerdict) -> dict:
    record = asdict(verdict)
    record["transport"] = verdict.transport.value
    record["defects"] = list(verdict.defects)
    return record


def _evidence_record(report: JudgeEvidenceReport) -> dict:
    return {
        "evidence_type": report.evidence_type,
        "deterministic_gate": report.deterministic_gate,
        "ground_truth_preferred": report.ground_truth_preferred,
        "judge_only_defects": list(report.judge_only_defects),
        "verdict_count": len(report.verdicts),
    }


def run_probe(
    *,
    output_path: Path = Path(".planning/spikes/d4.2-judge-panel.json"),
    write_output: bool = True,
) -> dict:
    same_model_panel = JudgePanelConfig(
        default_worker_model_id=DEFAULT_MODEL,
        default_worker_transport=JudgeTransport.AGY_OAUTH,
        judges=(
            JudgeModel(
                id="judge-default",
                model_id=DEFAULT_MODEL,
                transport=JudgeTransport.AGY_OAUTH,
            ),
        ),
    )
    agy_oauth_diverse_panel = JudgePanelConfig(
        default_worker_model_id=DEFAULT_MODEL,
        default_worker_transport=JudgeTransport.AGY_OAUTH,
        judges=(
            JudgeModel(
                id="judge-pro-on-agy",
                model_id="gemini-3.5-pro",
                transport=JudgeTransport.AGY_OAUTH,
            ),
        ),
    )
    diverse_judge = JudgeModel(
        id="judge-pro",
        model_id="gemini-3.5-pro",
        transport=JudgeTransport.GEMINI_SDK_API,
    )
    diverse_panel = JudgePanelConfig(
        default_worker_model_id=DEFAULT_MODEL,
        default_worker_transport=JudgeTransport.AGY_OAUTH,
        judges=(diverse_judge,),
    )
    verdict = record_judge_verdict(
        diverse_judge,
        rubric_sha="sha256:phase4-rubric",
        artifact_pointer="artifacts/phase4/candidate.md",
        passed=False,
        defects=("answer lacks cited evidence",),
    )
    soft_evidence = summarize_judge_evidence((verdict,), ground_truth_available=False)
    secondary_evidence = summarize_judge_evidence((verdict,), ground_truth_available=True)

    result = {
        "gate": "D4.2/judge-panel-soft-evidence",
        "passed": (
            not _validation_record(same_model_panel)["accepted"]
            and not _validation_record(agy_oauth_diverse_panel)["accepted"]
            and _validation_record(diverse_panel)["accepted"]
            and verdict.temperature == 0.0
            and soft_evidence.deterministic_gate is False
            and soft_evidence.judge_only_defects == ("answer lacks cited evidence",)
            and secondary_evidence.ground_truth_preferred is True
        ),
        "same_model_panel": _validation_record(same_model_panel),
        "agy_oauth_diverse_panel": _validation_record(agy_oauth_diverse_panel),
        "diverse_panel": _validation_record(diverse_panel),
        "judge_verdict": _verdict_record(verdict),
        "soft_evidence": _evidence_record(soft_evidence),
        "secondary_evidence": _evidence_record(secondary_evidence),
    }
    if write_output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".planning/spikes/d4.2-judge-panel.json"),
    )
    args = parser.parse_args()
    result = run_probe(output_path=args.output)
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "same_model_panel_accepted": result["same_model_panel"]["accepted"],
                "agy_oauth_diverse_panel_accepted": result["agy_oauth_diverse_panel"]["accepted"],
                "diverse_panel_accepted": result["diverse_panel"]["accepted"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
