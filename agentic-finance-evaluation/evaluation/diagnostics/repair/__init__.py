"""E2-F repair and independent validation.

Deterministic, evidence-grounded repair of diagnosed trading agents:
propose a constrained intervention, apply it to an isolated copy,
validate the candidate on diagnostic and held-out windows with the
existing E1 machinery, analyse regressions explicitly, and decide
without ever letting the repair certify itself.
"""

from evaluation.diagnostics.repair.accounting import (
    ADMISSION_RECORD_KIND,
    COMPLETED_OUTCOME,
    LEDGER_METHOD,
    LEDGER_VERSION,
    PARTIAL_OUTCOME,
    RepairAdmission,
    RepairBudgetLedger,
    ValidationConsumption,
    admission_marker_id,
)
from evaluation.diagnostics.repair.application import (
    ApplicationStatus,
    GuardrailedAgent,
    RepairApplication,
    RepairedCandidate,
    apply_repair,
    fingerprint_agent,
    snapshot_policy,
)
from evaluation.diagnostics.repair.proposal import RepairProposal
from evaluation.diagnostics.repair.provider import (
    DEFAULT_RATIONALE,
    DEFAULT_RULES,
    PROVIDER_METHOD,
    PROVIDER_VERSION,
    RULE_TABLE,
    DeterministicRuleProvider,
    RepairProvider,
)
from evaluation.diagnostics.repair.regression import (
    REGRESSION_METHOD,
    REGRESSION_VERSION,
    RegressionAnalysis,
    RegressionFinding,
    ToleranceRule,
    analyze_regression,
)
from evaluation.diagnostics.repair.results import (
    DECISION_METHOD,
    DECISION_VERSION,
    RepairDecision,
    RepairResult,
    run_repair,
)
from evaluation.diagnostics.repair.validation import (
    VALIDATOR_METHOD,
    VALIDATOR_VERSION,
    ValidationPartialFailure,
    ValidationReport,
    ValidationRun,
    run_validation,
)

__all__ = [
    "ADMISSION_RECORD_KIND",
    "COMPLETED_OUTCOME",
    "LEDGER_METHOD",
    "LEDGER_VERSION",
    "PARTIAL_OUTCOME",
    "RepairAdmission",
    "RepairBudgetLedger",
    "ValidationConsumption",
    "admission_marker_id",
    "ApplicationStatus",
    "GuardrailedAgent",
    "RepairApplication",
    "RepairedCandidate",
    "apply_repair",
    "fingerprint_agent",
    "snapshot_policy",
    "RepairProposal",
    "DEFAULT_RATIONALE",
    "DEFAULT_RULES",
    "PROVIDER_METHOD",
    "PROVIDER_VERSION",
    "RULE_TABLE",
    "DeterministicRuleProvider",
    "RepairProvider",
    "REGRESSION_METHOD",
    "REGRESSION_VERSION",
    "RegressionAnalysis",
    "RegressionFinding",
    "ToleranceRule",
    "analyze_regression",
    "DECISION_METHOD",
    "DECISION_VERSION",
    "RepairDecision",
    "RepairResult",
    "run_repair",
    "VALIDATOR_METHOD",
    "VALIDATOR_VERSION",
    "ValidationReport",
    "ValidationRun",
    "run_validation",
]
