"""Shared Codex model profiles for agy-swarms role routing."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

CODEX_STRONG_MODEL = "gpt-5.5"
CODEX_LIGHT_MODEL = "gpt-5.3-codex-spark"
CODEX_STRONG_REASONING_EFFORT = "high"
CODEX_LIGHT_REASONING_EFFORT = "medium"
CODEX_LIGHT_REASONING_EFFORT_LOW = "low"
CODEX_AUTHORITY_ROLES = frozenset({"planner", "reviewer", "evaluator", "closer"})


@dataclass(frozen=True)
class CodexRoleModel:
    """One resolved role-specific Codex model profile."""

    model: str
    reasoning_effort: str
    profile: str


def resolve_codex_role_model(
    role: str,
    *,
    env: Mapping[str, str] | None = None,
    light_effort: str | None = None,
) -> CodexRoleModel:
    """Resolve default Codex model and reasoning effort for one role."""
    source = env if env is not None else os.environ
    normalized_role = role.casefold()
    role_key = normalized_role.upper().replace("-", "_")
    if normalized_role in CODEX_AUTHORITY_ROLES:
        model = (
            source.get(f"AGY_CODEX_{role_key}_MODEL")
            or source.get("AGY_CODEX_STRONG_MODEL")
            or source.get("AGY_CODEX_MODEL")
            or CODEX_STRONG_MODEL
        )
        effort = (
            source.get(f"AGY_CODEX_{role_key}_REASONING_EFFORT")
            or source.get("AGY_CODEX_STRONG_REASONING_EFFORT")
            or source.get("AGY_CODEX_REASONING_EFFORT")
            or CODEX_STRONG_REASONING_EFFORT
        )
        return CodexRoleModel(model=model, reasoning_effort=effort, profile="codex_high")

    model = (
        source.get(f"AGY_CODEX_{role_key}_MODEL")
        or source.get("AGY_CODEX_LIGHT_MODEL")
        or source.get("AGY_CODEX_MODEL")
        or CODEX_LIGHT_MODEL
    )
    effort = (
        source.get(f"AGY_CODEX_{role_key}_REASONING_EFFORT")
        or source.get("AGY_CODEX_LIGHT_REASONING_EFFORT")
        or light_effort
        or CODEX_LIGHT_REASONING_EFFORT
    )
    return CodexRoleModel(model=model, reasoning_effort=effort, profile="codex_spark")
