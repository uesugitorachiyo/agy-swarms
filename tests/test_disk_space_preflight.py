from __future__ import annotations

import shutil
from pathlib import Path

from scripts import disk_space_preflight


def _usage(*, free_mib: int) -> shutil._ntuple_diskusage:
    free = free_mib * 1024 * 1024
    total = 16 * 1024 * 1024 * 1024
    used = total - free
    return shutil._ntuple_diskusage(total, used, free)


def test_run_preflight_fails_when_any_path_is_below_threshold(tmp_path: Path, monkeypatch):
    calls: list[str] = []

    def fake_disk_usage(path: str) -> shutil._ntuple_diskusage:
        calls.append(path)
        return _usage(free_mib=512)

    monkeypatch.setattr(disk_space_preflight.shutil, "disk_usage", fake_disk_usage)

    result = disk_space_preflight.run_preflight([tmp_path], min_free_mib=1024)

    assert result.ok is False
    assert result.checks[0].free_mib == 512
    assert result.checks[0].required_mib == 1024
    assert calls == [str(tmp_path.resolve())]


def test_run_preflight_checks_duplicate_paths_once(tmp_path: Path, monkeypatch):
    calls: list[str] = []

    def fake_disk_usage(path: str) -> shutil._ntuple_diskusage:
        calls.append(path)
        return _usage(free_mib=2048)

    monkeypatch.setattr(disk_space_preflight.shutil, "disk_usage", fake_disk_usage)

    result = disk_space_preflight.run_preflight([tmp_path, tmp_path.resolve()], min_free_mib=1024)

    assert result.ok is True
    assert len(result.checks) == 1
    assert calls == [str(tmp_path.resolve())]


def test_collect_paths_includes_repo_root_and_temp_dir(tmp_path: Path):
    repo_root = tmp_path / "repo"
    temp_dir = tmp_path / "tmp"
    repo_root.mkdir()
    temp_dir.mkdir()

    paths = disk_space_preflight.collect_paths(repo_root, temp_dir)

    assert paths == [repo_root.resolve(), temp_dir.resolve()]


def test_collect_paths_deduplicates_when_temp_dir_is_repo_root(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    paths = disk_space_preflight.collect_paths(repo_root, repo_root)

    assert paths == [repo_root.resolve()]


def test_cli_uses_environment_threshold_and_explains_tmpdir_override(
    tmp_path: Path, monkeypatch, capsys
):
    def fake_disk_usage(path: str) -> shutil._ntuple_diskusage:
        return _usage(free_mib=1536)

    monkeypatch.setattr(disk_space_preflight.shutil, "disk_usage", fake_disk_usage)
    monkeypatch.setenv("AGY_VERIFY_MIN_FREE_MIB", "2048")

    exit_code = disk_space_preflight.main(["--path", str(tmp_path), "--label", "workspace"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "workspace" in output
    assert "1536 MiB free" in output
    assert "2048 MiB required" in output
    assert "AGY_VERIFY_MIN_FREE_MIB" in output
    assert "TMPDIR" in output


def test_cli_accepts_multiple_labeled_paths(tmp_path: Path, monkeypatch, capsys):
    seen: list[str] = []

    def fake_disk_usage(path: str) -> shutil._ntuple_diskusage:
        seen.append(path)
        return _usage(free_mib=4096)

    workspace = tmp_path / "workspace"
    temp_dir = tmp_path / "temp"
    workspace.mkdir()
    temp_dir.mkdir()
    monkeypatch.setattr(disk_space_preflight.shutil, "disk_usage", fake_disk_usage)

    exit_code = disk_space_preflight.main(
        [
            "--min-free-mib",
            "1024",
            "--path",
            str(workspace),
            "--label",
            "workspace",
            "--path",
            str(temp_dir),
            "--label",
            "temp",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "workspace" in output
    assert "temp" in output
    assert "4096 MiB free" in output
    assert seen == [str(workspace.resolve()), str(temp_dir.resolve())]


def test_default_threshold_is_one_gib():
    assert disk_space_preflight.DEFAULT_MIN_FREE_MIB == 1024
