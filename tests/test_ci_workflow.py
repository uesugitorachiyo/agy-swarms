import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
DEPENDABOT_CONFIG = ROOT / ".github" / "dependabot.yml"
BRANCH_PROTECTION = ROOT / ".github" / "branch-protection.json"
BRANCH_PROTECTION_DOC = ROOT / "docs" / "branch-protection.md"
RELEASE_DOC = ROOT / "docs" / "release-verification.md"
DEPENDENCY_UPDATES_DOC = ROOT / "docs" / "dependency-updates.md"

REQUIRED_MAIN_STATUS_CHECKS = [
    "Fast Checks (ubuntu-latest)",
    "Fast Checks (macos-latest)",
    "Fast Checks (windows-2025-vs2026)",
    "Verify Package Install Modes",
    "Release Health",
]


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _release_workflow_text() -> str:
    return RELEASE_WORKFLOW.read_text(encoding="utf-8")


def _dependabot_text() -> str:
    return DEPENDABOT_CONFIG.read_text(encoding="utf-8")


def _branch_protection_policy() -> dict:
    return json.loads(BRANCH_PROTECTION.read_text(encoding="utf-8"))


def test_ci_workflow_runs_on_pull_requests_pushes_to_main_and_manual_dispatch():
    workflow = _workflow_text()

    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "branches:" in workflow
    assert "main" in workflow


def test_ci_workflow_runs_linux_macos_and_windows_matrix():
    workflow = _workflow_text()

    assert "matrix:" in workflow
    assert "ubuntu-latest" in workflow
    assert "macos-latest" in workflow
    assert "windows-2025-vs2026" in workflow
    assert "- windows-2025\n" not in workflow
    assert "windows-latest" not in workflow
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


def test_ci_workflow_cancels_superseded_pull_request_runs_only():
    workflow = _workflow_text()

    assert "concurrency:" in workflow
    assert (
        "group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"
        in workflow
    )
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in workflow


def test_ci_workflow_uses_distinct_uv_cache_suffixes_and_saves_only_on_main():
    workflow = _workflow_text()

    assert "cache-suffix: ci-fast-${{ matrix.os }}" in workflow
    assert "cache-suffix: ci-package-install" in workflow
    assert "cache-suffix: ci-release-health" in workflow
    assert workflow.count("save-cache: ${{ github.ref == 'refs/heads/main' }}") == 3


def test_main_branch_protection_requires_ci_status_checks():
    policy = _branch_protection_policy()
    main = policy["branches"]["main"]

    assert main["required_status_checks"]["strict"] is True
    assert main["required_status_checks"]["contexts"] == REQUIRED_MAIN_STATUS_CHECKS
    assert main["allow_force_pushes"] is False
    assert main["allow_deletions"] is False


def test_branch_protection_policy_matches_ci_workflow_job_names():
    workflow = _workflow_text()
    policy = _branch_protection_policy()
    required_checks = policy["branches"]["main"]["required_status_checks"]["contexts"]

    for check in required_checks:
        if check.startswith("Fast Checks ("):
            os_name = check.removeprefix("Fast Checks (").removesuffix(")")
            assert "name: Fast Checks (${{ matrix.os }})" in workflow
            assert f"- {os_name}" in workflow
        else:
            assert f"name: {check}" in workflow


def test_branch_protection_docs_record_required_merge_gate():
    policy = _branch_protection_policy()
    docs = BRANCH_PROTECTION_DOC.read_text(encoding="utf-8")

    assert ".github/branch-protection.json" in docs
    assert "Require branches to be up to date before merging" in docs
    assert "at least 1 approving review" in docs
    assert "block force pushes and branch deletion" in docs

    for check in policy["branches"]["main"]["required_status_checks"]["contexts"]:
        assert check in docs


def test_release_workflow_publishes_github_releases_from_version_tags():
    workflow = _release_workflow_text()

    assert "name: Release" in workflow
    assert "tags:" in workflow
    assert "- 'v*'" in workflow
    assert "workflow_dispatch:" in workflow
    assert "contents: write" in workflow
    assert "fetch-depth: 0" in workflow


def test_release_workflow_verifies_and_attaches_package_artifacts():
    workflow = _release_workflow_text()

    assert "uv sync --extra dev --extra gemini" in workflow
    assert "Verify Release Tag Matches Package Version" in workflow
    assert "scripts/verify_release_tag.py" in workflow
    assert "make verify" in workflow
    assert "uv build" in workflow
    assert "scripts/release_artifact_manifest.py" in workflow
    assert "dist/SHA256SUMS.txt" in workflow
    assert "dist/*.tar.gz" in workflow
    assert "dist/*.whl" in workflow
    assert "gh release create" in workflow
    assert "--generate-notes" in workflow
    assert "--verify-tag" in workflow


def test_release_workflow_self_checks_published_assets_after_publish():
    workflow = _release_workflow_text()

    publish_index = workflow.index("gh release create")
    verify_index = workflow.index("scripts/verify_release_assets.py")

    assert "Verify Published Release Assets" in workflow
    assert "GH_TOKEN: ${{ github.token }}" in workflow
    assert '--tag "$RELEASE_TAG"' in workflow
    assert "--repo uesugitorachiyo/agy-swarms" in workflow
    assert publish_index < verify_index


def test_release_workflow_serializes_publishing_by_tag_and_does_not_write_cache():
    workflow = _release_workflow_text()

    assert (
        "group: release-${{ github.event_name == 'workflow_dispatch' && inputs.tag || github.ref_name }}"
        in workflow
    )
    assert "cancel-in-progress: false" in workflow
    assert "cache-suffix: release" in workflow
    assert "save-cache: false" in workflow


def test_release_docs_explain_github_release_publishing():
    docs = RELEASE_DOC.read_text(encoding="utf-8")

    assert ".github/workflows/release.yml" in docs
    assert "GitHub Release" in docs
    assert "`v*`" in docs
    assert "dist/*.whl" in docs
    assert "dist/*.tar.gz" in docs
    assert "SHA256SUMS.txt" in docs
    assert "scripts/verify_release_assets.py" in docs
    assert "gh release download" in docs


def test_release_docs_explain_concurrency_and_cache_policy():
    docs = RELEASE_DOC.read_text(encoding="utf-8")

    assert "cancels superseded pull request runs" in docs
    assert "does not cancel `main` push runs" in docs
    assert "distinct `setup-uv` cache suffixes" in docs
    assert "release workflow serializes publishing per tag" in docs


def test_dependabot_config_updates_github_actions_and_uv_dependencies():
    config = _dependabot_text()

    assert "version: 2" in config
    assert 'package-ecosystem: "github-actions"' in config
    assert 'package-ecosystem: "uv"' in config
    assert config.count('directory: "/"') == 2
    assert config.count('interval: "weekly"') == 2
    assert config.count("open-pull-requests-limit: 5") == 2
    assert 'prefix: "deps"' in config
    assert "dependencies" in config
    assert "ci" in config
    assert "github-actions:" in config
    assert 'patterns: ["*"]' in config
    assert "python-dependencies:" in config


def test_dependabot_docs_explain_update_policy():
    docs = DEPENDENCY_UPDATES_DOC.read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert ".github/dependabot.yml" in docs
    assert "GitHub Actions" in docs
    assert "uv" in docs
    assert "weekly" in docs
    assert "make verify" in docs
    assert "docs/dependency-updates.md" in readme
