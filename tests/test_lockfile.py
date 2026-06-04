"""AC-31 — agy.lock loader (§D.5:363-374).

Maps the agy.lock TOML to the typed ``Lockfile``: ``[models.<name>].snapshot`` →
``model_pins``; ``[prompt_hashes]`` → ``prompt_hashes`` (explicit table, default ``{}``,
per D-2); ``[tools]`` + ``[adapters]`` → ``tool_versions``. Drift comparison over the
result is exercised in ``test_drift_recording.py``.
"""

from agy_swarms.lockfile import Lockfile, load_lockfile, loads_lockfile

_FULL = """
lockfile_version = 1
[models.default]
snapshot = "gemini-3.5-flash-2026"
thinking = "high"
[models.escalate]
snapshot = "gemini-3.1-pro-2026"
[managed_agents]
agent_id = "antigravity-X"
environment = "remote"
[tools]
grep = "sha256:aaa"
[adapters]
agy = "1.4.0"
[prompt_hashes]
plan = "h-plan"
synth = "h-synth"
"""


def test_loads_lockfile_parses_models_prompt_hashes_tools():
    lock = loads_lockfile(_FULL)
    assert lock.model_pins == {
        "default": "gemini-3.5-flash-2026",
        "escalate": "gemini-3.1-pro-2026",
    }
    assert lock.prompt_hashes == {"plan": "h-plan", "synth": "h-synth"}
    # [tools] + [adapters] merge into one tool_versions map (§D.5:373-374).
    assert lock.tool_versions == {"grep": "sha256:aaa", "agy": "1.4.0"}


def test_loads_lockfile_defaults_missing_tables_to_empty():
    lock = loads_lockfile("lockfile_version = 1\n")
    assert lock == Lockfile()  # all three maps default empty (D-2)


def test_load_lockfile_reads_from_file(tmp_path):
    p = tmp_path / "agy.lock"
    p.write_text(_FULL)
    assert load_lockfile(p) == loads_lockfile(_FULL)
