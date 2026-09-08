"""Adaptive selection loop orchestration for Phase 3.

This runner implements a lightweight adaptive loop that:
  - runs a small initial evaluation set
  - extracts vulnerabilities from observed failures
  - generates candidate scenarios biased by vulnerabilities
  - selects new scenarios deterministically (or randomly for baseline)
  - evaluates selected scenarios until budget exhausted

The implementation reuses Phase 2 primitives (episode runner, metrics,
evaluators) where available, and is written to be testable via
monkeypatching the ``_evaluate_episode`` method.

Phase-3 invariants (enforced, not caller discipline):
  - Holdout/OOD scenarios can never enter discovery through this runner.
  - The configured seed is propagated to the evaluation callable so the
    final trajectory/run record contains the experiment seed.
  - Each selection records rank/score/reason for scientific provenance.
"""
from typing import List, Dict, Any, Optional
import random
from collections import defaultdict

from agents.financial_agent.base import BaseTradingAgent
from src.schemas.vulnerability import VulnerabilityRecord
from src.schemas.scenario import StaticScenario
from src.schemas.static_evaluation import EpisodeEvaluation
from evaluation.adaptive.evidence_extractor import extract_vulnerabilities_from_episode
from evaluation.adaptive.selector import rank_candidates


# Source splits that must never enter Phase-3 discovery, even if mislabelled
# with holdout=False. The primary guard is `holdout == True`; this set is
# defense-in-depth for OOD pool-construction mistakes.
OOD_SOURCE_SPLITS = {"ood_validation", "holdout", "ood"}


def _validate_pool_has_no_holdout(scenario_pool: List[StaticScenario]) -> None:
    """Reject any holdout/OOD scenario before it can enter discovery."""
    for s in scenario_pool:
        if bool(getattr(s, "holdout", False)):
            raise ValueError(
                f"Holdout scenario '{s.scenario_id}' (holdout=True) must not "
                f"enter Phase-3 adaptive discovery. Build the candidate pool "
                f"from discovery splits only."
            )
        source = str(getattr(s, "source_split", "") or "")
        if source in OOD_SOURCE_SPLITS:
            raise ValueError(
                f"OOD scenario '{s.scenario_id}' (source_split='{source}') must not "
                f"enter Phase-3 adaptive discovery. Build the candidate pool "
                f"from discovery splits only."
            )


class AdaptiveRunner:
    """Simple adaptive selection runner.

    Arguments and defaults are conservative; the runner is intended to be
    deterministic given a seed and to be easy to test.
    """

    def __init__(self, scenario_pool: List[StaticScenario], seed: int = 0, evaluate_callable=None):
        """Create an AdaptiveRunner.

        Args:
            scenario_pool: list of `StaticScenario` to consider. Must exclude
                holdout/OOD; enforced with an explicit error (not silent filtering).
            seed: deterministic seed for selection. Propagated to the evaluation
                callable so trajectories carry the experiment seed.
            evaluate_callable: optional callable(agent, scenario, seed=None)
                -> EpisodeEvaluation. If None, caller should monkeypatch
                `_evaluate_episode` before running. This keeps tests
                flexible and avoids circular imports.
        """
        _validate_pool_has_no_holdout(list(scenario_pool))
        self.scenario_pool = {s.scenario_id: s for s in scenario_pool}
        self.seed = seed
        self.rng = random.Random(seed)
        if evaluate_callable is not None:
            # If evaluate_callable is already a bound method (has __self__), use it
            # as-is; otherwise bind it to this instance so it receives (self, ...)
            import types

            if hasattr(evaluate_callable, "__self__") and evaluate_callable.__self__ is not None:
                # bound method (e.g., static_eval.evaluate_on_scenario)
                # Wrap so the runner seed flows through the existing
                # (agent, scenario, seed=None) interface into Trajectory.seed.
                def adapter(_self, agent, scenario):
                    return evaluate_callable(agent, scenario, seed=_self.seed)

                self._evaluate_episode = types.MethodType(adapter, self)
            else:
                # unbound function; bind it so it receives (self, ...)
                self._evaluate_episode = types.MethodType(evaluate_callable, self)

    def _evaluate_episode(self, agent: BaseTradingAgent, scenario: StaticScenario) -> EpisodeEvaluation:
        """Default _evaluate_episode raises unless an evaluate_callable was provided.

        Callers may provide `evaluate_callable` in the constructor or monkeypatch
        this method in tests. In real runs pass `StaticEvaluator.evaluate_on_scenario`
        (bound) as the evaluate_callable.
        """
        raise NotImplementedError("_evaluate_episode must be provided by caller or monkeypatched in tests")

    def run(
        self,
        agent: BaseTradingAgent,
        initial_samples: int = 2,
        budget: int = 5,
        batch_size: int = 1,
        strategy: str = "adaptive",
    ) -> Dict[str, Any]:
        """Run the adaptive selection loop and return a report with provenance.

        Returns a dictionary with discovery metrics, evaluated episodes, the
        ordered scenario sequence, and per-step selection metadata (rank, score,
        reason) sufficient to reconstruct WHY each scenario was selected.
        """
        if strategy not in ("adaptive", "random"):
            raise ValueError(f"Unknown strategy '{strategy}'. Expected 'adaptive' or 'random'.")
        if budget < 1:
            raise ValueError(f"budget must be >= 1, got {budget}")
        if initial_samples < 1:
            raise ValueError(f"initial_samples must be >= 1, got {initial_samples}")
        if batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {batch_size}")
        if initial_samples > budget:
            raise ValueError(
                f"initial_samples ({initial_samples}) must not exceed budget ({budget})"
            )
        if initial_samples > len(self.scenario_pool):
            raise ValueError(
                f"initial_samples ({initial_samples}) exceeds pool size ({len(self.scenario_pool)})"
            )

        evaluated = {}
        episode_history: List[EpisodeEvaluation] = []
        vulnerabilities: List[VulnerabilityRecord] = []
        selection_history: List[Dict[str, Any]] = []

        # Initial sampling from pool (deterministic)
        pool_ids = list(self.scenario_pool.keys())
        self.rng.shuffle(pool_ids)
        initial = pool_ids[:initial_samples]

        for order, sid in enumerate(initial):
            scenario = self.scenario_pool[sid]
            ep = self._evaluate_episode(agent, scenario)
            evaluated[sid] = ep
            episode_history.append(ep)
            vulnerabilities.extend(extract_vulnerabilities_from_episode(ep, scenario_meta={
                "market_regime": scenario.market_regime,
                "difficulty": scenario.difficulty,
            }))
            selection_history.append({
                "step": order,
                "scenario_id": sid,
                "phase": "initial",
                "strategy": strategy,
                "rank": order,
                "score": None,
                "reason": "initial_sample: deterministic rng shuffle of candidate pool",
                "contributing_vulns": [],
                "contributing_categories": [],
                "market_regime": scenario.market_regime,
                "difficulty": scenario.difficulty,
            })

        remaining_budget = budget - len(initial)

        # Adaptive loop
        while remaining_budget > 0:
            # Build candidate pool excluding already evaluated
            candidates = [s for s in self.scenario_pool.values() if s.scenario_id not in evaluated]
            if not candidates:
                break

            if strategy == "random":
                # Random baseline: deterministic sampling with seed
                self.rng.shuffle(candidates)
                to_eval = candidates[:batch_size]
                scored_for_history: Dict[str, Optional[float]] = {s.scenario_id: None for s in to_eval}
                rank_for_history: Dict[str, int] = {
                    s.scenario_id: i for i, s in enumerate(to_eval)
                }
                reason_for_history: Dict[str, str] = {
                    s.scenario_id: "random_baseline: deterministic rng shuffle" for s in to_eval
                }
                contrib_for_history: Dict[str, List[str]] = {
                    s.scenario_id: [] for s in to_eval
                }
            else:
                # Aggregate ranked candidates across vulnerabilities.
                # If no vulnerabilities have been observed yet, fall back to a
                # deterministic random sampling to avoid an infinite loop where
                # no candidates are selected and the remaining budget never
                # decreases.
                if not vulnerabilities:
                    self.rng.shuffle(candidates)
                    to_eval = candidates[:batch_size]
                    scored_for_history = {s.scenario_id: None for s in to_eval}
                    rank_for_history = {s.scenario_id: i for i, s in enumerate(to_eval)}
                    reason_for_history = {
                        s.scenario_id: "adaptive_fallback_no_vulns: deterministic rng shuffle"
                        for s in to_eval
                    }
                    contrib_for_history = {s.scenario_id: [] for s in to_eval}
                else:
                    scores: Dict[str, float] = defaultdict(float)
                    contrib: Dict[str, List[str]] = defaultdict(list)
                    for v in vulnerabilities:
                        ranked = rank_candidates(v, candidates, top_k=len(candidates), seed=self.seed)
                        for s, sc in ranked:
                            scores[s.scenario_id] += sc
                            contrib[s.scenario_id].append(f"{v.category}:{v.subtype}")

                    # Sort by aggregated score
                    sorted_ids = sorted(scores.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
                    to_eval = [self.scenario_pool[sid] for sid, _ in sorted_ids[:batch_size]]
                    scored_for_history = {sid: scores[sid] for sid, _ in sorted_ids[:batch_size]}
                    rank_for_history = {
                        sid: rank for rank, (sid, _) in enumerate(sorted_ids[:batch_size])
                    }
                    reason_for_history = {}
                    contrib_for_history = {}
                    for sid, score in sorted_ids[:batch_size]:
                        cats = sorted(set(contrib[sid]))
                        scenario = self.scenario_pool[sid]
                        reason_for_history[sid] = (
                            f"adaptive_rank: aggregated_score={score:.6f} across "
                            f"{len(vulnerabilities)} vuln(s); categories={cats}; "
                            f"scenario regime={scenario.market_regime} "
                            f"difficulty={scenario.difficulty}"
                        )
                        contrib_for_history[sid] = cats

            # Evaluate selected candidates
            for scenario in to_eval:
                ep = self._evaluate_episode(agent, scenario)
                evaluated[scenario.scenario_id] = ep
                episode_history.append(ep)
                vulnerabilities.extend(extract_vulnerabilities_from_episode(ep, scenario_meta={
                    "market_regime": scenario.market_regime,
                    "difficulty": scenario.difficulty,
                }))
                step = len(selection_history)
                selection_history.append({
                    "step": step,
                    "scenario_id": scenario.scenario_id,
                    "phase": "selection",
                    "strategy": strategy,
                    "rank": rank_for_history.get(scenario.scenario_id),
                    "score": scored_for_history.get(scenario.scenario_id),
                    "reason": reason_for_history.get(scenario.scenario_id, ""),
                    "contributing_vulns": contrib_for_history.get(scenario.scenario_id, []),
                    "contributing_categories": contrib_for_history.get(scenario.scenario_id, []),
                    "market_regime": scenario.market_regime,
                    "difficulty": scenario.difficulty,
                })
                remaining_budget -= 1
                if remaining_budget <= 0:
                    break

        # Discovery metrics
        unique_vuln_types = set((v.category, v.subtype) for v in vulnerabilities)

        report = {
            "evaluated_count": len(evaluated),
            "unique_vulnerabilities": len(unique_vuln_types),
            "unique_vulnerability_categories": sorted(
                f"{c}:{s}" for c, s in unique_vuln_types
            ),
            "episodes": episode_history,
            "vulnerabilities": vulnerabilities,
            # Provenance for comparability and persistence
            "seed": self.seed,
            "strategy": strategy,
            "budget": budget,
            "initial_samples": initial_samples,
            "batch_size": batch_size,
            "scenario_sequence": [ep.scenario_id for ep in episode_history],
            "selection_history": selection_history,
        }

        return report
