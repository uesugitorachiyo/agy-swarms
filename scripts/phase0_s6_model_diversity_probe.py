#!/usr/bin/env python3
"""Run the Phase-0 S6/G0.6 agy model-diversity probe.

S6 is a capability gate. It does not need to prove that the `agy` CLI can vary
models; it needs to identify the judge/escalation diversity mechanism before
later phases depend on it.

The probe checks:
- `agy --help` exposes no per-call model flag;
- the authenticated default `agy` path records the current selected model label;
- an isolated HOME/config directory cannot reuse cached OAuth silently, so per-worker
  HOME/config model overrides are not a usable default mechanism;
- the fallback mechanism is therefore the explicitly configured Gemini SDK/API adapter,
  with the default `agy` path remaining OAuth/Flash-high.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
OAUTH_URL_PATTERN = re.compile(r"https://accounts\.google\.com/o/oauth2/auth\?[^\s]+")
MODEL_LABEL_PATTERN = re.compile(r'Propagating selected model override to backend: label="([^"]+)"')
AUTH_REQUIRED_PATTERN = re.compile(
    r"Authentication required|not authenticated|OAuth authentication flow|authentication timed out",
    re.I,
)


def redact(text: str) -> str:
    text = EMAIL_PATTERN.sub("<redacted-email>", text)
    text = OAUTH_URL_PATTERN.sub("<redacted-oauth-url>", text)
    return text.replace("\x04", "").replace("\x08", "").strip()


def run_command(
    command: list[str], *, env: dict[str, str] | None = None, timeout_s: int = 90
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout_s,
        )
        return {
            "command": command[:2] + ["<redacted>"] if "-p" in command else command,
            "returncode": completed.returncode,
            "elapsed_s": time.perf_counter() - started,
            "stdout": redact(completed.stdout),
            "stderr": redact(completed.stderr),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command[:2] + ["<redacted>"] if "-p" in command else command,
            "returncode": None,
            "elapsed_s": time.perf_counter() - started,
            "stdout": redact(
                (exc.stdout or "").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            ),
            "stderr": redact(
                (exc.stderr or "").decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            ),
            "timed_out": True,
        }


def help_probe(cli: str) -> dict[str, Any]:
    result = run_command([cli, "--help"], timeout_s=30)
    help_text = f"{result['stdout']}\n{result['stderr']}"
    return {
        "returncode": result["returncode"],
        "has_model_flag": "--model" in help_text,
        "has_add_dir": "--add-dir" in help_text,
        "has_log_file": "--log-file" in help_text,
        "help_excerpt": "\n".join(
            line for line in help_text.splitlines() if "model" in line.lower() or "--" in line
        )[:4000],
    }


def authenticated_model_probe(
    cli: str, log_file: Path, print_timeout: str, timeout_s: int
) -> dict[str, Any]:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    prompt = 'Return one JSON object only: {"s6_probe":"default_model","ok":true}'
    result = run_command(
        [cli, "--log-file", str(log_file), "-p", prompt, "--print-timeout", print_timeout],
        timeout_s=timeout_s,
    )
    raw_log = log_file.read_text(errors="replace") if log_file.exists() else ""
    redacted_log = redact(raw_log)
    if raw_log != redacted_log:
        log_file.write_text(redacted_log)
    labels = MODEL_LABEL_PATTERN.findall(redacted_log)
    return {
        "returncode": result["returncode"],
        "elapsed_s": result["elapsed_s"],
        "stdout_excerpt": result["stdout"][:2000],
        "log_file": str(log_file),
        "model_labels": labels,
        "selected_model_label": labels[-1] if labels else None,
        "authenticated": result["returncode"] == 0
        and not AUTH_REQUIRED_PATTERN.search(result["stdout"] + result["stderr"]),
    }


def isolated_home_probe(
    cli: str, base_dir: Path, requested_model_label: str, print_timeout: str, timeout_s: int
) -> dict[str, Any]:
    base_dir.mkdir(parents=True, exist_ok=True)
    isolated_home = Path(tempfile.mkdtemp(prefix="s6-isolated-home-", dir=base_dir))
    settings = isolated_home / ".gemini" / "antigravity-cli" / "settings.json"
    workspace = isolated_home / "workspace"
    log_file = isolated_home / "s6-isolated.log"
    settings.parent.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps(
            {
                "model": requested_model_label,
                "toolPermission": "always-proceed",
                "enableTelemetry": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    env = os.environ.copy()
    env["HOME"] = str(isolated_home)
    prompt = 'Return one JSON object only: {"s6_probe":"isolated_home","ok":true}'
    result = run_command(
        [
            cli,
            "--add-dir",
            str(workspace),
            "--log-file",
            str(log_file),
            "-p",
            prompt,
            "--print-timeout",
            print_timeout,
        ],
        env=env,
        timeout_s=timeout_s,
    )
    raw_log = log_file.read_text(errors="replace") if log_file.exists() else ""
    redacted_log = redact(raw_log)
    if raw_log != redacted_log:
        log_file.write_text(redacted_log)
    for generated_cache in (
        isolated_home / "Library" / "Caches" / "ms-playwright-go",
        isolated_home / ".cache" / "ms-playwright-go",
    ):
        if generated_cache.exists():
            shutil.rmtree(generated_cache)
    combined = "\n".join([result["stdout"], result["stderr"], redacted_log])
    labels = MODEL_LABEL_PATTERN.findall(redacted_log)
    auth_required = bool(AUTH_REQUIRED_PATTERN.search(combined))
    return {
        "requested_model_label": requested_model_label,
        "isolated_home": str(isolated_home),
        "returncode": result["returncode"],
        "elapsed_s": result["elapsed_s"],
        "auth_required": auth_required,
        "silently_reused_cached_oauth": result["returncode"] == 0 and not auth_required,
        "model_labels": labels,
        "selected_model_label": labels[-1] if labels else None,
        "stdout_excerpt": result["stdout"][:2000],
        "stderr_excerpt": result["stderr"][:2000],
        "log_file": str(log_file),
        "generated_caches_removed": True,
    }


def sdk_fallback_probe() -> dict[str, Any]:
    doc = (
        Path.home()
        / ".gemini/config/plugins/google-antigravity-sdk/skills/google-antigravity-sdk/references/agent_configuration.md"
    )
    text = doc.read_text(errors="replace") if doc.exists() else ""
    return {
        "mechanism": "explicit_gemini_sdk_api_adapter",
        "default_auth_unchanged": "agy_oauth",
        "api_key_default": False,
        "reason": "agy CLI model selection is global/unproven per invocation; later judge/escalation diversity must use an explicit model-configurable adapter.",
        "local_sdk_doc": str(doc) if doc.exists() else None,
        "local_sdk_doc_mentions_model_config": "model=" in text or "model identifiers" in text,
    }


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    cli_path = shutil.which(args.cli)
    if cli_path is None:
        raise SystemExit(f"{args.cli!r} is not installed or not on PATH.")
    help_result = help_probe(args.cli)
    default_result = authenticated_model_probe(
        args.cli, args.default_log_file, args.print_timeout, args.timeout_s
    )
    isolated_result = isolated_home_probe(
        args.cli,
        args.isolated_base_dir,
        args.requested_model_label,
        args.print_timeout,
        args.isolated_timeout_s,
    )
    fallback = sdk_fallback_probe()
    agy_per_config_override_works = bool(
        isolated_result["silently_reused_cached_oauth"]
        and isolated_result["selected_model_label"]
        and isolated_result["selected_model_label"] != default_result["selected_model_label"]
    )
    diversity_route = (
        "agy_per_config_dir_override"
        if agy_per_config_override_works
        else "explicit_gemini_sdk_api_adapter"
    )
    passed = bool(
        default_result["authenticated"]
        and not help_result["has_model_flag"]
        and (agy_per_config_override_works or fallback["local_sdk_doc_mentions_model_config"])
    )
    return {
        "gate": "S6/G0.6",
        "passed": passed,
        "cli": args.cli,
        "cli_path": cli_path,
        "help_probe": help_result,
        "default_authenticated_probe": default_result,
        "isolated_home_probe": isolated_result,
        "agy_per_config_override_works": agy_per_config_override_works,
        "diversity_route": diversity_route,
        "oq_2_resolution": (
            "agy per-config-dir model override works"
            if agy_per_config_override_works
            else "agy model selection is not mechanically usable per worker with cached OAuth; different-model judges and escalation route to an explicitly configured Gemini SDK/API adapter; Sonnet-via-agy is post-v0"
        ),
        "fallback_probe": fallback,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", default="agy")
    parser.add_argument(
        "--output", type=Path, default=Path(".planning/spikes/s6-g0.6-model-diversity.json")
    )
    parser.add_argument(
        "--default-log-file", type=Path, default=Path(".planning/spikes/s6-g0.6-default-agy.log")
    )
    parser.add_argument("--isolated-base-dir", type=Path, default=Path(tempfile.gettempdir()))
    parser.add_argument("--requested-model-label", default="Gemini 2.5 Pro")
    parser.add_argument("--print-timeout", default="1m0s")
    parser.add_argument("--timeout-s", type=int, default=120)
    parser.add_argument("--isolated-timeout-s", type=int, default=45)
    args = parser.parse_args()

    result = run_probe(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "default_model": result["default_authenticated_probe"]["selected_model_label"],
                "agy_per_config_override_works": result["agy_per_config_override_works"],
                "diversity_route": result["diversity_route"],
                "isolated_home_auth_required": result["isolated_home_probe"]["auth_required"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
