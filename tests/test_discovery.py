"""D4.3 loop-until-dry discovery predicate."""

import pytest

from agy_swarms.quality.discovery import (
    DiscoveryRound,
    DiscoveryStatus,
    loop_until_dry,
)


def test_new_items_keep_discovery_loop_running_until_dry():
    report = loop_until_dry(
        (
            DiscoveryRound(id="round-1", item_ids=("file:a", "file:b")),
            DiscoveryRound(id="round-2", item_ids=("file:b", "file:c")),
            DiscoveryRound(id="round-3", item_ids=("file:a", "file:c")),
        ),
        max_iterations=5,
    )

    assert report.status == DiscoveryStatus.DRY
    assert report.terminated is True
    assert report.iterations == 3
    assert report.discovered_item_ids == ("file:a", "file:b", "file:c")
    assert report.steps[0].new_item_ids == ("file:a", "file:b")
    assert report.steps[1].new_item_ids == ("file:c",)
    assert report.steps[2].new_item_ids == ()


def test_no_new_items_marks_dry_and_terminates():
    report = loop_until_dry(
        (DiscoveryRound(id="round-1", item_ids=()),),
        max_iterations=3,
    )

    assert report.status == DiscoveryStatus.DRY
    assert report.terminated is True
    assert report.iterations == 1
    assert report.discovered_item_ids == ()
    assert report.steps[0].dry is True


def test_max_iteration_cap_terminates_even_if_items_keep_arriving():
    report = loop_until_dry(
        (
            DiscoveryRound(id="round-1", item_ids=("claim:1",)),
            DiscoveryRound(id="round-2", item_ids=("claim:2",)),
            DiscoveryRound(id="round-3", item_ids=("claim:3",)),
        ),
        max_iterations=2,
    )

    assert report.status == DiscoveryStatus.MAX_ITERATIONS
    assert report.terminated is True
    assert report.iterations == 2
    assert report.discovered_item_ids == ("claim:1", "claim:2")
    assert report.blockers == ("max iterations reached before dry predicate",)


def test_discovery_loop_rejects_unbounded_iteration_cap():
    with pytest.raises(ValueError, match="max_iterations must be positive"):
        loop_until_dry((DiscoveryRound(id="round-1", item_ids=("claim:1",)),), max_iterations=0)
