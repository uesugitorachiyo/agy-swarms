from __future__ import annotations

import json
import subprocess
import sys

import pytest

from agy_swarms.graph_io import load_graph
from agy_swarms.review_bundle import write_review_bundle
from agy_swarms.review_bundle_inspection import (
    ReviewBundleInspectionError,
    summarize_review_bundle,
)


def test_review_bundle_inspection_summarizes_saved_bundle_without_execution(tmp_path):
    graph_path = "tests/fixtures/local_runner/success-graph.json"
    bundle_path = tmp_path / "bundle.json"
    write_review_bundle(load_graph(graph_path), graph_path=graph_path, output_path=bundle_path)

    summary = summarize_review_bundle(bundle_path)

    assert summary == {
        "kind": "review_bundle",
        "path": str(bundle_path),
        "format": "local-review-bundle",
        "schema_version": "v1",
        "graph_path": graph_path,
        "graph_sha256": json.loads(bundle_path.read_text(encoding="utf-8"))["graph_sha256"],
        "command_node_count": 2,
        "review_node_count": 2,
        "review_complete": True,
        "schemas": {
            "preflight": "schemas/local-graph-preflight-v1.schema.json",
            "command_review": "schemas/local-command-review-v1.schema.json",
            "review_bundle": "schemas/local-review-bundle-v1.schema.json",
        },
        "commands_executed": False,
    }


def test_review_bundle_inspection_rejects_malformed_bundle_with_redacted_diagnostic(
    tmp_path,
):
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "format": "local-review-bundle",
                "schema_version": "v1",
                "graph_path": "/tmp/secret-token-value/graph.json",
                "commands_executed": False,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReviewBundleInspectionError) as exc_info:
        summarize_review_bundle(bundle_path)

    message = str(exc_info.value)
    assert "missing required keys" in message
    assert "repair:" in message
    assert "secret-token-value" not in message
    assert "/tmp/" not in message


def test_inspect_review_bundle_cli_prints_summary_without_allow_local_commands(tmp_path):
    graph_path = "tests/fixtures/local_runner/success-graph.json"
    bundle_path = tmp_path / "bundle.json"
    write_review_bundle(load_graph(graph_path), graph_path=graph_path, output_path=bundle_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "inspect",
            "--review-bundle",
            str(bundle_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["kind"] == "review_bundle"
    assert payload["path"] == str(bundle_path)
    assert payload["graph_path"] == graph_path
    assert payload["command_node_count"] == 2
    assert payload["review_node_count"] == 2
    assert payload["review_complete"] is True
    assert payload["commands_executed"] is False
