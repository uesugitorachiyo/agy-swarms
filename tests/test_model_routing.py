"""FR-20 model-tier routing and escalation accounting."""

import json
from pathlib import Path

from agy_swarms.budget import Dims
from agy_swarms.model_routing import (
    ModelTier,
    resolve_thinking_config,
    route_model_tier,
    run_model_router_fixture,
)
from agy_swarms.types import Caps, NodeSpec


def _node(
    *,
    role: str = "worker",
    caps: Caps | None = None,
    objective: str = "do useful work",
) -> NodeSpec:
    return NodeSpec(
        id="n",
        role=role,
        objective=objective,
        caps=caps or Caps(max_output_tokens=100, max_thinking_tokens=50),
    )


def test_default_worker_stays_on_oauth_flash_high():
    decision = route_model_tier(_node())

    assert decision.tier == ModelTier.FLASH_HIGH
    assert decision.transport == "agy"
    assert decision.auth == "oauth"
    assert decision.escalated is False
    assert decision.reason == "default_flash_high"


def test_fixture_expected_model_tiers_reproduce_at_100_percent():
    result = run_model_router_fixture(
        router_cases_path=Path("benchmarks/router_cases.json"),
        lockfile_path=Path("agy.lock"),
    )

    assert result["passed"] is True
    assert result["accuracy"] == 1.0
    assert result["matched"] == result["total"] == 3
    assert result["router_cases_sha_matches_lock"] is True
    assert all(case["matched"] for case in result["cases"])
    assert {case["actual_model_tier"] for case in result["cases"]} == {"flash_high"}


def test_repeated_failure_escalates_to_pro_api_when_budget_allows():
    decision = route_model_tier(
        _node(caps=Caps(max_output_tokens=250, max_thinking_tokens=25)),
        failed_attempts=2,
        remaining_budget=Dims(tokens=1_000, usd=1.0),
    )

    assert decision.tier == ModelTier.PRO
    assert decision.transport == "gemini_api"
    assert decision.auth == "api_key"
    assert decision.escalated is True
    assert decision.budget_admitted is True
    assert decision.escalation_charge.tokens == 275
    assert decision.evidence["trigger"] == "repeated_failure"


def test_high_value_flag_escalates_to_pro_api_when_budget_allows():
    decision = route_model_tier(
        _node(),
        high_value=True,
        remaining_budget=Dims(tokens=500, usd=1.0),
    )

    assert decision.tier == ModelTier.PRO
    assert decision.escalated is True
    assert decision.evidence["trigger"] == "explicit_high_value"


def test_escalation_is_blocked_when_budget_does_not_allow_it():
    decision = route_model_tier(
        _node(caps=Caps(max_output_tokens=400, max_thinking_tokens=100)),
        failed_attempts=3,
        remaining_budget=Dims(tokens=499, usd=1.0),
    )

    assert decision.tier == ModelTier.FLASH_HIGH
    assert decision.transport == "agy"
    assert decision.escalated is False
    assert decision.budget_admitted is False
    assert decision.escalation_charge == Dims(tokens=500, usd=0.0)
    assert "escalation_budget_blocked" in decision.concerns


def test_fixture_result_is_json_serializable():
    result = run_model_router_fixture(
        router_cases_path=Path("benchmarks/router_cases.json"),
        lockfile_path=Path("agy.lock"),
    )

    assert json.loads(json.dumps(result))["gate"] == "AC-3/model-router-fixture"


def test_resolve_thinking_config_gemini_3():
    # Gemini 3.x series
    assert resolve_thinking_config("gemini-3.5-flash", ModelTier.FLASH_HIGH) == {
        "thinking_config": {"thinking_level": "high"}
    }
    assert resolve_thinking_config("gemini-3.5-flash-lite", ModelTier.FLASH_LITE) == {
        "thinking_config": {"thinking_level": "low"}
    }
    assert resolve_thinking_config("gemini-3.1-pro", ModelTier.PRO) == {
        "thinking_config": {"thinking_level": "high"}
    }


def test_resolve_thinking_config_gemini_2_5():
    # Gemini 2.5 series
    assert resolve_thinking_config("gemini-2.5-flash", ModelTier.FLASH_HIGH) == {
        "thinking_budget": -1
    }
    assert resolve_thinking_config("gemini-2.5-flash-lite", ModelTier.FLASH_LITE) == {
        "thinking_budget": 0
    }
