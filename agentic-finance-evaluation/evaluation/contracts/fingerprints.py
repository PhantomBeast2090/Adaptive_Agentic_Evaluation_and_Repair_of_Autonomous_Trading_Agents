"""Deterministic canonicalization and fingerprinting for E0 contracts.

This module is the single shared fingerprint utility for
``evaluation/contracts``. It extracts the idiom already used across the
repository (``Trajectory.content_digest``,
``IndianMultiAssetEnvironment.fingerprint``, ``HistoricalMarket.fingerprint``):

* canonical JSON with sorted keys and compact separators;
* SHA-256 over the UTF-8 encoding of that canonical form.

Rules:

* Equivalent semantic objects produce identical fingerprints.
* Materially different semantic objects produce different fingerprints.
* Process-dependent values (``hash()``, ``id()``, memory addresses, set
  iteration order, wall-clock timestamps) never enter a fingerprint:
  ``set``/``frozenset`` inputs are rejected so callers must use ordered
  tuples, and each contract's ``fingerprint()`` documents exactly which
  fields are included or excluded.
* ``float('nan')`` and infinities are rejected: they have no stable
  canonical form and must never be fingerprinted silently.
* Every contract documents its own include/exclude set; this module only
  provides the mechanism, never the policy.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from copy import deepcopy
from types import MappingProxyType
from typing import Any, Mapping


def freeze(value: Any) -> Any:
    """Recursively snapshot a contract value and prevent nested mutation."""
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (tuple, list)):
        return tuple(freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        raise TypeError("sets cannot be stored in deterministic contracts")
    return deepcopy(value)


def thaw(value: Any) -> Any:
    """Return ordinary mutable containers for serialized contract output."""
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return deepcopy(value)


def _normalize(value: Any) -> Any:
    """Convert ``value`` into a JSON-safe structure with deterministic order."""
    if value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("NaN and infinite floats have no canonical form")
        return repr(value)
    if isinstance(value, Mapping):
        items = []
        for key in value:
            if not isinstance(key, str):
                raise TypeError(
                    "canonical mappings must have string keys, "
                    f"got {type(key).__name__}"
                )
            items.append((key, _normalize(value[key])))
        return {key: val for key, val in sorted(items, key=lambda kv: kv[0])}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        raise TypeError(
            "sets have no deterministic order; use a sorted tuple instead"
        )
    if isinstance(value, bytes):
        raise TypeError("bytes have no canonical form; decode to str first")
    if dataclasses.is_dataclass(value):
        if hasattr(value, "to_dict") and callable(value.to_dict):
            return _normalize(value.to_dict())
        raise TypeError(
            f"dataclass {type(value).__name__} has no to_dict(); "
            "convert it explicitly before fingerprinting"
        )
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _normalize(value.to_dict())
    raise TypeError(
        f"objects of type {type(value).__name__} have no canonical form"
    )


def canonicalize(value: Any) -> str:
    """Render ``value`` as canonical JSON.

    Equivalent semantic values render identically regardless of dictionary
    insertion order. Raises ``TypeError``/``ValueError`` on values with no
    stable canonical form (sets, bytes, NaN, arbitrary objects).
    """
    # ``bool`` is a subclass of ``int``; _normalize handles it, but guard the
    # top-level fast path explicitly for clarity.
    normalized = _normalize(value)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def fingerprint(value: Any) -> str:
    """SHA-256 hex digest of :func:`canonicalize` applied to ``value``."""
    return hashlib.sha256(canonicalize(value).encode("utf-8")).hexdigest()


def fingerprint_of_dict(payload: Mapping[str, Any]) -> str:
    """Fingerprint an already canonical-ready mapping payload."""
    if not isinstance(payload, Mapping):
        raise TypeError("fingerprint payload must be a mapping")
    return fingerprint(dict(payload))
