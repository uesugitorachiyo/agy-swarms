from scripts.pr_verification import (
    END_MARKER,
    START_MARKER,
    render_verification_block,
    update_body,
)


def test_render_verification_block_includes_current_evidence():
    block = render_verification_block(
        commit="abc1234",
        command="make verify",
        pytest_count=704,
        mypy_files=95,
        release_health_passed=24,
        release_health_total=24,
    )

    assert START_MARKER in block
    assert END_MARKER in block
    assert "`abc1234`" in block
    assert "`make verify`" in block
    assert "pytest: `704 passed`" in block
    assert "mypy: `95 source files`" in block
    assert "release health: `24/24 checks passed`" in block


def test_update_body_replaces_existing_marked_verification_section():
    old = "\n".join(
        [
            "## Summary",
            "- Keep this",
            "",
            "## Verification",
            START_MARKER,
            "old evidence",
            END_MARKER,
            "",
            "## Notes",
            "Still here",
        ]
    )
    block = render_verification_block(
        commit="new",
        command="make verify",
        pytest_count=704,
        mypy_files=95,
        release_health_passed=24,
        release_health_total=24,
    )

    updated = update_body(old, block)

    assert "old evidence" not in updated
    assert "`new`" in updated
    assert "## Summary\n- Keep this" in updated
    assert "## Notes\nStill here" in updated
    assert updated.count(START_MARKER) == 1
    assert updated.count(END_MARKER) == 1


def test_update_body_appends_verification_section_when_no_marker_exists():
    block = render_verification_block(
        commit="abc1234",
        command="make verify",
        pytest_count=704,
        mypy_files=95,
        release_health_passed=24,
        release_health_total=24,
    )

    updated = update_body("## Summary\n- Keep this", block)

    assert updated.startswith("## Summary\n- Keep this")
    assert "## Verification" in updated
    assert START_MARKER in updated
    assert "`abc1234`" in updated


def test_update_body_replaces_legacy_test_plan_section():
    old = "\n".join(
        [
            "## Summary",
            "- Keep this",
            "",
            "## Test Plan",
            "- [x] `make verify`",
            "  - pytest passed: 701 tests",
        ]
    )
    block = render_verification_block(
        commit="abc1234",
        command="make verify",
        pytest_count=704,
        mypy_files=95,
        release_health_passed=24,
        release_health_total=24,
    )

    updated = update_body(old, block)

    assert "701 tests" not in updated
    assert "## Test Plan" not in updated
    assert "## Verification" in updated
    assert "pytest: `704 passed`" in updated
