import json

from src.schemas.agent import AgentProfile
from src.schemas.evaluation import EvaluationResult
from src.schemas.repair import RepairRecord
from src.schemas.scenario import Scenario


def _to_json(model):
    if hasattr(model, "model_dump_json"):
        return model.model_dump_json()
    return model.json()


def test_core_schemas_are_json_serializable():
    instances = [
        Scenario(
            scenario_id="scenario_001",
            source="synthetic",
            dimension="risk",
            difficulty="unit",
            market_regime="flat",
            information_state={"available_fields": ["date", "market_price", "vix"]},
            task="trade",
            constraints=["long_only"],
            ground_truth={},
            expected_behaviour="preserve capital",
            holdout=False,
        ),
        EvaluationResult(
            run_id="run_001",
            agent_version="v1",
            scenario_id="scenario_001",
            evaluator_id="phase1_smoke",
            score=1.0,
            failure=False,
            severity="NONE",
            evidence="complete episode executed",
            confidence=1.0,
            cost=0.0,
            latency=0.0,
            timestamp="2026-09-02T00:00:00Z",
        ),
        AgentProfile(
            agent_id="control",
            agent_version="v1",
            capability_scores={},
            known_failures=[],
            verified_causes=[],
            tested_dimensions=["environment_lifecycle"],
            untested_dimensions=[],
            repair_history=[],
            evaluation_history=["run_001"],
        ),
        RepairRecord(
            failure_id="failure_001",
            root_cause="not_applicable",
            repair_type="none",
            old_agent_version="v1",
            new_agent_version="v1",
            expected_effect="not_applicable",
            actual_effect="not_applicable",
            validation_result="not_run",
            regression_result="not_run",
        ),
    ]

    for instance in instances:
        encoded = _to_json(instance)
        decoded = json.loads(encoded)
        assert isinstance(decoded, dict)
