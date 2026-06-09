.PHONY: sync lint format-check type-check test build release-health verify-docs verify

sync:
	uv sync --extra dev --extra gemini

lint:
	uv run ruff check .

format-check:
	uv run ruff format --check .

type-check:
	uv run mypy --explicit-package-bases agy_swarms/commands agy_swarms/cli.py agy_swarms/local_runner.py agy_swarms/conductor.py agy_swarms/conductor_adapters.py agy_swarms/conductor_budget.py agy_swarms/conductor_checkpointing.py agy_swarms/conductor_commands.py agy_swarms/conductor_drift.py agy_swarms/conductor_fallback.py agy_swarms/conductor_pipeline.py agy_swarms/conductor_reports.py agy_swarms/conductor_review.py agy_swarms/conductor_review_budget.py scripts/release_health.py scripts/release_health_registry.py scripts/release_health_docs.py scripts/rewrite_release_health_docs.py

test:
	uv run python -m pytest -q

build:
	uv build

release-health:
	uv run python scripts/release_health.py

verify-docs:
	uv run python scripts/rewrite_release_health_docs.py
	git diff --exit-code docs/release-verification.md

verify: lint format-check type-check verify-docs test build release-health
