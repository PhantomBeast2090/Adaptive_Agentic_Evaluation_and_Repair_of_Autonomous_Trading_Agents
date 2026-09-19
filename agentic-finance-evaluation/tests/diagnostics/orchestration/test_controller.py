"""Controller input validation (no environment execution)."""

import pytest

from evaluation.diagnostics.orchestration.config import OrchestrationConfig
from evaluation.diagnostics.orchestration.controller import run

from ..execution_fixtures import HoldAgent
from .fixtures import make_loop_baseline, make_loop_config, make_loop_state

_FAKE_SPEC = {"market_fingerprint": "mfp-fixture"}


def _triplet(**cfg_overrides):
    baseline = make_loop_baseline()
    agent = HoldAgent()
    state = make_loop_state(baseline, _FAKE_SPEC)
    config = make_loop_config(baseline, agent, **cfg_overrides)
    return state, baseline, agent, config


def test_rejects_wrong_state_type():
    _, baseline, agent, config = _triplet()
    with pytest.raises(TypeError):
        run(diagnostic_state="nope", baseline=baseline,
            target_agent=agent, config=config)


def test_rejects_wrong_baseline_and_config_types():
    state, baseline, agent, config = _triplet()
    with pytest.raises(TypeError):
        run(diagnostic_state=state, baseline="nope",
            target_agent=agent, config=config)
    with pytest.raises(TypeError):
        run(diagnostic_state=state, baseline=baseline,
            target_agent=agent, config="nope")


def test_rejects_invalid_agent():
    state, baseline, _, config = _triplet()
    with pytest.raises(TypeError):
        run(diagnostic_state=state, baseline=baseline,
            target_agent=object(), config=config)


def test_rejects_agent_identity_mismatch():
    from ..execution_fixtures import BuyOnceAgent

    state, baseline, _, _ = _triplet()
    buyer = BuyOnceAgent()
    config = make_loop_config(baseline, HoldAgent())
    with pytest.raises(ValueError):
        run(diagnostic_state=state, baseline=baseline,
            target_agent=buyer, config=config)


def test_rejects_diagnostic_id_mismatch():
    state, baseline, agent, _ = _triplet()
    config = make_loop_config(baseline, agent, diagnostic_id="D-OTHER")
    with pytest.raises(ValueError):
        run(diagnostic_state=state, baseline=baseline,
            target_agent=agent, config=config)


def test_rejects_baseline_identity_mismatch():
    state, baseline, agent, config = _triplet()
    other = make_loop_baseline(evaluation_id="B-OTHER")
    with pytest.raises(ValueError):
        run(diagnostic_state=state, baseline=other,
            target_agent=agent, config=config)


def test_rejects_already_stopped_state():
    from evaluation.contracts.stopping import StoppingReason

    state, baseline, agent, config = _triplet()
    state.set_stopping_reason(StoppingReason.BUDGET_EXHAUSTED)
    with pytest.raises(ValueError):
        run(diagnostic_state=state, baseline=baseline,
            target_agent=agent, config=config)


def test_config_validation_rules():
    baseline = make_loop_baseline()
    agent = HoldAgent()
    good = make_loop_config(baseline, agent).to_dict()
    assert OrchestrationConfig.from_dict(good).fingerprint() == (
        make_loop_config(baseline, agent).fingerprint()
    )
    for bad_key, bad_value in [
        ("max_iterations", 0),
        ("max_iterations", -2),
        ("max_iterations", True),
        ("seed", 1.5),
        ("seed", True),
        ("diagnostic_id", "  "),
        ("agent_id", ""),
        ("base_dir", ""),
        ("window", ("2023-05-26", "2023-05-15")),
    ]:
        payload = dict(good)
        payload[bad_key] = bad_value
        with pytest.raises((TypeError, ValueError)):
            OrchestrationConfig.from_dict(payload)
    with pytest.raises(ValueError):
        OrchestrationConfig.from_dict({**good, "unknown_field": 1})
    with pytest.raises(TypeError):
        OrchestrationConfig.from_dict("not-a-mapping")
