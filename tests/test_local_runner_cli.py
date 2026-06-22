import json
import subprocess
import sys
from pathlib import Path

import pytest

from agy_swarms.conductor import RunReport
from agy_swarms.graph_io import load_graph
from agy_swarms.local_runner import LocalCommandPermissionError, run_local_graph
from agy_swarms.main import main
from agy_swarms.reporting import report_to_json
from agy_swarms.types import ErrorClass, NodeStatus, ResultEnvelope, RunStatus


def test_report_to_json_contains_operator_fields():
    report = RunReport(
        status=RunStatus.SUCCEEDED,
        results={},
        states={"a": NodeStatus.SUCCEEDED},
        blockers=[],
        spent_tokens=0,
        spent_usd=0.0,
    )

    payload = report_to_json(report)

    assert payload["status"] == "succeeded"
    assert payload["states"] == {"a": "succeeded"}
    assert payload["blockers"] == []
    assert payload["spent_tokens"] == 0
    assert payload["spent_usd"] == 0.0


def test_report_to_json_includes_node_result_details():
    report = RunReport(
        status=RunStatus.FAILED,
        results={
            "a": ResultEnvelope(
                node_id="a",
                idempotency_key="key-a",
                status="failed",
                error_class=ErrorClass.TOOL,
                artifact={"exit_code": 2, "stdout": "out", "stderr": "err"},
                concerns=["needs review"],
                changed_files=["src/example.py"],
            )
        },
        states={"a": NodeStatus.FAILED},
        blockers=[{"node_id": "b", "reason": "skipped"}],
        spent_tokens=4,
        spent_usd=0.5,
    )

    payload = report_to_json(report)

    assert payload["status"] == "failed"
    assert payload["results"]["a"]["status"] == "failed"
    assert payload["results"]["a"]["error_class"] == "tool"
    assert payload["results"]["a"]["exit_code"] == 2
    assert payload["results"]["a"]["stdout"] == "out"
    assert payload["results"]["a"]["stderr"] == "err"
    assert payload["concerns"] == ["needs review"]
    assert payload["changed_files"] == ["src/example.py"]


def test_local_runner_requires_explicit_command_permission(tmp_path: Path):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        '{"nodes":[{"id":"a","role":"test","objective":"echo","command":["python","-c","print(1)"]}],"edges":[]}',
        encoding="utf-8",
    )

    with pytest.raises(LocalCommandPermissionError):
        run_local_graph(load_graph(graph_file), allow_local_commands=False)


def test_local_runner_executes_command_node(tmp_path: Path):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "a",
                        "role": "test",
                        "objective": "echo",
                        "command": [sys.executable, "-c", "print(1)"],
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    payload = run_local_graph(load_graph(graph_file), allow_local_commands=True)

    assert payload["status"] == "succeeded"
    assert payload["states"]["a"] == "succeeded"
    assert payload["results"]["a"]["stdout"].strip() == "1"


def test_cli_run_graph_executes_with_explicit_permission(tmp_path: Path, capsys):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "a",
                        "role": "test",
                        "objective": "echo",
                        "command": [sys.executable, "-c", "print(7)"],
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["run", "--graph", str(graph_file), "--allow-local-commands"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"]["a"]["stdout"].strip() == "7"


def test_cli_run_graph_blocks_without_permission(tmp_path: Path, capsys):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "a",
                        "role": "test",
                        "objective": "echo",
                        "command": [sys.executable, "-c", "print(7)"],
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["run", "--graph", str(graph_file)])

    assert exit_code == 1
    assert "--allow-local-commands" in capsys.readouterr().err


def test_cli_run_graph_reports_redacted_graph_intake_errors(tmp_path: Path, capsys):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        json.dumps(
            {
                "nodes": [{"id": "safe", "role": "test", "objective": "echo safe"}],
                "edges": [["safe", "GEMINI_API_KEY=secret-token-value"]],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["run", "--graph", str(graph_file)])

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert stderr.startswith("Graph intake error: unknown edge endpoint at edge[0]")
    assert "target=<redacted>" in stderr
    assert "GEMINI_API_KEY" not in stderr
    assert "secret-token-value" not in stderr


def test_cli_preflight_graph_summarizes_without_running_commands(tmp_path: Path, capsys):
    marker = tmp_path / "marker.txt"
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "a",
                        "role": "test",
                        "objective": "would write marker",
                        "command": [
                            sys.executable,
                            "-c",
                            (f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"),
                        ],
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["preflight", "--graph", str(graph_file)])

    assert exit_code == 0
    assert not marker.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "valid"
    assert payload["node_count"] == 1
    assert payload["command_node_ids"] == ["a"]


def test_cli_preflight_command_review_summarizes_without_running_commands(tmp_path: Path, capsys):
    marker = tmp_path / "marker.txt"
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "a",
                        "role": "test",
                        "objective": "would write marker",
                        "command": [
                            sys.executable,
                            "-c",
                            (f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"),
                        ],
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["preflight", "--graph", str(graph_file), "--command-review"])

    assert exit_code == 0
    assert not marker.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["commands_executed"] is False
    assert payload["command_review"]["a"]["argv_count"] == 3
    assert payload["command_review"]["a"]["argv_sha256"]


def test_cli_preflight_reports_redacted_invalid_graph_json(tmp_path: Path, capsys):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(
        json.dumps(
            {
                "nodes": [{"id": "safe", "role": "test", "objective": "echo safe"}],
                "edges": [["safe", "GEMINI_API_KEY=secret-token-value"]],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["preflight", "--graph", str(graph_file)])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "invalid"
    assert "target=<redacted>" in payload["error"]
    assert "GEMINI_API_KEY" not in payload["error"]
    assert "secret-token-value" not in payload["error"]


def test_cli_review_route_defaults_to_codex_for_reviewer_and_closer(capsys):
    exit_code = main(["review-route"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "review_route_resolved"
    assert payload["reviewer"]["adapter"] == "codex"
    assert payload["reviewer"]["auth"] == "cli-session"
    assert payload["reviewer"]["model"] == "gpt-5.5"
    assert payload["closer"]["adapter"] == "codex"
    assert payload["closer"]["auth"] == "cli-session"
    assert payload["commands_executed"] is False


def test_cli_review_route_accepts_codex_reviewer_and_codex_closer(capsys):
    exit_code = main(["review-route", "--reviewer", "codex", "--closer", "codex"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["reviewer"]["transport"] == "codex-cli"
    assert payload["reviewer"]["auth"] == "cli-session"
    assert payload["closer"]["transport"] == "codex-cli"
    assert payload["closer"]["auth"] == "cli-session"
    assert payload["reviewer"]["read_only"] is True
    assert payload["closer"]["read_only"] is True


def test_cli_review_route_rejects_unknown_adapter(capsys):
    exit_code = main(["review-route", "--reviewer", "openai-api"])

    assert exit_code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_cli_review_route_includes_telemetry_recommendation(tmp_path: Path, capsys):
    telemetry_file = tmp_path / "review.jsonl"
    telemetry_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "node_id": "a",
                        "role": "reviewer",
                        "source": "codex",
                        "verdict": "block",
                        "model": "gpt-5.5",
                        "reasoning_effort": "low",
                        "later_outcome": "failed",
                    }
                ),
                json.dumps(
                    {
                        "node_id": "b",
                        "role": "reviewer",
                        "source": "codex",
                        "verdict": "block",
                        "model": "gpt-5.5",
                        "reasoning_effort": "low",
                        "later_outcome": "failed",
                    }
                ),
                json.dumps(
                    {
                        "node_id": "c",
                        "role": "reviewer",
                        "source": "codex",
                        "verdict": "pass",
                        "model": "gpt-5.5",
                        "reasoning_effort": "low",
                        "later_outcome": "passed",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = main(["review-route", "--telemetry", str(telemetry_file)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["recommendation"]["backend"] == "codex-low"
    assert payload["recommendation"]["reason"] == "codex_precision_good"


def test_cli_inspect_reads_run_report_json(tmp_path: Path, capsys):
    report_file = tmp_path / "report.json"
    report_file.write_text(
        json.dumps(
            {
                "status": "succeeded",
                "states": {"a": "succeeded"},
                "blockers": [],
                "spent_tokens": 0,
                "spent_usd": 0.0,
                "results": {},
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["inspect", "--checkpoint", str(report_file)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "run_report"
    assert payload["status"] == "succeeded"
    assert payload["states"] == {"a": "succeeded"}


def test_cli_inspect_summarizes_report_evidence(tmp_path: Path, capsys):
    report_file = tmp_path / "report.json"
    report_file.write_text(
        json.dumps(
            {
                "status": "failed",
                "states": {
                    "setup": "succeeded",
                    "unit": "failed",
                    "integration": "skipped",
                },
                "blockers": [{"node_id": "integration", "reason": "upstream failed"}],
                "spent_tokens": 0,
                "spent_usd": 0.0,
                "concerns": ["unit failed"],
                "changed_files": ["src/example.py"],
                "results": {},
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["inspect", "--checkpoint", str(report_file)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {
        "total_nodes": 3,
        "status_counts": {"succeeded": 1, "failed": 1, "skipped": 1},
        "failed_nodes": ["unit"],
        "skipped_nodes": ["integration"],
        "blocker_count": 1,
        "concern_count": 1,
        "changed_files_count": 1,
    }


def test_cli_resume_loads_run_report_json(tmp_path: Path, capsys):
    report_file = tmp_path / "report.json"
    report_file.write_text(
        json.dumps(
            {
                "status": "failed",
                "states": {"a": "failed", "b": "skipped"},
                "blockers": [{"node_id": "b", "reason": "upstream failed"}],
                "spent_tokens": 0,
                "spent_usd": 0.0,
                "results": {},
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["resume", "--checkpoint", str(report_file)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "resume_loaded"
    assert payload["source_status"] == "failed"
    assert payload["states"] == {"a": "failed", "b": "skipped"}


def test_cli_resume_summarizes_report_evidence(tmp_path: Path, capsys):
    report_file = tmp_path / "report.json"
    report_file.write_text(
        json.dumps(
            {
                "status": "failed",
                "states": {
                    "setup": "succeeded",
                    "unit": "failed",
                    "integration": "skipped",
                },
                "blockers": [{"node_id": "integration", "reason": "upstream failed"}],
                "spent_tokens": 0,
                "spent_usd": 0.0,
                "concerns": ["unit failed"],
                "changed_files": ["src/example.py"],
                "results": {},
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["resume", "--checkpoint", str(report_file)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {
        "total_nodes": 3,
        "status_counts": {"succeeded": 1, "failed": 1, "skipped": 1},
        "failed_nodes": ["unit"],
        "skipped_nodes": ["integration"],
        "blocker_count": 1,
        "concern_count": 1,
        "changed_files_count": 1,
    }


def test_cli_failure_report_inspect_and_resume_do_not_rerun_completed_nodes(tmp_path: Path, capsys):
    counter_file = tmp_path / "counter.txt"
    graph_file = tmp_path / "graph.json"
    report_file = tmp_path / "report.json"
    graph_file.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "a",
                        "role": "test",
                        "objective": "increment once",
                        "command": [
                            sys.executable,
                            "-c",
                            (
                                "from pathlib import Path; "
                                f"p=Path({str(counter_file)!r}); "
                                "p.write_text(str(int(p.read_text() or '0') + 1)) "
                                "if p.exists() else p.write_text('1')"
                            ),
                        ],
                    },
                    {
                        "id": "b",
                        "role": "verify",
                        "objective": "fail",
                        "dependencies": ["a"],
                        "command": [sys.executable, "-c", "raise SystemExit(2)"],
                    },
                    {
                        "id": "c",
                        "role": "verify",
                        "objective": "skipped",
                        "dependencies": ["b"],
                        "command": [sys.executable, "-c", "print('should-not-run')"],
                    },
                ],
                "edges": [["a", "b"], ["b", "c"]],
            }
        ),
        encoding="utf-8",
    )

    run_exit = main(
        [
            "run",
            "--graph",
            str(graph_file),
            "--allow-local-commands",
            "--report",
            str(report_file),
        ]
    )

    assert run_exit == 1
    run_payload = json.loads(capsys.readouterr().out)
    assert run_payload["states"] == {"a": "succeeded", "b": "failed", "c": "skipped"}
    assert report_file.exists()
    assert counter_file.read_text(encoding="utf-8") == "1"

    inspect_exit = main(["inspect", "--checkpoint", str(report_file)])
    assert inspect_exit == 0
    inspect_payload = json.loads(capsys.readouterr().out)
    assert inspect_payload["kind"] == "run_report"
    assert inspect_payload["states"]["c"] == "skipped"

    resume_exit = main(["resume", "--checkpoint", str(report_file)])
    assert resume_exit == 0
    resume_payload = json.loads(capsys.readouterr().out)
    assert resume_payload["status"] == "resume_loaded"
    assert resume_payload["states"]["a"] == "succeeded"
    assert counter_file.read_text(encoding="utf-8") == "1"


def test_cli_routing_maps_to_report_json_on_disk(tmp_path: Path, capsys, monkeypatch):
    def fake_run_subprocess(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        schema_path = Path(cmd[cmd.index("--output-schema") + 1])
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        role_fields = (
            {
                "accepted": True,
                "verification_evidence": ["fake verification evidence"],
                "unresolved_obligations": [],
                "release_ready": True,
            }
            if "accepted" in schema["properties"]
            else {"findings": []}
        )
        output_path.write_text(
            json.dumps(
                {
                    "summary": "Fake Codex review passed.",
                    "verdict": "pass",
                    "confidence": 1.0,
                    "concerns": [],
                    "blockers": [],
                    **role_fields,
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="tokens used\n0\n", stderr="")

    from agy_swarms.adapters.codex import CodexAdapter

    monkeypatch.setattr(CodexAdapter, "_run_subprocess", fake_run_subprocess)

    graph_file = tmp_path / "routing-graph.json"
    report_file = tmp_path / "routing-report.json"

    graph_file.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "rev",
                        "role": "reviewer",
                        "objective": "check changes",
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run",
            "--graph",
            str(graph_file),
            "--reviewer",
            "codex",
            "--report",
            str(report_file),
        ]
    )

    assert exit_code == 0
    assert report_file.exists()

    report_content = json.loads(report_file.read_text(encoding="utf-8"))
    assert report_content["status"] == "succeeded"
    assert "rev" in report_content["results"]
    assert report_content["results"]["rev"]["status"] == "succeeded"

    # Assert that custom routing information maps correctly to JSON on disk
    artifact = report_content["results"]["rev"]["artifact"]
    assert "route" in artifact
    assert artifact["route"]["adapter"] == "codex"
    assert artifact["route"]["transport"] == "codex-cli"
    assert artifact["route"]["auth"] == "cli-session"


def test_cli_run_writes_codex_review_telemetry(tmp_path: Path, monkeypatch):
    def fake_run_subprocess(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "summary": "Fake Codex review passed.",
                    "verdict": "pass",
                    "confidence": 1.0,
                    "concerns": [],
                    "blockers": [],
                    "findings": [],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="tokens used\n444\n", stderr="")

    from agy_swarms.adapters.codex import CodexAdapter

    monkeypatch.setattr(CodexAdapter, "_run_subprocess", fake_run_subprocess)

    graph_file = tmp_path / "routing-graph.json"
    telemetry_file = tmp_path / "review-telemetry.jsonl"
    graph_file.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "rev",
                        "role": "reviewer",
                        "objective": "check changes",
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run",
            "--graph",
            str(graph_file),
            "--reviewer",
            "codex",
            "--review-telemetry",
            str(telemetry_file),
        ]
    )

    assert exit_code == 0
    record = json.loads(telemetry_file.read_text(encoding="utf-8"))
    assert record["node_id"] == "rev"
    assert record["source"] == "codex"
    assert record["verdict"] == "pass"
    assert record["token_output"] == 444


def test_cli_review_benchmark_writes_report(tmp_path: Path, monkeypatch, capsys):
    def fake_run_subprocess(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "summary": "Fake Codex review passed.",
                    "verdict": "pass",
                    "confidence": 1.0,
                    "concerns": [],
                    "blockers": [],
                    "findings": [],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="tokens used\n222\n", stderr="")

    from agy_swarms.adapters.codex import CodexAdapter

    monkeypatch.setattr(CodexAdapter, "_run_subprocess", fake_run_subprocess)

    cases_file = tmp_path / "cases.json"
    report_file = tmp_path / "benchmark-report.json"
    cases_file.write_text(
        json.dumps(
            [
                {
                    "id": "clean_case",
                    "role": "reviewer",
                    "objective": "clean_case",
                    "expected_verdict": "pass",
                    "expected_labels": ["clean"],
                }
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "review-benchmark",
            "--cases",
            str(cases_file),
            "--backends",
            "codex-low",
            "--output",
            str(report_file),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    report_payload = json.loads(report_file.read_text(encoding="utf-8"))
    assert stdout_payload["status"] == "completed"
    assert report_payload["aggregate"]["codex-low"]["accuracy"] == 1.0
    assert report_payload["results"][0]["token_output"] == 222


def test_cli_preflight_mock_bundle_stdout(tmp_path: Path, capsys):
    graph_file = tmp_path / "graph.json"
    bundle_file = tmp_path / "bundle.json"

    graph_file.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "node_a",
                        "role": "worker",
                        "objective": "run mock worker",
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    bundle_file.write_text(
        json.dumps(
            {
                "node_a": {
                    "status": "succeeded",
                    "artifact": {"hello": "world"},
                    "token_usage": {"input": 42, "output": 24},
                    "cost_usd": 0.005,
                }
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["preflight", "--graph", str(graph_file), "--mock-bundle", str(bundle_file)])

    assert exit_code == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["status"] == "succeeded"
    assert "node_a" in report["results"]
    assert report["results"]["node_a"]["artifact"] == {"hello": "world"}
    assert report["spent_tokens"] == 24  # Conductor tracks output tokens


def test_cli_preflight_mock_bundle_output(tmp_path: Path, capsys):
    graph_file = tmp_path / "graph.json"
    bundle_file = tmp_path / "bundle.json"
    output_file = tmp_path / "report.json"

    graph_file.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "node_b",
                        "role": "worker",
                        "objective": "run another mock worker",
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    bundle_file.write_text(
        json.dumps(
            {
                "results": {
                    "node_b": {
                        "status": "failed",
                        "artifact": {"error": "crashed"},
                        "token_usage": {"input": 1, "output": 2},
                        "cost_usd": 0.001,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "preflight",
            "--graph",
            str(graph_file),
            "--mock-bundle",
            str(bundle_file),
            "--output",
            str(output_file),
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    res = json.loads(captured.out)
    assert res["status"] == "mock_report_written"
    assert res["output"] == str(output_file)

    assert output_file.exists()
    report = json.loads(output_file.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["results"]["node_b"]["status"] == "failed"
    assert report["results"]["node_b"]["artifact"] == {"error": "crashed"}
