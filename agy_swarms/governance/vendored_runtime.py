"""CON-7 vendored runtime and clean checkout validator (D6.7)."""

from __future__ import annotations

import sys
from pathlib import Path


class VendoredRuntimeError(Exception):
    """Raised when an illegal sibling repository reference or non-vendored runtime is detected."""


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def verify_clean_environment(repo_root: Path | str) -> None:
    """Enforce CON-7 clean-checkout: no sibling imports or outside PYTHONPATH paths."""
    root = Path(repo_root).resolve()

    # 1. Scan sys.path for sibling directory indicators
    sibling_names = ("ao2", "factory-v3", "factory_v3")
    for path_str in sys.path:
        if not path_str:
            continue
        try:
            path = Path(path_str).resolve()
        except Exception:
            continue

        if not _is_relative_to(path, root):
            # Check if any sibling repo name matches in path
            for sibling in sibling_names:
                if sibling in path.name or sibling in path.parts:
                    raise VendoredRuntimeError(
                        f"CON-7 Violation: sibling path detected in sys.path: {path_str}"
                    )

    # 2. Scan sys.modules for imported external/sibling modules
    for name, module in list(sys.modules.items()):
        if module is None:
            continue
        file_path_str = getattr(module, "__file__", None)
        if not file_path_str:
            continue

        try:
            file_path = Path(file_path_str).resolve()
        except Exception:
            continue

        # Check if the module is outside the repo root
        if not _is_relative_to(file_path, root):
            # Allow standard python library or virtual environment site-packages
            if "site-packages" in file_path.parts or "dist-packages" in file_path.parts:
                continue
            if "lib/python" in file_path.as_posix() or "lib-dynload" in file_path.as_posix():
                continue

            # Check if it has sibling keywords in name or path
            for sibling in sibling_names:
                if sibling in file_path.name or sibling in file_path.parts:
                    raise VendoredRuntimeError(
                        f"CON-7 Violation: Imported external module from sibling repository: {file_path_str}"
                    )


def validate_command_invocation(command: list[str]) -> None:
    """Enforce CON-7 toolchain isolation: block arbitrary non-vendored runtime execution."""
    if not command:
        return

    exe = command[0]
    exe_name = Path(exe).name.lower()

    # Declared allowed toolchain commands
    allowed_commands = {"python", "git", "pytest", "ruff", "uv", "python3"}

    # Known non-vendored runtimes we explicitly block
    blocked_runtimes = {"node", "ruby", "perl", "docker", "bash", "sh"}

    if exe_name in blocked_runtimes:
        raise VendoredRuntimeError(
            f"CON-7 Violation: Invocation of blocked non-vendored runtime: {exe}"
        )

    if exe_name not in allowed_commands:
        raise VendoredRuntimeError(
            f"CON-7 Violation: Command '{exe}' is not part of the declared toolchain"
        )
