"""I. Deterministic fingerprint tests."""

import pytest

from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.fingerprints import (
    canonicalize,
    fingerprint,
    fingerprint_of_dict,
)


def test_same_semantic_object_same_fingerprint():
    first = AgentIdentity("agent", "1.0")
    second = AgentIdentity("agent", "1.0")
    assert first.fingerprint() == second.fingerprint()
    assert fingerprint({"b": 1, "a": 2}) == fingerprint({"a": 2, "b": 1})


def test_material_change_different_fingerprint():
    assert AgentIdentity("agent", "1.0").fingerprint() != AgentIdentity(
        "agent", "2.0"
    ).fingerprint()
    assert fingerprint({"a": 1}) != fingerprint({"a": 2})
    assert fingerprint([1, 2]) != fingerprint([2, 1])


def test_dictionary_ordering_does_not_alter_fingerprint():
    nested_a = {"x": {"d": 4, "c": 3}, "a": [1, {"z": 1, "y": 2}]}
    nested_b = {"a": [1, {"y": 2, "z": 1}], "x": {"c": 3, "d": 4}}
    assert canonicalize(nested_a) == canonicalize(nested_b)
    assert fingerprint(nested_a) == fingerprint(nested_b)


def test_process_dependent_values_cannot_enter_fingerprints():
    import math

    with pytest.raises(TypeError):
        fingerprint({"a", "b"})
    with pytest.raises(ValueError):
        fingerprint(float("nan"))
    with pytest.raises(ValueError):
        fingerprint(math.inf)
    with pytest.raises(TypeError):
        fingerprint(b"bytes")
    with pytest.raises(TypeError):
        fingerprint_of_dict([("a", 1)])
    # Built-in hash() is salted per process; fingerprints must not use it.
    assert hash("agent") != fingerprint("agent")
    assert fingerprint("agent") == fingerprint("agent")
