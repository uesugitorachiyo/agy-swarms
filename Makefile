.PHONY: sync disk-preflight lint format-check type-check test build release-health verify-docs verify-fast verify pr-verification

sync:
	uv sync --extra dev --extra gemini

disk-preflight:
	uv run python scripts/disk_space_preflight.py

lint:
	uv run ruff check .

format-check:
	uv run ruff format --check .

type-check:
	uv run mypy --explicit-package-bases agy_swarms scripts/disk_space_preflight.py scripts/release_health.py scripts/release_health_registry.py scripts/release_health_docs.py scripts/rewrite_release_health_docs.py

test:
	uv run python -m pytest -q

build:
	uv build

release-health: disk-preflight
	uv run python scripts/release_health.py

verify-docs:
	uv run python scripts/rewrite_release_health_docs.py
	git diff --exit-code docs/release-verification.md

verify-fast: disk-preflight lint format-check type-check verify-docs test build

verify: verify-fast release-health

pr-verification:
	uv run python scripts/pr_verification.py --pr "$${PR_NUMBER:?set PR_NUMBER}" --pytest-count "$${PYTEST_COUNT:-722}" --mypy-files "$${MYPY_FILES:-96}" --release-health-passed "$${RELEASE_HEALTH_PASSED:-24}" --release-health-total "$${RELEASE_HEALTH_TOTAL:-24}"
