"""Default command runner for ``test``/``verify`` nodes (FR-34).

A runner maps a declared argv command to a ``CommandOutcome(exit_code, stdout, stderr)``.
The Phase-1 default shells out to a real subprocess (no sandbox yet — NFR-8 worktree
isolation is deferred until FR-12's subprocess adapter exists); these tests pin exit-code
and stream capture against POSIX ``true``/``false``/``echo``.
"""

import sys

from agy_swarms.runners import CommandOutcome, classify_exit, subprocess_runner
from agy_swarms.types import ErrorClass


def test_subprocess_runner_captures_zero_exit():
    outcome = subprocess_runner([sys.executable, "-c", "import sys; sys.exit(0)"])
    assert isinstance(outcome, CommandOutcome)
    assert outcome.exit_code == 0


def test_subprocess_runner_captures_nonzero_exit():
    assert subprocess_runner([sys.executable, "-c", "import sys; sys.exit(1)"]).exit_code != 0


def test_subprocess_runner_captures_stdout_stream():
    outcome = subprocess_runner([sys.executable, "-c", "print('hello')"])
    assert outcome.exit_code == 0
    assert "hello" in outcome.stdout


def test_subprocess_runner_signal_kill_is_negative_returncode():
    # AC-38 platform invariant (characterization): CPython sets returncode = -signum for a
    # child killed by a signal, so a SIGKILL'd worker surfaces as a NEGATIVE exit code. The
    # entire AC-38 signal→Transient classification rests on this; lock it explicitly.
    if sys.platform == "win32":
        import pytest

        pytest.skip("Windows does not support POSIX signals/SIGKILL return codes")
    out = subprocess_runner(
        [sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"]
    )
    assert out.exit_code < 0  # killed-by-signal, distinguishable from any clean nonzero exit


def test_subprocess_runner_missing_executable_is_contained_as_127():
    # AC-38 containment: a command whose executable does not exist must NOT raise
    # FileNotFoundError out of the runner (which would crash the conductor) — it is
    # contained as a CommandOutcome with the POSIX "command not found" code 127.
    out = subprocess_runner(["definitely-not-a-real-binary-xyzzy"])
    assert isinstance(out, CommandOutcome)
    assert out.exit_code == 127
    if sys.platform == "win32":
        assert "The system cannot find the file specified" in out.stderr
    else:
        assert "definitely-not-a-real-binary-xyzzy" in out.stderr


def test_classify_exit_signal_kill_is_timeout():
    # D-5: a negative (signal) exit classes as TIMEOUT (→Transient), NOT TOOL — a worker
    # killed by SIGKILL/OOM is an infra crash, retryable only if a node's policy opts in.
    assert classify_exit(CommandOutcome(exit_code=-9)) is ErrorClass.TIMEOUT


def test_classify_exit_clean_zero_is_none():
    assert classify_exit(CommandOutcome(exit_code=0)) is ErrorClass.NONE


def test_classify_exit_clean_nonzero_is_tool():
    # a clean nonzero (incl. 127 missing-exe) is a TOOL error — terminal under default policy
    assert classify_exit(CommandOutcome(exit_code=1)) is ErrorClass.TOOL
    assert classify_exit(CommandOutcome(exit_code=127)) is ErrorClass.TOOL
