"""Command runners for ``test``/``verify`` nodes (FR-34).

A runner maps a declared argv command to a ``CommandOutcome``. The Phase-1 default,
``subprocess_runner``, executes the command in a real subprocess and captures its exit
code and text streams. Sandboxing / worktree isolation (NFR-8 / FR-12) is deferred until
the subprocess worker adapter lands; this default carries NO isolation and must not run
untrusted commands until then.
"""

import subprocess
from dataclasses import dataclass

from .types import ErrorClass


@dataclass
class CommandOutcome:
    """Result of running a declared command (FR-34): exit code + captured text streams."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""


def subprocess_runner(command: list[str]) -> CommandOutcome:
    """Run ``command`` in a real subprocess; capture exit code + stdout/stderr as text.

    Total by construction (AC-38 containment): a missing executable is caught and surfaced
    as exit ``127`` (POSIX "command not found") rather than raised, so a bad command can
    never crash the conductor. A child killed by a signal surfaces as a NEGATIVE returncode
    (CPython convention). OS-level isolation (FR-12/NFR-8 worktree / hermetic FS) remains a
    Phase-2 concern; this default still carries NO sandbox.
    """
    import sys

    if command and command[0] == "python":
        command = [sys.executable] + command[1:]
    try:
        proc = subprocess.run(command, capture_output=True, text=True)
    except FileNotFoundError as exc:
        return CommandOutcome(127, "", str(exc))
    return CommandOutcome(proc.returncode, proc.stdout, proc.stderr)


def classify_exit(outcome: CommandOutcome) -> ErrorClass:
    """Map a command's exit code to a §D.2 ``ErrorClass`` (the crash-classification seam).

    Per decision D-5 a NEGATIVE returncode (a child killed by a signal — SIGKILL, OOM, the
    Phase-2 timeout kill) is ``TIMEOUT`` → Transient: an infra crash, retryable only when a
    node's policy opts in, never model-fallback'd. A clean ``0`` is ``NONE``; any clean
    nonzero (including ``127`` missing-executable) is ``TOOL``. The signal NUMBER rides
    losslessly in the negative ``exit_code`` itself (and thence the result artifact), so
    OOM-vs-timeout stays distinguishable without widening the closed §D.2 table.
    """
    if outcome.exit_code < 0:
        return ErrorClass.TIMEOUT
    if outcome.exit_code == 0:
        return ErrorClass.NONE
    return ErrorClass.TOOL
