import json

from agy_swarms.graph_io import load_graph
from agy_swarms.preflight import summarize_graph_preflight


def test_preflight_summary_reports_graph_shape_without_execution():
    graph = load_graph("tests/fixtures/local_runner/dependency-skip-graph.json")

    payload = summarize_graph_preflight(graph)

    assert payload == {
        "status": "valid",
        "node_count": 4,
        "edge_count": 3,
        "role_counts": {"test": 1, "verify": 3},
        "command_node_ids": ["docs", "lint", "package", "root"],
        "root_nodes": ["root"],
        "leaf_nodes": ["docs", "package"],
        "commands_executed": False,
        "dependency_fan_out": {
            "docs": {
                "dependencies": ["lint"],
                "dependents": [],
                "fan_in": 1,
                "fan_out": 0,
            },
            "lint": {
                "dependencies": ["root"],
                "dependents": ["docs", "package"],
                "fan_in": 1,
                "fan_out": 2,
            },
            "package": {
                "dependencies": ["lint"],
                "dependents": [],
                "fan_in": 1,
                "fan_out": 0,
            },
            "root": {
                "dependencies": [],
                "dependents": ["lint"],
                "fan_in": 0,
                "fan_out": 1,
            },
        },
    }


def test_preflight_summary_default_omits_command_review():
    graph = load_graph("tests/fixtures/local_runner/success-graph.json")

    payload = summarize_graph_preflight(graph)

    assert payload["commands_executed"] is False
    assert "command_review" not in payload


def test_preflight_command_review_contract_is_opt_in():
    graph = load_graph("tests/fixtures/local_runner/success-graph.json")

    default_payload = summarize_graph_preflight(graph)
    review_payload = summarize_graph_preflight(graph, include_command_review=True)

    assert "command_review" not in default_payload
    assert "command_review" in review_payload
    assert default_payload["commands_executed"] is False
    assert review_payload["commands_executed"] is False


def test_preflight_summary_can_include_redacted_command_review(tmp_path):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "safe",
                        "role": "test",
                        "objective": "secret command",
                        "command": [
                            "python",
                            "-c",
                            "print('ok')",
                            "GEMINI_API_KEY=secret-token-value",
                        ],
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )
    graph = load_graph(graph_file)

    payload = summarize_graph_preflight(graph, include_command_review=True)

    review = payload["command_review"]["safe"]
    assert review["executable"] == "python"
    assert review["argv_count"] == 4
    assert review["redacted_argv"] == ["python", "-c", "print('ok')", "<redacted>"]
    assert review["argv_sha256"]
    assert "secret-token-value" not in json.dumps(payload)
    assert payload["commands_executed"] is False
