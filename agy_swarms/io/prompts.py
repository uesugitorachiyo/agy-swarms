"""Cache-stable prompt assembly (FR-27)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..canonical import canonical, sha256_hex

__all__ = [
    "PromptBundle",
    "PromptExample",
    "PromptHistoryMessage",
    "PromptInput",
    "SWARM_SYSTEM_PROMPT",
    "ToolPromptSpec",
    "assemble_prompt",
]

SWARM_SYSTEM_PROMPT = (
    "AGY_SWARM_SYSTEM_PROMPT_V1\n"
    "You are an agy-swarms worker. Follow the scoped objective, use only allowed tools, "
    "return compact artifacts with pointers, and do not include raw transcripts."
)


@dataclass(frozen=True)
class ToolPromptSpec:
    """Static tool declaration included in the cacheable prefix."""

    name: str
    description: str = ""
    schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptExample:
    """Static example included in the cacheable prefix."""

    name: str
    input: dict[str, Any]
    output: dict[str, Any]


@dataclass(frozen=True)
class PromptHistoryMessage:
    """Dynamic history message excluded from the cacheable prefix."""

    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptInput:
    """Dynamic user/node input excluded from the cacheable prefix."""

    objective: str
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptBundle:
    """Assembled prompt plus the exact cacheable prefix bytes."""

    full_prompt: str
    cacheable_prefix: str
    cacheable_prefix_sha256: str
    sections: tuple[str, ...]


def assemble_prompt(
    *,
    tools: list[ToolPromptSpec] | tuple[ToolPromptSpec, ...],
    system: str,
    examples: list[PromptExample] | tuple[PromptExample, ...] = (),
    history: list[PromptHistoryMessage] | tuple[PromptHistoryMessage, ...] = (),
    user_input: PromptInput,
) -> PromptBundle:
    """Assemble prompt sections static→dynamic with a byte-stable prefix.

    Cacheable prefix contains only static material: tools, shared system prompt, caller
    system text, and examples. Dynamic history/input are appended after the prefix.
    """
    static_sections = [
        _section("tools", [_tool_payload(t) for t in sorted(tools, key=lambda t: t.name)]),
        _section(
            "system",
            {
                "shared": SWARM_SYSTEM_PROMPT,
                "task": system,
            },
        ),
        _section("examples", [_example_payload(e) for e in sorted(examples, key=lambda e: e.name)]),
    ]
    dynamic_sections = [
        _section("history", [_history_payload(m) for m in history]),
        _section("input", _input_payload(user_input)),
    ]
    cacheable_prefix = "\n".join(static_sections) + "\n"
    full_prompt = cacheable_prefix + "\n".join(dynamic_sections) + "\n"
    return PromptBundle(
        full_prompt=full_prompt,
        cacheable_prefix=cacheable_prefix,
        cacheable_prefix_sha256=sha256_hex(cacheable_prefix.encode("utf-8")),
        sections=("tools", "system", "examples", "history", "input"),
    )


def _section(name: str, payload: Any) -> str:
    return f"<{name}>\n{canonical(payload).decode('utf-8')}\n</{name}>"


def _tool_payload(tool: ToolPromptSpec) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "schema": tool.schema,
    }


def _example_payload(example: PromptExample) -> dict[str, Any]:
    return {
        "name": example.name,
        "input": example.input,
        "output": example.output,
    }


def _history_payload(message: PromptHistoryMessage) -> dict[str, Any]:
    return {
        "role": message.role,
        "content": message.content,
        "metadata": message.metadata,
    }


def _input_payload(prompt_input: PromptInput) -> dict[str, Any]:
    return {
        "objective": prompt_input.objective,
        "context": prompt_input.context,
        "metadata": prompt_input.metadata,
    }
