"""Candidate generation and selection utilities for Phase 3 adaptive selection.

Provides deterministic scoring and selection functions to choose next scenarios
to evaluate given observed vulnerabilities.
"""
from typing import List, Tuple, Dict, Any, Optional
import math
import random

from src.schemas.vulnerability import VulnerabilityRecord
from src.schemas.scenario import StaticScenario


SEVERITY_WEIGHTS = {
    "critical": 1.0,
    "high": 0.7,
    "medium": 0.4,
    "low": 0.1,
}


def score_scenario_for_vulnerability(
    vuln: VulnerabilityRecord,
    scenario: StaticScenario,
    seed: Optional[int] = None,
) -> float:
    """Compute a deterministic relevance score for a scenario given a vulnerability.

    Scoring is intentionally simple and interpretable:
      - +1.0 if market_regime matches one of vuln.affected_regimes
      - +0.5 if difficulty matches vuln.affected_difficulty
      - +severity weight
      - tiny deterministic tie-breaker from seed
    """
    score = 0.0

    if vuln.affected_regimes and scenario.market_regime in vuln.affected_regimes:
        score += 1.0

    if vuln.affected_difficulty and scenario.difficulty == vuln.affected_difficulty:
        score += 0.5

    if vuln.severity:
        score += SEVERITY_WEIGHTS.get(vuln.severity, 0.2)

    # Deterministic tiny tie-breaker
    rnd = random.Random(seed or 0)
    tie = rnd.random() * 1e-6
    return score + tie


def rank_candidates(
    vuln: VulnerabilityRecord,
    pool: List[StaticScenario],
    top_k: int = 10,
    seed: Optional[int] = None,
) -> List[Tuple[StaticScenario, float]]:
    """Return top-k candidate scenarios scored for the given vulnerability.

    Deterministic ordering is ensured via the provided seed.
    """
    scored: List[Tuple[StaticScenario, float]] = []
    for s in pool:
        sc = score_scenario_for_vulnerability(vuln, s, seed=seed)
        scored.append((s, sc))

    # Sort by score desc, then by scenario_id for deterministic tie-breaking
    scored.sort(key=lambda pair: (pair[1], pair[0].scenario_id), reverse=True)

    return scored[:top_k]
