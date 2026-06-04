"""§D.0 canonicalization & digest primitive.

The single canonical-serialization + hashing primitive every digest/hash/key in the
spec depends on. The load-bearing property: two correct implementations SHALL produce
byte-identical outputs (SPEC §D.0). These vectors lock that contract.
"""

import hashlib

import pytest

from agy_swarms.canonical import (
    canonical,
    output_schema_digest,
    resolved_input_digest,
    sha256_hex,
    tool_schema_impl_digest,
)


# --- canonical(): structure ------------------------------------------------


def test_canonical_returns_utf8_bytes():
    assert isinstance(canonical({"a": 1}), bytes)


def test_object_keys_sorted_so_field_order_is_irrelevant():
    # The whole point of §D.0: input field order must not change the bytes.
    assert canonical({"b": 1, "a": 2}) == canonical({"a": 2, "b": 1})
    assert canonical({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_arrays_preserve_element_order():
    assert canonical([3, 1, 2]) == b"[3,1,2]"


def test_no_insignificant_whitespace():
    assert canonical({"a": 1, "b": [1, 2]}) == b'{"a":1,"b":[1,2]}'


def test_nested_objects_sorted_recursively():
    assert canonical({"z": {"b": 1, "a": 2}, "a": [1, 2]}) == b'{"a":[1,2],"z":{"a":2,"b":1}}'


# --- canonical(): scalars --------------------------------------------------


def test_integers_are_bare_decimal():
    assert canonical(42) == b"42"
    assert canonical(-7) == b"-7"
    assert canonical({"n": 0}) == b'{"n":0}'


def test_floats_use_percent_6g():
    assert canonical(0.1) == b"0.1"
    assert canonical(1.0) == b"1"  # %.6g drops the trailing .0
    assert canonical(1.5) == b"1.5"
    assert canonical(1234567.0) == b"1.23457e+06"
    assert canonical(0.00001) == b"1e-05"
    assert canonical({"usd": 0.0}) == b'{"usd":0}'


def test_bool_and_null():
    assert canonical(True) == b"true"
    assert canonical(False) == b"false"
    assert canonical(None) == b"null"


def test_bool_is_not_serialized_as_int():
    # bool is a subclass of int in Python — must be checked first.
    assert canonical(True) == b"true"
    assert canonical({"ok": True}) == b'{"ok":true}'


def test_strings_minimally_escaped():
    assert canonical('a"b\\c') == b'"a\\"b\\\\c"'
    assert canonical("line\nbreak") == b'"line\\nbreak"'


def test_non_ascii_kept_as_utf8_not_escaped():
    # RFC-8785 minimal escaping: non-ASCII stays literal UTF-8.
    assert canonical("café") == b'"caf\xc3\xa9"'


def test_object_keys_sorted_by_utf16_code_unit_not_codepoint():
    # A supplementary char (U+10000) is a surrogate pair starting D800 in UTF-16,
    # which is < U+FFFF, so it sorts BEFORE U+FFFF — the opposite of codepoint order.
    out = canonical({"\U00010000": 1, "￿": 2})
    assert out == b'{"\xf0\x90\x80\x80":1,"\xef\xbf\xbf":2}'


def test_non_string_dict_key_is_rejected():
    # Silent coercion would break byte-identity; fail loudly instead.
    with pytest.raises(TypeError):
        canonical({1: "a"})


def test_non_finite_float_is_rejected():
    with pytest.raises(ValueError):
        canonical(float("inf"))
    with pytest.raises(ValueError):
        canonical(float("nan"))


# --- sha256_hex() ----------------------------------------------------------


def test_sha256_hex_known_vectors():
    assert sha256_hex(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert sha256_hex(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_sha256_hex_is_lowercase_64_chars():
    h = sha256_hex(b"anything")
    assert len(h) == 64
    assert h == h.lower()


# --- sub-digests (§D.0 used by idempotency_key §D.1) -----------------------


def test_output_schema_digest():
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    assert output_schema_digest(schema) == sha256_hex(canonical(schema))


def test_resolved_input_digest():
    val = {"summary": "done", "artifact": {"k": 1}}
    assert resolved_input_digest(val) == sha256_hex(canonical(val))


def test_tool_schema_impl_digest_is_canonical_schema_concat_impl_sha():
    schema = {"name": "read_file", "params": {"path": "string"}}
    impl_sha = "a" * 64
    expected = hashlib.sha256(canonical(schema) + impl_sha.encode("ascii")).hexdigest()
    assert tool_schema_impl_digest(schema, impl_sha) == expected
