from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pre_commit_pytest_uses_project_python_module_invocation():
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert "entry: uv run python -m pytest -q" in config
    assert "entry: uv run pytest -q" not in config


def test_readme_documents_project_python_module_pytest_invocation():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "uv run python -m pytest -q" in readme
    assert "uv run pytest -q" not in readme


def test_readme_installs_gemini_extra_for_full_test_suite():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "uv sync --extra dev --extra gemini" in readme


def test_release_docs_install_gemini_extra_for_full_test_suite():
    docs = (ROOT / "docs" / "release-verification.md").read_text(encoding="utf-8")

    assert "uv sync --extra dev --extra gemini" in docs


def test_architecture_doc_describes_command_conductor_and_helper_boundaries():
    docs = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")

    for expected_path in (
        "agy_swarms/cli.py",
        "agy_swarms/commands/",
        "agy_swarms/conductor.py",
        "agy_swarms/conductor_budget.py",
        "agy_swarms/conductor_checkpointing.py",
        "agy_swarms/conductor_fallback.py",
        "agy_swarms/conductor_pipeline.py",
        "agy_swarms/conductor_drift.py",
        "scripts/release_health.py",
        "scripts/release_health_registry.py",
    ):
        assert expected_path in docs


def test_conductor_helper_contracts_live_in_focused_test_module():
    helper_tests = (ROOT / "tests" / "test_conductor_helpers.py").read_text(encoding="utf-8")
    conductor_tests = (ROOT / "tests" / "test_conductor.py").read_text(encoding="utf-8")

    for expected_name in (
        "test_conductor_budget_helpers_are_importable",
        "test_checkpointing_helper_is_importable",
        "test_pipeline_helper_is_importable",
        "test_drift_helper_is_importable",
    ):
        assert expected_name in helper_tests
    assert "_helper_is_importable" not in conductor_tests


def test_conductor_behavior_tests_use_shared_support_helpers():
    support = ROOT / "tests" / "conductor_support.py"
    assert support.exists()
    support_text = support.read_text(encoding="utf-8")

    for expected_name in (
        "LIMIT",
        "def epoch",
        "def envelope",
        "def fanout_graph",
        "def scripted_fanout_adapter",
        "class CountingAdapter",
        "class FakeAdapter",
        "def single_graph",
    ):
        assert expected_name in support_text

    for test_file in (
        "test_conductor.py",
        "test_ac1_integration.py",
        "test_conductor_reducers.py",
        "test_conductor_test_node.py",
    ):
        text = (ROOT / "tests" / test_file).read_text(encoding="utf-8")
        assert "from tests.conductor_support import" in text
        assert "class FakeAdapter" not in text
        assert "def _epoch" not in text


def test_makefile_exposes_verification_targets():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    for target in (
        "sync:",
        "lint:",
        "format-check:",
        "test:",
        "build:",
        "release-health:",
        "verify-fast:",
        "verify:",
        "pr-verification:",
    ):
        assert target in makefile
    assert "uv sync --extra dev --extra gemini" in makefile
    assert "uv run python -m pytest -q" in makefile
    assert "uv run python scripts/release_health.py" in makefile
    assert "uv run python scripts/pr_verification.py" in makefile
    assert "verify-fast: lint format-check type-check verify-docs test build" in makefile
    assert "verify: verify-fast release-health" in makefile


def test_makefile_exposes_typecheck_target():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "type-check:" in makefile
    assert "uv run mypy" in makefile


def test_makefile_typecheck_covers_full_package_and_release_health_modules():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    for checked_path in (
        "agy_swarms",
        "scripts/release_health.py",
        "scripts/release_health_registry.py",
        "scripts/release_health_docs.py",
        "scripts/rewrite_release_health_docs.py",
    ):
        assert checked_path in makefile
    assert "--explicit-package-bases" in makefile


def test_makefile_exposes_verify_docs_target():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "verify-docs:" in makefile
    assert "uv run python scripts/rewrite_release_health_docs.py" in makefile
    assert "git diff --exit-code docs/release-verification.md" in makefile


def test_pyproject_declares_mypy_dev_dependency():
    import tomllib

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert any(
        dependency.startswith("mypy")
        for dependency in pyproject["project"]["optional-dependencies"]["dev"]
    )
