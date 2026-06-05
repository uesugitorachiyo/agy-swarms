"""Deterministic reviewer/closer routing for optional local CLI diversity."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum

__all__ = [
    "ReviewAdapter",
    "ReviewRole",
    "ReviewRoute",
    "ReviewRouteError",
    "route_review_role",
]


class ReviewRouteError(ValueError):
    """Raised when reviewer/closer routing cannot be resolved safely."""


class ReviewRole(StrEnum):
    """Read-only quality roles separate from worker execution."""

    REVIEWER = "reviewer"
    CLOSER = "closer"


class ReviewAdapter(StrEnum):
    """Supported local CLI adapters for review roles."""

    AGY = "agy"
    CODEX = "codex"
    CLAUDE = "claude"
    OLLAMA = "ollama"
    LLAMAFILE = "llamafile"
    OFF = "off"


@dataclass(frozen=True)
class ReviewRoute:
    """One deterministic reviewer/closer route decision."""

    role: ReviewRole
    adapter: ReviewAdapter
    transport: str
    auth: str
    model: str
    read_only: bool
    temperature: int
    requires_passing_gates: bool
    reason: str

    def to_json(self) -> dict[str, object]:
        """Return a stable JSON-compatible evidence payload."""
        payload = asdict(self)
        payload["role"] = self.role.value
        payload["adapter"] = self.adapter.value
        return payload


def route_review_role(
    role: ReviewRole | str, *, adapter: ReviewAdapter | str | None = None
) -> ReviewRoute:
    """Route a reviewer/closer role without requiring premium subscriptions by default."""
    review_role = _coerce_role(role)
    review_adapter = _coerce_adapter(adapter or ReviewAdapter.AGY)
    if review_adapter == ReviewAdapter.OFF:
        return ReviewRoute(
            role=review_role,
            adapter=review_adapter,
            transport="none",
            auth="none",
            model="none",
            read_only=True,
            temperature=0,
            requires_passing_gates=True,
            reason="user_disabled_cli_review",
        )
    if review_adapter == ReviewAdapter.AGY:
        return ReviewRoute(
            role=review_role,
            adapter=review_adapter,
            transport="agy",
            auth="oauth",
            model="gemini-3.5-flash",
            read_only=True,
            temperature=0,
            requires_passing_gates=True,
            reason="default_gemini_cli_review",
        )
    if review_adapter == ReviewAdapter.CODEX:
        return ReviewRoute(
            role=review_role,
            adapter=review_adapter,
            transport="codex-cli",
            auth="cli-session",
            model="gpt-5.5",
            read_only=True,
            temperature=0,
            requires_passing_gates=True,
            reason="user_selected_cli_review",
        )
    if review_adapter == ReviewAdapter.CLAUDE:
        return ReviewRoute(
            role=review_role,
            adapter=review_adapter,
            transport="claude-code-cli",
            auth="cli-session",
            model="gpt-5.5-high",
            read_only=True,
            temperature=0,
            requires_passing_gates=True,
            reason="user_selected_cli_review",
        )
    if review_adapter == ReviewAdapter.OLLAMA:
        return ReviewRoute(
            role=review_role,
            adapter=review_adapter,
            transport="ollama-cli",
            auth="none",
            model="default",
            read_only=True,
            temperature=0,
            requires_passing_gates=True,
            reason="user_selected_local_ollama",
        )
    if review_adapter == ReviewAdapter.LLAMAFILE:
        return ReviewRoute(
            role=review_role,
            adapter=review_adapter,
            transport="llamafile-cli",
            auth="none",
            model="default",
            read_only=True,
            temperature=0,
            requires_passing_gates=True,
            reason="user_selected_local_llamafile",
        )
    raise ReviewRouteError(f"unknown review adapter: {review_adapter}")


def _coerce_role(value: ReviewRole | str) -> ReviewRole:
    try:
        return value if isinstance(value, ReviewRole) else ReviewRole(str(value))
    except ValueError as exc:
        raise ReviewRouteError(f"unknown review role: {value}") from exc


def _coerce_adapter(value: ReviewAdapter | str) -> ReviewAdapter:
    try:
        return value if isinstance(value, ReviewAdapter) else ReviewAdapter(str(value))
    except ValueError as exc:
        raise ReviewRouteError(f"unknown review adapter: {value}") from exc
