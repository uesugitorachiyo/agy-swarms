#!/usr/bin/env python3
"""Verification probe for agy-swarms plugin installation and management."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN_INSTALL_EXCLUDES = (
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def prepare_install_source(repo_root: Path, parent: Path) -> Path:
    """Create a sparse plugin source tree without generated dependency/cache directories."""
    install_source = parent / "agy-swarms-plugin-source"
    shutil.copytree(
        repo_root,
        install_source,
        ignore=shutil.ignore_patterns(*PLUGIN_INSTALL_EXCLUDES),
    )
    return install_source


def run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    print("Running Plugin Installation & Management Smoke Probe...")
    agy_path = shutil.which("agy")
    if not agy_path:
        print("Warning: 'agy' CLI not found in PATH. Skipping plugin smoke check.")
        return 0

    with tempfile.TemporaryDirectory(prefix="agy-plugin-smoke-") as tmp:
        repo_root = _repo_root()
        install_source = prepare_install_source(repo_root, Path(tmp))
        install_source_str = str(install_source)

        # 1. Validate plugin
        print(f"Step 1: Validating plugin at {install_source_str}...")
        res = run_command(["agy", "plugin", "validate", install_source_str])
        if res.returncode != 0:
            print("Error: Plugin validation failed.")
            print(res.stderr)
            return 1
        print("[OK] Plugin validation succeeded.")

        # 2. Install plugin
        print("Step 2: Installing plugin...")
        res = run_command(["agy", "plugin", "install", install_source_str])
        if res.returncode != 0:
            print("Error: Plugin installation failed.")
            print(res.stderr)
            return 1
        print("[OK] Plugin installation succeeded.")

    # 3. List plugins and assert presence
    print("Step 3: Verifying plugin is listed...")
    res = run_command(["agy", "plugin", "list"])
    if res.returncode != 0:
        print("Error: Plugin listing failed.")
        print(res.stderr)
        return 1

    try:
        data = json.loads(res.stdout)
        imports = data.get("imports", [])
        names = [item.get("name") for item in imports]
        if "agy-swarms" not in names:
            print(f"Error: 'agy-swarms' not found in imported plugins. Found names: {names}")
            return 1
    except (json.JSONDecodeError, TypeError) as exc:
        print(f"Error parsing plugin list JSON: {exc}")
        print(res.stdout)
        return 1
    print("[OK] Plugin presence verified in 'agy plugin list'.")

    # 4. Uninstall plugin
    print("Step 4: Uninstalling plugin...")
    res = run_command(["agy", "plugin", "uninstall", "agy-swarms"])
    if res.returncode != 0:
        print("Error: Plugin uninstallation failed.")
        print(res.stderr)
        return 1
    print("[OK] Plugin uninstallation succeeded.")

    # 5. Verify uninstalled
    print("Step 5: Verifying plugin is removed...")
    res = run_command(["agy", "plugin", "list"])
    if "agy-swarms" in res.stdout:
        print("Error: 'agy-swarms' still appears in plugin list after uninstall.")
        print(res.stdout)
        return 1
    print("[OK] Plugin removal verified.")

    print("[OK] All plugin management checks passed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
