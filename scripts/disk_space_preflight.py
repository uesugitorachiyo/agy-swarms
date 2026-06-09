from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MIN_FREE_MIB = 1024
BYTES_PER_MIB = 1024 * 1024


@dataclass(frozen=True)
class PreflightCheck:
    label: str
    path: Path
    free_mib: int
    required_mib: int

    @property
    def ok(self) -> bool:
        return self.free_mib >= self.required_mib


@dataclass(frozen=True)
class PreflightResult:
    checks: tuple[PreflightCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)


def collect_paths(repo_root: Path, temp_dir: Path) -> list[Path]:
    """Return unique filesystem locations that heavy verification writes to."""
    paths: list[Path] = []
    seen: set[Path] = set()
    for path in (repo_root, temp_dir):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        paths.append(resolved)
    return paths


def _dedupe_labeled_paths(
    paths: Iterable[Path], labels: Sequence[str] | None = None
) -> list[tuple[str, Path]]:
    deduped: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    label_list = list(labels or ())
    for index, path in enumerate(paths):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        label = label_list[index] if index < len(label_list) else str(resolved)
        deduped.append((label, resolved))
    return deduped


def run_preflight(
    paths: Iterable[Path],
    min_free_mib: int,
    labels: Sequence[str] | None = None,
) -> PreflightResult:
    checks: list[PreflightCheck] = []
    for label, path in _dedupe_labeled_paths(paths, labels):
        usage = shutil.disk_usage(str(path))
        checks.append(
            PreflightCheck(
                label=label,
                path=path,
                free_mib=usage.free // BYTES_PER_MIB,
                required_mib=min_free_mib,
            )
        )
    return PreflightResult(tuple(checks))


def _parse_min_free_mib(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer MiB value") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1 MiB")
    return parsed


def _threshold_from_env() -> int:
    raw = os.environ.get("AGY_VERIFY_MIN_FREE_MIB")
    if raw is None:
        return DEFAULT_MIN_FREE_MIB
    return _parse_min_free_mib(raw)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail early when verification does not have enough free disk space."
    )
    parser.add_argument(
        "--min-free-mib",
        type=_parse_min_free_mib,
        default=None,
        help="Minimum free space required per checked filesystem in MiB.",
    )
    parser.add_argument(
        "--path",
        action="append",
        type=Path,
        help="Filesystem path to check. Defaults to the workspace and temp directory.",
    )
    parser.add_argument(
        "--label",
        action="append",
        help="Human-readable label for the corresponding --path.",
    )
    return parser


def _default_paths_and_labels() -> tuple[list[Path], list[str]]:
    paths = collect_paths(Path.cwd(), Path(tempfile.gettempdir()))
    labels = ["workspace" if path == Path.cwd().resolve() else "temp" for path in paths]
    return paths, labels


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    threshold = args.min_free_mib if args.min_free_mib is not None else _threshold_from_env()

    if args.path:
        paths = args.path
        labels = args.label or []
        if args.label and len(args.label) != len(args.path):
            parser.error("--label must be supplied once per --path")
    else:
        paths, labels = _default_paths_and_labels()

    result = run_preflight(paths, threshold, labels)
    status = "passed" if result.ok else "failed"
    print(f"Disk preflight {status}:")
    for check in result.checks:
        marker = "OK" if check.ok else "FAIL"
        print(
            f"  [{marker}] {check.label}: {check.free_mib} MiB free, "
            f"{check.required_mib} MiB required ({check.path})"
        )

    if result.ok:
        return 0

    print()
    print(
        "Free space before rerunning verification, lower the threshold with "
        "AGY_VERIFY_MIN_FREE_MIB only for intentional constrained runs, or point "
        "TMPDIR at a filesystem with more space."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
