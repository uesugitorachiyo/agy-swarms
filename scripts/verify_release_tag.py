from __future__ import annotations

import argparse
import tomllib
from pathlib import Path


class ReleaseTagMismatch(ValueError):
    pass


def read_package_version(pyproject_path: Path) -> str:
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    return str(pyproject["project"]["version"])


def verify_release_tag(tag: str, package_version: str) -> str:
    expected = f"v{package_version}"
    if tag != expected:
        raise ReleaseTagMismatch(
            f"release tag {tag!r} does not match pyproject.toml version {package_version!r}; "
            f"expected release tag {expected!r}"
        )
    return tag


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a release tag matches pyproject.toml.")
    parser.add_argument("--tag", required=True, help="Release tag, such as v0.5.3.")
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path("pyproject.toml"),
        help="Path to pyproject.toml.",
    )
    args = parser.parse_args(argv)

    package_version = read_package_version(args.pyproject)
    try:
        verified = verify_release_tag(args.tag, package_version)
    except ReleaseTagMismatch as exc:
        parser.exit(status=1, message=f"{exc}\n")

    print(f"Release tag {verified} matches pyproject.toml version {package_version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
