"""Preflight command handlers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agy_swarms.adapters.scripted import CannedResult, ScriptedAdapter
from agy_swarms.budget import Dims
from agy_swarms.conductor import Conductor
from agy_swarms.graph_io import GraphLoadError, load_graph
from agy_swarms.preflight import load_mock_bundle, summarize_graph_preflight
from agy_swarms.reporting import report_to_json
from agy_swarms.review_bundle import write_review_bundle
from agy_swarms.types import Epoch


def cmd_preflight(args: argparse.Namespace) -> int:
    """Validate and summarize a local graph without dispatching command nodes."""
    try:
        try:
            graph = load_graph(args.graph)
        except GraphLoadError as exc:
            print(json.dumps({"status": "invalid", "error": str(exc)}, indent=2))
            return 1
        if args.mock_bundle:
            return _write_mock_report(args, graph)
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


def _write_mock_report(args: argparse.Namespace, graph) -> int:
    try:
        transcript = load_mock_bundle(args.mock_bundle)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    for node in graph.nodes:
        if node.id not in transcript and node.idempotency_key not in transcript:
            transcript[node.id] = CannedResult()

    report = report_to_json(
        Conductor(
            graph,
            ScriptedAdapter(transcript),
            limit=Dims(tokens=100_000, usd=100.0),
            epoch=Epoch(epoch_seq=1, epoch_id="mock-preflight-run"),
            reviewer="agy",
            closer="agy",
        ).run()
    )

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


__all__ = ["cmd_preflight"]
