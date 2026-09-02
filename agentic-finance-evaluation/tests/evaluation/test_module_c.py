import pytest
from evaluation.evaluators.module_c import InterventionGenerator


def test_intervention_for_risk_sizing():
    """Intervention is generated for a Risk/Sizing vulnerability."""
    gen = InterventionGenerator()

    discovery = {
        "vulnerability_detected": True,
        "detected_category": "Risk/Sizing",
        "severity": "HIGH",
        "vulnerability_metric_value": 2.5,
        "raw_metrics": {"exposure_ratio": 2.5, "post_loss_drawdown": 0.02},
    }
    diagnosis = {
        "diagnosed_mechanism": "Agent increases position size after losses.",
        "confidence_score": 0.95,
    }

    result = gen.generate(discovery, diagnosis)

    assert result["intervention_applied"] is True
    assert "position size" in result["payload"]["behavioral_rule"].lower()
    assert result["provenance"]["detected_category"] == "Risk/Sizing"
    assert result["provenance"]["diagnosis_confidence"] == 0.95


def test_intervention_for_execution():
    """Intervention is generated for an Execution vulnerability."""
    gen = InterventionGenerator()

    discovery = {
        "vulnerability_detected": True,
        "detected_category": "Execution",
        "severity": "MEDIUM",
        "raw_metrics": {"post_loss_drawdown": 0.08},
    }
    diagnosis = {
        "diagnosed_mechanism": "Agent fails to adapt to market conditions.",
        "confidence_score": 0.7,
    }

    result = gen.generate(discovery, diagnosis)

    assert result["intervention_applied"] is True
    assert "vix" in result["payload"]["trigger_condition"].lower()


def test_no_intervention_for_no_vulnerability():
    """No intervention when no vulnerability was detected."""
    gen = InterventionGenerator()

    discovery = {
        "vulnerability_detected": False,
        "detected_category": "NONE",
        "severity": "NONE",
        "raw_metrics": {},
    }
    diagnosis = {
        "diagnosed_mechanism": "",
        "confidence_score": 0.0,
    }

    result = gen.generate(discovery, diagnosis)

    assert result["intervention_applied"] is False
    assert result["payload"] == {}


def test_no_intervention_for_unknown_category():
    """No intervention when the category is not in the catalog."""
    gen = InterventionGenerator()

    discovery = {
        "vulnerability_detected": True,
        "detected_category": "UnknownCategory",
        "severity": "HIGH",
        "raw_metrics": {},
    }
    diagnosis = {
        "diagnosed_mechanism": "Something unusual.",
        "confidence_score": 0.9,
    }

    result = gen.generate(discovery, diagnosis)

    assert result["intervention_applied"] is False
