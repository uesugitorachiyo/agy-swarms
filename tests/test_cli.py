from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from agy_swarms.main import main


def test_cli_plan_validates_and_emits_preview(tmp_path: Path, capsys):
    task_file = tmp_path / "task.json"
    task_file.write_text(
        json.dumps({"task": "Build the antigravity engine", "model_pins": {"default": "flash-A"}})
    )

    exit_code = main(["plan", "--task", str(task_file)])
    assert exit_code == 0

    stdout = capsys.readouterr().out
    preview = json.loads(stdout)
    assert "antigravity" in preview["task"]
    assert preview["model_pins"] == {"default": "flash-A"}
    assert len(preview["nodes"]) == 2
    assert preview["edges"] == [["worker_0", "worker_1"]]


def test_cli_run_executes_task_successfully(tmp_path: Path, capsys):
    task_file = tmp_path / "task.json"
    task_file.write_text(
        json.dumps({"task": "Test reference task", "model_pins": {"default": "flash-A"}})
    )

    exit_code = main(["run", "--task", str(task_file), "--adapter", "scripted"])
    assert exit_code == 0

    stdout = capsys.readouterr().out
    report = json.loads(stdout)
    assert report["status"] == "succeeded"
    assert report["spent_tokens"] > 0
    assert report["states"]["worker_0"] == "succeeded"
    assert report["states"]["worker_1"] == "succeeded"


def test_cli_resume_delegates_to_library(tmp_path: Path, capsys):
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()

    exit_code = main(["resume", "--checkpoint", str(checkpoint_dir)])
    assert exit_code == 0

    stdout = capsys.readouterr().out
    result = json.loads(stdout)
    assert result["status"] == "resumed"
    assert result["checkpoint"] == str(checkpoint_dir)


@patch("agy_swarms.main.Conductor")
def test_cli_proves_thinness_by_monkeypatching(mock_conductor, tmp_path: Path):
    # Proves the CLI is a thin wrapper by verifying it imports and invokes the library Conductor
    mock_inst = MagicMock()
    mock_inst.run.return_value.status.value = "succeeded"
    mock_inst.run.return_value.spent_tokens = 42
    mock_inst.run.return_value.spent_usd = 0.01
    mock_inst.run.return_value.states = {}
    mock_conductor.return_value = mock_inst

    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps({"task": "mocked task"}))

    exit_code = main(["run", "--task", str(task_file)])
    assert exit_code == 0
    assert mock_conductor.called


@patch("agy_swarms.main.Conductor")
def test_cli_run_dry_run_forces_codex_reviewers(mock_conductor, tmp_path: Path):
    mock_inst = MagicMock()
    mock_inst.run.return_value.status.value = "succeeded"
    mock_inst.run.return_value.spent_tokens = 0
    mock_inst.run.return_value.spent_usd = 0.0
    mock_inst.run.return_value.states = {}
    mock_conductor.return_value = mock_inst

    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps({"task": "mocked task"}))

    exit_code = main(["run", "--task", str(task_file), "--dry-run"])
    assert exit_code == 0
    assert mock_conductor.called
    kwargs = mock_conductor.call_args[1]
    assert kwargs["reviewer"] == "codex"
    assert kwargs["closer"] == "codex"


@patch("agy_swarms.main.run_local_graph")
@patch("agy_swarms.main.load_graph")
def test_cli_run_dry_run_forces_codex_with_graph(
    mock_load_graph, mock_run_local_graph, tmp_path: Path
):
    mock_run_local_graph.return_value = {"status": "succeeded"}
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(json.dumps({"nodes": [], "edges": []}))

    exit_code = main(["run", "--graph", str(graph_file), "--dry-run"])
    assert exit_code == 0
    assert mock_run_local_graph.called
    kwargs = mock_run_local_graph.call_args[1]
    assert kwargs["reviewer"] == "codex"
    assert kwargs["closer"] == "codex"


@patch("subprocess.run")
def test_cli_pre_commit_install_success(mock_run):
    mock_res = MagicMock()
    mock_res.stdout = "pre-commit installed at .git/hooks/pre-commit"
    mock_run.return_value = mock_res

    exit_code = main(["pre-commit-install"])
    assert exit_code == 0
    assert mock_run.called
    args = mock_run.call_args[0][0]
    assert "pre_commit" in args
    assert "install" in args


@patch("subprocess.run")
def test_cli_pre_commit_install_failure(mock_run):
    import subprocess

    mock_run.side_effect = subprocess.CalledProcessError(
        1, cmd="pre_commit install", stderr="failed to write"
    )

    exit_code = main(["pre-commit-install"])
    assert exit_code == 1
