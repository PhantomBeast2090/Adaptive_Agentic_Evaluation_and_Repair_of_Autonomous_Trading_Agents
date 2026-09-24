"""E4-D adversarial delivery tests: fail-closed on every invalid input."""

import pytest

from evaluation.context.benchmark import ContextualThresholdBenchmark
from evaluation.context.assembly import (
    ContextPackage,
    assemble,
    deliver,
)
from evaluation.context.learned import LearnedContext
from evaluation.context.retrieval import retrieve
from evaluation.contracts.agent import AgentIdentity

from ..benchmarks.fixtures import make_obs
from .test_assembly import _ctx_package, _package
from .test_retrieval import _context, _store


def _identity(agent_id):
    base = agent_id.split("@")
    return AgentIdentity(base[0], base[1] if len(base) > 1 else "1.0")


def test_candidate_context_delivery_refused():
    package, store = _ctx_package()
    candidate = LearnedContext(
        **{**_context("ctx-x").to_dict(), "status": "CANDIDATE"}
    )
    _, record = retrieve(store, agent_id=candidate.agent_id)
    with pytest.raises(ValueError):
        assemble(
            (candidate,), record, store.fingerprint(),
            _identity(candidate.agent_id),
        )


def test_rejected_and_quarantined_delivery_refused():
    from evaluation.context.retrieval import RetrievalRecord

    for status in ("REJECTED", "QUARANTINED"):
        context = LearnedContext(
            **{**_context("ctx-x").to_dict(), "status": status}
        )
        record = RetrievalRecord(
            agent_id="volatility-threshold-benchmark@1.0",
            store_fingerprint="sfp",
            retrieved_ids=(),
        )
        with pytest.raises(ValueError):
            assemble(
                (context,), record, "sfp", _identity(context.agent_id),
            )


def test_store_bypass_impossible():
    from evaluation.context.memory import MemoryStore

    agent = ContextualThresholdBenchmark()
    with pytest.raises((TypeError, ValueError)):
        deliver(agent, {"not": "a package"},
                MemoryStore(store_id="mem-1"))


def test_manually_constructed_admitted_context_still_checked():
    # Even a hand-built ADMITTED object must pass assembly validation:
    # unknown fields and identity mismatch fail closed at delivery.
    package, store = _ctx_package()
    agent = ContextualThresholdBenchmark()
    with pytest.raises(ValueError):
        deliver(agent, ContextPackage.from_dict(
            {**package.to_dict(),
             "agent_identity": {"agent_id": "other", "version": "9.9"}}
        ), store)


def test_tampered_package_fails_closed():
    package, store = _ctx_package()
    tampered_dict = package.to_dict()
    tampered_dict["knowledge"] = [
        {**tampered_dict["knowledge"][0], "context_id": "ctx-forged"}
    ]
    forged = ContextPackage.from_dict(tampered_dict)
    assert forged.fingerprint() != package.fingerprint()
    agent = ContextualThresholdBenchmark()
    # Tampering is now refused at delivery, not merely detectable
    # afterwards: the forged entry matches no admitted store entry.
    with pytest.raises(ValueError):
        deliver(agent, forged, store)


def test_stale_store_fails_closed():
    from evaluation.context.memory import MemoryStore

    package, _ = _ctx_package()
    agent = ContextualThresholdBenchmark()
    with pytest.raises(ValueError):
        deliver(agent, package, MemoryStore(store_id="other-mem"))


def test_mutation_after_assembly_cannot_reach_store():
    from evaluation.context.assembly import ContextPackage

    package, store = _ctx_package()
    snapshot = store.fingerprint()
    knowledge = package.to_dict()["knowledge"]
    knowledge.append({"context_id": "injected"})
    assert store.fingerprint() == snapshot
    rebuilt = ContextPackage.from_dict(
        {**package.to_dict(), "knowledge": knowledge}
    )
    assert rebuilt.fingerprint() != package.fingerprint()


def test_provenance_survives_delivery():
    package, store = _ctx_package()
    agent = ContextualThresholdBenchmark()
    delivered, record = deliver(agent, package, store)
    assert record.context_package_fingerprint == package.fingerprint()
    assert delivered.learned_contexts[0]["context_id"] == "ctx-1"


def test_irrelevant_context_never_applied():
    agent = ContextualThresholdBenchmark()
    agent.adapt({"entries": [{
        "context_id": "ctx-exp",
        "failure_mechanism": "exposure",
        "corrective_principle": "cap exposure",
    }]})
    from ..benchmarks.fixtures import make_obs

    assert agent._turnover_guard_active() is False
    assert agent.act(make_obs(vix=12.5, positions={
        "nse_equity:RELIANCE:EQ": 2.0,
    })) == ContextualThresholdBenchmark().act(make_obs(
        vix=12.5, positions={"nse_equity:RELIANCE:EQ": 2.0},
    ))


def test_malformed_empty_foreign_context_rejected():
    agent = ContextualThresholdBenchmark()
    with pytest.raises((TypeError, ValueError)):
        agent.adapt({"entries": [{"context_id": "bad"}]})
    with pytest.raises((TypeError, ValueError)):
        agent.adapt({"no_entries": []})
    with pytest.raises((TypeError, ValueError)):
        agent.adapt("nope")
    assert agent.learned_contexts == ()


def test_foreign_agent_context_not_delivered():
    from evaluation.contracts.agent import AgentIdentity

    package, _ = _ctx_package()
    assert package.agent_identity != AgentIdentity("other", "1.0")
