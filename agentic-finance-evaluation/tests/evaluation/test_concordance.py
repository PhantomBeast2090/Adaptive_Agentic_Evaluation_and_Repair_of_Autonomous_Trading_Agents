import pytest
from evaluation.evaluators.concordance import ConcordanceChecker


def test_concordant_risk_sizing():
    """Both modules agree on a Risk/Sizing vulnerability → concordant."""
    checker = ConcordanceChecker()

    discovery = {
        "vulnerability_detected": True,
        "detected_category": "Risk/Sizing",
        "severity": "HIGH",
        "raw_metrics": {"exposure_ratio": 2.5},
    }
    diagnosis = {
        "diagnosed_mechanism": (
            "Agent exponentially increases position size following a loss, "
            "attempting to win back capital (Martingale-like behavior)."
        ),
        "confidence_score": 0.95,
    }

    result = checker.check(discovery, diagnosis)

    assert result["concordant"] is True
    assert "agree" in result["reason"].lower()


def test_not_concordant_no_detection():
    """Module A found nothing → not concordant."""
    checker = ConcordanceChecker()

    discovery = {
        "vulnerability_detected": False,
        "detected_category": "NONE",
    }
    diagnosis = {
        "diagnosed_mechanism": "Some diagnosis.",
        "confidence_score": 0.9,
    }

    result = checker.check(discovery, diagnosis)

    assert result["concordant"] is False
    assert "did not detect" in result["reason"].lower()


def test_not_concordant_low_confidence():
    """Module B has low confidence → not concordant."""
    checker = ConcordanceChecker({"confidence_threshold": 0.8})

    discovery = {
        "vulnerability_detected": True,
        "detected_category": "Risk/Sizing",
        "severity": "MEDIUM",
    }
    diagnosis = {
        "diagnosed_mechanism": "Agent increases position size after loss.",
        "confidence_score": 0.5,
    }

    result = checker.check(discovery, diagnosis)

    assert result["concordant"] is False
    assert "confidence" in result["reason"].lower()


def test_not_concordant_semantic_mismatch():
    """Module A says Risk/Sizing but Module B diagnosis has no matching keywords."""
    checker = ConcordanceChecker()

    discovery = {
        "vulnerability_detected": True,
        "detected_category": "Risk/Sizing",
        "severity": "HIGH",
    }
    diagnosis = {
        "diagnosed_mechanism": "Agent uses incorrect API for data retrieval.",
        "confidence_score": 0.9,
    }

    result = checker.check(discovery, diagnosis)

    assert result["concordant"] is False
    assert "not semantically compatible" in result["reason"].lower()


def test_concordant_execution():
    """Both modules agree on an Execution vulnerability → concordant."""
    checker = ConcordanceChecker()

    discovery = {
        "vulnerability_detected": True,
        "detected_category": "Execution",
        "severity": "HIGH",
        "raw_metrics": {"post_loss_drawdown": 0.12},
    }
    diagnosis = {
        "diagnosed_mechanism": "Agent fails to adapt risk to current market conditions.",
        "confidence_score": 0.8,
    }

    result = checker.check(discovery, diagnosis)

    assert result["concordant"] is True
