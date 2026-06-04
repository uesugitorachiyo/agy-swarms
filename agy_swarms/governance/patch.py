"""Sandbox-first patch promotion (FR-12/FR-15/D6.2)."""

from __future__ import annotations

import shutil
from pathlib import Path
from agy_swarms.governance.sandbox import SandboxViolation, WorktreeSandbox


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def promote_patch(
    sandbox: WorktreeSandbox,
    target_repo: Path | str,
    *,
    allowed_paths: list[str] | tuple[str, ...] | None = None,
    model_claims: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    """Promote git-derived diffs from the isolated sandbox into the target repo.

    If any file violates safety checks or allowed path constraints, raises
    SandboxViolation and leaves the target repo completely unchanged.

    Returns:
        List of promoted relative paths.
    """
    target_root = Path(target_repo).resolve()
    if not target_root.is_dir():
        raise SandboxViolation(f"Target repository directory does not exist: {target_root}")

    # 1. Get real git-derived changed files from the sandbox
    changed = sandbox.changed_files()

    # 2. Reject model claims if they do not match git state exactly
    if model_claims is not None:
        if set(model_claims) != set(changed):
            raise SandboxViolation(
                f"Model claims do not match git state. Claims: {model_claims}, Actual: {changed}"
            )

    # 3. Get untracked directories in the sandbox to detect untracked artifact dirs
    untracked_dirs_raw = sandbox._git(
        "ls-files", "--others", "--exclude-standard", "--directory"
    ).stdout.splitlines()
    # Normalize untracked dirs as Paths relative to sandbox root
    untracked_dirs = [Path(d.strip("/")) for d in untracked_dirs_raw if d.strip()]

    # 4. Validate ALL changed files first (fail-closed, atomic check)
    allowed_resolved = None
    if allowed_paths is not None:
        allowed_resolved = []
        for ap in allowed_paths:
            # Resolve relative to target root to handle any symlinks/paths securely
            try:
                allowed_resolved.append((target_root / ap).resolve())
            except Exception:
                pass

    validations = []  # List of tuples: (rel_path, action, src_path, dst_path)

    for file_str in changed:
        # Check absolute path
        file_path = Path(file_str)
        if file_path.is_absolute() or file_str.startswith("/") or file_str.startswith("\\"):
            raise SandboxViolation(f"Path is absolute: {file_str}")

        # Check path traversal
        if ".." in file_path.parts:
            raise SandboxViolation(f"Path traversal detected: {file_str}")

        # Resolve paths in sandbox and target to check symlink escapes
        sandbox_path = (sandbox.root / file_path).resolve()
        if not _is_relative_to(sandbox_path, sandbox.root):
            raise SandboxViolation(f"Path escapes sandbox root: {file_str}")

        target_path = (target_root / file_path).resolve()
        if not _is_relative_to(target_path, target_root):
            raise SandboxViolation(f"Path escapes target repository root: {file_str}")

        # Check if the file is in an untracked artifact directory
        # Check if any parent of file_path is in untracked_dirs
        is_in_untracked_dir = False
        for parent in file_path.parents:
            if parent in untracked_dirs:
                is_in_untracked_dir = True
                break

        # Check if explicitly allowed (either by file path or parent path matching allowed_resolved)
        is_explicitly_allowed = False
        if allowed_resolved is not None:
            for allowed_p in allowed_resolved:
                if target_path == allowed_p or _is_relative_to(target_path, allowed_p):
                    is_explicitly_allowed = True
                    break

        # If it is in an untracked artifact dir, it must be explicitly allowed
        if is_in_untracked_dir and not is_explicitly_allowed:
            raise SandboxViolation(
                f"Untracked artifact directory not explicitly allowed: {file_str}"
            )

        # If allowed_paths was provided, the file must be explicitly allowed regardless
        if allowed_paths is not None and not is_explicitly_allowed:
            raise SandboxViolation(f"Path not explicitly allowed for promotion: {file_str}")

        # Determine action
        if sandbox_path.exists():
            action = "copy"
        else:
            action = "delete"

        validations.append((file_str, action, sandbox_path, target_path))

    # 5. Apply changes only after ALL validations pass (guarantees atomic behavior)
    promoted = []
    for file_str, action, src, dst in validations:
        if action == "copy":
            # Ensure parent directories exist in target
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        elif action == "delete":
            if dst.exists():
                dst.unlink()
                # Clean up empty parent directories if any
                parent = dst.parent
                while parent != target_root:
                    try:
                        parent.rmdir()
                        parent = parent.parent
                    except OSError:
                        # Directory not empty
                        break
        promoted.append(file_str)

    return promoted
