"""Gemini API model/transport adapter using the google-genai SDK (Phase-2)."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from typing import Any

from google import genai
from google.genai import types

from ..model_routing import resolve_thinking_config
from ..types import ErrorClass, FailureClass, NodeSpec, ResultEnvelope


class GeminiApiAdapter:
    """Gemini API model/transport adapter using the google-genai SDK (FR-14)."""

    accounting = "exact"

    def __init__(
        self,
        *,
        seed: int = 0,
        capabilities: Iterable[str] = frozenset(),
        api_key: str | None = None,
        model_pins: dict[str, str] | None = None,
    ) -> None:
        self.seed = seed
        self.capabilities = frozenset(capabilities)
        self.model_pins = model_pins or {}
        # Client parses GEMINI_API_KEY env var automatically if api_key is None
        self.client = genai.Client(api_key=api_key)
        self.name = "gemini_api"

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
        """Execute the node on Gemini API."""
        # 1. Resolve model name from model_pins
        model_name = "gemini-3.5-flash-05-2026"
        if self.model_pins:
            if node.model_tier == "pro" and "escalate" in self.model_pins:
                model_name = self.model_pins["escalate"]
            elif "default" in self.model_pins:
                model_name = self.model_pins["default"]

        # 2. Resolve thinking config
        thinking_conf = resolve_thinking_config(model_name, node.model_tier)

        # Determine thinking level for the response envelope
        thinking_level = "none"
        if "thinking_config" in thinking_conf:
            thinking_level = thinking_conf["thinking_config"].get("thinking_level", "high")
        elif "thinking_budget" in thinking_conf:
            thinking_level = "high" if thinking_conf["thinking_budget"] != 0 else "none"

        # 3. Build contents/prompt
        contents = node.objective

        # 4. Build configuration dictionary
        config_dict: dict[str, Any] = {
            "temperature": 0.0,  # temperature 0 for determinism
        }
        config_dict.update(thinking_conf)

        if node.boundaries:
            config_dict["system_instruction"] = node.boundaries

        if node.output_schema:
            config_dict["response_mime_type"] = "application/json"
            config_dict["response_schema"] = node.output_schema

        if node.caps and node.caps.max_output_tokens > 0:
            config_dict["max_output_tokens"] = node.caps.max_output_tokens

        config = types.GenerateContentConfig(**config_dict)

        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        error_class = ErrorClass.NONE
        failure_class = None
        status = "succeeded"
        artifact: dict[str, Any] = {}
        stdout_ref = None

        try:
            response = self.client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )

            # Retrieve token usage and cost
            usage = response.usage_metadata
            input_tokens = getattr(usage, "prompt_token_count", 0) or 0
            output_tokens = getattr(usage, "candidates_token_count", 0) or 0
            thinking_tokens = 0
            if usage and hasattr(usage, "thinking_token_count"):
                thinking_tokens = getattr(usage, "thinking_token_count", 0) or 0

            # Calculate cost (estimate for Flash/Pro models)
            # Flash snapshot input: $0.075 / 1M, output: $0.30 / 1M
            # Pro snapshot input: $1.25 / 1M, output: $5.00 / 1M
            is_pro = "pro" in model_name.lower()
            input_rate = 1.25 / 1_000_000 if is_pro else 0.075 / 1_000_000
            output_rate = 5.00 / 1_000_000 if is_pro else 0.30 / 1_000_000
            cost_usd = (input_tokens * input_rate) + (output_tokens * output_rate)

            token_usage = {
                "input": input_tokens,
                "thinking": thinking_tokens,
                "output": output_tokens,
                "cached": 0,
                "accounting": self.accounting,
            }

            # Parse model output
            text_out = response.text or ""
            if not text_out:
                artifact = {}
            else:
                try:
                    parsed = json.loads(text_out)
                    if isinstance(parsed, dict):
                        artifact = parsed
                    else:
                        artifact = {"text": text_out}
                except json.JSONDecodeError:
                    artifact = {"text": text_out}

        except Exception as exc:
            # Handle any API or transport exceptions
            status = "failed"
            error_str = str(exc)

            # Simple heuristic classification based on exception content/type
            err_lower = error_str.lower()
            if (
                "api_key" in err_lower
                or "api key" in err_lower
                or "invalid credentials" in err_lower
                or "auth" in err_lower
            ):
                error_class = ErrorClass.AUTH
                failure_class = FailureClass.DETERMINISTIC
            elif "timeout" in err_lower or "deadline exceeded" in err_lower:
                error_class = ErrorClass.TIMEOUT
                failure_class = FailureClass.TRANSIENT
            elif "limit" in err_lower or "quota" in err_lower:
                error_class = ErrorClass.BUDGET
                failure_class = FailureClass.BUDGET
            elif (
                "connect" in err_lower
                or "network" in err_lower
                or "dns" in err_lower
                or "endpoint" in err_lower
            ):
                error_class = ErrorClass.TRANSPORT
                failure_class = FailureClass.TRANSIENT
            else:
                error_class = ErrorClass.UNKNOWN
                failure_class = FailureClass.DETERMINISTIC

            stdout_ref = f"{type(exc).__name__}: {exc}"
            token_usage = {
                "input": 0,
                "thinking": 0,
                "output": 0,
                "cached": 0,
                "accounting": self.accounting,
            }
            cost_usd = 0.0

        ended_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        return ResultEnvelope(
            node_id=node.id,
            idempotency_key=node.idempotency_key,
            status=status,
            attempt=attempt,
            adapter=self.name,
            model=model_name,
            thinking_level=thinking_level,
            reservation_id=reservation_id,
            started_at=started_at,
            ended_at=ended_at,
            error_class=error_class,
            failure_class=failure_class,
            artifact=artifact,
            stdout_ref=stdout_ref,
            token_usage=token_usage,
            cost_usd=cost_usd,
        )
