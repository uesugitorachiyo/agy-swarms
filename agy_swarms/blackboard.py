"""FR-8 single-writer blackboard + FR-31/FR-32 section-conflict / epoch-bump (§D.6).

The blackboard arbitrates shared state: each section has exactly one writer node (the
plan-time guard is ``validate._check_single_writer``; this is the runtime guard). A
committed section is keyed by ``(epoch_id, section)`` — sections bind to ``epoch_id``
(content identity) so a revert reproducing a prior ``epoch_id`` sees the same committed
sections (§D.6 Fix-3). Durability (the SQLite-WAL barrier commit, FR-8.4/CON-12) is added
by ``checkpoint.py``; this module owns the single-writer *policy* and snapshot reads.

Conflict rules (FR-31/FR-32):
- no committed value yet → write commits (also the crash-resume re-write case);
- committed value, different writer → ``SectionConflict(different-writer)``;
- committed value, same writer, section authorized by the active ``EpochBump`` → overwrite;
- committed value, same writer, not authorized → ``SectionConflict`` (``committed-value-
  exists`` with no bump, else ``not-authorized-by-epoch-bump``).
"""

from __future__ import annotations

from collections.abc import Container, Mapping
from dataclasses import dataclass
from typing import Any

from .types import Epoch, EpochBump, SectionConflict

__all__ = ["Blackboard", "SectionConflictError", "ScopedReadError"]


class SectionConflictError(Exception):
    """Raised on a forbidden section write (FR-31/FR-32); carries the §D.6 record."""

    def __init__(self, conflict: SectionConflict) -> None:
        super().__init__(f"section conflict on {conflict.section!r}: {conflict.reason}")
        self.conflict = conflict


class ScopedReadError(Exception):
    """A node attempted to read a section outside its declared input scope (FR-8)."""


@dataclass
class _Committed:
    value: Any
    writer_node: str
    epoch_id: str


class Blackboard:
    """In-memory single-writer section store with epoch-scoped overwrite authorization."""

    def __init__(self, epoch: Epoch) -> None:
        self.epoch = epoch
        self._sections: dict[str, _Committed] = {}
        self._authorized_overwrite: set[str] = set()
        self._bump_active = False

    def write(self, section: str, node_id: str, value: Any) -> None:
        """Commit ``value`` to ``section`` or raise ``SectionConflictError`` (FR-31/32)."""
        existing = self._sections.get(section)
        if existing is None:
            self._sections[section] = _Committed(value, node_id, self.epoch.epoch_id)
            return
        if existing.writer_node != node_id:
            raise SectionConflictError(
                self._conflict(section, existing, node_id, "different-writer")
            )
        if section in self._authorized_overwrite:
            self._sections[section] = _Committed(value, node_id, self.epoch.epoch_id)
            return
        reason = "not-authorized-by-epoch-bump" if self._bump_active else "committed-value-exists"
        raise SectionConflictError(self._conflict(section, existing, node_id, reason))

    def read(self, section: str) -> Any:
        """Return a committed section value (raises ``KeyError`` if uncommitted)."""
        return self._sections[section].value

    def read_scoped(self, section: str, allowed: Container[str]) -> Any:
        """Read only within a node's declared input scope (AC-S5)."""
        if section not in allowed:
            raise ScopedReadError(f"section {section!r} is outside the node's input scope")
        return self.read(section)

    def is_committed(self, section: str) -> bool:
        return section in self._sections

    def writer_of(self, section: str) -> str | None:
        committed = self._sections.get(section)
        return committed.writer_node if committed is not None else None

    def snapshot(self) -> dict[str, Any]:
        """A consistent, isolated copy of all committed section values (no torn reads)."""
        return {section: c.value for section, c in self._sections.items()}

    def clean_superseded(self) -> list[str]:
        """Prune only sections explicitly marked ``superseded``.

        Obligation/evidence sections are retained even if a worker marks them superseded:
        closure and replay must never be weakened by the cleaner role.
        """
        removed: list[str] = []
        for section, committed in list(self._sections.items()):
            if _protected_section(section):
                continue
            if _is_superseded(committed.value):
                del self._sections[section]
                removed.append(section)
        return sorted(removed)

    def apply_epoch_bump(self, bump: EpochBump) -> None:
        """Advance to a new epoch and authorize overwrite of the bump's closed allowlist."""
        self.epoch = bump.new_epoch
        self._authorized_overwrite = set(bump.sections)
        self._bump_active = True

    def _conflict(
        self, section: str, existing: _Committed, attempted_writer: str, reason: str
    ) -> SectionConflict:
        return SectionConflict(
            section=section,
            epoch=existing.epoch_id,
            existing_writer_node=existing.writer_node,
            attempted_writer_node=attempted_writer,
            reason=reason,
        )


def _protected_section(section: str) -> bool:
    return section.startswith("obligation.") or section.startswith("evidence.")


def _is_superseded(value: Any) -> bool:
    return isinstance(value, Mapping) and value.get("status") == "superseded"
