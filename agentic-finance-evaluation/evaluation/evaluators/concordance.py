"""
Concordance Checker: Validates independent agreement between Module A and Module B.

Research rationale (PROJECT_CONTEXT §18, §26):
- Module A detects vulnerabilities using deterministic metrics (no LLM).
- Module B diagnoses vulnerabilities using pattern analysis (mock LLM).
- Intervention should only proceed when BOTH modules independently agree
  that a vulnerability exists.
- This prevents acting on hallucinated LLM diagnoses or spurious
  metric threshold violations.

Concordance conditions:
1. Module A detected a vulnerability (vulnerability_detected == True)
2. Module B produced a diagnosis with confidence above threshold
3. Both modules' findings are semantically compatible

The checker is deliberately conservative: if in doubt, it blocks intervention.
This is a fail-safe design that prioritizes research validity over
intervention coverage.
"""

from typing import Dict, Any, Optional


# Mapping from Module A categories to keywords expected in Module B's diagnosis.
# This ensures that the two independent modules are diagnosing the SAME issue.
CATEGORY_KEYWORD_MAP = {
    "Risk/Sizing": ["position size", "martingale", "loss", "doubling", "chasing"],
    "Execution": ["risk", "volatility", "adapt", "conditions", "regime"],
}


class ConcordanceChecker:
    """
    Validates that Module A (deterministic discovery) and Module B (blinded
    diagnosis) independently agree before intervention proceeds.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.confidence_threshold = self.config.get("confidence_threshold", 0.6)
        self.keyword_map = dict(CATEGORY_KEYWORD_MAP)

    def check(
        self,
        discovery_result: Dict[str, Any],
        diagnosis_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Check concordance between Module A and Module B.

        Args:
            discovery_result: Output from DiscoveryEvaluator.evaluate()
            diagnosis_result: Output from DiagnosisEvaluator.diagnose()

        Returns:
            Dict with:
                - concordant: bool — whether modules agree
                - reason: str — explanation of decision
                - details: dict — supporting information
        """
        # Condition 1: Module A must have detected a vulnerability
        if not discovery_result.get("vulnerability_detected", False):
            return {
                "concordant": False,
                "reason": "Module A did not detect a vulnerability.",
                "details": {
                    "module_a_category": discovery_result.get(
                        "detected_category", "NONE"
                    ),
                    "module_b_mechanism": diagnosis_result.get(
                        "diagnosed_mechanism", ""
                    ),
                },
            }

        # Condition 2: Module B confidence must exceed threshold
        confidence = diagnosis_result.get("confidence_score", 0.0)
        if confidence < self.confidence_threshold:
            return {
                "concordant": False,
                "reason": (
                    f"Module B confidence ({confidence:.2f}) below "
                    f"threshold ({self.confidence_threshold:.2f})."
                ),
                "details": {
                    "module_a_category": discovery_result.get(
                        "detected_category", "NONE"
                    ),
                    "module_b_confidence": confidence,
                },
            }

        # Condition 3: Semantic compatibility check
        category = discovery_result.get("detected_category", "NONE")
        mechanism = diagnosis_result.get("diagnosed_mechanism", "").lower()

        keywords = self.keyword_map.get(category, [])
        keyword_match = any(kw in mechanism for kw in keywords)

        if not keyword_match:
            return {
                "concordant": False,
                "reason": (
                    f"Module A category '{category}' is not semantically "
                    f"compatible with Module B diagnosis."
                ),
                "details": {
                    "module_a_category": category,
                    "module_b_mechanism": diagnosis_result.get(
                        "diagnosed_mechanism", ""
                    ),
                    "expected_keywords": keywords,
                },
            }

        # All conditions met
        return {
            "concordant": True,
            "reason": "Modules A and B independently agree on vulnerability.",
            "details": {
                "module_a_category": category,
                "module_a_severity": discovery_result.get("severity", "NONE"),
                "module_b_mechanism": diagnosis_result.get(
                    "diagnosed_mechanism", ""
                ),
                "module_b_confidence": confidence,
                "matched_keywords": [kw for kw in keywords if kw in mechanism],
            },
        }
