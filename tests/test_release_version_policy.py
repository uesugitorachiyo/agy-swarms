from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_CHECKLIST = ROOT / "docs" / "release-operator-checklist.md"


def test_changelog_records_frozen_ac0_ac6_and_v050_release():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_version = pyproject["project"]["version"]

    assert "v0.0.0-ac0-ac6" in changelog
    assert f"v{package_version}" in changelog
    assert "v0.5.3 - 2026-06-09" in changelog
    assert "verification disk preflight" in changelog
    assert "automatic pull-request and `main` push CI" in changelog
    assert "PR verification updater" in changelog
    assert "723 passed" in changelog
    assert "24/24 checks passed" in changelog
    assert "AC0-AC6" in changelog
    assert "v0.5.0 - 2026-06-01" in changelog
    assert "Local Runner Report Contracts" in changelog
    assert "scripts/v05_report_contract_probe.py" in changelog
    assert "v0.4.0 - 2026-06-01" in changelog
    assert "Local Runner Replay Fixtures" in changelog
    assert "v0.3 local runner hardening" in changelog
    assert "scripts/v04_fixture_replay_probe.py" in changelog
    assert "v0.2.0 - 2026-05-31" in changelog
    assert "v0.2 Local Runner MVP" in changelog
    assert "v0.1.0 - 2026-05-31" in changelog
    assert "v0.1 release engineering" in changelog
    assert "GitHub Actions billing" in changelog
    assert "manual-only" in changelog


def test_versioning_policy_records_050_release_gate():
    policy = (ROOT / "docs" / "versioning.md").read_text(encoding="utf-8")
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_version = pyproject["project"]["version"]

    assert "v0.0.0-ac0-ac6" in policy
    assert f"`{package_version}`" in policy
    assert f"`v{package_version}`" in policy
    assert "scripts/release_health.py" in policy
    assert "scripts/v02_local_runner_probe.py" in policy
    assert "scripts/v04_fixture_replay_probe.py" in policy
    assert "scripts/v05_report_contract_probe.py" in policy
    assert "fresh_clone_smoke.py" in policy
    assert "automatic pull requests" in policy
    assert "pushes to `main`" in policy
    assert "remote CI" in policy


def test_package_version_matches_v050_release():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == "0.5.3"


def test_lockfile_package_version_matches_pyproject():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lockfile = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))

    package = next(package for package in lockfile["package"] if package["name"] == "agy-swarms")
    assert package["version"] == pyproject["project"]["version"]


def test_release_docs_explain_cross_platform_verification():
    release_docs = (ROOT / "docs" / "release-verification.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "windows-2025" in release_docs
    assert "macos-latest" in release_docs
    assert "ubuntu-latest" in release_docs
    assert "workflow_dispatch" in release_docs
    assert "uv build" in release_docs
    assert "uv build" in readme


def test_release_operator_checklist_covers_end_to_end_release_flow():
    checklist = RELEASE_CHECKLIST.read_text(encoding="utf-8")

    assert "Release Operator Checklist" in checklist
    assert "pyproject.toml" in checklist
    assert "uv.lock" in checklist
    assert "CHANGELOG.md" in checklist
    assert "make verify" in checklist
    assert "gh pr checks" in checklist
    assert "git tag -a" in checklist
    assert "git push origin" in checklist
    assert "gh workflow run release.yml" in checklist
    assert "gh release view" in checklist
    assert "agy_swarms-<version>-py3-none-any.whl" in checklist
    assert "agy_swarms-<version>.tar.gz" in checklist


def test_release_policy_links_operator_checklist():
    policy = (ROOT / "docs" / "versioning.md").read_text(encoding="utf-8")
    release_docs = (ROOT / "docs" / "release-verification.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "docs/release-operator-checklist.md" in policy
    assert "docs/release-operator-checklist.md" in release_docs
    assert "docs/release-operator-checklist.md" in readme
