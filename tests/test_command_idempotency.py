"""``command`` participates in idempotency hashing (FR-34 / §D.1 / AC-36 support).

A ``test``/``verify`` node carries a declared ``command``; two such nodes that differ
only in their command MUST hash to distinct ``idempotency_key``s — otherwise a changed
test command would cache-hit the prior result (FR-7). The field is hashed
**only-when-present** (the §D.1 ``map``/``reducer`` precedent at ``compute_idempotency_key``),
so every existing command-less node keeps a byte-identical key (AC-1 cache tests intact).
"""

from agy_swarms.types import NodeSpec, compute_idempotency_key


def test_command_value_distinguishes_idempotency_key():
    a = NodeSpec(id="t", role="test", objective="t", command=["pytest", "-x"])
    b = NodeSpec(id="t", role="test", objective="t", command=["pytest", "-q"])
    assert compute_idempotency_key(a) != compute_idempotency_key(b)


def test_command_presence_distinguishes_idempotency_key():
    without = NodeSpec(id="t", role="test", objective="t")
    with_cmd = NodeSpec(id="t", role="test", objective="t", command=["pytest"])
    assert compute_idempotency_key(without) != compute_idempotency_key(with_cmd)
