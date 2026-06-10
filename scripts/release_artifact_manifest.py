from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def build_manifest(artifacts: list[Path]) -> list[str]:
    """Return stable SHA-256 manifest lines for release artifact paths."""
    lines: list[str] = []
    for artifact in sorted(artifacts, key=lambda path: path.name):
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        lines.append(f"{digest}  {artifact.name}")
    return lines


def write_manifest(artifacts: list[Path], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(build_manifest(artifacts)) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write a SHA-256 checksum manifest for release artifacts."
    )
    parser.add_argument(
        "artifacts",
        nargs="+",
        type=Path,
        help="Release artifact files to include in the manifest.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist") / "SHA256SUMS.txt",
        help="Output manifest path.",
    )
    args = parser.parse_args(argv)

    write_manifest(args.artifacts, args.output)
    print(f"Wrote {args.output} with {len(args.artifacts)} artifact checksums.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
