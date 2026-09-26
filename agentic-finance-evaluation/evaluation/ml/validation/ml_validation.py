"""ML validation boundary: hypotheses are checked, never admitted here.

``validate_candidate`` verifies schema, provenance, temporal support,
and pipeline compatibility of a DiagnosticHypothesis WITHOUT calling
``extract_candidate``, ``gate.adjudicate``, or any MemoryStore API.
This module must never import MemoryStore, gate, or extraction — a
test pins that boundary. Rejection or acceptance here is validation
evidence, not admission.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

FORBIDDEN_IMPORTS = ("MemoryStore", "memory_store", "gate.adjudicate",
                     "extract_candidate")

MIN_SAMPLE_COUNT = 15
MIN_EFFECT_DELTA = 0.02


def validate_candidate(hypothesis: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a validation verdict dict; never touches admission."""
    checks: Dict[str, Any] = {}
    required = ("hypothesis_id", "target", "condition", "mechanism",
                "observed_adverse_rate", "baseline_adverse_rate",
                "effect_delta", "temporal_support", "sample_count",
                "model_metadata", "feature_provenance",
                "information_set_fingerprint", "provenance_class",
                "status")
    missing = [f for f in required if f not in hypothesis]
    checks["schema_complete"] = not missing
    checks["missing_fields"] = missing
    checks["status_is_candidate"] = hypothesis.get("status") == "CANDIDATE"
    cond = hypothesis.get("condition") or []
    checks["condition_nonempty"] = bool(cond)
    checks["sample_sufficient"] = (
        hypothesis.get("sample_count", 0) >= MIN_SAMPLE_COUNT)
    checks["effect_positive"] = (
        hypothesis.get("effect_delta", 0) >= MIN_EFFECT_DELTA)
    support = {k: v for k, v in
               (dict(hypothesis.get("temporal_support") or {}).items())}
    checks["temporal_support_present"] = bool(support)
    prov = dict(hypothesis.get("feature_provenance") or {})
    checks["no_evaluator_only_in_features"] = all(
        v != "EVALUATOR_ONLY" for v in prov.values())
    checks["mechanism_prescribes_no_action"] = not any(
        word in str(hypothesis.get("mechanism", "")).upper()
        for word in ("BUY", "SELL", "DO NOT TRADE", "HOLD"))
    passed = all([checks["schema_complete"],
                  checks["status_is_candidate"],
                  checks["condition_nonempty"],
                  checks["sample_sufficient"],
                  checks["effect_positive"],
                  checks["temporal_support_present"],
                  checks["no_evaluator_only_in_features"],
                  checks["mechanism_prescribes_no_action"]])
    return {"verdict": ("ACCEPT_FOR_ADMISSION_REVIEW"
                        if passed else "REJECT"),
            "checks": checks,
            "admission": "NOT_PERFORMED (out of scope for this layer)"}
