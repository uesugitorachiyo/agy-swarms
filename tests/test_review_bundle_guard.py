from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from agy_swarms.graph_io import load_graph
from agy_swarms.review_bundle import write_review_bundle
from agy_swarms.review_bundle_guard import validate_review_bundle_for_graph


def _write_modified_graph(source: str, destination: Path, marker: Path) -> None:
    payload = json.loads(Path(source).read_text(encoding="utf-8"))
    for node in payload["nodes"]:
        if node["id"] == "verify":
            node["command"] = [
                sys.executable,
                "-c",
                f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
            ]
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_review_bundle_guard_accepts_matching_saved_bundle(tmp_path):
    graph_path = "tests/fixtures/local_runner/success-graph.json"
    bundle_path = tmp_path / "bundle.json"
    write_review_bundle(load_graph(graph_path), graph_path=graph_path, output_path=bundle_path)

    summary = validate_review_bundle_for_graph(graph_path, bundle_path)

    assert summary["kind"] == "review_bundle_run_guard"
    assert summary["graph_path"] == graph_path
    assert summary["bundle_path"] == str(bundle_path)
    assert summary["graph_sha256_match"] is True
    assert summary["review_complete"] is True
    assert summary["missing_command_reviews"] == []
    assert summary["commands_executed"] is False


def test_review_bundle_guard_rejects_graph_digest_mismatch_before_execution(tmp_path):
    before_graph = "tests/fixtures/local_runner/success-graph.json"
    after_graph = tmp_path / "after-graph.json"
    bundle_path = tmp_path / "bundle.json"
    marker = tmp_path / "marker.txt"
    _write_modified_graph(before_graph, after_graph, marker)
    write_review_bundle(load_graph(before_graph), graph_path=before_graph, output_path=bundle_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "run",
            "--graph",
            str(after_graph),
            "--allow-local-commands",
            "--require-review-bundle",
            str(bundle_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "review bundle does not match graph" in result.stderr
    assert "write_text" not in result.stderr
    assert not marker.exists()


def test_review_bundle_guard_writes_rejection_report_before_execution(tmp_path):
    before_graph = "tests/fixtures/local_runner/success-graph.json"
    after_graph = tmp_path / "after-graph.json"
    bundle_path = tmp_path / "bundle.json"
    report_path = tmp_path / "guard-rejection.json"
    marker = tmp_path / "marker.txt"
    _write_modified_graph(before_graph, after_graph, marker)
    write_review_bundle(load_graph(before_graph), graph_path=before_graph, output_path=bundle_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "run",
            "--graph",
            str(after_graph),
            "--allow-local-commands",
            "--require-review-bundle",
            str(bundle_path),
            "--report",
            str(report_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert not marker.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["format"] == "local-runner-guard-rejection"
    assert report["schema_version"] == "v1"
    assert report["status"] == "rejected"
    assert report["reason_class"] == "graph_digest_mismatch"
    assert report["diagnostic"] == "review bundle does not match graph"
    assert report["repair_hint"] == "regenerate the review bundle for this graph"
    assert report["commands_executed"] is False
    assert report["schema"] == "schemas/local-runner-guard-rejection-v1.schema.json"
    guard = report["review_bundle_guard"]
    assert guard["kind"] == "review_bundle_run_guard"
    assert guard["guarded_run"] is False
    assert guard["graph_path"] == str(after_graph)
    assert guard["bundle_path"] == str(bundle_path)
    assert guard["graph_sha256_match"] is False
    assert guard["review_complete"] is True
    assert guard["missing_command_reviews"] == []
    assert guard["mismatched_command_reviews"] == ["verify"]
    assert guard["commands_executed"] is False


def test_review_bundle_guard_writes_malformed_bundle_rejection_report_before_execution(
    tmp_path,
):
    graph_path = "tests/fixtures/local_runner/success-graph.json"
    bundle_path = tmp_path / "malformed-bundle.json"
    report_path = tmp_path / "guard-rejection.json"
    bundle_path.write_text("{not-json", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "run",
            "--graph",
            graph_path,
            "--allow-local-commands",
            "--require-review-bundle",
            str(bundle_path),
            "--report",
            str(report_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["format"] == "local-runner-guard-rejection"
    assert report["status"] == "rejected"
    assert report["reason_class"] == "malformed_review_bundle"
    assert report["diagnostic"] == "review bundle is not valid JSON: line 1 column 2"
    assert report["repair_hint"] == "regenerate the review bundle"
    assert report["commands_executed"] is False
    guard = report["review_bundle_guard"]
    assert guard["kind"] == "review_bundle_run_guard"
    assert guard["guarded_run"] is False
    assert guard["graph_path"] == graph_path
    assert guard["bundle_path"] == str(bundle_path)
    assert len(guard["graph_sha256"]) == 64
    assert guard["bundle_graph_sha256"] == ""
    assert guard["graph_sha256_match"] is False
    assert guard["review_complete"] is False
    assert guard["missing_command_reviews"] == []
    assert guard["mismatched_command_reviews"] == []
    assert guard["commands_executed"] is False


def test_guarded_run_report_records_review_bundle_guard_provenance(tmp_path):
    graph_path = "tests/fixtures/local_runner/success-graph.json"
    bundle_path = tmp_path / "bundle.json"
    report_path = tmp_path / "report.json"
    write_review_bundle(load_graph(graph_path), graph_path=graph_path, output_path=bundle_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "run",
            "--graph",
            graph_path,
            "--allow-local-commands",
            "--require-review-bundle",
            str(bundle_path),
            "--report",
            str(report_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    guard = report["review_bundle_guard"]
    assert guard["kind"] == "review_bundle_run_guard"
    assert guard["guarded_run"] is True
    assert guard["graph_path"] == graph_path
    assert guard["bundle_path"] == str(bundle_path)
    assert guard["graph_sha256_match"] is True
    assert guard["review_complete"] is True
    assert guard["missing_command_reviews"] == []
    assert guard["mismatched_command_reviews"] == []
    assert guard["commands_executed"] is False


def test_guarded_report_inspect_and_resume_surface_guard_summary(tmp_path):
    graph_path = "tests/fixtures/local_runner/success-graph.json"
    bundle_path = tmp_path / "bundle.json"
    report_path = tmp_path / "report.json"
    write_review_bundle(load_graph(graph_path), graph_path=graph_path, output_path=bundle_path)

    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "run",
            "--graph",
            graph_path,
            "--allow-local-commands",
            "--require-review-bundle",
            str(bundle_path),
            "--report",
            str(report_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert run.returncode == 0, run.stderr

    inspect = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "inspect",
            "--checkpoint",
            str(report_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    resume = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "resume",
            "--checkpoint",
            str(report_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert inspect.returncode == 0, inspect.stderr
    assert resume.returncode == 0, resume.stderr
    inspect_payload = json.loads(inspect.stdout)
    resume_payload = json.loads(resume.stdout)
    expected = {
        "has_review_bundle_guard": True,
        "guarded_run": True,
        "graph_sha256_match": True,
        "review_complete": True,
        "missing_command_review_count": 0,
        "mismatched_command_review_count": 0,
        "commands_executed": False,
    }
    assert inspect_payload["summary"]["guarded_report"] == expected
    assert resume_payload["summary"]["guarded_report"] == expected
    assert resume_payload["status"] == "resume_loaded"


def test_unguarded_report_inspect_summary_omits_guarded_report(tmp_path):
    graph_path = "tests/fixtures/local_runner/success-graph.json"
    report_path = tmp_path / "report.json"
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "run",
            "--graph",
            graph_path,
            "--allow-local-commands",
            "--report",
            str(report_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert run.returncode == 0, run.stderr

    inspect = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "inspect",
            "--checkpoint",
            str(report_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert inspect.returncode == 0, inspect.stderr
    payload = json.loads(inspect.stdout)
    assert "guarded_report" not in payload["summary"]
