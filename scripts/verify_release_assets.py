from __future__ import annotations

import argparse
import hashlib
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath


class ReleaseAssetVerificationError(ValueError):
    pass


Runner = Callable[[list[str]], None]


def parse_manifest(text: str) -> dict[str, str]:
    """Parse SHA256SUMS.txt content into filename -> expected digest."""
    entries: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        digest, separator, filename = line.partition("  ")
        if separator == "" or not digest or not filename:
            raise ReleaseAssetVerificationError(f"invalid checksum manifest line: {line!r}")
        if filename != PurePosixPath(filename).name or filename != PureWindowsPath(filename).name:
            raise ReleaseAssetVerificationError(f"invalid release asset name: {filename}")
        if filename in entries:
            raise ReleaseAssetVerificationError(f"duplicate checksum entry: {filename}")
        entries[filename] = digest
    return entries


def verify_release_assets(directory: Path, *, manifest_name: str = "SHA256SUMS.txt") -> list[str]:
    """Verify every file named in a release checksum manifest."""
    manifest_path = directory / manifest_name
    if not manifest_path.is_file():
        raise ReleaseAssetVerificationError(f"missing checksum manifest: {manifest_path}")

    manifest = parse_manifest(manifest_path.read_text(encoding="utf-8"))
    if not manifest:
        raise ReleaseAssetVerificationError(f"empty checksum manifest: {manifest_path}")

    asset_names = {
        asset_path.name
        for asset_path in directory.iterdir()
        if asset_path.is_file() and asset_path.name != manifest_name
    }
    unexpected_assets = sorted(asset_names - manifest.keys())
    if unexpected_assets:
        raise ReleaseAssetVerificationError(
            "release assets not listed in checksum manifest: " + ", ".join(unexpected_assets)
        )

    verified: list[str] = []
    for filename, expected_digest in manifest.items():
        artifact_path = directory / filename
        if not artifact_path.is_file():
            raise ReleaseAssetVerificationError(f"missing release asset: {filename}")
        actual_digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if actual_digest != expected_digest:
            raise ReleaseAssetVerificationError(
                f"checksum mismatch for {filename}: expected {expected_digest}, got {actual_digest}"
            )
        verified.append(filename)
    return verified


def download_release_assets(
    tag: str,
    directory: Path,
    *,
    repository: str | None = None,
    runner: Runner | None = None,
) -> None:
    """Download all assets for one GitHub Release into a directory with gh."""
    directory.mkdir(parents=True, exist_ok=True)
    command = ["gh", "release", "download", tag]
    if repository is not None:
        command.extend(["--repo", repository])
    command.extend(["--dir", str(directory), "--clobber"])
    (runner or _run)(command)


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def _verify_downloaded_release(
    tag: str,
    *,
    repository: str | None,
    output_dir: Path | None,
) -> list[str]:
    if output_dir is not None:
        download_release_assets(tag, output_dir, repository=repository)
        return verify_release_assets(output_dir)

    with tempfile.TemporaryDirectory(prefix=f"agy-release-{tag}-") as tmp:
        directory = Path(tmp)
        download_release_assets(tag, directory, repository=repository)
        return verify_release_assets(directory)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download GitHub Release assets and verify SHA256SUMS.txt."
    )
    parser.add_argument("--tag", required=True, help="Release tag, such as v0.5.4.")
    parser.add_argument(
        "--repo",
        help="Repository in owner/name form. Defaults to the current gh repository context.",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        help="Directory for downloaded assets. Defaults to a temporary directory.",
    )
    args = parser.parse_args(argv)

    try:
        verified = _verify_downloaded_release(args.tag, repository=args.repo, output_dir=args.dir)
    except (ReleaseAssetVerificationError, subprocess.CalledProcessError) as exc:
        parser.exit(status=1, message=f"{exc}\n")

    print(f"Verified {len(verified)} release assets for {args.tag}:")
    for filename in verified:
        print(f"  {filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
