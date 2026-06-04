"""FR-20 model-tier routing and escalation evidence."""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .budget import Dims, est
from .types import Caps, NodeSpec

__all__ = [
    "ModelRouteDecision",
    "ModelTier",
    "route_model_tier",
    "run_model_router_fixture",
    "resolve_thinking_config",
]


class ModelTier(StrEnum):
    """FR-20 model-tier classes."""

    FLASH_LITE = "flash_lite"
    FLASH_HIGH = "flash_high"
    PRO = "pro"


@dataclass(frozen=True)
class ModelRouteDecision:
    """One deterministic model-tier route decision."""

    tier: ModelTier
    transport: str
    auth: str
    reason: str
    escalated: bool = False
    budget_admitted: bool = True
    escalation_charge: Dims = Dims()
    concerns: tuple[str, ...] = ()
    evidence: dict[str, Any] | None = None


def route_model_tier(
    node: NodeSpec,
    *,
    failed_attempts: int = 0,
    high_value: bool = False,
    remaining_budget: Dims | None = None,
    allow_low_tier: bool = False,
) -> ModelRouteDecision:
    """Route one node to its model tier.

    Defaults stay on the OAuth-backed agy Flash-high path. Escalation is only admitted for
    repeated failure or explicit high-value work, and only when the caller supplies enough
    remaining budget for the node's caps-driven estimate.
    """
    trigger = _escalation_trigger(failed_attempts=failed_attempts, high_value=high_value)
    if trigger is not None:
        charge = Dims(tokens=est(node), usd=0.0)
        admitted = remaining_budget is not None and charge.fits_within(remaining_budget)
        if admitted:
            return ModelRouteDecision(
                tier=ModelTier.PRO,
                transport="gemini_api",
                auth="api_key",
                reason="budget_admitted_escalation",
                escalated=True,
                budget_admitted=True,
                escalation_charge=charge,
                evidence={
                    "trigger": trigger,
                    "failed_attempts": failed_attempts,
                    "charge": asdict(charge),
                },
            )
        return ModelRouteDecision(
            tier=ModelTier.FLASH_HIGH,
            transport="agy",
            auth="oauth",
            reason="escalation_budget_blocked",
            escalated=False,
            budget_admitted=False,
            escalation_charge=charge,
            concerns=("escalation_budget_blocked",),
            evidence={
                "trigger": trigger,
                "failed_attempts": failed_attempts,
                "charge": asdict(charge),
                "remaining_budget": asdict(remaining_budget) if remaining_budget else None,
            },
        )

    if allow_low_tier and _is_trivial(node):
        return ModelRouteDecision(
            tier=ModelTier.FLASH_LITE,
            transport="agy",
            auth="oauth",
            reason="trivial_low_tier",
        )
    return ModelRouteDecision(
        tier=ModelTier.FLASH_HIGH,
        transport="agy",
        auth="oauth",
        reason="default_flash_high",
    )


def run_model_router_fixture(
    *,
    router_cases_path: Path = Path("benchmarks/router_cases.json"),
    lockfile_path: Path = Path("agy.lock"),
) -> dict[str, Any]:
    """Evaluate expected FR-20 model-tier labels in the pinned router fixture."""
    cases = json.loads(router_cases_path.read_text())
    content = router_cases_path.read_bytes().replace(b"\r\n", b"\n")
    actual_sha = hashlib.sha256(content).hexdigest()
    locked_sha = _locked_router_cases_sha(lockfile_path)
    evaluated: list[dict[str, Any]] = []
    for case in cases:
        node = NodeSpec(
            id=str(case["id"]),
            role="worker",
            objective=str(case["task"]),
            caps=Caps(max_output_tokens=100, max_thinking_tokens=50),
        )
        decision = route_model_tier(node)
        expected = str(case["expected_model_tier"])
        actual = decision.tier.value
        evaluated.append(
            {
                "id": case["id"],
                "expected_model_tier": expected,
                "actual_model_tier": actual,
                "matched": actual == expected,
                "transport": decision.transport,
                "auth": decision.auth,
                "reason": decision.reason,
                "escalated": decision.escalated,
            }
        )

    matched = sum(1 for case in evaluated if case["matched"])
    total = len(evaluated)
    accuracy = matched / total if total else 0.0
    sha_matches_lock = actual_sha == locked_sha
    return {
        "gate": "AC-3/model-router-fixture",
        "passed": total > 0 and matched == total and sha_matches_lock,
        "accuracy": accuracy,
        "matched": matched,
        "total": total,
        "router_cases_path": str(router_cases_path),
        "router_cases_sha": actual_sha,
        "locked_router_cases_sha": locked_sha,
        "router_cases_sha_matches_lock": sha_matches_lock,
        "cases": evaluated,
    }


def _escalation_trigger(*, failed_attempts: int, high_value: bool) -> str | None:
    if high_value:
        return "explicit_high_value"
    if failed_attempts >= 2:
        return "repeated_failure"
    return None


def _is_trivial(node: NodeSpec) -> bool:
    text = f"{node.role} {node.objective}".casefold()
    return any(term in text for term in ("trivial", "rename", "single file", "small"))


def _locked_router_cases_sha(lockfile_path: Path) -> str:
    data = tomllib.loads(lockfile_path.read_text())
    return str(data.get("benchmarks", {}).get("router_cases_sha", ""))


def resolve_thinking_config(model_id: str, tier: ModelTier | str) -> dict[str, Any]:
    """Resolve the appropriate API request thinking configuration dictionary based on model generation.

    Gemini 3.x series uses categorical `thinking_level` inside `thinking_config`
    (e.g., {"thinking_config": {"thinking_level": "high"}}).

    Gemini 2.5 series uses numeric `thinking_budget` (e.g., {"thinking_budget": -1}).

    Never send both on a Gemini-3 model.
    """
    model_lower = model_id.lower()

    # Check if Gemini 3.x or 3.5 series
    is_gemini_3 = (
        "gemini-3" in model_lower or "gemini-3.5" in model_lower or "gemini-3.1" in model_lower
    )

    if is_gemini_3:
        # Map ModelTier or tier string to categorical thinking_level
        # Levels: minimal | low | medium | high
        if "lite" in str(tier).lower():
            level = "low"
        elif "low" in str(tier).lower():
            level = "low"
        elif "medium" in str(tier).lower():
            level = "medium"
        else:
            level = "high"
        return {"thinking_config": {"thinking_level": level}}
    else:
        # Default/Fallback to Gemini 2.5-gen budget: numeric integer (-1 = dynamic/max effort)
        # Trivial tiers or Lite may map to 0 (disabled thinking)
        if "lite" in str(tier).lower() or "low" in str(tier).lower():
            budget = 0
        else:
            budget = -1
        return {"thinking_budget": budget}
