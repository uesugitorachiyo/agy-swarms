"""§D.5 ``agy.lock`` lockfile — the resolved pins that drift is checked against.

Phase 1 ships the typed ``Lockfile`` value (``model_pins`` / ``prompt_hashes`` /
``tool_versions``) and a ``tomllib`` loader. The per-key drift comparison + abort rule
lives in ``validate.check_drift`` (AC-31, §D.5). The agy.lock TOML shape is §D.5:363-374:
``[models.<name>].snapshot`` → ``model_pins``; ``[prompt_hashes]`` → ``prompt_hashes`` (an
explicit table, default ``{}``); ``[tools]`` + ``[adapters]`` → ``tool_versions``.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from os import PathLike
from typing import Any

__all__ = ["Lockfile", "load_lockfile", "loads_lockfile"]


@dataclass(frozen=True)
class Lockfile:
    """Resolved lockfile pins (§D.5). Each map defaults empty (D-2: absent table ⇒ ``{}``)."""

    model_pins: dict[str, str] = field(default_factory=dict)
    prompt_hashes: dict[str, str] = field(default_factory=dict)
    tool_versions: dict[str, str] = field(default_factory=dict)
    skill_hashes: dict[str, str] = field(default_factory=dict)
    policy_version: str = ""


def loads_lockfile(text: str) -> Lockfile:
    """Parse agy.lock TOML *text* → ``Lockfile`` (§D.5:363-374)."""
    return _from_data(tomllib.loads(text))


def load_lockfile(path: str | PathLike[str]) -> Lockfile:
    """Read + parse an agy.lock file → ``Lockfile`` (§D.5:363-374)."""
    with open(path, "rb") as fh:
        return _from_data(tomllib.load(fh))


def _from_data(data: dict[str, Any]) -> Lockfile:
    """Project the §D.5 TOML tables onto the typed maps.

    ``[models.<name>].snapshot`` → ``model_pins[name]``; ``[prompt_hashes]`` →
    ``prompt_hashes``; ``[tools]`` + ``[adapters]`` → a merged ``tool_versions`` map. A
    missing table defaults to ``{}`` (D-2); values are coerced to ``str`` defensively.
    """
    models = data.get("models", {})
    model_pins = {
        name: str(tbl.get("snapshot", "")) for name, tbl in models.items() if isinstance(tbl, dict)
    }
    prompt_hashes = {str(k): str(v) for k, v in data.get("prompt_hashes", {}).items()}
    merged_tools = {**data.get("tools", {}), **data.get("adapters", {})}
    tool_versions = {str(k): str(v) for k, v in merged_tools.items()}
    skill_hashes = {str(k): str(v) for k, v in data.get("skills", {}).items()}
    policy_version = str(data.get("meta", {}).get("policy_version", ""))
    return Lockfile(
        model_pins=model_pins,
        prompt_hashes=prompt_hashes,
        tool_versions=tool_versions,
        skill_hashes=skill_hashes,
        policy_version=policy_version,
    )
