"""CLI parser and dispatch for the agy-swarms console entrypoint."""

from __future__ import annotations

import argparse

from agy_swarms.review_benchmark import DEFAULT_REVIEW_BENCHMARK_CASES


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser without executing any command."""
    parser = argparse.ArgumentParser(prog="agy", description="Thin CLI wrapper over agy-swarms.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_plan = subparsers.add_parser("plan", help="Validate a task and preview its graph shape.")
    p_plan.add_argument("--task", required=True, help="Path to task spec file.")

    p_run = subparsers.add_parser("run", help="Decompose and execute a task spec.")
    p_run.add_argument("--task", required=False, help="Path to task spec file.")
    p_run.add_argument("--graph", required=False, help="Path to TaskGraph JSON file.")
    p_run.add_argument(
        "--report", required=False, help="Optional path to write the run report JSON."
    )
    p_run.add_argument("--adapter", default="scripted", help="Adapter type (default: scripted).")
    p_run.add_argument(
        "--allow-local-commands",
        action="store_true",
        help="Allow local subprocess command nodes.",
    )
    p_run.add_argument(
        "--require-review-bundle",
        required=False,
        help="Require a saved local review bundle before executing graph commands.",
    )
    p_run.add_argument("--allow-drift", action="store_true", help="Allow lockfile drift.")
    p_run.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute the graph locally routing review/closer nodes to zero-cost offline/CLI adapters ('codex') to audit logic without API costs.",
    )
    p_run.add_argument(
        "--reviewer",
        default="agy",
        choices=["agy", "codex", "claude", "ollama", "llamafile", "off"],
        help="Reviewer adapter: agy, codex, claude, ollama, llamafile, or off.",
    )
    p_run.add_argument(
        "--closer",
        default="agy",
        choices=["agy", "codex", "claude", "ollama", "llamafile", "off"],
        help="Closer adapter: agy, codex, claude, ollama, llamafile, or off.",
    )
    p_run.add_argument(
        "--review-telemetry",
        required=False,
        help="Optional JSONL path for code-free reviewer/closer telemetry records.",
    )

    p_preflight = subparsers.add_parser(
        "preflight", help="Validate and summarize a local graph without execution."
    )
    p_preflight.add_argument("--graph", required=True, help="Path to TaskGraph JSON file.")
    p_preflight.add_argument(
        "--command-review",
        action="store_true",
        help="Include redacted local command review evidence without execution.",
    )
    p_preflight.add_argument(
        "--review-bundle",
        action="store_true",
        help="Write a deterministic saved review bundle without execution.",
    )
    p_preflight.add_argument(
        "--mock-bundle",
        required=False,
        help="Path to a custom pre-saved execution bundle JSON to generate a mock run report.",
    )
    p_preflight.add_argument(
        "--output",
        required=False,
        help="Path to write when --review-bundle or --mock-bundle is set.",
    )

    p_resume = subparsers.add_parser("resume", help="Resume from an existing checkpoint.")
    p_resume.add_argument(
        "--checkpoint", required=True, help="Path to checkpoint file or directory."
    )

    p_inspect = subparsers.add_parser(
        "inspect", help="Inspect a checkpoint, report, or saved review bundle."
    )
    p_inspect_group = p_inspect.add_mutually_exclusive_group(required=True)
    p_inspect_group.add_argument("--checkpoint", help="Path to checkpoint.")
    p_inspect_group.add_argument(
        "--review-bundle",
        help="Path to saved local review bundle JSON.",
    )
    p_inspect_group.add_argument(
        "--review-bundle-diff",
        nargs=2,
        metavar=("BEFORE", "AFTER"),
        help="Compare two saved local review bundle JSON files.",
    )

    p_handoff = subparsers.add_parser("handoff", help="Generate a read-only agy review prompt.")
    p_handoff.add_argument("--report", required=True, help="Path to run report JSON.")

    p_review_route = subparsers.add_parser(
        "review-route", help="Resolve reviewer/closer adapter routing without execution."
    )
    p_review_route.add_argument(
        "--reviewer",
        default="agy",
        choices=["agy", "codex", "claude", "ollama", "llamafile", "off"],
        help="Reviewer adapter: agy, codex, claude, ollama, llamafile, or off.",
    )
    p_review_route.add_argument(
        "--closer",
        default="agy",
        choices=["agy", "codex", "claude", "ollama", "llamafile", "off"],
        help="Closer adapter: agy, codex, claude, ollama, llamafile, or off.",
    )
    p_review_route.add_argument(
        "--telemetry",
        required=False,
        help="Optional review telemetry JSONL path used to recommend codex-low/codex-high.",
    )

    p_review_benchmark = subparsers.add_parser(
        "review-benchmark",
        help="Run seeded reviewer/closer benchmark cases against selected backends.",
    )
    p_review_benchmark.add_argument(
        "--cases",
        default=str(DEFAULT_REVIEW_BENCHMARK_CASES),
        help="Path to seeded review benchmark cases JSON.",
    )
    p_review_benchmark.add_argument(
        "--backends",
        default="codex-low,codex-high",
        help="Comma-separated benchmark backends, e.g. codex-low,codex-high.",
    )
    p_review_benchmark.add_argument(
        "--output",
        required=False,
        help="Optional path to write benchmark report JSON.",
    )

    subparsers.add_parser(
        "pre-commit-install", help="Install pre-commit git hooks in the local workspace."
    )
    return parser


def dispatch(args: argparse.Namespace) -> int:
    """Dispatch parsed CLI args to command handlers."""
    import agy_swarms.commands as commands

    handlers = {
        "plan": commands.cmd_plan,
        "run": commands.cmd_run,
        "preflight": commands.cmd_preflight,
        "resume": commands.cmd_resume,
        "inspect": commands.cmd_inspect,
        "handoff": commands.cmd_handoff,
        "review-route": commands.cmd_review_route,
        "review-benchmark": commands.cmd_review_benchmark,
        "pre-commit-install": commands.cmd_pre_commit_install,
    }
    return handlers[args.command](args)


def main(argv: list[str] | None = None) -> int:
    """Parse argv and run the selected CLI command."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else 1
    return dispatch(args)
