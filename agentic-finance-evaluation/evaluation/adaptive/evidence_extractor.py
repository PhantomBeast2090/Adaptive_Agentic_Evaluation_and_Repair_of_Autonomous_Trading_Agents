"""Evidence extraction utilities for Phase 3 adaptive selection.

These utilities convert Phase 2 EpisodeEvaluation artifacts into
VulnerabilityRecord objects that the adaptive selector can consume.
"""
from typing import Dict, List, Optional

from src.schemas.vulnerability import VulnerabilityRecord
from src.schemas.static_evaluation import EpisodeEvaluation, FailureRecord


def extract_vulnerabilities_from_episode(
    episode: EpisodeEvaluation,
    scenario_meta: Optional[Dict[str, str]] = None,
) -> List[VulnerabilityRecord]:
    """Extract one or more vulnerability records from an EpisodeEvaluation.

    This function is intentionally conservative: each distinct FailureRecord
    becomes one VulnerabilityRecord. Later phases (diagnosis) can merge and
    interpret these observations.
    """
    vulns = []

    for failure in episode.failures:
        # failure is a FailureRecord
        evidence = [failure.model_dump()]

        metrics = {}
        # If the metric name exists in episode.metrics, surface it
        metric_val = episode.metrics.get(failure.metric_name)
        if metric_val is not None:
            metrics[failure.metric_name] = metric_val

        affected_regimes = []
        affected_difficulty = None
        if scenario_meta is not None:
            affected_regimes = [scenario_meta.get("market_regime")] if scenario_meta.get("market_regime") else []
            affected_difficulty = scenario_meta.get("difficulty")

        vuln = VulnerabilityRecord(
            vuln_id=f"{episode.episode_id}:{failure.metric_name}",
            category=failure.dimension,
            subtype=failure.metric_name,
            evidence=evidence,
            metrics=metrics,
            triggering_condition=failure.evidence,
            affected_regimes=affected_regimes,
            affected_difficulty=affected_difficulty,
            severity=failure.severity,
            provenance={
                "episode_id": episode.episode_id,
                "scenario_id": episode.scenario_id,
            },
            confidence=1.0,
        )

        vulns.append(vuln)

    return vulns
