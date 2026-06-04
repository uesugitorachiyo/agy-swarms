"""Tool registry and dict-dispatch execution for the FR-9 agent loop."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "RegisteredTool",
    "ToolError",
    "ToolNotFoundError",
    "ToolObservation",
    "ToolRegistry",
    "ToolSchemaError",
]


class ToolError(Exception):
    """Base class for tool-dispatch failures."""


class ToolNotFoundError(ToolError):
    """Raised when a model requests a tool absent from the registry."""


class ToolSchemaError(ToolError):
    """Raised when tool arguments do not match the registered schema subset."""


@dataclass(frozen=True)
class RegisteredTool:
    """One dictionary-dispatched tool entry."""

    name: str
    func: Callable[[dict[str, Any]], Any]
    schema: dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass(frozen=True)
class ToolObservation:
    """The normalized observation emitted after one tool call."""

    tool_name: str
    ok: bool
    duration_s: float
    result: Any = None
    error: str | None = None


class ToolRegistry:
    """Closed registry for agent-loop tools.

    Tool execution is pure dictionary dispatch by registered name. Model-emitted text is
    never interpreted as code; a requested name either matches a registered entry or fails.
    """

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        self._clock = clock or time.perf_counter

    def register(
        self,
        name: str,
        func: Callable[[dict[str, Any]], Any],
        *,
        schema: dict[str, Any] | None = None,
        description: str = "",
    ) -> None:
        if not name:
            raise ValueError("tool name must be non-empty")
        self._tools[name] = RegisteredTool(
            name=name,
            func=func,
            schema=dict(schema or {}),
            description=description,
        )

    def dispatch(self, name: str, arguments: Mapping[str, Any] | None = None) -> ToolObservation:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(f"unknown tool: {name}")
        args = dict(arguments or {})
        _validate_args(tool.schema, args)
        started = self._clock()
        try:
            result = tool.func(args)
        except Exception as exc:  # noqa: BLE001 - tool failure becomes observation.
            ended = self._clock()
            return ToolObservation(
                tool_name=name,
                ok=False,
                duration_s=ended - started,
                error=f"{type(exc).__name__}: {exc}",
            )
        ended = self._clock()
        return ToolObservation(
            tool_name=name,
            ok=True,
            duration_s=ended - started,
            result=result,
        )


def _validate_args(schema: Mapping[str, Any], args: Mapping[str, Any]) -> None:
    """Validate a small JSON-schema subset used by local tools.

    Phase 2 needs deterministic, dependency-free checks for object-shaped tool
    arguments. This covers the registered schemas currently used by tests and fixtures:
    object type, required fields, primitive property types, and additionalProperties.
    """
    if not schema:
        return
    if schema.get("type", "object") != "object":
        raise ToolSchemaError("tool schema root must be an object")

    required = set(schema.get("required", []))
    missing = sorted(required - set(args))
    if missing:
        raise ToolSchemaError(f"missing required argument: {missing[0]}")

    properties = schema.get("properties", {})
    if schema.get("additionalProperties", True) is False:
        unexpected = sorted(set(args) - set(properties))
        if unexpected:
            raise ToolSchemaError(f"unexpected argument: {unexpected[0]}")

    for key, value in args.items():
        spec = properties.get(key)
        if spec is None:
            continue
        expected = spec.get("type")
        if expected is not None and not _matches_type(value, expected):
            raise ToolSchemaError(f"argument {key!r} must be {expected}")


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, int | float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "null":
        return value is None
    raise ToolSchemaError(f"unsupported schema type: {expected}")
