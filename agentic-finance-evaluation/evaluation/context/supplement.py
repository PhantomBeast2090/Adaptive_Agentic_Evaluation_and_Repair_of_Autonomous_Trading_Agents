"""E4-F supplement verification (E4-owned; frozen code untouched).

``verify_e4f_supplement`` file-anchors the E4-F window supplement to
the overlay manifest and protocol document bytes, then enforces the
structural window contract: three roles, strict chronological order,
pairwise disjointness, session/unknown/gold admissibility minima, and
distinct environment fingerprints. Pure and deterministic; no market
episodes. The frozen two-window ``amendment.py`` surface is not
involved and not modified.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Mapping

SUPPLEMENT_METHOD = "e4f-supplement-verify"
SUPPLEMENT_VERSION = "v1"

REQUIRED_WINDOWS = ("w1_diagnostic", "w2_diagnostic", "w3_heldout")
MIN_SESSIONS = 20
MIN_GOLD_DATES = 20


def sha256_file(path: str) -> str:
    """SHA-256 hex digest over a file's raw bytes."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("path must be a non-empty string")
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def verify_e4f_supplement(
    *,
    supplement: Mapping[str, Any],
    manifest_e4f_path: str,
    protocol_doc_path: str,
) -> Dict[str, Any]:
    """Verify an E4-F window supplement; return the resolved record."""
    if not isinstance(supplement, Mapping):
        raise TypeError("supplement must be a mapping")
    for field_name in (
        "amendment_id",
        "amendment_version",
        "base_manifest",
        "base_manifest_fingerprint",
        "protocol_document",
        "protocol_fingerprint",
        "authority",
        "provenance",
    ):
        value = supplement.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"supplement {field_name!r} must be a non-empty string"
            )
    if supplement["amendment_id"] != "E4-F.1":
        raise ValueError(
            f"unsupported supplement {supplement['amendment_id']!r}: refusing"
        )
    measured_base = sha256_file(manifest_e4f_path)
    if measured_base != supplement["base_manifest_fingerprint"]:
        raise ValueError(
            "supplement base-manifest fingerprint does not match the "
            "overlay file bytes: refusing stale or foreign linkage"
        )
    measured_protocol = sha256_file(protocol_doc_path)
    if measured_protocol != supplement["protocol_fingerprint"]:
        raise ValueError(
            "supplement protocol fingerprint does not match the "
            "protocol document bytes: refusing"
        )
    windows = supplement.get("windows")
    if not isinstance(windows, Mapping):
        raise TypeError("supplement windows must be a mapping")
    missing = [key for key in REQUIRED_WINDOWS if key not in windows]
    if missing:
        raise ValueError(
            f"supplement windows missing roles: {missing}"
        )
    resolved = {}
    for key in REQUIRED_WINDOWS:
        block = windows[key]
        if not isinstance(block, Mapping):
            raise TypeError(f"window {key!r} must be a mapping")
        for field_name in ("role", "start", "end",
                           "environment_fingerprint"):
            value = block.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"window {key!r} field {field_name!r} must be a "
                    "non-empty string"
                )
        if not block["end"] >= block["start"]:
            raise ValueError(
                f"window {key!r} end precedes start: refusing"
            )
        if int(block.get("nse_sessions", 0)) < MIN_SESSIONS:
            raise ValueError(
                f"window {key!r} has fewer than "
                f"{MIN_SESSIONS} sessions: refusing"
            )
        if int(block.get("unknown_calendar", 1)) != 0:
            raise ValueError(
                f"window {key!r} has UNKNOWN calendar rows: refusing"
            )
        if int(block.get("gold_contract_trade_dates", 0)) < MIN_GOLD_DATES:
            raise ValueError(
                f"window {key!r} has fewer than "
                f"{MIN_GOLD_DATES} gold dates: refusing"
            )
        resolved[key] = {
            "role": block["role"],
            "start": block["start"],
            "end": block["end"],
            "nse_sessions": int(block["nse_sessions"]),
            "environment_fingerprint": block["environment_fingerprint"],
        }
    ordered = [resolved[key] for key in REQUIRED_WINDOWS]
    for first, second in zip(ordered, ordered[1:]):
        if not second["start"] > first["end"]:
            raise ValueError(
                "supplement windows are not strictly ordered and "
                f"disjoint: {first['start']}..{first['end']} vs "
                f"{second['start']}..{second['end']}"
            )
    env_fps = [block["environment_fingerprint"] for block in ordered]
    if len(set(env_fps)) != len(env_fps):
        raise ValueError(
            "supplement environment fingerprints are not distinct: refusing"
        )
    return {
        "amendment_id": supplement["amendment_id"],
        "base_manifest_fingerprint": measured_base,
        "protocol_fingerprint": measured_protocol,
        "windows": resolved,
        "method": SUPPLEMENT_METHOD,
        "version": SUPPLEMENT_VERSION,
    }
