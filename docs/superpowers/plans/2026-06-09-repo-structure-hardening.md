# Repo Structure Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce command drift, dependency coupling, and large-file maintenance risk without changing public CLI behavior.

**Architecture:** Keep public entrypoints stable while moving configuration and helpers behind smaller modules. Release health reads a typed local registry, provider-backed adapters stay lazily imported, CLI parsing moves out of `main.py`, and conductor report summarization moves into a focused helper module.

**Tech Stack:** Python 3.11+, uv, pytest, ruff, hatchling.

---

### Task 1: Release Health Registry

**Files:**
- Create: `scripts/release_health_registry.py`
- Modify: `scripts/release_health.py`
- Test: `tests/test_release_health.py`

- [ ] **Step 1: Write failing tests**

```python
def test_release_health_registry_exposes_stable_probe_commands():
    from scripts.release_health_registry import PROBES

    assert ["uv", "run", "python", "-m", "pytest", "-q"] in [p["command"] for p in PROBES]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_release_health.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.release_health_registry'`.

- [ ] **Step 3: Implement registry and import it from release health**

Move the `PROBES` list into `scripts/release_health_registry.py` and make `scripts/release_health.py` import `PROBES`.

- [ ] **Step 4: Verify**

Run: `uv run python -m pytest -q tests/test_release_health.py`
Expected: PASS.

### Task 2: Optional Provider SDK Extra

**Files:**
- Modify: `pyproject.toml`
- Test: `tests/test_adapter_imports.py`

- [ ] **Step 1: Write failing test**

```python
def test_google_genai_is_declared_as_gemini_extra_not_core_dependency():
    import tomllib

    data = tomllib.loads(Path("pyproject.toml").read_text())
    assert "google-genai" not in " ".join(data["project"].get("dependencies", []))
    assert any(dep.startswith("google-genai") for dep in data["project"]["optional-dependencies"]["gemini"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_adapter_imports.py`
Expected: FAIL because `google-genai` is still in core dependencies.

- [ ] **Step 3: Move dependency**

Remove `google-genai` from `[project].dependencies` and add `[project.optional-dependencies].gemini = ["google-genai>=0.3.0"]`.

- [ ] **Step 4: Verify**

Run: `uv lock && uv sync --extra dev --extra gemini && uv run python -m pytest -q tests/test_adapter_imports.py tests/test_gemini_api.py`
Expected: PASS.

### Task 3: CLI Parser Extraction

**Files:**
- Create: `agy_swarms/cli.py`
- Modify: `agy_swarms/main.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing test**

```python
def test_cli_module_exposes_parser_builder():
    from agy_swarms.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["review-route", "--reviewer", "codex"])
    assert args.command == "review-route"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_cli.py::test_cli_module_exposes_parser_builder`
Expected: FAIL with missing module or function.

- [ ] **Step 3: Extract parser and dispatch**

Move parser construction and command dispatch from `agy_swarms/main.py` into `agy_swarms/cli.py`. Keep `agy_swarms.main:main` as the console entrypoint.

- [ ] **Step 4: Verify**

Run: `uv run python -m pytest -q tests/test_cli.py`
Expected: PASS.

### Task 4: Conductor Report Helper Extraction

**Files:**
- Create: `agy_swarms/conductor_reports.py`
- Modify: `agy_swarms/conductor.py`
- Test: `tests/test_conductor.py`

- [ ] **Step 1: Write failing test**

```python
def test_conductor_report_module_exports_report_types():
    from agy_swarms.conductor_reports import RunReport

    assert RunReport.__name__ == "RunReport"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -q tests/test_conductor.py::test_conductor_report_module_exports_report_types`
Expected: FAIL with missing module.

- [ ] **Step 3: Move report dataclasses**

Move `NodeRecord`, `RunReport`, `PipelineItemReport`, and `PipelineReport` to `agy_swarms/conductor_reports.py`; import them in `conductor.py`.

- [ ] **Step 4: Verify**

Run: `uv run python -m pytest -q tests/test_conductor.py tests/test_ac1_integration.py`
Expected: PASS.

### Final Verification

- [ ] Run `uv run ruff check .`
- [ ] Run `uv run ruff format --check .`
- [ ] Run `uv run python -m pytest -q`
- [ ] Run `uv build`
- [ ] Run `uv run python scripts/release_health.py`
