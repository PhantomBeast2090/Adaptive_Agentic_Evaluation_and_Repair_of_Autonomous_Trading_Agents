"""Baseline evidence derivation (E1).

Converts selected baseline ``MetricResult`` items into E0
``BehavioralEvidence``. This is derivation, not diagnosis: each item reports
a measured behavior with its method and record references. No thresholds,
no failure labels, no ``Hypothesis`` objects — this module does not import
the hypothesis contract at all.

Evidence always lands in the ``baseline_evidence`` slot of
``EvaluationState``; the ``evidence`` slot stays empty for the later
adaptive layer (E2).
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence, Tuple

from evaluation.baseline.metrics import MetricResult
from evaluation.contracts.evidence import BehavioralEvidence, EvidenceCategory

# Metric name -> evidence category. Only these metrics become evidence;
# every other computed metric remains available on BaselineResult.metrics.
EVIDENCE_METRICS: Tuple[Tuple[str, EvidenceCategory], ...] = (
    ("turnover", EvidenceCategory.DECISION_BEHAVIOR),
    ("concentration_cost_basis_max", EvidenceCategory.RISK),
    ("gross_exposure_max", EvidenceCategory.RISK),
    ("max_drawdown", EvidenceCategory.RISK),
    ("position_persistence", EvidenceCategory.DECISION_BEHAVIOR),
    ("inactivity_rate", EvidenceCategory.DECISION_BEHAVIOR),
    ("reversal_rate", EvidenceCategory.DECISION_BEHAVIOR),
    ("invalid_order_rate", EvidenceCategory.EXECUTION),
    ("universe_violation_count", EvidenceCategory.EXECUTION),
    ("transaction_cost_total", EvidenceCategory.EXECUTION),
    ("unavailable_info_rate", EvidenceCategory.INFORMATION_USAGE),
)

EVALUATOR_ID = "e1-baseline"


def derive_baseline_evidence(
    evaluation_id: str,
    metrics: Mapping[str, MetricResult],
    decision_fingerprints: Sequence[str],
    provenance: Mapping[str, Any],
) -> Tuple[BehavioralEvidence, ...]:
    """Derive baseline evidence items from computed metrics.

    Args:
        evaluation_id: deterministic id shared with the run config.
        metrics: metric name to ``MetricResult`` (as from ``compute_all``).
        decision_fingerprints: fingerprints of the records the metrics
            were derived from; every item references all of them.
        provenance: mapping carrying at least ``market_fingerprint``.

    Undefined metrics (``value=None``) still yield evidence items carrying
    the metric's undefined reason: absence of measurement is itself
    recorded explicitly.
    """
    if not isinstance(evaluation_id, str) or not evaluation_id.strip():
        raise ValueError("evaluation_id must be a non-empty string")
    if not isinstance(metrics, Mapping):
        raise TypeError("metrics must be a mapping of name to MetricResult")
    for name, metric in metrics.items():
        if not isinstance(metric, MetricResult):
            raise TypeError(
                f"metrics[{name!r}] must be a MetricResult, "
                f"got {type(metric).__name__}"
            )
    if isinstance(decision_fingerprints, (str, bytes)) or not isinstance(
        decision_fingerprints, (tuple, list)
    ):
        raise TypeError("decision_fingerprints must be a tuple/list of strings")
    refs = tuple(decision_fingerprints)
    if not refs:
        raise ValueError(
            "evidence requires at least one decision fingerprint; "
            "empty trajectories yield no evidence"
        )
    for ref in refs:
        if not isinstance(ref, str) or not ref:
            raise ValueError(
                "decision_fingerprints entries must be non-empty strings"
            )
    if len(set(refs)) != len(refs):
        raise ValueError("decision_fingerprints must not contain duplicates")
    if not isinstance(provenance, Mapping):
        raise TypeError("provenance must be a mapping")
    provenance = dict(provenance)
    marker = provenance.get("market_fingerprint")
    if not isinstance(marker, str) or not marker:
        raise ValueError(
            "provenance must carry a non-empty 'market_fingerprint'"
        )

    out: list[BehavioralEvidence] = []
    for metric_name, category in EVIDENCE_METRICS:
        try:
            metric = metrics[metric_name]
        except KeyError as exc:
            raise ValueError(
                f"metrics missing required evidence metric {metric_name!r}"
            ) from exc
        out.append(
            BehavioralEvidence(
                evidence_id=f"E1-{evaluation_id}-{metric_name}",
                category=category,
                metric_name=metric_name,
                value=metric.value,
                value_absent_reason=metric.undefined_reason,
                decision_refs=refs,
                derivation={
                    "method": metric.derivation,
                    "evaluator": EVALUATOR_ID,
                    "metric": metric_name,
                },
                provenance=dict(provenance),
            )
        )
    return tuple(out)


def evidence_metric_names() -> Tuple[str, ...]:
    """Names of the metrics promoted to baseline evidence, in order."""
    return tuple(name for name, _ in EVIDENCE_METRICS)
