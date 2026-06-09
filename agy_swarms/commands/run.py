"""Plan and run command handlers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agy_swarms.adapters.scripted import CannedResult, ScriptedAdapter
from agy_swarms.budget import Dims
from agy_swarms.conductor import Conductor
from agy_swarms.graph_io import GraphLoadError, load_graph
from agy_swarms.graph_store import GraphStore
from agy_swarms.local_runner import run_local_graph
from agy_swarms.planner import PlanArtifact, decompose
from agy_swarms.review_bundle_guard import (
    ReviewBundleGuardError,
    build_malformed_review_bundle_guard_summary,
    validate_review_bundle_for_graph,
    write_guard_rejection_report,
)
from agy_swarms.review_bundle_inspection import ReviewBundleInspectionError
from agy_swarms.types import Epoch, NodeSpec, TaskSpec


def load_task_spec(task_path: str | Path) -> TaskSpec:
    """Load a TaskSpec from JSON, TOML, or raw text file."""
    path = Path(task_path)
    if not path.exists():
        raise FileNotFoundError(f"Task file not found: {task_path}")

    content = path.read_text(encoding="utf-8")
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            context_hash = data.get("context_hash", "")
            model_pins = data.get("model_pins", {"default": "gemini-3.5-flash"})
            return TaskSpec(
                task=str(data.get("task", "")),
                model_pins=model_pins if isinstance(model_pins, dict) else {},
                context_hash=context_hash if isinstance(context_hash, str) else "",
            )
    except json.JSONDecodeError:
        pass
    return TaskSpec(task=content, model_pins={"default": "gemini-3.5-flash"})


class ScriptedCliPlanner:
    """CLI-friendly scripted planner that decomposes a task into a canned graph."""

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
        graph = decompose(
            spec,
            ScriptedCliPlanner(),
            graph_store=GraphStore(),
            epoch=Epoch(epoch_seq=1, epoch_id="cli-plan-epoch"),
        )
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
    """Execute a task or local graph through library code."""
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
            return _run_graph(args)
        if not args.task:
            print("Error: run requires --task or --graph", file=sys.stderr)
            return 1
        return _run_task(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _run_graph(args: argparse.Namespace) -> int:
    try:
        graph = load_graph(args.graph)
    except GraphLoadError as exc:
        print(f"Graph intake error: {exc}", file=sys.stderr)
        return 1

    guard_summary = None
    if args.require_review_bundle:
        try:
            guard_summary = validate_review_bundle_for_graph(args.graph, args.require_review_bundle)
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
        output["review_bundle_guard"] = {**guard_summary, "guarded_run": True}
    if args.report:
        Path(args.report).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0 if output["status"] == "succeeded" else 1


def _run_task(args: argparse.Namespace) -> int:
    spec = load_task_spec(args.task)
    graph = decompose(
        spec,
        ScriptedCliPlanner(),
        graph_store=GraphStore(),
        epoch=Epoch(epoch_seq=1, epoch_id="cli-run-epoch"),
    )
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
    report = Conductor(
        graph,
        ScriptedAdapter(transcript),
        limit=Dims(tokens=10000, usd=10.0),
        epoch=Epoch(epoch_seq=1, epoch_id="cli-run-epoch"),
        allow_drift=args.allow_drift,
        reviewer=args.reviewer,
        closer=args.closer,
        review_telemetry_path=args.review_telemetry,
    ).run()
    print(
        json.dumps(
            {
                "status": report.status.value,
                "spent_tokens": report.spent_tokens,
                "spent_usd": report.spent_usd,
                "states": {node_id: status.value for node_id, status in report.states.items()},
            },
            indent=2,
        )
    )
    return 0 if report.status.value == "succeeded" else 1


__all__ = ["ScriptedCliPlanner", "cmd_plan", "cmd_run", "load_task_spec"]
