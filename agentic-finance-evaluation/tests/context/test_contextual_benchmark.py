"""E4-D contextual benchmark: C0/C1 behaviour, reset, isolation."""

import pytest

from evaluation.context.benchmark import (
    TURNOVER_MECHANISM,
    ContextualThresholdBenchmark,
)
from benchmarks.volatility_threshold import VolatilityThresholdBenchmark
from evaluation.contracts.agent import AgentIdentity
from evaluation.diagnostics.repair.application import fingerprint_agent

from ..benchmarks.fixtures import make_obs


def _turnover_entry(**overrides):
    entry = {
        "context_id": "ctx-1",
        "failure_mechanism": TURNOVER_MECHANISM,
        "corrective_principle": "throttle accumulation",
    }
    entry.update(overrides)
    return entry


def _low_with_positions():
    return make_obs(
        vix=12.5,
        positions={"nse_equity:RELIANCE:EQ": 4.0},
    )


def test_c0_reproduces_frozen_benchmark():
    frozen = VolatilityThresholdBenchmark()
    fresh = ContextualThresholdBenchmark()
    assert fresh.identity.agent_id == "contextual-threshold-benchmark"
    for obs_kwargs in (
        {"vix": 12.5},
        {"vix": 20.0},
        {"vix": 30.0},
        {"vix": None},
    ):
        obs = make_obs(**obs_kwargs)
        assert fresh.act(dict(obs)) == frozen.act(dict(obs))
    fresh.reset()
    assert fresh.calls == 0


def test_c1_alters_identical_observation():
    plain = ContextualThresholdBenchmark()
    informed = ContextualThresholdBenchmark()
    informed.adapt({"entries": [_turnover_entry()]})
    base_orders = plain.act(_low_with_positions())
    assert len(base_orders) == 2
    changed_orders = informed.act(_low_with_positions())
    assert len(changed_orders) == 1
    assert changed_orders[0]["instrument"] == "TCS:EQ"
    assert changed_orders[0]["side"] == "BUY"


def test_irrelevant_context_does_not_change_behaviour():
    agent = ContextualThresholdBenchmark()
    agent.adapt({"entries": [_turnover_entry(
        failure_mechanism="exposure",
    )]})
    assert agent.act(_low_with_positions()) == (
        ContextualThresholdBenchmark().act(_low_with_positions())
    )
    assert agent.act(make_obs(vix=20.0)) == []


def test_empty_and_malformed_context_rejected_or_inert():
    agent = ContextualThresholdBenchmark()
    before = list(agent.learned_contexts)
    with pytest.raises((TypeError, ValueError)):
        agent.adapt({"entries": []})
    assert list(agent.learned_contexts) == before
    with pytest.raises((TypeError, ValueError)):
        agent.adapt({"entries": [{"context_id": "x"}]})
    with pytest.raises((TypeError, ValueError)):
        agent.adapt("not-a-mapping")


def test_reset_preserves_context_clears_episode_state():
    agent = ContextualThresholdBenchmark()
    agent.adapt({"entries": [_turnover_entry()]})
    agent.act(_low_with_positions())
    assert agent.calls == 1
    agent.reset()
    assert agent.calls == 0
    assert len(agent.learned_contexts) == 1
    assert len(agent.act(_low_with_positions())) == 1


def test_original_agent_isolation_by_fingerprint():
    from benchmarks.volatility_threshold import (
        VolatilityThresholdBenchmark as Frozen,
    )

    agent = ContextualThresholdBenchmark()
    before = fingerprint_agent(agent, agent.identity)
    agent.adapt({"entries": [_turnover_entry()]})
    assert fingerprint_agent(agent, agent.identity) != before
    frozen = Frozen()
    assert fingerprint_agent(frozen, frozen.identity) == fingerprint_agent(
        Frozen(), Frozen().identity
    )
    assert isinstance(agent.identity, AgentIdentity)


def test_high_and_missing_branches_unchanged_by_context():
    agent = ContextualThresholdBenchmark()
    agent.adapt({"entries": [_turnover_entry()]})
    assert agent.act(make_obs(vix=None)) == []
    assert agent.act(make_obs(vix=20.0)) == []


def test_applicability_matching_is_deferred_not_evaluated():
    # DEFERRED ARCHITECTURE (E4-D limitation, pinned here): the
    # benchmark keys its guard on failure_mechanism only.
    # Applicability strings travel with the context as provenance
    # but are not evaluated against the live observation; genuinely
    # applicability-aware selection is future work, and no claim in
    # this suite implies it already exists.
    agent = ContextualThresholdBenchmark()
    agent.adapt({"entries": [_turnover_entry(
        applicability_conditions=("never-applies-here",),
    )]})
    assert len(agent.act(_low_with_positions())) == 1
