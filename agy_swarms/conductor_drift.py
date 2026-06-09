"""Conductor-facing drift check helpers."""

from __future__ import annotations

from collections.abc import Sequence

from .lockfile import Lockfile
from .types import DriftRecord
from .validate import check_drift


def collect_drift_records(
    locked: Lockfile | None,
    actual: Lockfile | None,
    *,
    allow_drift: bool,
) -> list[DriftRecord]:
    """Return drift records, skipping checks until both lockfiles are available."""
    if locked is None or actual is None:
        return []
    return check_drift(locked, actual, allow_drift=allow_drift)


def report_drift_records(records: Sequence[DriftRecord]) -> list[DriftRecord]:
    """Return a report-safe copy of recorded drift."""
    return list(records)
