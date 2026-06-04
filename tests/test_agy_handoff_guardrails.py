from agy_swarms.handoff import build_agy_review_prompt
from agy_swarms.main import main


def test_agy_handoff_is_read_only():
    prompt = build_agy_review_prompt(report_path="report.json")

    assert "Do not implement changes" in prompt
    assert "do not commit" in prompt
    assert "do not push" in prompt
    assert "Report findings first" in prompt
    assert "uv run python scripts/release_health.py" in prompt


def test_cli_handoff_prints_read_only_prompt(capsys):
    exit_code = main(["handoff", "--report", "report.json"])

    assert exit_code == 0
    prompt = capsys.readouterr().out
    assert "Report path: report.json" in prompt
    assert "Do not implement changes" in prompt
