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


def _universe_kwargs():
    from ..execution_fixtures import FULL_UNIVERSE

    return {"universe": {k: list(v) for k, v in FULL_UNIVERSE.items()}}


def test_universe_top_level_assignment_fails():
    state, baseline, agent, _ = _triplet()
    config = make_loop_config(baseline, agent, **_universe_kwargs())
    with pytest.raises(TypeError):
        config.universe["nse_equity"] = ()


def test_universe_nested_mutation_fails():
    state, baseline, agent, _ = _triplet()
    config = make_loop_config(baseline, agent, **_universe_kwargs())
    with pytest.raises((TypeError, AttributeError)):
        config.universe["nse_equity"].append("INFY:EQ")


def test_universe_fingerprint_stable():
    state, baseline, agent, _ = _triplet()
    config = make_loop_config(baseline, agent, **_universe_kwargs())
    before = config.fingerprint()
    for attempt in (
        lambda: config.universe.__setitem__("nse_equity", ()),
        lambda: config.universe["nse_equity"].append("INFY:EQ"),
    ):
        try:
            attempt()
        except (TypeError, AttributeError):
            pass
    assert config.fingerprint() == before


def test_caller_owned_universe_cannot_mutate_config():
    state, baseline, agent, _ = _triplet()
    owned = {k: list(v) for k, v in _universe_kwargs()["universe"].items()}
    config = make_loop_config(baseline, agent, universe=owned)
    before = config.fingerprint()
    owned["nse_equity"].append("INFY:EQ")
    owned["mcx_gold"] = []
    assert config.fingerprint() == before
    assert tuple(config.universe["nse_equity"]) == (
        "RELIANCE:EQ", "TCS:EQ",
    )


def test_universe_round_trip_stable():
    state, baseline, agent, _ = _triplet()
    config = make_loop_config(baseline, agent, **_universe_kwargs())
    restored = OrchestrationConfig.from_dict(config.to_dict())
    assert restored == config
    assert restored.fingerprint() == config.fingerprint()


def test_malformed_universe_rejected():
    state, baseline, agent, _ = _triplet()
    bad_universes = [
        {"nse_future": ["X"]},
        {"nse_equity": [""]},
        {"nse_equity": ["RELIANCE:EQ", "RELIANCE:EQ"]},
        {"nse_equity": [], "mcx_gold": []},
    ]
    for bad in bad_universes:
        with pytest.raises((TypeError, ValueError)):
            make_loop_config(baseline, agent, universe=bad)
    with pytest.raises(TypeError):
        make_loop_config(baseline, agent, universe="nse_equity")


def test_matching_explicit_scope_accepted_without_environment():
    from evaluation.diagnostics.orchestration.controller import (
        _episode_scope,
    )
    from ..execution_fixtures import FULL_UNIVERSE

    baseline = make_loop_baseline()
    agent = HoldAgent()
    reordered = {
        "mcx_gold": ["GOLDAUG2023"],
        "nse_equity": ["TCS:EQ", "RELIANCE:EQ"],
    }
    config = make_loop_config(
        baseline,
        agent,
        window=["2023-05-15", "2023-05-26"],
        universe=reordered,
    )
    episode = _episode_scope(baseline, config, seed=7)
    assert (episode.start_date, episode.end_date) == (
        "2023-05-15", "2023-05-26",
    )
    assert episode.seed == 7
    assert sorted(episode.universe["nse_equity"]) == [
        "RELIANCE:EQ", "TCS:EQ",
    ]
    assert list(episode.universe["mcx_gold"]) == ["GOLDAUG2023"]
    assert FULL_UNIVERSE["nse_equity"] == ["RELIANCE:EQ", "TCS:EQ"]


def _assert_scope_rejected(state, baseline, agent, **overrides):
    before = state.fingerprint()
    before_proposals = len(state.proposals)
    before_rationales = len(state.rationales)
    before_results = len(state.test_results)
    config = make_loop_config(baseline, agent, **overrides)
    with pytest.raises(ValueError):
        run(diagnostic_state=state, baseline=baseline,
            target_agent=agent, config=config)
    assert state.fingerprint() == before
    assert len(state.proposals) == before_proposals
    assert len(state.rationales) == before_rationales
    assert len(state.test_results) == before_results
    assert state.stopping_reason is None


def test_mismatching_window_rejected_before_execution():
    state, baseline, agent, _ = _triplet()
    _assert_scope_rejected(
        state, baseline, agent, window=["2023-05-15", "2023-05-20"]
    )


def test_mismatching_universe_rejected_before_execution():
    state, baseline, agent, _ = _triplet()
    _assert_scope_rejected(
        state, baseline, agent,
        universe={"nse_equity": ["RELIANCE:EQ", "INFY:EQ"],
                  "mcx_gold": ["GOLDAUG2023"]},
    )


def test_subset_universe_rejected():
    state, baseline, agent, _ = _triplet()
    _assert_scope_rejected(
        state, baseline, agent,
        universe={"nse_equity": ["RELIANCE:EQ"],
                  "mcx_gold": ["GOLDAUG2023"]},
    )


def test_superset_universe_rejected():
    state, baseline, agent, _ = _triplet()
    _assert_scope_rejected(
        state, baseline, agent,
        universe={"nse_equity": ["RELIANCE:EQ", "TCS:EQ", "INFY:EQ"],
                  "mcx_gold": ["GOLDAUG2023"]},
    )


def test_disjoint_universe_rejected():
    state, baseline, agent, _ = _triplet()
    _assert_scope_rejected(
        state, baseline, agent,
        universe={"nse_equity": ["INFY:EQ"], "mcx_gold": ["GOLDSILVER2023"]},
    )
