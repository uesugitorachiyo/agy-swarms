from pathlib import Path

from scripts.release_health import PROBES


def test_release_health_includes_fresh_clone_install_smoke():
    commands = [probe["command"] for probe in PROBES]

    assert ["python", "scripts/fresh_clone_smoke.py"] not in commands
    assert any(command[-1] == "scripts/fresh_clone_smoke.py" for command in commands)


def test_release_health_includes_v02_local_runner_probe():
    commands = [probe["command"] for probe in PROBES]

    assert any(command[-1] == "scripts/v02_local_runner_probe.py" for command in commands)


def test_release_health_includes_v04_fixture_replay_probe():
    commands = [probe["command"] for probe in PROBES]

    assert any(command[-1] == "scripts/v04_fixture_replay_probe.py" for command in commands)


def test_release_health_includes_v05_report_contract_probe():
    commands = [probe["command"] for probe in PROBES]

    assert any(command[-1] == "scripts/v05_report_contract_probe.py" for command in commands)


def test_release_health_includes_v06_graph_preflight_probe():
    commands = [probe["command"] for probe in PROBES]

    assert any(command[-1] == "scripts/v06_graph_preflight_probe.py" for command in commands)


def test_release_health_includes_v07_preflight_contract_probe():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "V07 Preflight Contract Gate" in source
    assert "scripts/v07_preflight_contract_probe.py" in source


def test_release_health_includes_v08_command_review_probe():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "V08 Command Review Gate" in source
    assert "scripts/v08_command_review_probe.py" in source


def test_release_health_includes_v09_command_review_contract_probe():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "V09 Command Review Contract Gate" in source
    assert "scripts/v09_command_review_contract_probe.py" in source


def test_release_health_includes_v10_review_bundle_probe():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "V10 Review Bundle Gate" in source
    assert "scripts/v10_review_bundle_probe.py" in source


def test_release_health_includes_v11_review_bundle_inspection_probe():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "V11 Review Bundle Inspection Gate" in source
    assert "scripts/v11_review_bundle_inspection_probe.py" in source


def test_release_health_includes_v12_review_bundle_diff_probe():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "V12 Review Bundle Diff Gate" in source
    assert "scripts/v12_review_bundle_diff_probe.py" in source


def test_release_health_includes_v13_review_bundle_run_guard_probe():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "V13 Review Bundle Run Guard" in source
    assert "scripts/v13_review_bundle_run_guard_probe.py" in source


def test_release_health_includes_v14_guarded_run_provenance_probe():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "V14 Guarded Run Provenance" in source
    assert "scripts/v14_guarded_run_provenance_probe.py" in source


def test_release_health_includes_v15_guarded_report_inspection_probe():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "V15 Guarded Report Inspection" in source
    assert "scripts/v15_guarded_report_inspection_probe.py" in source


def test_release_health_includes_v16_saved_report_summary_contract_probe():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "V16 Saved Report Summary Contracts" in source
    assert "scripts/v16_saved_report_summary_contract_probe.py" in source


def test_release_health_includes_v17_guarded_report_contract_probe():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "V17 Guarded Report Contract Coverage" in source
    assert "scripts/v17_guarded_report_contract_probe.py" in source


def test_release_health_includes_v18_guarded_failure_report_contract_probe():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "V18 Guarded Failure Report Contracts" in source
    assert "scripts/v18_guarded_failure_report_contract_probe.py" in source


def test_release_health_includes_v19_guard_rejection_report_contract_probe():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "V19 Guard Rejection Report Contracts" in source
    assert "scripts/v19_guard_rejection_report_contract_probe.py" in source


def test_release_health_includes_v20_guard_rejection_inspection_probe():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "V20 Guard Rejection Report Inspection" in source
    assert "scripts/v20_guard_rejection_inspection_probe.py" in source


def test_release_health_includes_v21_hybrid_review_routing_probe():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "V21 Hybrid Review Routing" in source
    assert "scripts/v21_hybrid_review_routing_probe.py" in source


def test_release_health_includes_plugin_smoke_probe():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "V22 Plugin Installation Smoke" in source
    assert "scripts/plugin_smoke_probe.py" in source


def test_release_health_reports_milestone_neutral_certification_label():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "READY (local-release-health-certified)" in source


def test_release_health_status_markers_are_windows_ascii_safe():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "release_health.py").read_text(
        encoding="utf-8"
    )

    assert "[OK]" in source
    assert "[FAIL]" in source
    assert "✓" not in source
    assert "✗" not in source
