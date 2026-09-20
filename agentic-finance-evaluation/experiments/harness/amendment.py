"""E3-D.1 amendment overlay: verified overrides over the frozen base.

Authority model: the E3-C.2 manifest is the single base protocol;
this supplement authorises exactly six leaf overrides (four temporal
bounds, two environment fingerprints) for Tier-1 execution. Every
other field resolves straight through to base values at use time —
there is no second manifest.

Declared fingerprints are assertions to verify, never authorities to
trust: the base manifest file and the narrative amendment file are
hashed from actual bytes and compared. `save()`-side fail-closed
semantics from the remediation patch apply unchanged.

Known wart (documented, not silently fixed): the base manifest's
descriptive session/gold-count fields under ``temporal`` describe the
retired pair and are NOT in the authorised override surface, so they
carry through into the effective mapping unchanged. No verification
or execution path consumes them (config verification reads windows,
universe, costs, pool, sequence, budgets only); the authoritative
counts for the fresh pair live in E3-D.1 §5. Extending the surface
requires a new approved amendment, not a silent widening here.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any, Dict, Mapping, Tuple

import yaml

from evaluation.contracts.fingerprints import fingerprint_of_dict
from experiments.harness.errors import IntegrityFailure

AMENDMENT_ID = "E3-D.1"

ALLOWED_OVERRIDES: Tuple[Tuple[str, ...], ...] = (
    ("temporal", "diagnostic_start"),
    ("temporal", "diagnostic_end"),
    ("temporal", "heldout_start"),
    ("temporal", "heldout_end"),
    ("fingerprints", "diagnostic_env"),
    ("fingerprints", "heldout_env"),
)

_ALLOWED_TOP = frozenset({"temporal", "fingerprints"})


def sha256_file(path: str) -> str:
    """SHA-256 over a file's raw bytes (deterministic, read-only)."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("path must be a non-empty string")
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError as exc:
        raise IntegrityFailure(
            f"cannot read file for fingerprinting {path!r}: {exc}"
        ) from exc


def load_supplement(path: str) -> Dict[str, Any]:
    """Parse the amendment supplement (no verification yet)."""
    data = yaml.safe_load(open(path, encoding="utf-8").read())
    if not isinstance(data, Mapping):
        raise IntegrityFailure(
            f"supplement {path!r} must be a mapping at top level"
        )
    return dict(data)


def verify_supplement(
    *,
    manifest: Mapping[str, Any],
    manifest_path: str,
    supplement: Mapping[str, Any],
    amendment_doc_path: str,
) -> Dict[str, Any]:
    """Verify the overlay against actual frozen files. Fail closed."""
    if not isinstance(manifest, Mapping):
        raise TypeError("manifest must be a mapping")
    if not isinstance(supplement, Mapping):
        raise TypeError("supplement must be a mapping")
    if supplement.get("amendment_id") != AMENDMENT_ID:
        raise IntegrityFailure(
            f"supplement amendment_id must be {AMENDMENT_ID!r}, "
            f"got {supplement.get('amendment_id')!r}"
        )
    measured_base = sha256_file(manifest_path)
    if supplement.get("base_manifest_fingerprint") != measured_base:
        raise IntegrityFailure(
            "supplement base_manifest_fingerprint does not match the "
            f"actual manifest file {manifest_path!r}: failing closed"
        )
    measured_amendment = sha256_file(amendment_doc_path)
    if supplement.get("amendment_fingerprint") != measured_amendment:
        raise IntegrityFailure(
            "supplement amendment_fingerprint does not match the "
            f"actual amendment document {amendment_doc_path!r}"
        )
    overrides = supplement.get("overrides")
    if not isinstance(overrides, Mapping):
        raise IntegrityFailure("supplement must carry an overrides mapping")
    unknown_top = set(overrides) - _ALLOWED_TOP
    if unknown_top:
        raise IntegrityFailure(
            f"unknown override sections: {sorted(unknown_top)}"
        )
    seen: Dict[Tuple[str, ...], bool] = {}
    for section in _ALLOWED_TOP:
        block = overrides.get(section, {})
        if not isinstance(block, Mapping):
            raise IntegrityFailure(
                f"override section {section!r} must be a mapping"
            )
        for key in block:
            seen[(section, key)] = True
    for path in seen:
        if path not in ALLOWED_OVERRIDES:
            raise IntegrityFailure(
                f"override {'.'.join(path)!r} is not authorised: "
                "failing closed"
            )
    required = set(ALLOWED_OVERRIDES)
    missing = required - set(seen)
    if missing:
        raise IntegrityFailure(
            "supplement missing required overrides: "
            f"{sorted('.'.join(p) for p in missing)}"
        )
    for path in required:
        value = overrides[path[0]][path[1]]
        if not isinstance(value, str) or not value.strip():
            raise IntegrityFailure(
                f"override {'.'.join(path)!r} must be a non-empty string"
            )
    return dict(supplement)


def resolve_effective(
    *, manifest: Mapping[str, Any], supplement: Mapping[str, Any]
) -> Tuple[Dict[str, Any], str]:
    """Resolve base + verified supplement into effective config + fp.

    Pure and deterministic: neither input is mutated (deep-copied
    before override application). Returns (effective_dict,
    effective_fingerprint) where the fingerprint is canonical JSON
    SHA-256 over the resolved mapping.
    """
    manifest_snapshot = copy.deepcopy(dict(manifest))
    effective = copy.deepcopy(dict(manifest))
    overrides = supplement.get("overrides", {})
    for section, key in ALLOWED_OVERRIDES:
        try:
            value = overrides[section][key]
        except (KeyError, TypeError) as exc:
            raise IntegrityFailure(
                f"verified supplement lacks override "
                f"{section}.{key}: {exc}"
            ) from exc
        target = effective.get(section)
        if not isinstance(target, Mapping):
            raise IntegrityFailure(
                f"base manifest lacks section {section!r} for override"
            )
        target = dict(target)
        target[key] = value
        effective[section] = target
    if dict(manifest) != manifest_snapshot:
        raise IntegrityFailure(
            "internal error: resolution mutated the base manifest"
        )
    return effective, fingerprint_of_dict(effective)
