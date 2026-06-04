"""FR-4 ``validate_or_die`` + AC-27 pin-required intake + §D.1.1 templating.

``validate_or_die`` is the plan-time gate: acyclicity, dependency completeness, the
reducer/map field-presence rules (§D.1), and the restricted Mustache-subset templating
(§D.1.1, where an undeclared-input reference is a plan-time error, FR-1.2).
``validate_intake`` enforces AC-27 (a pin-less TaskSpec is rejected before dispatch).
"""

import pytest

from agy_swarms.types import MapSpec, NodeSpec, Reducer, TaskGraph, TaskSpec
from agy_swarms.validate import ValidationError, validate_intake, validate_or_die


def _g(nodes, edges=None):
    return TaskGraph(nodes=nodes, edges=edges or [])


# --- acyclicity + dependency completeness (FR-4) ---------------------------


def test_acyclic_graph_passes():
    a = NodeSpec(id="a", role="worker", objective="o")
    b = NodeSpec(id="b", role="worker", objective="o", dependencies=["a"])
    validate_or_die(_g([a, b]))


def test_two_node_cycle_raises():
    a = NodeSpec(id="a", role="worker", objective="o", dependencies=["b"])
    b = NodeSpec(id="b", role="worker", objective="o", dependencies=["a"])
    with pytest.raises(ValidationError):
        validate_or_die(_g([a, b]))


def test_self_cycle_raises():
    a = NodeSpec(id="a", role="worker", objective="o", dependencies=["a"])
    with pytest.raises(ValidationError):
        validate_or_die(_g([a]))


def test_duplicate_node_ids_raise():
    a = NodeSpec(id="a", role="worker", objective="o")
    a2 = NodeSpec(id="a", role="worker", objective="o2")
    with pytest.raises(ValidationError):
        validate_or_die(_g([a, a2]))


def test_dependency_on_unknown_node_raises():
    a = NodeSpec(id="a", role="worker", objective="o", dependencies=["ghost"])
    with pytest.raises(ValidationError):
        validate_or_die(_g([a]))


# --- reducer field rules (§D.1) --------------------------------------------


def test_reducer_role_requires_reducer_object():
    r = NodeSpec(id="r", role="reducer", objective="o")
    with pytest.raises(ValidationError):
        validate_or_die(_g([r]))


def test_non_reducer_role_must_not_carry_reducer():
    w = NodeSpec(id="w", role="worker", objective="o", reducer=Reducer(kind="concat"))
    with pytest.raises(ValidationError):
        validate_or_die(_g([w]))


def test_reducer_role_with_concat_passes():
    r = NodeSpec(id="r", role="reducer", objective="o", reducer=Reducer(kind="concat"))
    validate_or_die(_g([r]))


def test_custom_reducer_requires_custom_id():
    r = NodeSpec(id="r", role="reducer", objective="o", reducer=Reducer(kind="custom"))
    with pytest.raises(ValidationError):
        validate_or_die(_g([r]))


def test_non_custom_reducer_must_not_carry_custom_id():
    r = NodeSpec(
        id="r",
        role="reducer",
        objective="o",
        reducer=Reducer(kind="concat", custom_id="x"),
    )
    with pytest.raises(ValidationError):
        validate_or_die(_g([r]))


def test_custom_reducer_id_resolved_against_registry():
    r = NodeSpec(
        id="r",
        role="reducer",
        objective="o",
        reducer=Reducer(kind="custom", custom_id="myred"),
    )
    with pytest.raises(ValidationError):
        validate_or_die(_g([r]), reducers={})
    validate_or_die(_g([r]), reducers={"myred": lambda xs: xs})


def test_unknown_reducer_kind_raises():
    r = NodeSpec(id="r", role="reducer", objective="o", reducer=Reducer(kind="bogus"))
    with pytest.raises(ValidationError):
        validate_or_die(_g([r]))


# --- map field rules (§D.1.2) ----------------------------------------------


def test_map_kind_requires_mapspec():
    m = NodeSpec(id="m", role="worker", objective="o", kind="map")
    with pytest.raises(ValidationError):
        validate_or_die(_g([m]))


def test_single_kind_must_not_carry_mapspec():
    ms = MapSpec(collection_input="x", element_artifact="y", max_fanout=2, child_template="t")
    m = NodeSpec(id="m", role="worker", objective="o", kind="single", map=ms)
    with pytest.raises(ValidationError):
        validate_or_die(_g([m]))


def test_unknown_kind_raises():
    n = NodeSpec(id="n", role="worker", objective="o", kind="weird")
    with pytest.raises(ValidationError):
        validate_or_die(_g([n]))


# --- templating (§D.1.1 / FR-1.2) ------------------------------------------


def test_valid_template_interpolation_passes():
    a = NodeSpec(id="a", role="worker", objective="o")
    b = NodeSpec(
        id="b",
        role="worker",
        objective="o",
        inputs=["a"],
        dependencies=["a"],
        prompt_template="use {{input.a.summary}} and {{input.a.artifact.data}}",
    )
    validate_or_die(_g([a, b]))


def test_template_referencing_undeclared_input_raises():
    b = NodeSpec(
        id="b",
        role="worker",
        objective="o",
        prompt_template="{{input.a.summary}}",
    )
    with pytest.raises(ValidationError):
        validate_or_die(_g([b]))


def test_template_unknown_key_form_raises():
    a = NodeSpec(id="a", role="worker", objective="o")
    b = NodeSpec(
        id="b",
        role="worker",
        objective="o",
        inputs=["a"],
        dependencies=["a"],
        prompt_template="{{input.a.foo}}",
    )
    with pytest.raises(ValidationError):
        validate_or_die(_g([a, b]))


def test_template_garbage_interpolation_raises():
    b = NodeSpec(id="b", role="worker", objective="o", prompt_template="{{garbage}}")
    with pytest.raises(ValidationError):
        validate_or_die(_g([b]))


def test_escaped_braces_are_literal_not_interpolation():
    b = NodeSpec(
        id="b",
        role="worker",
        objective="o",
        prompt_template=r"literal \{{not_an_input}} stays literal",
    )
    validate_or_die(_g([b]))


# --- AC-27 pin-required intake ---------------------------------------------


def test_intake_rejects_taskspec_without_model_pins():
    with pytest.raises(ValidationError):
        validate_intake(TaskSpec(task="do x"))


def test_intake_accepts_taskspec_with_model_pins():
    validate_intake(TaskSpec(task="do x", model_pins={"default": "gemini-3.5-flash-X"}))


# --- FR-8.1 single-writer blackboard (AC-S5 part a) ------------------------


def test_single_writer_violation_rejected():
    a = NodeSpec(id="a", role="worker", objective="o", outputs=["sec.shared"])
    b = NodeSpec(id="b", role="worker", objective="o", outputs=["sec.shared"])
    with pytest.raises(ValidationError):
        validate_or_die(_g([a, b]))


def test_distinct_section_writers_allowed():
    a = NodeSpec(id="a", role="worker", objective="o", outputs=["sec.a"])
    b = NodeSpec(id="b", role="worker", objective="o", outputs=["sec.b"])
    validate_or_die(_g([a, b]))
