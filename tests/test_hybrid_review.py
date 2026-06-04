import pytest

from agy_swarms.hybrid_review import (
    ReviewAdapter,
    ReviewRole,
    ReviewRouteError,
    route_review_role,
)


def test_reviewer_defaults_to_agy_oauth_gemini_flash():
    route = route_review_role(ReviewRole.REVIEWER)

    assert route.role == ReviewRole.REVIEWER
    assert route.adapter == ReviewAdapter.AGY
    assert route.transport == "agy"
    assert route.auth == "oauth"
    assert route.model == "gemini-3.5-flash"
    assert route.read_only is True
    assert route.temperature == 0
    assert route.reason == "default_gemini_cli_review"


def test_closer_defaults_to_agy_oauth_gemini_flash():
    route = route_review_role(ReviewRole.CLOSER)

    assert route.role == ReviewRole.CLOSER
    assert route.adapter == ReviewAdapter.AGY
    assert route.transport == "agy"
    assert route.auth == "oauth"
    assert route.model == "gemini-3.5-flash"
    assert route.read_only is True
    assert route.requires_passing_gates is True


def test_reviewer_can_use_codex_cli_when_user_selects_it():
    route = route_review_role(ReviewRole.REVIEWER, adapter="codex")

    assert route.adapter == ReviewAdapter.CODEX
    assert route.transport == "codex-cli"
    assert route.auth == "cli-session"
    assert route.model == "default"
    assert route.read_only is True
    assert route.reason == "user_selected_cli_review"


def test_closer_can_use_claude_code_cli_when_user_selects_it():
    route = route_review_role(ReviewRole.CLOSER, adapter="claude")

    assert route.adapter == ReviewAdapter.CLAUDE
    assert route.transport == "claude-code-cli"
    assert route.auth == "cli-session"
    assert route.model == "default"
    assert route.read_only is True
    assert route.requires_passing_gates is True


def test_review_routing_rejects_unknown_adapter():
    with pytest.raises(ReviewRouteError, match="unknown review adapter"):
        route_review_role(ReviewRole.REVIEWER, adapter="openai-api")


def test_review_route_serializes_without_api_key_defaults():
    payload = route_review_role(ReviewRole.CLOSER, adapter="codex").to_json()

    assert payload["role"] == "closer"
    assert payload["adapter"] == "codex"
    assert payload["auth"] == "cli-session"
    assert payload["read_only"] is True
    assert "api_key" not in payload.values()


def test_conductor_executes_review_node_with_custom_routing():
    from agy_swarms.types import NodeSpec, TaskGraph
    from agy_swarms.conductor import Conductor
    from agy_swarms.adapters.scripted import ScriptedAdapter, CannedResult
    from agy_swarms.types import Epoch
    from agy_swarms.budget import Dims

    node = NodeSpec(id="rev", role="reviewer", objective="review code")
    graph = TaskGraph(nodes=[node])

    # Test Codex routing
    cond = Conductor(
        graph,
        ScriptedAdapter({}),
        limit=Dims(tokens=1000, usd=1.0),
        epoch=Epoch(epoch_seq=1, epoch_id="test"),
        reviewer="codex",
    )
    report = cond.run()
    assert report.status.value == "succeeded"
    assert report.results["rev"].artifact["route"]["adapter"] == "codex"
    assert report.results["rev"].artifact["route"]["transport"] == "codex-cli"

    # Test Claude routing
    cond_claude = Conductor(
        graph,
        ScriptedAdapter({}),
        limit=Dims(tokens=1000, usd=1.0),
        epoch=Epoch(epoch_seq=1, epoch_id="test"),
        reviewer="claude",
    )
    report_claude = cond_claude.run()
    assert report_claude.status.value == "succeeded"
    assert report_claude.results["rev"].artifact["route"]["adapter"] == "claude"
    assert report_claude.results["rev"].artifact["route"]["transport"] == "claude-code-cli"

    cond2 = Conductor(
        graph,
        ScriptedAdapter({"rev": CannedResult(status="succeeded", artifact={"ok": True})}),
        limit=Dims(tokens=1000, usd=1.0),
        epoch=Epoch(epoch_seq=1, epoch_id="test"),
        reviewer="agy",
    )
    report2 = cond2.run()
    assert report2.status.value == "succeeded"
    assert report2.results["rev"].artifact["ok"] is True


def test_off_adapter_routing():
    route = route_review_role(ReviewRole.REVIEWER, adapter="off")
    assert route.adapter == ReviewAdapter.OFF
    assert route.transport == "none"
    assert route.auth == "none"
    assert route.read_only is True
    assert route.reason == "user_disabled_cli_review"


def test_invalid_role_routing():
    with pytest.raises(ReviewRouteError, match="unknown review role"):
        route_review_role("invalid-role")


def test_conductor_with_disabled_reviewer():
    from agy_swarms.types import NodeSpec, TaskGraph
    from agy_swarms.conductor import Conductor
    from agy_swarms.adapters.scripted import ScriptedAdapter
    from agy_swarms.types import Epoch
    from agy_swarms.budget import Dims

    node = NodeSpec(id="rev", role="reviewer", objective="review code")
    graph = TaskGraph(nodes=[node])

    cond = Conductor(
        graph,
        ScriptedAdapter({}),
        limit=Dims(tokens=1000, usd=1.0),
        epoch=Epoch(epoch_seq=1, epoch_id="test"),
        reviewer="off",
    )
    report = cond.run()
    assert report.status.value == "succeeded"
    assert report.results["rev"].artifact["route"]["adapter"] == "off"
    assert report.results["rev"].artifact["route"]["transport"] == "none"


def test_conductor_review_budget_alert():
    from agy_swarms.types import NodeSpec, TaskGraph
    from agy_swarms.conductor import Conductor
    from agy_swarms.adapters.scripted import ScriptedAdapter, CannedResult
    from agy_swarms.types import Epoch
    from agy_swarms.budget import Dims

    node = NodeSpec(id="rev", role="reviewer", objective="review code")
    graph = TaskGraph(nodes=[node])

    # Run with token usage under the threshold (800 tokens)
    cond_under = Conductor(
        graph,
        ScriptedAdapter(
            {
                "rev": CannedResult(
                    status="succeeded",
                    artifact={"ok": True},
                    token_usage={
                        "input": 500,
                        "thinking": 200,
                        "output": 100,
                        "cached": 0,
                        "accounting": "exact",
                    },
                )
            }
        ),
        limit=Dims(tokens=5000, usd=2.0),
        epoch=Epoch(epoch_seq=1, epoch_id="test"),
        reviewer="agy",
    )
    cond_under.run()
    alerts_under = [e for e in cond_under.events if e.get("type") == "review_budget_alert"]
    assert len(alerts_under) == 0

    # Run with token usage over the threshold (1200 tokens)
    cond_over = Conductor(
        graph,
        ScriptedAdapter(
            {
                "rev": CannedResult(
                    status="succeeded",
                    artifact={"ok": True},
                    token_usage={
                        "input": 800,
                        "thinking": 900,
                        "output": 300,
                        "cached": 0,
                        "accounting": "exact",
                    },
                )
            }
        ),
        limit=Dims(tokens=5000, usd=2.0),
        epoch=Epoch(epoch_seq=1, epoch_id="test"),
        reviewer="agy",
    )
    cond_over.run()
    alerts_over = [e for e in cond_over.events if e.get("type") == "review_budget_alert"]
    assert len(alerts_over) == 1
    assert alerts_over[0]["node_id"] == "rev"
    assert alerts_over[0]["spent_tokens"] == 1200
    assert alerts_over[0]["threshold"] == 1000
    assert "exceeded lightweight token guardrail" in alerts_over[0]["warning"]


def test_conductor_closer_downgrade_auto_triage():
    from agy_swarms.types import NodeSpec, TaskGraph
    from agy_swarms.conductor import Conductor
    from agy_swarms.adapters.scripted import ScriptedAdapter, CannedResult
    from agy_swarms.types import Epoch
    from agy_swarms.budget import Dims

    nodes = [
        NodeSpec(id="rev", role="reviewer", objective="review code"),
        NodeSpec(id="cls", role="closer", objective="verify and close", dependencies=["rev"]),
    ]
    graph = TaskGraph(nodes=nodes)

    # Reviewer exceeds threshold, prompting closer downgrade
    cond = Conductor(
        graph,
        ScriptedAdapter(
            {
                "rev": CannedResult(
                    status="succeeded",
                    artifact={"ok": True},
                    token_usage={
                        "input": 800,
                        "thinking": 900,
                        "output": 300,
                        "cached": 0,
                        "accounting": "exact",
                    },
                ),
                "cls": CannedResult(
                    status="succeeded",
                    artifact={"ok": True},
                    token_usage={
                        "input": 100,
                        "thinking": 50,
                        "output": 50,
                        "cached": 0,
                        "accounting": "exact",
                    },
                ),
            }
        ),
        limit=Dims(tokens=5000, usd=2.0),
        epoch=Epoch(epoch_seq=1, epoch_id="test"),
        reviewer="agy",
        closer="agy",
    )
    report = cond.run()

    # Assert triage event was raised (agy -> codex)
    triage_events = [e for e in cond.events if e.get("type") == "review_auto_triage"]
    assert len(triage_events) == 1
    assert triage_events[0]["node_id"] == "rev"
    assert triage_events[0]["action"] == "downgrade_closer"
    assert triage_events[0]["previous_closer"] == "agy"
    assert triage_events[0]["new_closer"] == "codex"

    # Assert Conductor's closer attribute was modified
    assert cond.closer == "codex"

    # Assert closer node executed with the "codex" route configuration
    assert report.results["cls"].artifact["route"]["adapter"] == "codex"
    assert report.results["cls"].artifact["route"]["transport"] == "codex-cli"


def test_conductor_closer_downgrade_codex_to_off():
    from agy_swarms.types import NodeSpec, TaskGraph
    from agy_swarms.conductor import Conductor
    from agy_swarms.adapters.scripted import ScriptedAdapter, CannedResult
    from agy_swarms.types import Epoch
    from agy_swarms.budget import Dims

    nodes = [
        NodeSpec(id="rev", role="reviewer", objective="review code"),
        NodeSpec(id="cls", role="closer", objective="verify and close", dependencies=["rev"]),
    ]
    graph = TaskGraph(nodes=nodes)

    # Reviewer exceeds threshold, prompting closer downgrade from codex to off
    cond = Conductor(
        graph,
        ScriptedAdapter(
            {
                "rev": CannedResult(
                    status="succeeded",
                    artifact={"ok": True},
                    token_usage={
                        "input": 800,
                        "thinking": 900,
                        "output": 300,
                        "cached": 0,
                        "accounting": "exact",
                    },
                ),
                "cls": CannedResult(
                    status="succeeded",
                    artifact={"ok": True},
                    token_usage={
                        "input": 100,
                        "thinking": 50,
                        "output": 50,
                        "cached": 0,
                        "accounting": "exact",
                    },
                ),
            }
        ),
        limit=Dims(tokens=5000, usd=2.0),
        epoch=Epoch(epoch_seq=1, epoch_id="test"),
        reviewer="agy",
        closer="codex",
    )
    report = cond.run()

    # Assert triage event was raised (codex -> off)
    triage_events = [e for e in cond.events if e.get("type") == "review_auto_triage"]
    assert len(triage_events) == 1
    assert triage_events[0]["node_id"] == "rev"
    assert triage_events[0]["action"] == "downgrade_closer"
    assert triage_events[0]["previous_closer"] == "codex"
    assert triage_events[0]["new_closer"] == "off"

    # Assert Conductor's closer attribute was modified to off
    assert cond.closer == "off"

    # Assert closer node executed with the "off" route configuration
    assert report.results["cls"].artifact["route"]["adapter"] == "off"
    assert report.results["cls"].artifact["route"]["transport"] == "none"


def test_conductor_reviewer_fallback_on_failure():
    from agy_swarms.types import NodeSpec, TaskGraph
    from agy_swarms.conductor import Conductor
    from agy_swarms.adapters.scripted import ScriptedAdapter, CannedResult
    from agy_swarms.types import Epoch, ErrorClass
    from agy_swarms.budget import Dims

    node = NodeSpec(id="rev", role="reviewer", objective="review code")
    graph = TaskGraph(nodes=[node])

    # Run with reviewer=agy, but the scripted adapter canned result fails (simulate agy CLI failure)
    cond = Conductor(
        graph,
        ScriptedAdapter(
            {
                "rev": CannedResult(
                    status="failed",
                    error_class=ErrorClass.TIMEOUT,
                    artifact={},
                )
            }
        ),
        limit=Dims(tokens=5000, usd=2.0),
        epoch=Epoch(epoch_seq=1, epoch_id="test"),
        reviewer="agy",
    )
    report = cond.run()

    # Assert model_switch was raised (agy -> codex)
    switch_events = [e for e in cond.events if e.get("type") == "model_switch"]
    assert len(switch_events) == 1
    assert switch_events[0]["node_id"] == "rev"
    assert switch_events[0]["from"] == "agy"
    assert switch_events[0]["to"] == "codex"
    assert switch_events[0]["error_class"] == "timeout"

    # Conductor reviewer attribute updated to codex
    assert cond.reviewer == "codex"

    # Node status should be succeeded (the fallback to codex succeeded)
    assert report.status.value == "succeeded"
    assert report.results["rev"].status == "succeeded"
    assert report.results["rev"].artifact["route"]["adapter"] == "codex"


def test_reviewer_can_use_ollama_when_user_selects_it():
    route = route_review_role(ReviewRole.REVIEWER, adapter="ollama")
    assert route.adapter == ReviewAdapter.OLLAMA
    assert route.transport == "ollama-cli"
    assert route.auth == "none"
    assert route.model == "default"
    assert route.read_only is True
    assert route.reason == "user_selected_local_ollama"


def test_closer_can_use_llamafile_when_user_selects_it():
    route = route_review_role(ReviewRole.CLOSER, adapter="llamafile")
    assert route.adapter == ReviewAdapter.LLAMAFILE
    assert route.transport == "llamafile-cli"
    assert route.auth == "none"
    assert route.model == "default"
    assert route.read_only is True
    assert route.reason == "user_selected_local_llamafile"
