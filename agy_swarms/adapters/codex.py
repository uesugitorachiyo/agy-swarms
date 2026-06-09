"""Codex CLI model/transport adapter for read-only reviewer and closer routing."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..types import ErrorClass, FailureClass, NodeSpec, ResultEnvelope

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


_BASE_REVIEW_PROPERTIES: dict[str, Any] = {
    "summary": {"type": "string"},
    "verdict": {"type": "string", "enum": ["pass", "concerns", "block", "unknown"]},
    "confidence": {"type": "number"},
    "concerns": {"type": "array", "items": {"type": "string"}},
    "blockers": {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "reason": {"type": "string"},
                "detail": {"type": "string"},
            },
            "required": ["reason", "detail"],
        },
    },
}
_BASE_REVIEW_REQUIRED = ["summary", "verdict", "confidence", "concerns", "blockers"]


@dataclass(frozen=True)
class CodexModelConfig:
    """Resolved Codex model slug and reasoning effort."""

    model: str
    reasoning_effort: str


def resolve_codex_model_config(
    role: str,
    *,
    escalated: bool = False,
    env: Mapping[str, str] | None = None,
) -> CodexModelConfig:
    """Resolve Codex model settings without conflating model slug and reasoning effort."""
    source = env if env is not None else os.environ
    role_prefix = "CLOSER" if role == "closer" else "REVIEWER"
    model = (
        source.get(f"AGY_CODEX_{role_prefix}_MODEL") or source.get("AGY_CODEX_ESCALATED_MODEL")
        if escalated
        else None
    )
    if model is None:
        model = source.get(f"AGY_CODEX_{role_prefix}_MODEL") or source.get("AGY_CODEX_MODEL")
    if model is None:
        model = "gpt-5.5"

    effort = (
        source.get(f"AGY_CODEX_{role_prefix}_REASONING_EFFORT")
        or source.get("AGY_CODEX_ESCALATED_REASONING_EFFORT")
        if escalated
        else None
    )
    if effort is None:
        effort = source.get(f"AGY_CODEX_{role_prefix}_REASONING_EFFORT") or source.get(
            "AGY_CODEX_REASONING_EFFORT"
        )
    if effort is None:
        effort = "high" if escalated else "low"
    return CodexModelConfig(model=model, reasoning_effort=effort)


_REVIEWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        **_BASE_REVIEW_PROPERTIES,
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": ["integer", "null"]},
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                    },
                    "message": {"type": "string"},
                    "suggested_action": {"type": "string"},
                },
                "required": ["file", "line", "severity", "message", "suggested_action"],
            },
        },
    },
    "required": [*_BASE_REVIEW_REQUIRED, "findings"],
}


_CLOSER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        **_BASE_REVIEW_PROPERTIES,
        "accepted": {"type": "boolean"},
        "verification_evidence": {"type": "array", "items": {"type": "string"}},
        "unresolved_obligations": {"type": "array", "items": {"type": "string"}},
        "release_ready": {"type": "boolean"},
    },
    "required": [
        *_BASE_REVIEW_REQUIRED,
        "accepted",
        "verification_evidence",
        "unresolved_obligations",
        "release_ready",
    ],
}

_BATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "nodes": {
            "type": "object",
            "additionalProperties": {"type": "object"},
        }
    },
    "required": ["nodes"],
}


class CodexAdapter:
    """Run reviewer/closer nodes through the Codex CLI in read-only mode."""

    accounting = "exact"

    def __init__(
        self,
        *,
        seed: int = 0,
        capabilities: Iterable[str] = frozenset(),
        model: str | None = None,
        reasoning_effort: str | None = None,
        runner: Runner | None = None,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        escalated: bool = False,
        telemetry_path: str | Path | None = None,
    ) -> None:
        self.seed = seed
        self.capabilities = frozenset(capabilities)
        self.name = "codex"
        self.model_override = model
        self.reasoning_effort_override = reasoning_effort
        self.runner = runner or self._run_subprocess
        self.cwd = Path(cwd) if cwd is not None else Path.cwd()
        self.env = env
        self.escalated = escalated
        self.telemetry_path = Path(telemetry_path) if telemetry_path is not None else None

    def covers(self, required_capabilities: Iterable[str]) -> bool:
        """True iff this adapter declares every required capability."""
        return set(required_capabilities) <= self.capabilities

    def run(
        self,
        node: NodeSpec,
        *,
        attempt: int = 0,
        reservation_id: str | None = None,
    ) -> ResultEnvelope:
        """Execute the review/closer node on Codex CLI in read-only mode."""
        from ..hybrid_review import route_review_role

        route = route_review_role(node.role, adapter="codex")
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with tempfile.TemporaryDirectory(prefix="agy-codex-") as temp_dir:
            temp_path = Path(temp_dir)
            schema_path = temp_path / "codex-review-schema.json"
            output_path = temp_path / "codex-review-output.json"
            schema_path.write_text(json.dumps(_schema_for_role(node.role)), encoding="utf-8")
            config = self._config_for_node(node)
            cmd = self._command(
                node, schema_path=schema_path, output_path=output_path, config=config
            )
            proc = self.runner(cmd)
            ended_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            if proc.returncode != 0:
                error_class, failure_class = _classify_process_error(proc.stderr or proc.stdout)
                return self._envelope(
                    node,
                    route=route.to_json(),
                    status="failed",
                    attempt=attempt,
                    reservation_id=reservation_id,
                    started_at=started_at,
                    ended_at=ended_at,
                    error_class=error_class,
                    failure_class=failure_class,
                    stdout_ref=_join_streams(proc.stdout, proc.stderr),
                    token_usage=_token_usage(proc.stdout),
                    model=config.model,
                    reasoning_effort=config.reasoning_effort,
                )

            try:
                review = _parse_review_output(output_path, role=node.role)
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
                return self._envelope(
                    node,
                    route=route.to_json(),
                    status="failed",
                    attempt=attempt,
                    reservation_id=reservation_id,
                    started_at=started_at,
                    ended_at=ended_at,
                    error_class=ErrorClass.SCHEMA_INVALID,
                    failure_class=FailureClass.TRANSIENT,
                    stdout_ref=f"{type(exc).__name__}: {exc}",
                    token_usage=_token_usage(proc.stdout),
                    model=config.model,
                    reasoning_effort=config.reasoning_effort,
                )

            return self._envelope_from_review(
                node,
                route=route.to_json(),
                review=review,
                attempt=attempt,
                reservation_id=reservation_id,
                started_at=started_at,
                ended_at=ended_at,
                stdout_ref=proc.stdout,
                token_usage=_token_usage(proc.stdout),
                model=config.model,
                reasoning_effort=config.reasoning_effort,
            )

    def _envelope_from_review(
        self,
        node: NodeSpec,
        *,
        route: dict[str, object],
        review: dict[str, Any],
        attempt: int,
        reservation_id: str | None,
        started_at: str,
        ended_at: str,
        stdout_ref: str | None,
        token_usage: dict[str, Any],
        model: str,
        reasoning_effort: str,
    ) -> ResultEnvelope:
        blockers = _normalize_blockers(review.get("blockers", []))
        status = "failed" if blockers or review.get("verdict") == "block" else "succeeded"
        return self._envelope(
            node,
            route=route,
            status=status,
            attempt=attempt,
            reservation_id=reservation_id,
            started_at=started_at,
            ended_at=ended_at,
            artifact_review=review,
            concerns=_string_list(review.get("concerns", [])),
            blockers=blockers,
            error_class=ErrorClass.NONE if status == "succeeded" else ErrorClass.UNKNOWN,
            failure_class=None if status == "succeeded" else FailureClass.DETERMINISTIC,
            stdout_ref=stdout_ref,
            token_usage=token_usage,
            model=model,
            reasoning_effort=reasoning_effort,
        )

    def run_batch(
        self,
        nodes: Iterable[NodeSpec],
        *,
        attempt: int = 0,
        reservation_id: str | None = None,
    ) -> list[ResultEnvelope]:
        """Review multiple reviewer/closer nodes with one Codex CLI invocation."""
        from ..hybrid_review import route_review_role

        node_list = list(nodes)
        if not node_list:
            return []

        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with tempfile.TemporaryDirectory(prefix="agy-codex-batch-") as temp_dir:
            temp_path = Path(temp_dir)
            schema_path = temp_path / "codex-review-batch-schema.json"
            output_path = temp_path / "codex-review-batch-output.json"
            schema_path.write_text(json.dumps(_BATCH_SCHEMA), encoding="utf-8")
            config = self._config_for_node(node_list[0])
            cmd = self._batch_command(
                node_list, schema_path=schema_path, output_path=output_path, config=config
            )
            proc = self.runner(cmd)
            ended_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            routes = {
                node.id: route_review_role(node.role, adapter="codex").to_json()
                for node in node_list
            }

            if proc.returncode != 0:
                error_class, failure_class = _classify_process_error(proc.stderr or proc.stdout)
                return [
                    self._envelope(
                        node,
                        route=routes[node.id],
                        status="failed",
                        attempt=attempt,
                        reservation_id=reservation_id,
                        started_at=started_at,
                        ended_at=ended_at,
                        error_class=error_class,
                        failure_class=failure_class,
                        stdout_ref=_join_streams(proc.stdout, proc.stderr),
                        token_usage=_token_usage(proc.stdout),
                        model=config.model,
                        reasoning_effort=config.reasoning_effort,
                    )
                    for node in node_list
                ]

            try:
                batch = json.loads(output_path.read_text(encoding="utf-8"))
                reviews = batch["nodes"]
                if not isinstance(reviews, dict):
                    raise ValueError("codex batch output nodes must be an object")
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                return [
                    self._envelope(
                        node,
                        route=routes[node.id],
                        status="failed",
                        attempt=attempt,
                        reservation_id=reservation_id,
                        started_at=started_at,
                        ended_at=ended_at,
                        error_class=ErrorClass.SCHEMA_INVALID,
                        failure_class=FailureClass.TRANSIENT,
                        stdout_ref=f"{type(exc).__name__}: {exc}",
                        token_usage=_token_usage(proc.stdout),
                        model=config.model,
                        reasoning_effort=config.reasoning_effort,
                    )
                    for node in node_list
                ]

            envelopes: list[ResultEnvelope] = []
            for node in node_list:
                try:
                    review = _validate_review_output(reviews[node.id], role=node.role)
                except (KeyError, TypeError, ValueError) as exc:
                    envelopes.append(
                        self._envelope(
                            node,
                            route=routes[node.id],
                            status="failed",
                            attempt=attempt,
                            reservation_id=reservation_id,
                            started_at=started_at,
                            ended_at=ended_at,
                            error_class=ErrorClass.SCHEMA_INVALID,
                            failure_class=FailureClass.TRANSIENT,
                            stdout_ref=f"{type(exc).__name__}: {exc}",
                            token_usage=_token_usage(proc.stdout),
                            model=config.model,
                            reasoning_effort=config.reasoning_effort,
                        )
                    )
                    continue

                envelopes.append(
                    self._envelope_from_review(
                        node,
                        route=routes[node.id],
                        review=review,
                        attempt=attempt,
                        reservation_id=reservation_id,
                        started_at=started_at,
                        ended_at=ended_at,
                        stdout_ref=proc.stdout,
                        token_usage=_token_usage(proc.stdout),
                        model=config.model,
                        reasoning_effort=config.reasoning_effort,
                    )
                )
            return envelopes

    def _config_for_node(self, node: NodeSpec) -> CodexModelConfig:
        resolved = resolve_codex_model_config(node.role, escalated=self.escalated, env=self.env)
        return CodexModelConfig(
            model=self.model_override or resolved.model,
            reasoning_effort=self.reasoning_effort_override or resolved.reasoning_effort,
        )

    def _command(
        self,
        node: NodeSpec,
        *,
        schema_path: Path,
        output_path: Path,
        config: CodexModelConfig,
    ) -> list[str]:
        return [
            "codex",
            "-a",
            "never",
            "exec",
            "-m",
            config.model,
            "-c",
            f'model_reasoning_effort="{config.reasoning_effort}"',
            "--cd",
            str(self.cwd),
            "--sandbox",
            "read-only",
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            _review_prompt(node),
        ]

    def _batch_command(
        self,
        nodes: list[NodeSpec],
        *,
        schema_path: Path,
        output_path: Path,
        config: CodexModelConfig,
    ) -> list[str]:
        return [
            "codex",
            "-a",
            "never",
            "exec",
            "-m",
            config.model,
            "-c",
            f'model_reasoning_effort="{config.reasoning_effort}"',
            "--cd",
            str(self.cwd),
            "--sandbox",
            "read-only",
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            _batch_review_prompt(nodes),
        ]

    def _envelope(
        self,
        node: NodeSpec,
        *,
        route: dict[str, object],
        status: str,
        attempt: int,
        reservation_id: str | None,
        started_at: str,
        ended_at: str,
        error_class: ErrorClass,
        failure_class: FailureClass | None = None,
        artifact_review: dict[str, Any] | None = None,
        concerns: list[str] | None = None,
        blockers: list[dict[str, str]] | None = None,
        stdout_ref: str | None = None,
        token_usage: dict[str, Any] | None = None,
        model: str,
        reasoning_effort: str,
    ) -> ResultEnvelope:
        artifact = {
            "route": route,
            "review": artifact_review or {},
            "commands_executed": False,
        }
        envelope = ResultEnvelope(
            node_id=node.id,
            idempotency_key=node.idempotency_key,
            status=status,
            attempt=attempt,
            adapter=self.name,
            model=model,
            thinking_level=reasoning_effort,
            reservation_id=reservation_id,
            started_at=started_at,
            ended_at=ended_at,
            error_class=error_class,
            failure_class=failure_class,
            artifact=artifact,
            pointers=[],
            changed_files=[],
            concerns=concerns or [],
            blockers=blockers or [],
            stdout_ref=stdout_ref,
            token_usage=token_usage or _token_usage(""),
            cost_usd=0.0,
        )
        self._record_telemetry(node, envelope)
        return envelope

    def _record_telemetry(self, node: NodeSpec, envelope: ResultEnvelope) -> None:
        if self.telemetry_path is None:
            return
        from ..review_telemetry import ReviewTelemetryRecord, append_review_telemetry

        review = envelope.artifact.get("review", {})
        append_review_telemetry(
            self.telemetry_path,
            ReviewTelemetryRecord(
                node_id=node.id,
                role=node.role,
                source=self.name,
                verdict=str(review.get("verdict", envelope.status)),
                model=envelope.model,
                reasoning_effort=envelope.thinking_level,
                concern_count=len(envelope.concerns),
                blocker_count=len(envelope.blockers),
                token_output=int(envelope.token_usage.get("output", 0)),
                later_outcome="unknown",
            ),
        )

    def _run_subprocess(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            cwd=self.cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=900,
        )


def _review_prompt(node: NodeSpec) -> str:
    role = "closer" if node.role == "closer" else "reviewer"
    role_instruction = (
        "Do not accept unless verification evidence supports closure.\n"
        "Check unresolved obligations, release readiness, and whether blockers remain."
        if role == "closer"
        else "Find concrete bugs, regressions, missing tests, and behavioral risks.\n"
        "Report file-scoped findings when you can identify a specific location."
    )
    return (
        f"You are the read-only {role} for an agy-swarms task graph node.\n"
        "Do not modify files. Do not run commands. Inspect only what is needed.\n"
        f"{role_instruction}\n"
        "Return only JSON matching the provided schema.\n\n"
        f"review_context:\n{json.dumps(_node_review_context(node), sort_keys=True)}\n"
    )


def _batch_review_prompt(nodes: list[NodeSpec]) -> str:
    payload = [_node_review_context(node) for node in nodes]
    return (
        "You are the read-only reviewer/closer for an agy-swarms task subgraph.\n"
        "Do not modify files. Do not run commands. Inspect only what is needed.\n"
        "Return one review per node id in a top-level JSON object named nodes.\n"
        "Reviewer nodes need findings; closer nodes need acceptance and verification evidence.\n\n"
        f"Nodes:\n{json.dumps(payload, sort_keys=True)}"
    )


def _node_review_context(node: NodeSpec) -> dict[str, Any]:
    """Return compact, code-free context for Codex review prompts."""
    return {
        "id": node.id,
        "role": node.role,
        "objective": node.objective,
        "dependencies": list(node.dependencies),
        "inputs": list(node.inputs),
        "outputs": list(node.outputs),
        "required_capabilities": list(node.required_capabilities),
        "model_tier": node.model_tier,
        "boundaries": node.boundaries or "No extra boundaries declared.",
        "command_present": node.command is not None,
        "output_schema_present": bool(node.output_schema),
    }


def _schema_for_role(role: str) -> dict[str, Any]:
    return _CLOSER_SCHEMA if role == "closer" else _REVIEWER_SCHEMA


def _parse_review_output(output_path: Path, *, role: str) -> dict[str, Any]:
    data = json.loads(output_path.read_text(encoding="utf-8"))
    return _validate_review_output(data, role=role)


def _validate_review_output(data: Any, *, role: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("codex review output must be a JSON object")
    required = _schema_for_role(role)["required"]
    for key in required:
        if key not in data:
            raise ValueError(f"codex review output missing {key!r}")
    return data


def _normalize_blockers(value: Any) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    if not isinstance(value, list):
        return blockers
    for item in value:
        if isinstance(item, dict):
            reason = str(item.get("reason", "blocker"))
            detail = str(item.get("detail", ""))
        else:
            reason = "blocker"
            detail = str(item)
        blockers.append({"reason": reason, "detail": detail})
    return blockers


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _classify_process_error(text: str) -> tuple[ErrorClass, FailureClass]:
    lowered = text.casefold()
    if "timeout" in lowered or "deadline" in lowered:
        return ErrorClass.TIMEOUT, FailureClass.TRANSIENT
    if "auth" in lowered or "login" in lowered or "credential" in lowered:
        return ErrorClass.AUTH, FailureClass.DETERMINISTIC
    if "quota" in lowered or "limit" in lowered or "budget" in lowered:
        return ErrorClass.BUDGET, FailureClass.BUDGET
    if "network" in lowered or "connect" in lowered or "websocket" in lowered:
        return ErrorClass.TRANSPORT, FailureClass.TRANSIENT
    return ErrorClass.UNKNOWN, FailureClass.DETERMINISTIC


def _join_streams(stdout: str, stderr: str) -> str:
    return "\n".join(part for part in (stdout, stderr) if part)


def _token_usage(stdout: str) -> dict[str, Any]:
    tokens = 0
    match = re.search(r"tokens used\s+([0-9,]+)", stdout, flags=re.IGNORECASE)
    if match is not None:
        tokens = int(match.group(1).replace(",", ""))
    return {
        "input": 0,
        "thinking": 0,
        "output": tokens,
        "cached": 0,
        "accounting": "exact",
    }
