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

    assert "uv sync --extra dev --extra gemini" in workflow
    assert "uv sync --extra dev\n" not in workflow
    assert "uv run pytest -q" not in workflow
    assert "PYTHONIOENCODING: utf-8" in workflow
    assert "fast-checks:" in workflow
    assert "Run Fast Verification" in workflow
    assert "make verify-fast" in workflow


def test_ci_workflow_verifies_package_install_modes():
    workflow = _workflow_text()

    assert "package-install-modes:" in workflow
    assert "uv pip install --python .venv-core/bin/python ." in workflow
    assert "uv pip install --python .venv-gemini/bin/python '.[gemini]'" in workflow
    assert "from agy_swarms.adapters.scripted import ScriptedAdapter" in workflow
    assert "from agy_swarms.adapters.gemini_api import GeminiApiAdapter" in workflow


def test_ci_workflow_checks_release_docs_probe_drift():
    workflow = _workflow_text()

    assert "make verify-fast" in workflow
    assert "make release-health" in workflow


def test_ci_workflow_runs_make_verify_facade():
    workflow = _workflow_text()

    assert "release-health:" in workflow
    assert "needs: fast-checks" in workflow
    assert "Run Release Health" in workflow
    assert "make release-health" in workflow


def test_ci_workflow_caches_uv_from_lockfile():
    workflow = _workflow_text()

    assert "enable-cache: true" in workflow
    assert "cache-dependency-glob: uv.lock" in workflow
