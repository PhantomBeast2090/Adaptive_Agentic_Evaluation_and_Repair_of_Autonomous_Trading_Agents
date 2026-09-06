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


class AdaptiveRunner:
    """Simple adaptive selection runner.

    Arguments and defaults are conservative; the runner is intended to be
    deterministic given a seed and to be easy to test.
    """

    def __init__(self, scenario_pool: List[StaticScenario], seed: int = 0, evaluate_callable=None):
        """Create an AdaptiveRunner.

        Args:
            scenario_pool: list of `StaticScenario` to consider (should exclude holdout)
            seed: deterministic seed for selection
            evaluate_callable: optional callable(agent, scenario) -> EpisodeEvaluation. If None,
                caller should monkeypatch `_evaluate_episode` before running. This keeps tests
                flexible and avoids circular imports.
        """
        self.scenario_pool = {s.scenario_id: s for s in scenario_pool}
        self.seed = seed
        self.rng = random.Random(seed)
        if evaluate_callable is not None:
            # If evaluate_callable is already a bound method (has __self__), use it
            # as-is; otherwise bind it to this instance so it receives (self, ...)
            import types

            if hasattr(evaluate_callable, "__self__") and evaluate_callable.__self__ is not None:
                # bound method (e.g., static_eval.evaluate_on_scenario)
                # wrap in a thin adapter to match (agent, scenario) signature
                def adapter(_self, agent, scenario):
                    # evaluate_callable expects (agent, scenario, seed=None) on its bound self
                    return evaluate_callable(agent, scenario)

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
        """Run the adaptive selection loop and return a small report.

        Returns a dictionary with discovery metrics and evaluated episodes.
        The implementation is intentionally synchronous and simple.
        """
        evaluated = {}
        episode_history: List[EpisodeEvaluation] = []
        vulnerabilities: List[VulnerabilityRecord] = []

        # Initial sampling from pool (deterministic)
        pool_ids = list(self.scenario_pool.keys())
        self.rng.shuffle(pool_ids)
        initial = pool_ids[:initial_samples]

        for sid in initial:
            scenario = self.scenario_pool[sid]
            ep = self._evaluate_episode(agent, scenario)
            evaluated[sid] = ep
            episode_history.append(ep)
            vulnerabilities.extend(extract_vulnerabilities_from_episode(ep, scenario_meta={
                "market_regime": scenario.market_regime,
                "difficulty": scenario.difficulty,
            }))

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
            else:
                # Aggregate ranked candidates across vulnerabilities.
                # If no vulnerabilities have been observed yet, fall back to a
                # deterministic random sampling to avoid an infinite loop where
                # no candidates are selected and the remaining budget never
                # decreases.
                if not vulnerabilities:
                    self.rng.shuffle(candidates)
                    to_eval = candidates[:batch_size]
                else:
                    scores: Dict[str, float] = defaultdict(float)
                    for v in vulnerabilities:
                        ranked = rank_candidates(v, candidates, top_k=len(candidates), seed=self.seed)
                        for s, sc in ranked:
                            scores[s.scenario_id] += sc

                    # Sort by aggregated score
                    sorted_ids = sorted(scores.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
                    to_eval = [self.scenario_pool[sid] for sid, _ in sorted_ids[:batch_size]]

            # Evaluate selected candidates
            for scenario in to_eval:
                ep = self._evaluate_episode(agent, scenario)
                evaluated[scenario.scenario_id] = ep
                episode_history.append(ep)
                vulnerabilities.extend(extract_vulnerabilities_from_episode(ep, scenario_meta={
                    "market_regime": scenario.market_regime,
                    "difficulty": scenario.difficulty,
                }))
                remaining_budget -= 1
                if remaining_budget <= 0:
                    break

        # Discovery metrics
        unique_vuln_types = set((v.category, v.subtype) for v in vulnerabilities)

        report = {
            "evaluated_count": len(evaluated),
            "unique_vulnerabilities": len(unique_vuln_types),
            "episodes": episode_history,
            "vulnerabilities": vulnerabilities,
        }

        return report
