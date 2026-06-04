from __future__ import annotations

import pytest

from agy_swarms.lockfile import Lockfile
from agy_swarms.types import DriftRecord
from agy_swarms.validate import ValidationError, check_drift


def test_lockfile_matching_pins_pass():
    lock = Lockfile(
        model_pins={"default": "flash-A"},
        prompt_hashes={"plan": "h-A"},
        tool_versions={"git": "2.40.0"},
        skill_hashes={"search": "hash-S"},
        policy_version="1.0",
    )
    # Drift check with identical files returns no drift records and does not abort
    assert check_drift(lock, lock, allow_drift=False) == []


def test_lockfile_missing_tool_hash_blocks_ac6():
    # If a tool hash is missing (absent/empty in actual), it blocks AC-6 and raises ValidationError without allow_drift
    locked = Lockfile(tool_versions={"git": "2.40.0"})
    actual = Lockfile(tool_versions={})  # missing 'git'

    with pytest.raises(ValidationError, match="tool_versions.git"):
        check_drift(locked, actual, allow_drift=False)

    # Under allow_drift, it is recorded as a drift record
    records = check_drift(locked, actual, allow_drift=True)
    assert records == [
        DriftRecord(category="tool_versions", key="git", expected="2.40.0", actual="")
    ]


def test_lockfile_skill_hash_mismatch_aborts_without_allow_drift():
    locked = Lockfile(skill_hashes={"search": "hash-A"})
    actual = Lockfile(skill_hashes={"search": "hash-B"})

    with pytest.raises(ValidationError, match="skill_hashes.search"):
        check_drift(locked, actual, allow_drift=False)

    records = check_drift(locked, actual, allow_drift=True)
    assert records == [
        DriftRecord(category="skill_hashes", key="search", expected="hash-A", actual="hash-B")
    ]


def test_lockfile_policy_version_mismatch_aborts_without_allow_drift():
    locked = Lockfile(policy_version="1.0")
    actual = Lockfile(policy_version="2.0")

    with pytest.raises(ValidationError, match="policy_version.default"):
        check_drift(locked, actual, allow_drift=False)

    records = check_drift(locked, actual, allow_drift=True)
    assert records == [
        DriftRecord(category="policy_version", key="default", expected="1.0", actual="2.0")
    ]


def test_lockfile_tool_version_mismatch_does_not_abort_without_allow_drift():
    # As per previous behavior, a tool version mismatch (not missing entirely) is warn-only and never aborts
    locked = Lockfile(tool_versions={"git": "2.40.0"})
    actual = Lockfile(tool_versions={"git": "2.41.0"})

    records = check_drift(locked, actual, allow_drift=False)
    assert records == [
        DriftRecord(category="tool_versions", key="git", expected="2.40.0", actual="2.41.0")
    ]
