import json
import subprocess
from pathlib import Path

from agy_swarms.adapters.codex import CodexAdapter, resolve_codex_model_config
from agy_swarms.types import ErrorClass, NodeSpec


def test_codex_adapter_invokes_codex_exec_and_parses_review_json(tmp_path: Path):
    calls: list[list[str]] = []

    def fake_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "summary": "Review completed.",
                    "verdict": "pass",
                    "confidence": 0.82,
                    "concerns": ["minor naming concern"],
                    "blockers": [],
                    "findings": [],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="tokens used\n1,234\n", stderr="")

    node = NodeSpec(id="rev", role="reviewer", objective="Review the current patch.")
    envelope = CodexAdapter(runner=fake_runner, cwd=tmp_path).run(node, attempt=2)

    assert calls
    cmd = calls[0]
    assert cmd[:4] == ["codex", "-a", "never", "exec"]
    assert cmd[cmd.index("-m") + 1] == "gpt-5.5"
    assert 'model_reasoning_effort="high"' in cmd
    assert "--sandbox" in cmd
    assert cmd[cmd.index("--sandbox") + 1] == "read-only"
    assert "--ignore-user-config" in cmd
    assert "--ignore-rules" in cmd
    assert "--ephemeral" in cmd
    assert "--output-schema" in cmd

    assert envelope.status == "succeeded"
    assert envelope.adapter == "codex"
    assert envelope.model == "gpt-5.5"
    assert envelope.thinking_level == "high"
    assert envelope.artifact["route"]["adapter"] == "codex"
    assert envelope.artifact["review"]["verdict"] == "pass"
    assert envelope.concerns == ["minor naming concern"]
    assert envelope.blockers == []
    assert envelope.token_usage["output"] == 1234


def test_codex_adapter_maps_nonzero_exit_to_failed_transport(tmp_path: Path):
    def fake_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="network timeout")

    node = NodeSpec(id="rev", role="reviewer", objective="Review the current patch.")
    envelope = CodexAdapter(runner=fake_runner, cwd=tmp_path).run(node)

    assert envelope.status == "failed"
    assert envelope.error_class == ErrorClass.TIMEOUT
    assert "network timeout" in (envelope.stdout_ref or "")


def test_codex_reviewer_schema_requires_file_scoped_findings(tmp_path: Path):
    def fake_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        schema_path = Path(cmd[cmd.index("--output-schema") + 1])
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert "findings" in schema["properties"]
        finding_props = schema["properties"]["findings"]["items"]["properties"]
        assert {"file", "line", "severity", "message", "suggested_action"} <= set(finding_props)
        prompt = cmd[-1]
        assert "Find concrete bugs, regressions, missing tests, and behavioral risks." in prompt

        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "summary": "Review found one issue.",
                    "verdict": "concerns",
                    "confidence": 0.75,
                    "concerns": ["missing test coverage"],
                    "blockers": [],
                    "findings": [
                        {
                            "file": "tests/example.py",
                            "line": 12,
                            "severity": "medium",
                            "message": "Missing regression test.",
                            "suggested_action": "Add a focused test.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    node = NodeSpec(id="rev", role="reviewer", objective="Review the patch.")
    envelope = CodexAdapter(runner=fake_runner, cwd=tmp_path).run(node)

    assert envelope.status == "succeeded"
    assert envelope.artifact["review"]["findings"][0]["file"] == "tests/example.py"
    assert envelope.concerns == ["missing test coverage"]


def test_codex_review_prompt_uses_compact_context_without_command_contents(tmp_path: Path):
    def fake_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        prompt = cmd[-1]
        assert "review_context" in prompt
        assert '"command_present": true' in prompt
        assert "secret-token-value" not in prompt
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "summary": "Review completed.",
                    "verdict": "pass",
                    "confidence": 0.82,
                    "concerns": [],
                    "blockers": [],
                    "findings": [],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    node = NodeSpec(
        id="rev",
        role="reviewer",
        objective="Review command safety.",
        command=["python", "-c", "print('secret-token-value')"],
    )

    envelope = CodexAdapter(runner=fake_runner, cwd=tmp_path).run(node)

    assert envelope.status == "succeeded"


def test_codex_closer_schema_requires_verification_evidence(tmp_path: Path):
    def fake_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        schema_path = Path(cmd[cmd.index("--output-schema") + 1])
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert "accepted" in schema["properties"]
        assert "verification_evidence" in schema["properties"]
        prompt = cmd[-1]
        assert "Do not accept unless verification evidence supports closure." in prompt

        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "summary": "Closure criteria satisfied.",
                    "verdict": "pass",
                    "confidence": 0.9,
                    "concerns": [],
                    "blockers": [],
                    "accepted": True,
                    "verification_evidence": ["pytest passed"],
                    "unresolved_obligations": [],
                    "release_ready": True,
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    node = NodeSpec(id="cls", role="closer", objective="Close the task.")
    envelope = CodexAdapter(runner=fake_runner, cwd=tmp_path).run(node)

    assert envelope.status == "succeeded"
    assert envelope.artifact["review"]["accepted"] is True
    assert envelope.artifact["review"]["verification_evidence"] == ["pytest passed"]


def test_resolve_codex_model_config_defaults_reviewer_to_gpt_5_5_high():
    config = resolve_codex_model_config("reviewer", env={})

    assert config.model == "gpt-5.5"
    assert config.reasoning_effort == "high"


def test_resolve_codex_model_config_defaults_worker_to_spark_medium():
    config = resolve_codex_model_config("worker", env={})

    assert config.model == "gpt-5.3-codex-spark"
    assert config.reasoning_effort == "medium"


def test_resolve_codex_model_config_uses_high_effort_for_escalation():
    config = resolve_codex_model_config("closer", escalated=True, env={})

    assert config.model == "gpt-5.5"
    assert config.reasoning_effort == "high"


def test_codex_adapter_uses_role_specific_env_override(tmp_path: Path):
    calls: list[list[str]] = []

    def fake_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "summary": "Closure criteria satisfied.",
                    "verdict": "pass",
                    "confidence": 0.9,
                    "concerns": [],
                    "blockers": [],
                    "accepted": True,
                    "verification_evidence": ["pytest passed"],
                    "unresolved_obligations": [],
                    "release_ready": True,
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    node = NodeSpec(id="cls", role="closer", objective="Close the task.")
    envelope = CodexAdapter(
        runner=fake_runner,
        cwd=tmp_path,
        env={
            "AGY_CODEX_CLOSER_MODEL": "gpt-5.4-mini",
            "AGY_CODEX_CLOSER_REASONING_EFFORT": "medium",
        },
    ).run(node)

    assert calls[0][calls[0].index("-m") + 1] == "gpt-5.4-mini"
    assert 'model_reasoning_effort="medium"' in calls[0]
    assert envelope.model == "gpt-5.4-mini"
    assert envelope.thinking_level == "medium"


def test_codex_adapter_batches_review_nodes_in_one_exec(tmp_path: Path):
    calls: list[list[str]] = []

    def fake_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        schema_path = Path(cmd[cmd.index("--output-schema") + 1])
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert "nodes" in schema["properties"]
        assert "Return one review per node id" in cmd[-1]

        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "nodes": {
                        "rev": {
                            "summary": "Reviewer found a concern.",
                            "verdict": "concerns",
                            "confidence": 0.7,
                            "concerns": ["missing edge-case test"],
                            "blockers": [],
                            "findings": [
                                {
                                    "file": "tests/example.py",
                                    "line": 7,
                                    "severity": "medium",
                                    "message": "Missing edge-case coverage.",
                                    "suggested_action": "Add the regression test.",
                                }
                            ],
                        },
                        "cls": {
                            "summary": "Closer blocked release.",
                            "verdict": "block",
                            "confidence": 0.95,
                            "concerns": [],
                            "blockers": [
                                {
                                    "reason": "missing_verification",
                                    "detail": "No passing test evidence.",
                                }
                            ],
                            "accepted": False,
                            "verification_evidence": [],
                            "unresolved_obligations": ["run tests"],
                            "release_ready": False,
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="tokens used\n2,000\n", stderr="")

    nodes = [
        NodeSpec(id="rev", role="reviewer", objective="Review the patch."),
        NodeSpec(id="cls", role="closer", objective="Close the task."),
    ]
    envelopes = CodexAdapter(runner=fake_runner, cwd=tmp_path).run_batch(nodes)

    assert len(calls) == 1
    assert [envelope.node_id for envelope in envelopes] == ["rev", "cls"]
    assert envelopes[0].status == "succeeded"
    assert envelopes[0].concerns == ["missing edge-case test"]
    assert envelopes[1].status == "failed"
    assert envelopes[1].blockers == [
        {"reason": "missing_verification", "detail": "No passing test evidence."}
    ]


def test_codex_adapter_optionally_records_review_telemetry(tmp_path: Path):
    ledger = tmp_path / "telemetry.jsonl"

    def fake_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "summary": "Review blocked.",
                    "verdict": "block",
                    "confidence": 0.9,
                    "concerns": ["bug risk"],
                    "blockers": [{"reason": "bug", "detail": "Needs a fix."}],
                    "findings": [],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="tokens used\n333\n", stderr="")

    node = NodeSpec(id="rev", role="reviewer", objective="Review the patch.")
    CodexAdapter(runner=fake_runner, cwd=tmp_path, telemetry_path=ledger).run(node)

    record = json.loads(ledger.read_text(encoding="utf-8"))
    assert record["node_id"] == "rev"
    assert record["source"] == "codex"
    assert record["verdict"] == "block"
    assert record["token_output"] == 333
    assert record["concern_count"] == 1
    assert record["blocker_count"] == 1
