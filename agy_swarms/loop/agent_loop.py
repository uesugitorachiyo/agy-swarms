"""Model→tool→observe loop substrate (FR-9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .tools import ToolNotFoundError, ToolObservation, ToolRegistry, ToolSchemaError

__all__ = [
    "AgentLoop",
    "AgentModel",
    "AgentRunResult",
    "AgentStep",
    "ToolCall",
]


@dataclass(frozen=True)
class ToolCall:
    """A model-requested tool call."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentStep:
    """One model step: either final text or a tool call."""

    final: str | None = None
    tool_call: ToolCall | None = None


class AgentModel(Protocol):
    """Minimal protocol for a stepwise model driver."""

    def next_step(self, history: list[dict[str, Any]]) -> AgentStep:
        """Return the next model step from the current loop history."""


@dataclass
class AgentRunResult:
    """Terminal result of an agent-loop run."""

    status: str
    turns: int
    final: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    tool_observations: list[ToolObservation] = field(default_factory=list)
    blockers: list[dict[str, str]] = field(default_factory=list)


class AgentLoop:
    """Run a bounded model→tool→observe loop over a closed tool registry."""

    def __init__(self, tools: ToolRegistry) -> None:
        self.tools = tools

    def run(
        self,
        objective: str,
        model: AgentModel,
        *,
        max_turns: int,
        tool_allowlist: list[str] | tuple[str, ...],
    ) -> AgentRunResult:
        if max_turns < 1:
            raise ValueError("max_turns must be >= 1")
        allowed = set(tool_allowlist)
        history: list[dict[str, Any]] = [{"role": "user", "content": objective}]
        observations: list[ToolObservation] = []
        blockers: list[dict[str, str]] = []

        for turn in range(1, max_turns + 1):
            step = model.next_step(history)
            history.append(_step_record(step))
            if step.final is not None:
                return AgentRunResult(
                    status="succeeded",
                    turns=turn,
                    final=step.final,
                    history=history,
                    tool_observations=observations,
                )
            if step.tool_call is None:
                blockers.append({"kind": "model", "detail": "empty model step"})
                return AgentRunResult(
                    status="failed",
                    turns=turn,
                    history=history,
                    tool_observations=observations,
                    blockers=blockers,
                )
            if step.tool_call.name not in allowed:
                blockers.append(
                    {"kind": "tool", "detail": f"tool not allowed: {step.tool_call.name}"}
                )
                return AgentRunResult(
                    status="failed",
                    turns=turn,
                    history=history,
                    tool_observations=observations,
                    blockers=blockers,
                )
            try:
                observation = self.tools.dispatch(step.tool_call.name, step.tool_call.arguments)
            except (ToolNotFoundError, ToolSchemaError) as exc:
                blockers.append({"kind": "tool", "detail": str(exc)})
                return AgentRunResult(
                    status="failed",
                    turns=turn,
                    history=history,
                    tool_observations=observations,
                    blockers=blockers,
                )
            observations.append(observation)
            history.append(_observation_record(observation))
            if not observation.ok:
                blockers.append(
                    {
                        "kind": "tool",
                        "detail": observation.error or f"tool failed: {observation.tool_name}",
                    }
                )
                return AgentRunResult(
                    status="failed",
                    turns=turn,
                    history=history,
                    tool_observations=observations,
                    blockers=blockers,
                )

        return AgentRunResult(
            status="max_turns_exceeded",
            turns=max_turns,
            history=history,
            tool_observations=observations,
            blockers=[{"kind": "max_turns", "detail": f"max_turns={max_turns} reached"}],
        )


def _step_record(step: AgentStep) -> dict[str, Any]:
    if step.final is not None:
        return {"role": "assistant", "final": step.final}
    if step.tool_call is not None:
        return {
            "role": "assistant",
            "tool_call": {
                "name": step.tool_call.name,
                "arguments": dict(step.tool_call.arguments),
            },
        }
    return {"role": "assistant"}


def _observation_record(observation: ToolObservation) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": "tool",
        "tool_name": observation.tool_name,
        "ok": observation.ok,
        "duration_s": observation.duration_s,
    }
    if observation.ok:
        payload["result"] = observation.result
    else:
        payload["error"] = observation.error
    return payload
