"""Failure classification and retry eligibility helpers for the conductor."""

from __future__ import annotations

from .types import ErrorClass, FailureClass, ResultEnvelope


# The total error_class -> FailureClass table (§D.2). ``none`` maps to ``None`` so the
# fail-closed branch (a non-succeeded status carrying ``none``) resolves to Deterministic.
_ERROR_TO_FAILURE: dict[ErrorClass, FailureClass | None] = {
    ErrorClass.NONE: None,
    ErrorClass.SCHEMA_INVALID: FailureClass.TRANSIENT,
    ErrorClass.TRANSPORT: FailureClass.TRANSIENT,
    ErrorClass.TIMEOUT: FailureClass.TRANSIENT,
    ErrorClass.TOOL: FailureClass.TRANSIENT,
    ErrorClass.AUTH: FailureClass.DETERMINISTIC,
    ErrorClass.BUDGET: FailureClass.BUDGET,
    ErrorClass.UNKNOWN: FailureClass.DETERMINISTIC,
}


def classify(envelope: ResultEnvelope) -> FailureClass | None:
    """Derive the §D.2 ``FailureClass`` retry verdict from a result envelope."""
    if envelope.status == "succeeded":
        return None
    if envelope.failure_class is not None:
        return envelope.failure_class
    if envelope.status == "timed_out":
        return FailureClass.TRANSIENT
    derived = _ERROR_TO_FAILURE.get(envelope.error_class, FailureClass.DETERMINISTIC)
    return derived if derived is not None else FailureClass.DETERMINISTIC


def retry_eligible(
    failure_class: FailureClass | None,
    error_class: ErrorClass,
    remaining_retries: int,
    retryable_error_classes: tuple[str, ...],
) -> bool:
    """Return whether the normative §D.2 retry predicate admits another attempt."""
    return (
        failure_class == FailureClass.TRANSIENT
        and remaining_retries > 0
        and error_class in retryable_error_classes
    )


__all__ = ["classify", "retry_eligible"]
