"""Agent loop substrate (FR-9).

The loop package owns model→tool→observe iteration, tool registry dispatch, and
per-tool timing. It deliberately contains no dynamic code execution path.
"""

from .agent_loop import AgentLoop, AgentRunResult, AgentStep, ToolCall
from .tools import RegisteredTool, ToolObservation, ToolRegistry

__all__ = [
    "AgentLoop",
    "AgentRunResult",
    "AgentStep",
    "RegisteredTool",
    "ToolCall",
    "ToolObservation",
    "ToolRegistry",
]
