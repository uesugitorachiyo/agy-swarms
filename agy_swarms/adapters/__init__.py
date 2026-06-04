"""Model/transport adapters (FR-13..FR-17).

Phase 1 ships only the scripted zero-token adapter (FR-17) — the deterministic
substrate the AC-1 gate runs against. Live adapters (api/agy/managed) land later.

Crash containment (AC-38): the conductor wraps every adapter ``run()`` so a worker that
RAISES is contained into a failed (UNKNOWN→Deterministic) envelope rather than crashing the
run; a declared command killed by a signal is classified TIMEOUT→Transient (D-5). OS-level
isolation of adapter subprocesses (FR-12 worktree / NFR-8 hermetic FS) remains Phase-2.
"""

from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .gemini_api import GeminiApiAdapter
from .scripted import CannedResult, ScriptedAdapter, ScriptedAdapterError

__all__ = [
    "CannedResult",
    "ScriptedAdapter",
    "ScriptedAdapterError",
    "ClaudeAdapter",
    "CodexAdapter",
    "GeminiApiAdapter",
]
