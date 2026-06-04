from __future__ import annotations

import subprocess

from scripts.phase1_ac1_exit_probe import AC1_TEST_FILES, run_probe


def test_ac1_exit_probe_runs_the_phase1_exit_cluster():
    calls: list[list[str]] = []

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="100 passed in 0.72s\n",
            stderr="",
        )

    result = run_probe(command_runner=runner, write_output=False)

    assert result["gate"] == "AC-1"
    assert result["passed"] is True
    assert result["status"] == "PHASE-1 EXIT READY"
    assert result["command"] == ["uv", "run", "pytest", *AC1_TEST_FILES, "-q"]
    assert result["test_files"] == list(AC1_TEST_FILES)
    assert result["summary"] == "100 passed in <duration>"
    assert result["stdout"] == "100 passed in <duration>\n"
    assert calls == [result["command"]]


def test_ac1_exit_probe_blocks_on_test_failure():
    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="1 failed, 99 passed\n",
            stderr="",
        )

    result = run_probe(command_runner=runner, write_output=False)

    assert result["passed"] is False
    assert result["status"] == "BLOCKED"
    assert result["summary"] == "1 failed, 99 passed"


def test_ac1_exit_probe_normalizes_volatile_pytest_durations():
    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="................ [100%]\n100 passed in 0.14s\n",
            stderr="",
        )

    result = run_probe(command_runner=runner, write_output=False)

    assert result["summary"] == "100 passed in <duration>"
    assert result["stdout"] == "................ [100%]\n100 passed in <duration>\n"
