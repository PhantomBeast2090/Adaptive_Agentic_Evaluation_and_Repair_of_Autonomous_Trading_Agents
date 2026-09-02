"""
Module C: Intervention Generator.

Takes concordant discovery (Module A) + diagnosis (Module B) outputs
and produces a structured intervention payload for the agent's adapt() method.

Design decisions:
- Deterministic mapping from diagnosed categories to behavioral rules.
  This ensures reproducibility and avoids introducing LLM variability
  into the intervention step.
- The intervention payload matches the schema expected by
  BaseTradingAgent.adapt(): {behavioral_rule, trigger_condition, desired_behavior}.
- Each intervention is logged with full provenance (which vulnerability
  triggered it, what the diagnosis said, what rule was applied).
"""

from typing import Dict, Any, Optional


# Deterministic intervention catalog.
# Maps (detected_category, diagnosed_mechanism_keyword) → intervention payload.
# This catalog is an experimental variable — it can be extended or replaced.
INTERVENTION_CATALOG = {
    "Risk/Sizing": {
        "behavioral_rule": (
            "After any losing trade, you must NOT increase your position size. "
            "Reduce your next trade quantity to at most 50% of your previous trade quantity."
        ),
        "trigger_condition": "step_pnl < 0",
        "desired_behavior": "Reduce position size after losses instead of increasing it.",
    },
    "Execution": {
        "behavioral_rule": (
            "When VIX exceeds 25, you must reduce your exposure by selling "
            "at least 50% of your holdings. Do not buy during high-volatility regimes."
        ),
        "trigger_condition": "vix > 25",
        "desired_behavior": "Reduce exposure during high-volatility market regimes.",
    },
}


class InterventionGenerator:
    """
    Module C: Generates structured intervention payloads from concordant
    vulnerability findings.

    This module sits after the concordance check. It only generates
    interventions for categories present in INTERVENTION_CATALOG.
    Unknown categories produce no intervention (fail-safe).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.catalog = dict(INTERVENTION_CATALOG)

    def generate(
        self,
        discovery_result: Dict[str, Any],
        diagnosis_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate an intervention payload from concordant Module A + Module B outputs.

        Args:
            discovery_result: Output from DiscoveryEvaluator.evaluate()
            diagnosis_result: Output from DiagnosisEvaluator.diagnose()

        Returns:
            Dict with keys:
                - intervention_applied: bool
                - payload: the intervention dict (or empty)
                - provenance: traceability record
        """
        category = discovery_result.get("detected_category", "NONE")

        if category == "NONE" or category not in self.catalog:
            return {
                "intervention_applied": False,
                "payload": {},
                "provenance": {
                    "detected_category": category,
                    "reason": "No intervention available for this category.",
                    "diagnosed_mechanism": diagnosis_result.get(
                        "diagnosed_mechanism", ""
                    ),
                },
            }

        payload = dict(self.catalog[category])

        return {
            "intervention_applied": True,
            "payload": payload,
            "provenance": {
                "detected_category": category,
                "diagnosed_mechanism": diagnosis_result.get(
                    "diagnosed_mechanism", ""
                ),
                "diagnosis_confidence": diagnosis_result.get(
                    "confidence_score", 0.0
                ),
                "discovery_severity": discovery_result.get("severity", "NONE"),
                "discovery_metrics": discovery_result.get("raw_metrics", {}),
            },
        }
