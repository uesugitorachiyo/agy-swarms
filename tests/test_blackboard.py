"""FR-8 single-writer blackboard + FR-31/FR-32 section-conflict / epoch-bump (§D.6).

A committed section has exactly one writer; a different-node write raises
``SectionConflict(different-writer)``; a same-node re-write to an already-committed
section raises (``committed-value-exists``) unless an ``EpochBump`` authorizes that exact
section (FR-32, closed allowlist). A write where no committed value yet exists is allowed
(the crash-resume case, FR-31). Readers see a consistent snapshot — no torn reads (FR-8).
Exercised by AC-S5.
"""

import pytest

from agy_swarms.blackboard import Blackboard, ScopedReadError, SectionConflictError
from agy_swarms.types import Epoch, EpochBump


def _bb():
    return Blackboard(Epoch(epoch_seq=0, epoch_id="e0"))


def test_fresh_write_commits_and_reads_back():
    bb = _bb()
    bb.write("sec.a", "writer1", {"v": 1})
    assert bb.read("sec.a") == {"v": 1}


def test_read_uncommitted_section_raises_keyerror():
    bb = _bb()
    with pytest.raises(KeyError):
        bb.read("sec.missing")


def test_write_to_uncommitted_section_allowed_after_orphaned_attempt():
    # FR-31 crash-resume: no committed value yet → the re-invoked output is accepted.
    bb = _bb()
    bb.write("sec.a", "writer1", {"attempt": "final"})
    assert bb.read("sec.a") == {"attempt": "final"}


def test_different_writer_raises_section_conflict():
    bb = _bb()
    bb.write("sec.a", "writer1", {"v": 1})
    with pytest.raises(SectionConflictError) as ei:
        bb.write("sec.a", "writer2", {"v": 2})
    c = ei.value.conflict
    assert c.reason == "different-writer"
    assert c.existing_writer_node == "writer1"
    assert c.attempted_writer_node == "writer2"
    assert c.section == "sec.a"
    assert c.epoch == "e0"
    assert bb.read("sec.a") == {"v": 1}  # original retained


def test_same_writer_rewrite_of_committed_raises_committed_value_exists():
    bb = _bb()
    bb.write("sec.a", "writer1", {"v": 1})
    with pytest.raises(SectionConflictError) as ei:
        bb.write("sec.a", "writer1", {"v": 2})
    assert ei.value.conflict.reason == "committed-value-exists"
    assert bb.read("sec.a") == {"v": 1}


def test_epoch_bump_authorizes_overwrite_of_listed_section():  # FR-32
    bb = _bb()
    bb.write("sec.a", "writer1", {"v": 1})
    bb.apply_epoch_bump(EpochBump(new_epoch=Epoch(1, "e1"), sections=["sec.a"]))
    bb.write("sec.a", "writer1", {"v": 2})
    assert bb.read("sec.a") == {"v": 2}
    assert bb.epoch.epoch_id == "e1"


def test_epoch_bump_does_not_authorize_unlisted_section():  # FR-32 closed allowlist
    bb = _bb()
    bb.write("sec.a", "writer1", {"v": 1})
    bb.write("sec.b", "writer1", {"v": 1})
    bb.apply_epoch_bump(EpochBump(new_epoch=Epoch(1, "e1"), sections=["sec.b"]))
    with pytest.raises(SectionConflictError) as ei:
        bb.write("sec.a", "writer1", {"v": 2})
    assert ei.value.conflict.reason == "not-authorized-by-epoch-bump"


def test_scoped_read_enforces_allowed_sections():  # AC-S5 scoped read
    bb = _bb()
    bb.write("sec.a", "writer1", {"v": 1})
    assert bb.read_scoped("sec.a", allowed={"sec.a"}) == {"v": 1}
    with pytest.raises(ScopedReadError):
        bb.read_scoped("sec.a", allowed={"sec.other"})


def test_snapshot_is_isolated_copy():  # consistent snapshot / no torn reads
    bb = _bb()
    bb.write("sec.a", "writer1", {"v": 1})
    snap = bb.snapshot()
    snap["sec.a"] = {"v": 999}
    assert bb.read("sec.a") == {"v": 1}


def test_snapshot_reflects_committed_sections():
    bb = _bb()
    bb.write("sec.a", "writer1", {"v": 1})
    bb.write("sec.b", "writer2", {"v": 2})
    assert bb.snapshot() == {"sec.a": {"v": 1}, "sec.b": {"v": 2}}


def test_cleaner_prunes_only_superseded_sections():
    bb = _bb()
    bb.write("message.old", "worker1", {"status": "superseded", "body": "drop"})
    bb.write("message.keep", "worker2", {"status": "active", "body": "keep"})

    removed = bb.clean_superseded()

    assert removed == ["message.old"]
    assert bb.snapshot() == {"message.keep": {"status": "active", "body": "keep"}}


def test_cleaner_never_removes_obligations_or_evidence_even_when_marked_superseded():
    bb = _bb()
    bb.write("obligation.fr10", "worker1", {"status": "superseded"})
    bb.write("evidence.test", "worker2", {"status": "superseded"})

    removed = bb.clean_superseded()

    assert removed == []
    assert bb.is_committed("obligation.fr10")
    assert bb.is_committed("evidence.test")
