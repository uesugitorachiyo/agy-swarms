"""FR-7 checkpoint — SQLite-WAL epoch-validated journal + atomic barrier commit.

The durable resume substrate (FR-7; CON-12: SQLite-WAL is the only shipped backend). One
row per node holds its latest result (keyed by ``idempotency_key``) plus the runtime the
budget gate depends on (``status``, ``attempt``, ``remaining_schema_retries``,
``budget_consumed``). A barrier writes its whole batch in a SINGLE transaction
(NFR-4/FR-8.4 — all-or-none): if any entry is malformed the batch rolls back and the
prior journal is untouched.

Two read paths, deliberately different:

* ``lookup(idempotency_key)`` is the **cache** (FR-7). It returns a hit ONLY when the
  stored ``epoch_id`` equals the current epoch — cache validity folds in ``epoch_id``, so
  a model/prompt/engine bump or a changed ``idempotency_key`` cold-busts it while a revert
  reproducing the ``epoch_id`` re-hits.
* ``get_runtime(node_id)`` is **epoch-agnostic** — it returns the persisted runtime so a
  node that consumed 0.8 of its ceiling pre-crash is admitted against that
  ``budget_consumed`` (never zero) on resume (AC-1 monotonicity), and an exhausted node
  stays terminal ``failed``.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .types import Epoch, ErrorClass, FailureClass, ResultEnvelope

__all__ = ["Checkpoint", "CheckpointError", "JournalEntry"]


class CheckpointError(Exception):
    """Raised on a malformed barrier entry or an underlying SQLite error."""


@dataclass
class JournalEntry:
    """One node's durable checkpoint row (FR-7): result + budget/retry runtime."""

    node_id: str
    idempotency_key: str
    epoch_id: str
    epoch_seq: int
    status: str
    attempt: int
    remaining_schema_retries: int
    budget_consumed: dict[str, Any] = field(default_factory=lambda: {"tokens": 0, "usd": 0.0})
    envelope: ResultEnvelope | None = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS node_journal (
    node_id                  TEXT PRIMARY KEY,
    idempotency_key          TEXT NOT NULL,
    epoch_id                 TEXT NOT NULL,
    epoch_seq                INTEGER NOT NULL,
    status                   TEXT NOT NULL,
    attempt                  INTEGER NOT NULL,
    remaining_schema_retries INTEGER NOT NULL,
    budget_consumed          TEXT NOT NULL,
    envelope                 TEXT
);
CREATE INDEX IF NOT EXISTS idx_journal_key
    ON node_journal (idempotency_key, epoch_id);
"""

_COLUMNS = (
    "node_id",
    "idempotency_key",
    "epoch_id",
    "epoch_seq",
    "status",
    "attempt",
    "remaining_schema_retries",
    "budget_consumed",
    "envelope",
)


def _envelope_to_text(envelope: ResultEnvelope | None) -> str | None:
    # StrEnum fields serialize as their string value natively (StrEnum is a str
    # subclass), so no custom encoder is needed; sort_keys keeps rows stable.
    if envelope is None:
        return None
    return json.dumps(asdict(envelope), sort_keys=True)


def _envelope_from_text(text: str | None) -> ResultEnvelope | None:
    if text is None:
        return None
    data = json.loads(text)
    data["error_class"] = ErrorClass(data["error_class"])
    if data.get("failure_class") is not None:
        data["failure_class"] = FailureClass(data["failure_class"])
    return ResultEnvelope(**data)


def _row_to_entry(row: sqlite3.Row) -> JournalEntry:
    return JournalEntry(
        node_id=row["node_id"],
        idempotency_key=row["idempotency_key"],
        epoch_id=row["epoch_id"],
        epoch_seq=row["epoch_seq"],
        status=row["status"],
        attempt=row["attempt"],
        remaining_schema_retries=row["remaining_schema_retries"],
        budget_consumed=json.loads(row["budget_consumed"]),
        envelope=_envelope_from_text(row["envelope"]),
    )


class Checkpoint:
    """A SQLite-WAL journal scoped to one current ``Epoch`` (FR-7/CON-12)."""

    def __init__(self, path: str | Path, epoch: Epoch) -> None:
        self.epoch = epoch
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    def journal_mode(self) -> str:
        """The active SQLite journal mode (``"wal"`` for a file-backed DB; CON-12)."""
        return self._conn.execute("PRAGMA journal_mode").fetchone()[0]

    def commit_barrier(self, entries: Sequence[JournalEntry]) -> None:
        """Write ``entries`` in one transaction — all land or none do (NFR-4/FR-8.4)."""
        sql = (
            f"INSERT OR REPLACE INTO node_journal ({', '.join(_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in _COLUMNS)})"
        )
        try:
            with self._conn:  # commits on clean exit, rolls back on any exception
                for entry in entries:
                    if not entry.node_id:
                        raise CheckpointError("journal entry missing node_id")
                    self._conn.execute(
                        sql,
                        (
                            entry.node_id,
                            entry.idempotency_key,
                            entry.epoch_id,
                            entry.epoch_seq,
                            entry.status,
                            entry.attempt,
                            entry.remaining_schema_retries,
                            json.dumps(entry.budget_consumed, sort_keys=True),
                            _envelope_to_text(entry.envelope),
                        ),
                    )
        except sqlite3.Error as exc:  # DB-level failure — also already rolled back
            raise CheckpointError(str(exc)) from exc

    def lookup(self, idempotency_key: str) -> JournalEntry | None:
        """Cache read (FR-7): a hit ONLY if the row's ``epoch_id`` is the current epoch."""
        row = self._conn.execute(
            "SELECT * FROM node_journal WHERE idempotency_key = ? AND epoch_id = ?",
            (idempotency_key, self.epoch.epoch_id),
        ).fetchone()
        return _row_to_entry(row) if row is not None else None

    def get_runtime(self, node_id: str) -> JournalEntry | None:
        """Epoch-agnostic runtime read — persisted ``budget_consumed``/retry state (AC-1)."""
        row = self._conn.execute(
            "SELECT * FROM node_journal WHERE node_id = ?", (node_id,)
        ).fetchone()
        return _row_to_entry(row) if row is not None else None

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Checkpoint:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
