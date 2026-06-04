from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from agy_swarms.graph_io import load_graph
from agy_swarms.review_bundle import write_review_bundle
from agy_swarms.review_bundle_diff import summarize_review_bundle_diff


def _write_modified_graph(source: str, destination: Path) -> None:
    payload = json.loads(Path(source).read_text(encoding="utf-8"))
    for node in payload["nodes"]:
        if node["id"] == "verify":
            node["command"] = ["python", "-c", "print('fixture-success:changed')"]
    payload["nodes"].append(
        {
            "id": "audit",
            "role": "verify",
            "objective": "emit deterministic fixture audit evidence",
            "dependencies": ["verify"],
            "command": ["python", "-c", "print('fixture-success:audit')"],
        }
    )
    payload["edges"].append(["verify", "audit"])
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_review_bundle_diff_summarizes_saved_bundle_changes_without_execution(tmp_path):
    before_graph = "tests/fixtures/local_runner/success-graph.json"
    after_graph = tmp_path / "after-graph.json"
    before_bundle = tmp_path / "before-bundle.json"
    after_bundle = tmp_path / "after-bundle.json"
    _write_modified_graph(before_graph, after_graph)

    write_review_bundle(
        load_graph(before_graph), graph_path=before_graph, output_path=before_bundle
    )
    write_review_bundle(load_graph(after_graph), graph_path=after_graph, output_path=after_bundle)

    summary = summarize_review_bundle_diff(before_bundle, after_bundle)

    assert summary["kind"] == "review_bundle_diff"
    assert summary["before_path"] == str(before_bundle)
    assert summary["after_path"] == str(after_bundle)
    assert summary["before_schema_version"] == "v1"
    assert summary["after_schema_version"] == "v1"
    assert summary["before_graph_sha256"] != summary["after_graph_sha256"]
    assert summary["graph_changed"] is True
    assert summary["command_changes"] == {
        "added": ["audit"],
        "removed": [],
        "changed": ["verify"],
        "unchanged": ["prepare"],
    }
    assert summary["before_review_complete"] is True
    assert summary["after_review_complete"] is True
    assert summary["commands_executed"] is False

    reversed_summary = summarize_review_bundle_diff(after_bundle, before_bundle)
    assert reversed_summary["command_changes"]["added"] == []
    assert reversed_summary["command_changes"]["removed"] == ["audit"]


def test_inspect_review_bundle_diff_cli_prints_summary_without_allow_local_commands(
    tmp_path,
):
    before_graph = "tests/fixtures/local_runner/success-graph.json"
    after_graph = tmp_path / "after-graph.json"
    before_bundle = tmp_path / "before-bundle.json"
    after_bundle = tmp_path / "after-bundle.json"
    _write_modified_graph(before_graph, after_graph)

    write_review_bundle(
        load_graph(before_graph), graph_path=before_graph, output_path=before_bundle
    )
    write_review_bundle(load_graph(after_graph), graph_path=after_graph, output_path=after_bundle)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "inspect",
            "--review-bundle-diff",
            str(before_bundle),
            str(after_bundle),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["kind"] == "review_bundle_diff"
    assert payload["command_changes"]["added"] == ["audit"]
    assert payload["command_changes"]["changed"] == ["verify"]
    assert payload["commands_executed"] is False
