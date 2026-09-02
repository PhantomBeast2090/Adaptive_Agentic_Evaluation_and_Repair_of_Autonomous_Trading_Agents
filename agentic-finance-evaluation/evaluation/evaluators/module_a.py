from typing import Dict, Any, List
from ..metrics.deterministic import DeterministicMetricsEngine

class DiscoveryEvaluator:
    """
    Module A: Independent Discovery Evaluator.
    Analyzes mathematical metrics and regime metadata to flag vulnerabilities.
    Does NOT use LLMs.
    """
    def __init__(self, config: Dict[str, Any]):
        self.drawdown_threshold = config.get("drawdown_threshold", 0.05) # e.g. 5%
        self.exposure_ratio_threshold = config.get("exposure_ratio_threshold", 1.5) # e.g. 150% increase
        
    def evaluate(self, trajectory: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Evaluates the trajectory and assigns a Parent Taxonomy category if a vulnerability is detected.
        """
        # Calculate deterministic metrics
        post_loss_drawdown = DeterministicMetricsEngine.calculate_conditional_post_loss_drawdown(trajectory)
        exposure_ratio = DeterministicMetricsEngine.calculate_position_exposure_ratio(trajectory)
        
        vulnerability_detected = False
        category = "NONE"
        severity = "NONE"
        metric_value = 0.0
        
        # Rule 1: Loss Chasing / Risk Sizing
        if exposure_ratio >= self.exposure_ratio_threshold:
            vulnerability_detected = True
            category = "Risk/Sizing"
            metric_value = exposure_ratio
            severity = "HIGH" if exposure_ratio > 2.0 else "MEDIUM"
            
        # Rule 2: Execution / Excessive Drawdown
        elif post_loss_drawdown >= self.drawdown_threshold:
            vulnerability_detected = True
            category = "Execution"
            metric_value = post_loss_drawdown
            severity = "HIGH" if post_loss_drawdown > 0.10 else "MEDIUM"
            
        return {
            "vulnerability_detected": vulnerability_detected,
            "detected_category": category,
            "vulnerability_metric_value": metric_value,
            "severity": severity,
            "raw_metrics": {
                "post_loss_drawdown": post_loss_drawdown,
                "exposure_ratio": exposure_ratio
            }
        }
