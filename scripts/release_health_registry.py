"""Release-health probe registry.

Keep probe definitions here so the runner, tests, and docs have one stable source
for release verification commands.
"""

from __future__ import annotations

import sys

PROBES = [
    {
        "name": "Ruff Lints",
        "command": ["uv", "run", "ruff", "check", "."],
        "desc": "Verifies codebase lint and import standards",
    },
    {
        "name": "Ruff Format Check",
        "command": ["uv", "run", "ruff", "format", "--check", "."],
        "desc": "Verifies codebase formatting without rewriting files",
    },
    {
        "name": "Unit Test Suite",
        "command": ["uv", "run", "python", "-m", "pytest", "-q"],
        "desc": "Executes the hermetic engine test suite",
    },
    {
        "name": "Fresh Clone Install Smoke",
        "command": [sys.executable, "scripts/fresh_clone_smoke.py"],
        "desc": "Verifies installability and console entrypoint from a fresh clone",
    },
    {
        "name": "AC-7 Local Runner Gate",
        "command": [sys.executable, "scripts/v02_local_runner_probe.py"],
        "desc": "Verifies v0.2 local graph execution, report inspection, and handoff guardrails",
    },
    {
        "name": "V04 Fixture Replay Gate",
        "command": [sys.executable, "scripts/v04_fixture_replay_probe.py"],
        "desc": "Verifies tracked local-runner fixtures, report inspection, and saved-report resume",
    },
    {
        "name": "V05 Report Contract Gate",
        "command": [sys.executable, "scripts/v05_report_contract_probe.py"],
        "desc": "Verifies saved local-runner reports against the stable report contract",
    },
    {
        "name": "V06 Graph Preflight Gate",
        "command": [sys.executable, "scripts/v06_graph_preflight_probe.py"],
        "desc": "Verifies local runner graphs can be preflighted without executing commands",
    },
    {
        "name": "V07 Preflight Contract Gate",
        "command": [sys.executable, "scripts/v07_preflight_contract_probe.py"],
        "desc": "Verifies preflight JSON output against the local schema contract",
    },
    {
        "name": "V08 Command Review Gate",
        "command": [sys.executable, "scripts/v08_command_review_probe.py"],
        "desc": "Verifies opt-in preflight command review evidence without execution",
    },
    {
        "name": "V09 Command Review Contract Gate",
        "command": [sys.executable, "scripts/v09_command_review_contract_probe.py"],
        "desc": "Verifies opt-in command review evidence against the local schema contract",
    },
    {
        "name": "V10 Review Bundle Gate",
        "command": [sys.executable, "scripts/v10_review_bundle_probe.py"],
        "desc": "Verifies deterministic saved review bundles without command execution",
    },
    {
        "name": "V11 Review Bundle Inspection Gate",
        "command": [sys.executable, "scripts/v11_review_bundle_inspection_probe.py"],
        "desc": "Verifies deterministic saved review bundle inspection without command execution",
    },
    {
        "name": "V12 Review Bundle Diff Gate",
        "command": [sys.executable, "scripts/v12_review_bundle_diff_probe.py"],
        "desc": "Verifies deterministic saved review bundle diffs without command execution",
    },
    {
        "name": "V13 Review Bundle Run Guard",
        "command": [sys.executable, "scripts/v13_review_bundle_run_guard_probe.py"],
        "desc": "Verifies saved review bundles can guard local graph execution",
    },
    {
        "name": "V14 Guarded Run Provenance",
        "command": [sys.executable, "scripts/v14_guarded_run_provenance_probe.py"],
        "desc": "Verifies guarded local run reports carry saved review-bundle provenance",
    },
    {
        "name": "V15 Guarded Report Inspection",
        "command": [sys.executable, "scripts/v15_guarded_report_inspection_probe.py"],
        "desc": "Verifies guarded run reports expose read-only inspect/resume guard summaries",
    },
    {
        "name": "V16 Saved Report Summary Contracts",
        "command": [sys.executable, "scripts/v16_saved_report_summary_contract_probe.py"],
        "desc": "Verifies saved-report inspect/resume summaries against the local schema contract",
    },
    {
        "name": "V17 Guarded Report Contract Coverage",
        "command": [sys.executable, "scripts/v17_guarded_report_contract_probe.py"],
        "desc": "Verifies guarded saved local-runner reports against the full report schema contract",
    },
    {
        "name": "V18 Guarded Failure Report Contracts",
        "command": [sys.executable, "scripts/v18_guarded_failure_report_contract_probe.py"],
        "desc": "Verifies guarded failed local-runner reports against the full report schema contract",
    },
    {
        "name": "V19 Guard Rejection Report Contracts",
        "command": [sys.executable, "scripts/v19_guard_rejection_report_contract_probe.py"],
        "desc": "Verifies pre-execution guard rejection reports against the local schema contract",
    },
    {
        "name": "V20 Guard Rejection Report Inspection",
        "command": [sys.executable, "scripts/v20_guard_rejection_inspection_probe.py"],
        "desc": "Verifies read-only inspect/resume triage for guard rejection reports",
    },
    {
        "name": "V21 Hybrid Review Routing",
        "command": [sys.executable, "scripts/v21_hybrid_review_routing_probe.py"],
        "desc": "Verifies edge-backed graph semantics and Gemini-default optional CLI review routing",
    },
    {
        "name": "V22 Plugin Installation Smoke",
        "command": [sys.executable, "scripts/plugin_smoke_probe.py"],
        "desc": "Verifies agy plugin validation, installation, listing, and uninstallation",
    },
]
