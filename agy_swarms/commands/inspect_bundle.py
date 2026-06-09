"""Review bundle inspection helpers for the inspect command."""

from __future__ import annotations

import json
import sys

from agy_swarms.review_bundle_diff import summarize_review_bundle_diff
from agy_swarms.review_bundle_inspection import (
    ReviewBundleInspectionError,
    summarize_review_bundle,
)


def inspect_review_bundle_diff(paths: list[str]) -> int:
    try:
        before_path, after_path = paths
        print(json.dumps(summarize_review_bundle_diff(before_path, after_path), indent=2))
        return 0
    except ReviewBundleInspectionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def inspect_review_bundle(path: str) -> int:
    try:
        print(json.dumps(summarize_review_bundle(path), indent=2))
        return 0
    except ReviewBundleInspectionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


__all__ = ["inspect_review_bundle", "inspect_review_bundle_diff"]
