"""Thin CLI over the engine library (FR-17/D6.5)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from agy_swarms.adapters.scripted import CannedResult, ScriptedAdapter
from agy_swarms.budget import Dims
from agy_swarms.conductor import Conductor
from agy_swarms.graph_io import GraphLoadError, load_graph
from agy_swarms.graph_store import GraphStore
from agy_swarms.handoff import build_agy_review_prompt
from agy_swarms.hybrid_review import ReviewRole, ReviewRouteError, route_review_role
from agy_swarms.local_runner import run_local_graph
from agy_swarms.planner import PlanArtifact, decompose
from agy_swarms.preflight import summarize_graph_preflight, load_mock_bundle
from agy_swarms.review_bundle import write_review_bundle
from agy_swarms.review_bundle_diff import summarize_review_bundle_diff
from agy_swarms.review_bundle_guard import (
    ReviewBundleGuardError,
    build_malformed_review_bundle_guard_summary,
    validate_review_bundle_for_graph,
    write_guard_rejection_report,
)
from agy_swarms.review_bundle_inspection import (
    ReviewBundleInspectionError,
    summarize_review_bundle,
)
from agy_swarms.review_benchmark import (
    DEFAULT_REVIEW_BENCHMARK_CASES,
    load_seeded_review_cases,
    run_review_benchmark,
)
from agy_swarms.review_routing_policy import recommend_review_backend
from agy_swarms.review_telemetry import summarize_review_telemetry
from agy_swarms.types import Epoch, NodeSpec, TaskSpec


def load_task_spec(task_path: str | Path) -> TaskSpec:
    """Load a TaskSpec from JSON, TOML, or raw text file."""
    path = Path(task_path)
    if not path.exists():
        raise FileNotFoundError(f"Task file not found: {task_path}")

    content = path.read_text(encoding="utf-8")
    # Try parsing as JSON first
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return TaskSpec(
                task=data.get("task", ""),
                model_pins=data.get("model_pins", {"default": "gemini-3.5-flash"}),
                context_hash=data.get("context_hash"),
            )
    except json.JSONDecodeError:
        pass

    # Fallback to loading raw text
    return TaskSpec(task=content, model_pins={"default": "gemini-3.5-flash"})


class ScriptedCliPlanner:
    """A CLI-friendly scripted planner that decomposes a task into a canned PlanArtifact."""

    def __init__(self, artifact: PlanArtifact | None = None) -> None:
        self.artifact = artifact or PlanArtifact(
            nodes=(
                NodeSpec(
                    id="worker_0",
                    role="worker",
                    objective="Perform task operation 0",
                    required_capabilities=["code"],
                ),
                NodeSpec(
                    id="worker_1",
                    role="worker",
                    objective="Perform task operation 1",
                    required_capabilities=["code"],
                    dependencies=["worker_0"],
                ),
            ),
            edges=(("worker_0", "worker_1"),),
        )

    def plan(self, task_spec: TaskSpec) -> PlanArtifact:
        return self.artifact


def cmd_plan(args: argparse.Namespace) -> int:
    """Validate a task and emit a graph preview without dispatch."""
    try:
        spec = load_task_spec(args.task)
        planner = ScriptedCliPlanner()
        epoch = Epoch(epoch_seq=1, epoch_id="cli-plan-epoch")
        graph_store = GraphStore()

        graph = decompose(spec, planner, graph_store=graph_store, epoch=epoch)
        # Structural validation is done inside decompose, let's output a preview
        preview = {
            "task": spec.task[:100] + "..." if len(spec.task) > 100 else spec.task,
            "model_pins": spec.model_pins,
            "nodes": [{"id": n.id, "role": n.role, "objective": n.objective} for n in graph.nodes],
            "edges": graph.edges,
        }
        print(json.dumps(preview, indent=2))
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_run(args: argparse.Namespace) -> int:
    """Execute a task through library code."""
    try:
        if args.dry_run:
            if args.reviewer == "agy":
                args.reviewer = "codex"
            if args.closer == "agy":
                args.closer = "codex"
            print(
                "Offline dry-run mode: forced zero-cost reviewer/closer routing ('codex')",
                file=sys.stderr,
            )
        if args.graph:
            try:
                graph = load_graph(args.graph)
            except GraphLoadError as exc:
                print(f"Graph intake error: {exc}", file=sys.stderr)
                return 1
            guard_summary = None
            if args.require_review_bundle:
                try:
                    guard_summary = validate_review_bundle_for_graph(
                        args.graph, args.require_review_bundle
                    )
                except ReviewBundleGuardError as exc:
                    if args.report:
                        write_guard_rejection_report(
                            args.report,
                            reason_class=exc.reason_class,
                            summary=exc.summary,
                            message=str(exc),
                        )
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1
                except ReviewBundleInspectionError as exc:
                    if args.report:
                        write_guard_rejection_report(
                            args.report,
                            reason_class="malformed_review_bundle",
                            summary=build_malformed_review_bundle_guard_summary(
                                args.graph, args.require_review_bundle
                            ),
                            message=str(exc),
                        )
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1
            output = run_local_graph(
                graph,
                allow_local_commands=args.allow_local_commands,
                reviewer=args.reviewer,
                closer=args.closer,
                review_telemetry_path=args.review_telemetry,
            )
            if guard_summary is not None:
                output["review_bundle_guard"] = {
                    **guard_summary,
                    "guarded_run": True,
                }
            if args.report:
                Path(args.report).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(output, indent=2))
            return 0 if output["status"] == "succeeded" else 1

        if not args.task:
            print("Error: run requires --task or --graph", file=sys.stderr)
            return 1

        spec = load_task_spec(args.task)
        planner = ScriptedCliPlanner()
        epoch = Epoch(epoch_seq=1, epoch_id="cli-run-epoch")
        graph_store = GraphStore()

        graph = decompose(spec, planner, graph_store=graph_store, epoch=epoch)

        # In scripted mode, plant canned results for the conductor
        transcript = {
            "worker_0": CannedResult(
                status="succeeded",
                artifact={"output": "data_0"},
                token_usage={"input": 50, "output": 20, "thinking": 0},
            ),
            "worker_1": CannedResult(
                status="succeeded",
                artifact={"output": "data_1"},
                token_usage={"input": 50, "output": 20, "thinking": 0},
            ),
        }
        adapter = ScriptedAdapter(transcript)

        conductor = Conductor(
            graph,
            adapter,
            limit=Dims(tokens=10000, usd=10.0),
            epoch=epoch,
            allow_drift=args.allow_drift,
            reviewer=args.reviewer,
            closer=args.closer,
            review_telemetry_path=args.review_telemetry,
        )
        report = conductor.run()

        output = {
            "status": report.status.value,
            "spent_tokens": report.spent_tokens,
            "spent_usd": report.spent_usd,
            "states": {node_id: status.value for node_id, status in report.states.items()},
        }
        print(json.dumps(output, indent=2))
        return 0 if report.status.value == "succeeded" else 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_preflight(args: argparse.Namespace) -> int:
    """Validate and summarize a local graph without dispatching command nodes."""
    try:
        try:
            graph = load_graph(args.graph)
        except GraphLoadError as exc:
            print(json.dumps({"status": "invalid", "error": str(exc)}, indent=2))
            return 1
        if args.mock_bundle:
            try:
                transcript = load_mock_bundle(args.mock_bundle)
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

            # Ensure all nodes in the graph have a canned result
            from agy_swarms.adapters.scripted import CannedResult

            for node in graph.nodes:
                if node.id not in transcript and node.idempotency_key not in transcript:
                    transcript[node.id] = CannedResult()

            from agy_swarms.adapters.scripted import ScriptedAdapter
            from agy_swarms.conductor import Conductor
            from agy_swarms.reporting import report_to_json
            from agy_swarms.types import Epoch
            from agy_swarms.budget import Dims

            adapter = ScriptedAdapter(transcript)
            conductor = Conductor(
                graph,
                adapter,
                limit=Dims(tokens=100_000, usd=100.0),
                epoch=Epoch(epoch_seq=1, epoch_id="mock-preflight-run"),
                reviewer="agy",
                closer="agy",
            )
            report = report_to_json(conductor.run())

            if args.output:
                out_path = Path(args.output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
                print(
                    json.dumps(
                        {
                            "status": "mock_report_written",
                            "output": args.output,
                            "commands_executed": False,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                print(json.dumps(report, indent=2))
            return 0

        if args.review_bundle:
            if not args.output:
                print("Error: --review-bundle requires --output", file=sys.stderr)
                return 1
            write_review_bundle(graph, graph_path=args.graph, output_path=args.output)
            print(
                json.dumps(
                    {
                        "status": "review_bundle_written",
                        "output": args.output,
                        "commands_executed": False,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        print(
            json.dumps(
                summarize_graph_preflight(graph, include_command_review=args.command_review),
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_resume(args: argparse.Namespace) -> int:
    """Resume execution from an existing checkpoint path."""
    try:
        checkpoint_path = Path(args.checkpoint)
        if not checkpoint_path.exists():
            print(f"Error: Checkpoint path does not exist: {checkpoint_path}", file=sys.stderr)
            return 1

        report = _try_load_run_report(checkpoint_path)
        if report is not None:
            print(
                json.dumps(
                    {
                        "status": "resume_loaded",
                        "checkpoint": str(checkpoint_path),
                        "source_status": report.get("status"),
                        "states": report.get("states", {}),
                        "blockers": report.get("blockers", []),
                        "summary": _summarize_run_report(report),
                    },
                    indent=2,
                )
            )
            return 0

        rejection_report = _try_load_guard_rejection_report(checkpoint_path)
        if rejection_report is not None:
            print(
                json.dumps(
                    {
                        "status": "resume_loaded",
                        "checkpoint": str(checkpoint_path),
                        "source_status": rejection_report.get("status"),
                        "reason_class": rejection_report.get("reason_class"),
                        "summary": _summarize_guard_rejection_report(rejection_report),
                    },
                    indent=2,
                )
            )
            return 0

        print(json.dumps({"status": "resumed", "checkpoint": str(checkpoint_path)}))
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_inspect(args: argparse.Namespace) -> int:
    """Inspect a checkpoint or run report."""
    try:
        if args.review_bundle_diff:
            try:
                before_path, after_path = args.review_bundle_diff
                print(
                    json.dumps(
                        summarize_review_bundle_diff(before_path, after_path),
                        indent=2,
                    )
                )
                return 0
            except ReviewBundleInspectionError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

        if args.review_bundle:
            try:
                print(
                    json.dumps(
                        summarize_review_bundle(args.review_bundle),
                        indent=2,
                    )
                )
                return 0
            except ReviewBundleInspectionError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

        path = Path(args.checkpoint)
        if not path.exists():
            print(f"Error: File not found: {path}", file=sys.stderr)
            return 1

        report = _try_load_run_report(path)
        if report is not None:
            print(
                json.dumps(
                    {
                        "kind": "run_report",
                        "path": str(path),
                        "size_bytes": path.stat().st_size,
                        "status": report.get("status"),
                        "states": report.get("states", {}),
                        "blockers": report.get("blockers", []),
                        "summary": _summarize_run_report(report),
                    },
                    indent=2,
                )
            )
            return 0

        rejection_report = _try_load_guard_rejection_report(path)
        if rejection_report is not None:
            print(
                json.dumps(
                    {
                        "kind": "guard_rejection_report",
                        "path": str(path),
                        "size_bytes": path.stat().st_size,
                        "status": rejection_report.get("status"),
                        "reason_class": rejection_report.get("reason_class"),
                        "summary": _summarize_guard_rejection_report(rejection_report),
                    },
                    indent=2,
                )
            )
            return 0

        print(json.dumps({"kind": "file", "path": str(path), "size_bytes": path.stat().st_size}))
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_handoff(args: argparse.Namespace) -> int:
    """Generate a read-only agy review prompt for a run report."""
    print(build_agy_review_prompt(report_path=args.report))
    return 0


def cmd_review_route(args: argparse.Namespace) -> int:
    """Resolve read-only reviewer/closer routes without provider execution."""
    try:
        reviewer = route_review_role(ReviewRole.REVIEWER, adapter=args.reviewer)
        closer = route_review_role(ReviewRole.CLOSER, adapter=args.closer)
    except ReviewRouteError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    payload: dict[str, Any] = {
        "status": "review_route_resolved",
        "reviewer": reviewer.to_json(),
        "closer": closer.to_json(),
        "commands_executed": False,
    }
    if args.telemetry:
        telemetry_summary = summarize_review_telemetry(args.telemetry)
        recommendation = recommend_review_backend(telemetry_summary)
        payload["telemetry"] = telemetry_summary
        payload["recommendation"] = {
            "backend": recommendation.backend,
            "reason": recommendation.reason,
            "sample_count": recommendation.sample_count,
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_review_benchmark(args: argparse.Namespace) -> int:
    """Run seeded reviewer/closer benchmark cases against selected backends."""
    try:
        cases = load_seeded_review_cases(args.cases)
        report = run_review_benchmark(
            cases,
            backends=args.backends.split(","),
            cwd=Path.cwd(),
        )
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_pre_commit_install(args: argparse.Namespace) -> int:
    """Install pre-commit git hooks in the local workspace."""
    import subprocess
    import sys

    print("Installing pre-commit git hooks...")
    try:
        res = subprocess.run(
            [sys.executable, "-m", "pre_commit", "install"],
            capture_output=True,
            text=True,
            check=True,
        )
        print(res.stdout)
        print("Success: pre-commit hooks installed.")
        return 0
    except subprocess.CalledProcessError as exc:
        print(
            f"Error: Failed to install pre-commit hooks:\n{exc.stderr or exc.stdout}",
            file=sys.stderr,
        )
        return 1


def _try_load_run_report(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict) and "status" in data and "states" in data:
        return data
    return None


def _try_load_guard_rejection_report(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        isinstance(data, dict)
        and data.get("format") == "local-runner-guard-rejection"
        and data.get("schema_version") == "v1"
        and data.get("status") == "rejected"
    ):
        return data
    return None


def _summarize_guard_rejection_report(report: dict[str, object]) -> dict[str, Any]:
    guard = report.get("review_bundle_guard")
    if not isinstance(guard, dict):
        guard = {}
    missing = guard.get("missing_command_reviews", [])
    mismatched = guard.get("mismatched_command_reviews", [])
    return {
        "format": "local-runner-guard-rejection",
        "schema_version": "v1",
        "status": "rejected",
        "reason_class": str(report.get("reason_class", "")),
        "commands_executed": report.get("commands_executed") is True,
        "guarded_run": guard.get("guarded_run") is True,
        "graph_sha256_match": guard.get("graph_sha256_match") is True,
        "review_complete": guard.get("review_complete") is True,
        "missing_command_review_count": len(missing) if isinstance(missing, list) else 0,
        "mismatched_command_review_count": len(mismatched) if isinstance(mismatched, list) else 0,
    }


def _summarize_guarded_report(report: dict[str, object]) -> dict[str, Any] | None:
    guard = report.get("review_bundle_guard")
    if not isinstance(guard, dict):
        return None
    missing = guard.get("missing_command_reviews", [])
    mismatched = guard.get("mismatched_command_reviews", [])
    return {
        "has_review_bundle_guard": True,
        "guarded_run": guard.get("guarded_run") is True,
        "graph_sha256_match": guard.get("graph_sha256_match") is True,
        "review_complete": guard.get("review_complete") is True,
        "missing_command_review_count": len(missing) if isinstance(missing, list) else 0,
        "mismatched_command_review_count": len(mismatched) if isinstance(mismatched, list) else 0,
        "commands_executed": guard.get("commands_executed") is True,
    }


def _summarize_run_report(report: dict[str, object]) -> dict[str, Any]:
    states = report.get("states", {})
    if not isinstance(states, dict):
        states = {}
    status_by_node = {str(node_id): str(status) for node_id, status in states.items()}
    counts = Counter(status_by_node.values())
    blockers = report.get("blockers", [])
    concerns = report.get("concerns", [])
    changed_files = report.get("changed_files", [])
    summary = {
        "total_nodes": len(status_by_node),
        "status_counts": dict(sorted(counts.items())),
        "failed_nodes": [
            node_id for node_id, status in status_by_node.items() if status == "failed"
        ],
        "skipped_nodes": [
            node_id for node_id, status in status_by_node.items() if status == "skipped"
        ],
        "blocker_count": len(blockers) if isinstance(blockers, list) else 0,
        "concern_count": len(concerns) if isinstance(concerns, list) else 0,
        "changed_files_count": len(changed_files) if isinstance(changed_files, list) else 0,
    }
    guarded_report = _summarize_guarded_report(report)
    if guarded_report is not None:
        summary["guarded_report"] = guarded_report
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agy", description="Thin CLI wrapper over agy-swarms.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # plan command
    p_plan = subparsers.add_parser("plan", help="Validate a task and preview its graph shape.")
    p_plan.add_argument("--task", required=True, help="Path to task spec file.")

    # run command
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

    # preflight command
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

    # resume command
    p_resume = subparsers.add_parser("resume", help="Resume from an existing checkpoint.")
    p_resume.add_argument(
        "--checkpoint", required=True, help="Path to checkpoint file or directory."
    )

    # inspect command
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

    # handoff command
    p_handoff = subparsers.add_parser("handoff", help="Generate a read-only agy review prompt.")
    p_handoff.add_argument("--report", required=True, help="Path to run report JSON.")

    # review-route command
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

    # review-benchmark command
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

    # pre-commit-install command
    subparsers.add_parser(
        "pre-commit-install", help="Install pre-commit git hooks in the local workspace."
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code or 0

    if args.command == "plan":
        return cmd_plan(args)
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "preflight":
        return cmd_preflight(args)
    elif args.command == "resume":
        return cmd_resume(args)
    elif args.command == "inspect":
        return cmd_inspect(args)
    elif args.command == "handoff":
        return cmd_handoff(args)
    elif args.command == "review-route":
        return cmd_review_route(args)
    elif args.command == "review-benchmark":
        return cmd_review_benchmark(args)
    elif args.command == "pre-commit-install":
        return cmd_pre_commit_install(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
