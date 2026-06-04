from __future__ import annotations

from agy_swarms.io.prompts import (
    PromptExample,
    PromptHistoryMessage,
    PromptInput,
    ToolPromptSpec,
    assemble_prompt,
)


def _bundle_with_reordered_dicts():
    return assemble_prompt(
        tools=[
            ToolPromptSpec(
                name="write",
                description="Write a file",
                schema={
                    "required": ["path", "content"],
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "path": {"type": "string"},
                    },
                },
            ),
            ToolPromptSpec(
                name="read",
                description="Read a file",
                schema={
                    "properties": {"path": {"type": "string"}},
                    "type": "object",
                    "required": ["path"],
                },
            ),
        ],
        system="Return compact JSON artifacts with pointers.",
        examples=[
            PromptExample(
                name="artifact",
                input={"objective": "summarize", "scope": ["a", "b"]},
                output={"pointers": ["a"], "summary": "done"},
            )
        ],
        history=[
            PromptHistoryMessage(
                role="assistant", content="prior", metadata={"created_at": "2026-05-31T00:00:00Z"}
            )
        ],
        user_input=PromptInput(
            objective="Inspect docs",
            context={"z": 1, "a": 2},
            metadata={"timestamp": "2026-05-31T00:00:01Z"},
        ),
    )


def test_prompt_assembly_uses_static_to_dynamic_section_order():
    bundle = _bundle_with_reordered_dicts()

    assert bundle.full_prompt.index("<tools>") < bundle.full_prompt.index("<system>")
    assert bundle.full_prompt.index("<system>") < bundle.full_prompt.index("<examples>")
    assert bundle.full_prompt.index("<examples>") < bundle.full_prompt.index("<history>")
    assert bundle.full_prompt.index("<history>") < bundle.full_prompt.index("<input>")


def test_cacheable_prefix_is_byte_stable_with_deterministic_key_ordering():
    first = _bundle_with_reordered_dicts()
    second = assemble_prompt(
        tools=[
            ToolPromptSpec(
                name="read",
                description="Read a file",
                schema={
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                    "type": "object",
                },
            ),
            ToolPromptSpec(
                name="write",
                description="Write a file",
                schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            ),
        ],
        system="Return compact JSON artifacts with pointers.",
        examples=[
            PromptExample(
                name="artifact",
                input={"scope": ["a", "b"], "objective": "summarize"},
                output={"summary": "done", "pointers": ["a"]},
            )
        ],
        history=[
            PromptHistoryMessage(
                role="assistant", content="prior", metadata={"created_at": "different"}
            )
        ],
        user_input=PromptInput(
            objective="Inspect docs",
            context={"a": 2, "z": 1},
            metadata={"timestamp": "different"},
        ),
    )

    assert first.cacheable_prefix == second.cacheable_prefix
    assert first.cacheable_prefix_sha256 == second.cacheable_prefix_sha256
    assert '"content":{"type":"string"}' in first.cacheable_prefix
    assert "b'" not in first.cacheable_prefix
    write_schema = first.cacheable_prefix.split('"name":"write"', maxsplit=1)[1]
    assert write_schema.index('"content"') < write_schema.index('"path"')


def test_cacheable_prefix_excludes_history_input_and_timestamps():
    bundle = _bundle_with_reordered_dicts()

    assert "prior" not in bundle.cacheable_prefix
    assert "Inspect docs" not in bundle.cacheable_prefix
    assert "2026-05-31" not in bundle.cacheable_prefix
    assert "AGY_SWARM_SYSTEM_PROMPT_V1" in bundle.cacheable_prefix
    assert "Inspect docs" in bundle.full_prompt
