from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_ci_workflow_is_manual_only_while_billing_is_postponed():
    workflow = _workflow_text()

    assert "workflow_dispatch:" in workflow
    assert "push:" not in workflow
    assert "pull_request:" not in workflow


def test_ci_workflow_runs_linux_macos_and_windows_matrix():
    workflow = _workflow_text()

    assert "matrix:" in workflow
    assert "ubuntu-latest" in workflow
    assert "macos-latest" in workflow
    assert "windows-latest" in workflow
    assert "runs-on: ${{ matrix.os }}" in workflow


def test_ci_workflow_verifies_lint_tests_and_package_build():
    workflow = _workflow_text()

    assert "uv run ruff check ." in workflow
    assert "uv run pytest -q" in workflow
    assert "uv build" in workflow
    assert "PYTHONIOENCODING: utf-8" in workflow
