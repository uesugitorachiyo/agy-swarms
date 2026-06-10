from pathlib import Path

import pytest

from scripts.verify_release_assets import (
    ReleaseAssetVerificationError,
    download_release_assets,
    parse_manifest,
    verify_release_assets,
)


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_parse_manifest_ignores_blank_lines_and_preserves_manifest_filenames():
    manifest = "\nabc123  agy_swarms-0.5.4.tar.gz\n\nff00aa  agy_swarms-0.5.4.whl\n"

    assert parse_manifest(manifest) == {
        "agy_swarms-0.5.4.tar.gz": "abc123",
        "agy_swarms-0.5.4.whl": "ff00aa",
    }


def test_parse_manifest_rejects_duplicate_asset_names():
    manifest = "\n".join(
        [
            f"{'0' * 64}  agy_swarms-0.5.4.tar.gz",
            f"{'1' * 64}  agy_swarms-0.5.4.tar.gz",
        ]
    )

    with pytest.raises(ReleaseAssetVerificationError, match="duplicate checksum entry"):
        parse_manifest(manifest)


@pytest.mark.parametrize(
    "filename",
    [
        "../agy_swarms-0.5.4.tar.gz",
        "/tmp/agy_swarms-0.5.4.tar.gz",
        "nested/agy_swarms-0.5.4.tar.gz",
        r"nested\agy_swarms-0.5.4.tar.gz",
    ],
)
def test_parse_manifest_rejects_asset_paths(filename: str):
    manifest = f"{'0' * 64}  {filename}\n"

    with pytest.raises(ReleaseAssetVerificationError, match="invalid release asset name"):
        parse_manifest(manifest)


def test_verify_release_assets_validates_manifested_files(tmp_path: Path):
    sdist = tmp_path / "agy_swarms-0.5.4.tar.gz"
    wheel = tmp_path / "agy_swarms-0.5.4-py3-none-any.whl"
    sdist.write_bytes(b"sdist")
    wheel.write_bytes(b"wheel")
    (tmp_path / "SHA256SUMS.txt").write_text(
        f"{_sha256(sdist)}  {sdist.name}\n{_sha256(wheel)}  {wheel.name}\n",
        encoding="utf-8",
    )

    verified = verify_release_assets(tmp_path)

    assert verified == [sdist.name, wheel.name]


def test_verify_release_assets_rejects_digest_mismatch(tmp_path: Path):
    artifact = tmp_path / "agy_swarms-0.5.4.tar.gz"
    artifact.write_bytes(b"actual")
    (tmp_path / "SHA256SUMS.txt").write_text(
        f"{'0' * 64}  {artifact.name}\n",
        encoding="utf-8",
    )

    with pytest.raises(ReleaseAssetVerificationError, match="checksum mismatch"):
        verify_release_assets(tmp_path)


def test_verify_release_assets_rejects_assets_missing_from_manifest(tmp_path: Path):
    artifact = tmp_path / "agy_swarms-0.5.4.tar.gz"
    extra = tmp_path / "agy_swarms-0.5.4-py3-none-any.whl"
    artifact.write_bytes(b"sdist")
    extra.write_bytes(b"wheel")
    (tmp_path / "SHA256SUMS.txt").write_text(
        f"{_sha256(artifact)}  {artifact.name}\n",
        encoding="utf-8",
    )

    with pytest.raises(ReleaseAssetVerificationError, match="not listed in checksum manifest"):
        verify_release_assets(tmp_path)


def test_download_release_assets_invokes_gh_release_download(tmp_path: Path):
    calls: list[list[str]] = []

    def runner(command: list[str]) -> None:
        calls.append(command)

    download_release_assets("v0.5.4", tmp_path, repository="owner/repo", runner=runner)

    assert calls == [
        [
            "gh",
            "release",
            "download",
            "v0.5.4",
            "--repo",
            "owner/repo",
            "--dir",
            str(tmp_path),
            "--clobber",
        ]
    ]
