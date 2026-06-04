from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from agy_swarms.loop.agent_loop import AgentLoop, AgentStep, ToolCall
from agy_swarms.loop.tools import ToolRegistry, ToolSchemaError


@dataclass
class ScriptedModel:
    steps: list[AgentStep]
    calls: int = 0

    def next_step(self, history):
        self.calls += 1
        return self.steps.pop(0)


def test_agent_loop_dispatches_registered_tool_and_records_duration():
    times = iter([10.0, 10.25])
    registry = ToolRegistry(clock=lambda: next(times))
    registry.register(
        "add",
        lambda args: {"sum": args["left"] + args["right"]},
        schema={
            "type": "object",
            "required": ["left", "right"],
            "properties": {"left": {"type": "integer"}, "right": {"type": "integer"}},
            "additionalProperties": False,
        },
    )
    model = ScriptedModel(
        [
            AgentStep(tool_call=ToolCall("add", {"left": 2, "right": 3})),
            AgentStep(final="done"),
        ]
    )

    result = AgentLoop(registry).run("add numbers", model, max_turns=3, tool_allowlist=["add"])

    assert result.status == "succeeded"
    assert result.final == "done"
    assert result.turns == 2
    assert result.tool_observations[0].tool_name == "add"
    assert result.tool_observations[0].result == {"sum": 5}
    assert result.tool_observations[0].duration_s == pytest.approx(0.25)


def test_agent_loop_halts_at_max_turns_without_extra_model_call():
    calls = []
    registry = ToolRegistry(clock=lambda: 0.0)
    registry.register("noop", lambda args: calls.append(args) or {"ok": True})
    model = ScriptedModel(
        [
            AgentStep(tool_call=ToolCall("noop", {"turn": 1})),
            AgentStep(tool_call=ToolCall("noop", {"turn": 2})),
            AgentStep(tool_call=ToolCall("noop", {"turn": 3})),
        ]
    )

    result = AgentLoop(registry).run("loop forever", model, max_turns=2, tool_allowlist=["noop"])

    assert result.status == "max_turns_exceeded"
    assert result.turns == 2
    assert model.calls == 2
    assert calls == [{"turn": 1}, {"turn": 2}]
    assert result.blockers == [{"kind": "max_turns", "detail": "max_turns=2 reached"}]


def test_agent_loop_never_executes_model_emitted_strings_as_code(tmp_path: Path):
    marker = tmp_path / "executed"
    payload = f"__import__('pathlib').Path({str(marker)!r}).write_text('bad')"
    registry = ToolRegistry(clock=lambda: 0.0)
    model = ScriptedModel([AgentStep(tool_call=ToolCall(payload, {"ignored": True}))])

    result = AgentLoop(registry).run(
        "malicious tool name", model, max_turns=1, tool_allowlist=["safe"]
    )

    assert result.status == "failed"
    assert result.blockers == [{"kind": "tool", "detail": f"tool not allowed: {payload}"}]
    assert not marker.exists()


def test_tool_registry_rejects_arguments_outside_schema():
    registry = ToolRegistry(clock=lambda: 0.0)
    registry.register(
        "echo",
        lambda args: args,
        schema={
            "type": "object",
            "required": ["message"],
            "properties": {"message": {"type": "string"}},
            "additionalProperties": False,
        },
    )

    with pytest.raises(ToolSchemaError, match="unexpected argument"):
        registry.dispatch("echo", {"message": "hi", "extra": "nope"})
