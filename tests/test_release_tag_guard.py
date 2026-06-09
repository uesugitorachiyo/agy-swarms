from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verify_release_tag import ReleaseTagMismatch, main, verify_release_tag


def test_verify_release_tag_accepts_matching_version_tag():
    assert verify_release_tag("v1.2.3", "1.2.3") == "v1.2.3"


def test_verify_release_tag_rejects_missing_v_prefix():
    with pytest.raises(ReleaseTagMismatch, match="expected release tag 'v1.2.3'"):
        verify_release_tag("1.2.3", "1.2.3")


def test_verify_release_tag_rejects_wrong_version():
    with pytest.raises(ReleaseTagMismatch, match="release tag 'v1.2.4'"):
        verify_release_tag("v1.2.4", "1.2.3")


def test_release_tag_guard_main_accepts_matching_pyproject(tmp_path, capsys):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "demo"\nversion = "1.2.3"\n',
        encoding="utf-8",
    )

    assert main(["--tag", "v1.2.3", "--pyproject", str(pyproject)]) == 0

    assert "matches pyproject.toml version 1.2.3" in capsys.readouterr().out


def test_release_tag_guard_main_rejects_mismatched_pyproject(tmp_path, capsys):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "demo"\nversion = "1.2.3"\n',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        main(["--tag", "v1.2.4", "--pyproject", str(pyproject)])

    assert exc.value.code == 1
    assert "expected release tag 'v1.2.3'" in capsys.readouterr().err


def test_release_workflow_uses_tested_release_tag_guard_script():
    workflow = Path(__file__).parents[1] / ".github" / "workflows" / "release.yml"
    text = workflow.read_text(encoding="utf-8")

    assert "scripts/verify_release_tag.py" in text
    assert 'uv run python scripts/verify_release_tag.py --tag "$RELEASE_TAG"' in text
