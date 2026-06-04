#!/usr/bin/env python3
"""Run the Phase-0 S3/G0.3 deterministic spine + budget-ledger probe.

This zero-token probe exercises the existing deterministic conductor substrate:

- two fresh scripted runs of the same fixed fan-out graph produce byte-identical
  canonical RunReports
- idempotency keys, artifacts, states, and budget totals are stable
- one reserve->commit and one reserve->release ledger cycle each appear exactly once
  under their `(epoch_seq, node_id)` key, with no double reservation/spend
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agy_swarms.adapters.scripted import CannedResult, ScriptedAdapter
from agy_swarms.budget import BudgetLedger, Dims
from agy_swarms.canonical import canonical, sha256_hex
from agy_swarms.conductor import Conductor
from agy_swarms.types import Caps, Epoch, NodeSpec, TaskGraph


def _epoch() -> Epoch:
    return Epoch(epoch_seq=1, epoch_id="phase0-s3")


def _node(node_id: str, objective: str, dependencies: list[str] | None = None) -> NodeSpec:
    return NodeSpec(
        id=node_id,
        role="worker",
        objective=objective,
        dependencies=dependencies or [],
        caps=Caps(max_output_tokens=100, max_thinking_tokens=25),
        transport="scripted",
        model_tier="flash_high",
    )


def _graph() -> TaskGraph:
    root = _node("root", "produce shared input")
    a = _node("a", "derive branch a", ["root"])
    b = _node("b", "derive branch b", ["root"])
    return TaskGraph(nodes=[root, a, b], edges=[("root", "a"), ("root", "b")], seed=123)


def _scripted() -> ScriptedAdapter:
    usage = {"input": 0, "thinking": 0, "output": 10, "cached": 0, "accounting": "exact"}
    return ScriptedAdapter(
        {
            "root": CannedResult(artifact={"data": 1}, token_usage=usage),
            "a": CannedResult(artifact={"x": 2}, token_usage=usage),
            "b": CannedResult(artifact={"y": 3}, token_usage=usage),
        }
    )


def _canonical_report(report: Any) -> bytes:
    return canonical(asdict(report))


def run_conductor_probe() -> dict[str, Any]:
    c1 = Conductor(
        _graph(), _scripted(), limit=Dims(tokens=10_000, usd=100.0), epoch=_epoch(), cap=2
    )
    c2 = Conductor(
        _graph(), _scripted(), limit=Dims(tokens=10_000, usd=100.0), epoch=_epoch(), cap=2
    )
    r1 = c1.run()
    r2 = c2.run()
    b1 = _canonical_report(r1)
    b2 = _canonical_report(r2)
    keys1 = {node_id: env.idempotency_key for node_id, env in r1.results.items()}
    keys2 = {node_id: env.idempotency_key for node_id, env in r2.results.items()}
    artifacts1 = {node_id: env.artifact for node_id, env in r1.results.items()}
    artifacts2 = {node_id: env.artifact for node_id, env in r2.results.items()}
    states1 = {node_id: str(status) for node_id, status in r1.states.items()}
    states2 = {node_id: str(status) for node_id, status in r2.states.items()}
    return {
        "report_hash_1": sha256_hex(b1),
        "report_hash_2": sha256_hex(b2),
        "byte_identical": b1 == b2,
        "idempotency_keys_stable": keys1 == keys2 and all(keys1.values()),
        "artifacts_stable": artifacts1 == artifacts2,
        "states_stable": states1 == states2,
        "spent_tokens_stable": r1.spent_tokens == r2.spent_tokens == 30,
        "spent_usd_stable": r1.spent_usd == r2.spent_usd == 0.0,
        "states": states1,
        "idempotency_keys": keys1,
        "spent_tokens": r1.spent_tokens,
    }


def run_ledger_probe() -> dict[str, Any]:
    node = _node("ledger-node", "ledger cycle")
    ledger = BudgetLedger(Dims(tokens=1_000, usd=10.0))

    commit_admission = ledger.reserve(3, "commit-node", node, epoch_id="phase0-s3")
    ledger.commit(3, "commit-node", Dims(tokens=60, usd=0.0))

    release_admission = ledger.reserve(3, "release-node", node, epoch_id="phase0-s3")
    second_release_admission = ledger.reserve(3, "release-node", node, epoch_id="phase0-s3")
    ledger.release(3, "release-node")

    commit_entry = ledger.entries[(3, "commit-node")]
    release_entry = ledger.entries[(3, "release-node")]
    keys = sorted(list(ledger.entries.keys()))
    return {
        "keys": [[epoch_seq, node_id] for epoch_seq, node_id in keys],
        "reserve_commit_exactly_once": keys.count((3, "commit-node")) == 1
        and commit_admission.admitted
        and commit_entry.status == "committed"
        and commit_entry.reserved == Dims()
        and commit_entry.committed == Dims(tokens=60, usd=0.0),
        "reserve_release_exactly_once": keys.count((3, "release-node")) == 1
        and release_admission.admitted
        and second_release_admission.admitted
        and second_release_admission.reservation_id == release_admission.reservation_id
        and release_entry.status == "released"
        and release_entry.reserved == Dims()
        and release_entry.committed == Dims(),
        "no_double_reservation": ledger.reserved == Dims(),
        "spent_tokens": ledger.spent.tokens,
        "available_tokens": ledger.available.tokens,
        "entries": {
            f"{epoch_seq}:{node_id}": {
                "status": entry.status,
                "reserved": asdict(entry.reserved),
                "committed": asdict(entry.committed),
                "reservation_id": entry.reservation_id,
            }
            for (epoch_seq, node_id), entry in ledger.entries.items()
        },
    }


def run_probe() -> dict[str, Any]:
    conductor = run_conductor_probe()
    ledger = run_ledger_probe()
    passed = (
        conductor["byte_identical"]
        and conductor["idempotency_keys_stable"]
        and conductor["artifacts_stable"]
        and conductor["states_stable"]
        and conductor["spent_tokens_stable"]
        and conductor["spent_usd_stable"]
        and ledger["reserve_commit_exactly_once"]
        and ledger["reserve_release_exactly_once"]
        and ledger["no_double_reservation"]
    )
    return {
        "gate": "S3/G0.3",
        "transport": "scripted",
        "zero_token": True,
        "passed": passed,
        "conductor": conductor,
        "ledger": ledger,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path(".planning/spikes/s3-g0.3-determinism-budget.json")
    )
    args = parser.parse_args()

    result = run_probe()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "report_hash": result["conductor"]["report_hash_1"],
                "spent_tokens": result["conductor"]["spent_tokens"],
                "ledger_spent_tokens": result["ledger"]["spent_tokens"],
            },
            indent=2,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
