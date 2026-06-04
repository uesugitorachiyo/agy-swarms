from __future__ import annotations

import hashlib
import json
import subprocess
import sys

from agy_swarms.graph_io import load_graph
from agy_swarms.review_bundle import build_review_bundle, write_review_bundle


def test_review_bundle_wraps_preflight_and_command_review_without_execution():
    graph_path = "tests/fixtures/local_runner/success-graph.json"
    graph = load_graph(graph_path)

    bundle = build_review_bundle(graph, graph_path=graph_path)

    assert bundle["format"] == "local-review-bundle"
    assert bundle["schema_version"] == "v1"
    assert bundle["graph_path"] == graph_path
    assert bundle["graph_sha256"] == hashlib.sha256(open(graph_path, "rb").read()).hexdigest()
    assert bundle["commands_executed"] is False
    assert bundle["schemas"] == {
        "preflight": "schemas/local-graph-preflight-v1.schema.json",
        "command_review": "schemas/local-command-review-v1.schema.json",
        "review_bundle": "schemas/local-review-bundle-v1.schema.json",
    }
    assert bundle["preflight"]["commands_executed"] is False
    assert "command_review" in bundle["preflight"]
    assert bundle["review_bundle"]["command_node_count"] == len(
        bundle["preflight"]["command_node_ids"]
    )


def test_write_review_bundle_is_byte_stable(tmp_path):
    graph_path = "tests/fixtures/local_runner/dependency-skip-graph.json"
    graph = load_graph(graph_path)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_review_bundle(graph, graph_path=graph_path, output_path=first)
    write_review_bundle(graph, graph_path=graph_path, output_path=second)

    assert first.read_bytes() == second.read_bytes()
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["commands_executed"] is False


def test_preflight_review_bundle_cli_writes_output_without_execution(tmp_path):
    output = tmp_path / "bundle.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "preflight",
            "--graph",
            "tests/fixtures/local_runner/success-graph.json",
            "--review-bundle",
            "--output",
            str(output),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["format"] == "local-review-bundle"
    assert payload["commands_executed"] is False
    assert json.loads(result.stdout)["output"] == str(output)
