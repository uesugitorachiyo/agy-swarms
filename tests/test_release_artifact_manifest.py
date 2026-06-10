from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.release_artifact_manifest import build_manifest, main, write_manifest


def test_build_manifest_returns_stable_sha256_lines_sorted_by_filename(tmp_path: Path):
    wheel = tmp_path / "agy_swarms-1.2.3-py3-none-any.whl"
    sdist = tmp_path / "agy_swarms-1.2.3.tar.gz"
    wheel.write_bytes(b"wheel bytes\n")
    sdist.write_bytes(b"sdist bytes\n")

    lines = build_manifest([wheel, sdist])

    assert lines == [
        f"{hashlib.sha256(wheel.read_bytes()).hexdigest()}  {wheel.name}",
        f"{hashlib.sha256(sdist.read_bytes()).hexdigest()}  {sdist.name}",
    ]


def test_write_manifest_writes_trailing_newline(tmp_path: Path):
    artifact = tmp_path / "agy_swarms-1.2.3.tar.gz"
    output = tmp_path / "SHA256SUMS.txt"
    artifact.write_bytes(b"sdist bytes\n")

    write_manifest([artifact], output)

    assert output.read_text(encoding="utf-8") == (
        f"{hashlib.sha256(artifact.read_bytes()).hexdigest()}  {artifact.name}\n"
    )


def test_release_artifact_manifest_cli_writes_default_dist_manifest(tmp_path: Path):
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "agy_swarms-1.2.3-py3-none-any.whl"
    sdist = dist / "agy_swarms-1.2.3.tar.gz"
    wheel.write_bytes(b"wheel bytes\n")
    sdist.write_bytes(b"sdist bytes\n")

    assert main([str(sdist), str(wheel), "--output", str(dist / "SHA256SUMS.txt")]) == 0

    manifest = (dist / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert f"{hashlib.sha256(wheel.read_bytes()).hexdigest()}  {wheel.name}" in manifest
    assert f"{hashlib.sha256(sdist.read_bytes()).hexdigest()}  {sdist.name}" in manifest
