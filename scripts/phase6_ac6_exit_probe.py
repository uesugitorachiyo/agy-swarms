#!/usr/bin/env python3
"""Run the AC-6 Phase-6 exit evidence probe."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from agy_swarms.governance.footprint import FootprintGate
from agy_swarms.governance.vendored_runtime import verify_clean_environment


def run_exit_probe() -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]

    # 1. Run CON-7 clean-checkout verification
    con7_passed = True
    con7_error = None
    try:
        verify_clean_environment(repo_root)
    except Exception as exc:
        con7_passed = False
        con7_error = str(exc)

    # 2. Run D6.6 Footprint Gate verification
    footprint_gate = FootprintGate(repo_root)
    footprint_passed = True
    footprint_error = None
    total_loc = 0
    source_files_count = 0
    try:
        res = footprint_gate.run_check()
        total_loc = res["total_loc"]
        source_files_count = res["source_files_count"]
    except Exception as exc:
        footprint_passed = False
        footprint_error = str(exc)

    # 3. Check that D6.2 (sandbox/patch.py) and D6.3 (evidence.py) exist
    sandbox_files_exist = (repo_root / "agy_swarms/governance/patch.py").exists() and (
        repo_root / "tests/test_patch_promotion.py"
    ).exists()

    evidence_files_exist = (repo_root / "agy_swarms/governance/evidence.py").exists() and (
        repo_root / "tests/test_evidence.py"
    ).exists()

    # 4. Check that D6.5 thin CLI exists
    cli_files_exist = (repo_root / "agy_swarms/main.py").exists() and (
        repo_root / "tests/test_cli.py"
    ).exists()

    passed = (
        con7_passed
        and footprint_passed
        and sandbox_files_exist
        and evidence_files_exist
        and cli_files_exist
    )

    return {
        "gate": "AC-6",
        "passed": passed,
        "sandbox_patch_promotion": {
            "passed": sandbox_files_exist,
            "source_file": "agy_swarms/governance/patch.py",
            "test_file": "tests/test_patch_promotion.py",
        },
        "evidence_replay_externalization": {
            "passed": evidence_files_exist,
            "source_file": "agy_swarms/governance/evidence.py",
            "test_file": "tests/test_evidence.py",
        },
        "thin_cli": {
            "passed": cli_files_exist,
            "source_file": "agy_swarms/main.py",
            "test_file": "tests/test_cli.py",
        },
        "footprint_gate": {
            "passed": footprint_passed,
            "total_loc": total_loc,
            "source_files_count": source_files_count,
            "error": footprint_error,
        },
        "con7_clean_checkout": {
            "passed": con7_passed,
            "error": con7_error,
        },
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write output JSON to disk")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write output JSON to disk (deprecated, default)",
    )
    args = parser.parse_args()
    result = run_exit_probe()
    if args.write and not args.no_write:
        output_path = Path(__file__).resolve().parents[1] / ".planning/spikes/ac6-phase6-exit.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
