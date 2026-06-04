"""AC-31 — lockfile drift recording (§D.5 / §D.7, SPEC:492).

A ``model_pins``/``prompt_hashes`` mismatch is control-flow-affecting: WITHOUT
``--allow-drift`` it aborts the run (``ValidationError``); WITH ``--allow-drift`` it is
downgraded to a recorded ``DriftRecord`` carrying the per-key mismatch (§D.5:378-380). A
``tool_versions`` mismatch is warn-only — recorded, never aborting (§D.5:379). The drift
records surface in the run record (§D.7:443). (AC-31, SPEC:492.)
"""

import pytest

from agy_swarms.budget import Dims
from agy_swarms.conductor import Conductor
from agy_swarms.lockfile import Lockfile
from agy_swarms.types import (
    DriftRecord,
    Epoch,
    NodeSpec,
    ResultEnvelope,
    RunStatus,
    TaskGraph,
)
from agy_swarms.validate import ValidationError, check_drift

_LIMIT = Dims(tokens=1_000_000, usd=1000.0)


def _epoch():
    return Epoch(epoch_seq=1, epoch_id="E1")


def _one_node_graph():
    return TaskGraph(nodes=[NodeSpec(id="w", role="worker", objective="o")], edges=[])


class _OkAdapter:
    """A worker adapter that always succeeds — isolates the drift seam from dispatch."""

    accounting = "exact"

    def covers(self, required):
        return True

    def run(self, node, *, attempt=0, reservation_id=None):
        return ResultEnvelope(node_id=node.id, idempotency_key="", status="succeeded")


# --- model_pins: control-flow-affecting (§D.5:378) -------------------------


def test_clean_lockfile_yields_no_drift_records():
    lock = Lockfile(model_pins={"default": "flash-A"})
    assert check_drift(lock, lock, allow_drift=False) == []


def test_model_pin_drift_without_allow_drift_aborts():
    locked = Lockfile(model_pins={"default": "flash-A"})
    actual = Lockfile(model_pins={"default": "flash-B"})
    with pytest.raises(ValidationError, match="default"):
        check_drift(locked, actual, allow_drift=False)


def test_model_pin_drift_with_allow_drift_records_per_key_mismatch():
    # AC-31 core: --allow-drift downgrades the abort to a recorded per-key drift_record.
    locked = Lockfile(model_pins={"default": "flash-A"})
    actual = Lockfile(model_pins={"default": "flash-B"})
    records = check_drift(locked, actual, allow_drift=True)
    assert records == [
        DriftRecord(category="model_pins", key="default", expected="flash-A", actual="flash-B")
    ]


# --- prompt_hashes: also control-flow-affecting (§D.5:378) ------------------


def test_prompt_hash_drift_without_allow_drift_aborts():
    locked = Lockfile(prompt_hashes={"plan": "h-A"})
    actual = Lockfile(prompt_hashes={"plan": "h-B"})
    with pytest.raises(ValidationError, match="plan"):
        check_drift(locked, actual, allow_drift=False)


def test_prompt_hash_drift_with_allow_drift_records_mismatch():
    locked = Lockfile(prompt_hashes={"plan": "h-A"})
    actual = Lockfile(prompt_hashes={"plan": "h-B"})
    records = check_drift(locked, actual, allow_drift=True)
    assert records == [
        DriftRecord(category="prompt_hashes", key="plan", expected="h-A", actual="h-B")
    ]


# --- tool_versions: warn-only, never aborts (§D.5:379) ----------------------


def test_tool_version_drift_is_warn_only_not_abort():
    # A tool_versions mismatch SHALL warn but SHALL NOT abort, even WITHOUT --allow-drift:
    # the record is still produced, the run is not aborted.
    locked = Lockfile(tool_versions={"agy": "1.0"})
    actual = Lockfile(tool_versions={"agy": "2.0"})
    records = check_drift(locked, actual, allow_drift=False)  # must NOT raise
    assert records == [
        DriftRecord(category="tool_versions", key="agy", expected="1.0", actual="2.0")
    ]


# --- conductor integration: drift in the run record (§D.7) -----------------


def test_conductor_records_drift_under_allow_drift():
    # AC-31 end-to-end: --allow-drift ⇒ run proceeds and the per-key mismatch surfaces in
    # the run record (§D.7:443).
    cond = Conductor(
        _one_node_graph(),
        _OkAdapter(),
        limit=_LIMIT,
        epoch=_epoch(),
        lockfile=Lockfile(model_pins={"default": "flash-A"}),
        resolved_lockfile=Lockfile(model_pins={"default": "flash-B"}),
        allow_drift=True,
    )
    report = cond.run()
    assert report.status == RunStatus.SUCCEEDED
    assert DriftRecord("model_pins", "default", "flash-A", "flash-B") in report.drift_records


def test_conductor_aborts_on_drift_without_allow_drift():
    # Without --allow-drift the same control-flow drift aborts before any node runs.
    cond = Conductor(
        _one_node_graph(),
        _OkAdapter(),
        limit=_LIMIT,
        epoch=_epoch(),
        lockfile=Lockfile(model_pins={"default": "flash-A"}),
        resolved_lockfile=Lockfile(model_pins={"default": "flash-B"}),
        allow_drift=False,
    )
    with pytest.raises(ValidationError, match="default"):
        cond.run()


def test_conductor_without_lockfiles_records_no_drift():
    # Backward-compatible: no lockfile params ⇒ no drift check, empty drift_records.
    report = Conductor(_one_node_graph(), _OkAdapter(), limit=_LIMIT, epoch=_epoch()).run()
    assert report.drift_records == []
