from pathlib import Path

from agy_swarms.profiling import (
    ConductorProfile,
    compute_reference_task_sha,
    decide_rust_port,
    profile_conductor,
)


def _profile(*, overhead_pct=10.0, fanout=16, binding="not_gil_bound"):
    return ConductorProfile(
        reference_task_sha="abc123",
        worker_count=4,
        wall_clock_s=1.0,
        model_wait_s=0.9,
        conductor_overhead_s=0.1,
        conductor_overhead_pct=overhead_pct,
        useful_fanout_ceiling=fanout,
        fanout_binding=binding,
    )


def test_rust_port_triggers_when_conductor_overhead_exceeds_threshold():
    decision = decide_rust_port(_profile(overhead_pct=20.1, fanout=32))

    assert decision.rust_port_triggered is True
    assert decision.status == "trigger_rust_port"
    assert decision.reasons == ("conductor_overhead_pct 20.10 > 20.00",)


def test_rust_port_triggers_when_gil_caps_useful_fanout_below_16():
    decision = decide_rust_port(_profile(overhead_pct=5.0, fanout=8, binding="gil"))

    assert decision.rust_port_triggered is True
    assert decision.reasons == ("gil_bound_fanout_ceiling 8 < 16",)


def test_non_gil_fanout_caps_do_not_trigger_rust_port():
    decision = decide_rust_port(_profile(overhead_pct=5.0, fanout=4, binding="cost"))

    assert decision.rust_port_triggered is False
    assert decision.status == "accepted_as_no_port"
    assert decision.reasons == (
        "conductor_overhead_pct 5.00 <= 20.00",
        "fanout ceiling is cost-bound, not GIL-bound",
    )


def test_compute_reference_task_sha_reads_file_bytes(tmp_path):
    path = tmp_path / "reference_task.md"
    path.write_bytes(b"reference task\n")

    assert compute_reference_task_sha(path) == (
        "db150b8fcf54534f4b4ce9529046690ce5b7b20a07cc365404aec64b8d59c095"
    )


def test_profile_conductor_reports_reference_hash_and_decision_inputs():
    reference = Path("benchmarks/reference_task.md")

    profile = profile_conductor(reference, worker_count=4, model_wait_s=0.001)

    assert profile.reference_task_sha == compute_reference_task_sha(reference)
    assert profile.worker_count == 4
    assert profile.wall_clock_s > 0
    assert profile.model_wait_s >= 0.004
    assert profile.conductor_overhead_s >= 0
    assert profile.useful_fanout_ceiling >= 1
