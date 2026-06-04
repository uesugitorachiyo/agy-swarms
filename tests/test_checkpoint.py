"""FR-7 checkpoint — SQLite-WAL epoch-validated journal + atomic barrier commit.

The checkpoint is the durable resume substrate (FR-7 / CON-12: SQLite-WAL is the only
shipped backend). Per-node results (keyed by ``idempotency_key``) and runtime
``{status, attempt, remaining_schema_retries, budget_consumed}`` are written in a SINGLE
transaction per barrier (NFR-4 / FR-8.4 — all-or-none). On resume a result is a cache hit
ONLY when its stored ``epoch_id`` equals the current epoch (FR-7 cache validity folds in
``epoch_id``): a model/prompt/engine bump OR a changed ``idempotency_key`` cold-busts it,
while a revert reproducing the ``epoch_id`` re-hits. Persisted ``budget_consumed`` is read
back for admission (AC-1 cross-resume monotonicity) and an exhausted node stays terminal.
"""

import pytest

from agy_swarms.checkpoint import Checkpoint, CheckpointError, JournalEntry
from agy_swarms.types import Epoch, ErrorClass, FailureClass, ResultEnvelope


def _epoch(epoch_id="E1", seq=1):
    return Epoch(epoch_seq=seq, epoch_id=epoch_id)


def _env(node_id="a", **kw):
    base = dict(node_id=node_id, idempotency_key=f"key-{node_id}", status="succeeded")
    base.update(kw)
    return ResultEnvelope(**base)


_MISSING = object()


def _entry(
    node_id="a",
    key=None,
    epoch_id="E1",
    epoch_seq=1,
    status="succeeded",
    attempt=0,
    remaining=0,
    budget=None,
    envelope=_MISSING,
):
    return JournalEntry(
        node_id=node_id,
        idempotency_key=key if key is not None else f"key-{node_id}",
        epoch_id=epoch_id,
        epoch_seq=epoch_seq,
        status=status,
        attempt=attempt,
        remaining_schema_retries=remaining,
        budget_consumed=budget if budget is not None else {"tokens": 0, "usd": 0.0},
        envelope=_env(node_id, status=status) if envelope is _MISSING else envelope,
    )


def _open(tmp_path, epoch=None):
    return Checkpoint(tmp_path / "ckpt.db", epoch or _epoch())


# --- core journal: commit + lookup -----------------------------------------


def test_commit_and_lookup_returns_the_journaled_entry(tmp_path):
    ck = _open(tmp_path)
    ck.commit_barrier([_entry("a", budget={"tokens": 50, "usd": 0.1})])
    hit = ck.lookup("key-a")
    assert hit is not None
    assert hit.node_id == "a"
    assert hit.budget_consumed == {"tokens": 50, "usd": 0.1}
    ck.close()


def test_lookup_unknown_key_returns_none(tmp_path):
    ck = _open(tmp_path)
    assert ck.lookup("nope") is None
    ck.close()


def test_results_survive_a_reopen(tmp_path):  # FR-7 resume durability
    ck = _open(tmp_path)
    ck.commit_barrier([_entry("a")])
    ck.close()
    ck2 = _open(tmp_path)
    assert ck2.lookup("key-a") is not None
    ck2.close()


# --- FR-7 cache validity folds in epoch_id ---------------------------------


def test_lookup_is_cold_when_epoch_id_differs(tmp_path):
    c1 = Checkpoint(tmp_path / "c.db", _epoch("E1"))
    c1.commit_barrier([_entry("a", epoch_id="E1")])
    c1.close()
    c2 = Checkpoint(tmp_path / "c.db", _epoch("E2", seq=2))
    assert c2.lookup("key-a") is None  # model/prompt/engine bump → cold
    c2.close()


def test_lookup_re_hits_after_an_epoch_revert(tmp_path):
    p = tmp_path / "c.db"
    c1 = Checkpoint(p, _epoch("E1"))
    c1.commit_barrier([_entry("a", epoch_id="E1")])
    c1.close()
    c2 = Checkpoint(p, _epoch("E2", seq=2))
    assert c2.lookup("key-a") is None
    c2.close()
    c3 = Checkpoint(p, _epoch("E1", seq=3))  # epoch_seq advanced, epoch_id reverted
    assert c3.lookup("key-a") is not None  # revert re-hits the cache
    c3.close()


def test_a_changed_idempotency_key_misses_the_cache(tmp_path):
    ck = _open(tmp_path)
    ck.commit_barrier([_entry("a", key="key-a")])
    assert ck.lookup("key-a-v2") is None  # replan edited the node → new key → re-run
    ck.close()


# --- NFR-4 / FR-8.4 atomic barrier commit ----------------------------------


def test_commit_barrier_is_atomic_all_or_none(tmp_path):
    ck = _open(tmp_path)
    ck.commit_barrier([_entry("a")])  # lands first
    with pytest.raises(CheckpointError):
        ck.commit_barrier([_entry("b"), _entry("", key="bad")])  # 2nd entry invalid
    assert ck.lookup("key-b") is None  # whole batch rolled back
    assert ck.lookup("key-a") is not None  # prior commit untouched
    ck.close()


def test_barrier_commits_multiple_entries_together(tmp_path):  # multi-artifact
    ck = _open(tmp_path)
    ck.commit_barrier([_entry("a"), _entry("b"), _entry("c")])
    assert ck.lookup("key-a") and ck.lookup("key-b") and ck.lookup("key-c")
    ck.close()


# --- resume runtime: budget monotonicity + retry exhaustion ----------------


def test_get_runtime_returns_persisted_budget_consumed(tmp_path):  # AC-1 monotonicity
    ck = _open(tmp_path)
    ck.commit_barrier([_entry("a", budget={"tokens": 800, "usd": 0.0})])
    ck.close()
    ck2 = _open(tmp_path)
    rt = ck2.get_runtime("a")
    assert rt.budget_consumed == {"tokens": 800, "usd": 0.0}
    ck2.close()


def test_get_runtime_preserves_terminal_failed_with_zero_retries(tmp_path):
    ck = _open(tmp_path)
    ck.commit_barrier(
        [_entry("a", status="failed", remaining=0, envelope=_env("a", status="failed"))]
    )
    rt = ck.get_runtime("a")
    assert rt.status == "failed"
    assert rt.remaining_schema_retries == 0  # stays terminal on resume (no fresh retries)
    ck.close()


def test_get_runtime_unknown_node_returns_none(tmp_path):
    ck = _open(tmp_path)
    assert ck.get_runtime("ghost") is None
    ck.close()


# --- envelope (de)serialization incl. enums --------------------------------


def test_envelope_roundtrips_through_the_journal(tmp_path):
    env = _env(
        "a",
        status="failed",
        error_class=ErrorClass.TRANSPORT,
        failure_class=FailureClass.TRANSIENT,
        retryable=True,
        artifact={"k": 1},
        concerns=["c"],
        cost_usd=0.25,
    )
    ck = _open(tmp_path)
    ck.commit_barrier([_entry("a", status="failed", envelope=env)])
    ck.close()
    ck2 = _open(tmp_path)
    got = ck2.lookup("key-a").envelope
    assert got == env  # full structural + enum equality after SQLite round-trip
    ck2.close()


def test_entry_with_no_envelope_roundtrips_as_none(tmp_path):
    ck = _open(tmp_path)
    ck.commit_barrier([_entry("a", envelope=None)])
    assert ck.lookup("key-a").envelope is None
    ck.close()


# --- CON-12 SQLite-WAL backend + context manager ---------------------------


def test_wal_mode_is_enabled(tmp_path):
    ck = _open(tmp_path)
    assert ck.journal_mode() == "wal"
    ck.close()


def test_checkpoint_is_a_context_manager(tmp_path):
    with _open(tmp_path) as ck:
        ck.commit_barrier([_entry("a")])
    with _open(tmp_path) as ck2:
        assert ck2.lookup("key-a") is not None
