"""E4-D assembly/delivery tests: provenance, isolation, adapt-once."""

import pytest

from evaluation.context.benchmark import ContextualThresholdBenchmark
from evaluation.context.benchmark import ContextualThresholdBenchmark
from evaluation.context.assembly import (
    ASSEMBLY_METHOD,
    ContextPackage,
    DeliveryRecord,
    assemble,
    deliver,
)
from evaluation.context.learned import ContextStatus, LearnedContext
from evaluation.context.memory import MemoryStore
from evaluation.context.retrieval import retrieve
from evaluation.contracts.agent import AgentIdentity

from .test_retrieval import _context, _store


def _package(agent_id="volatility-threshold-benchmark@1.0"):
    store = _store(_context("ctx-1", agent_id=agent_id))
    contexts, record = retrieve(store, agent_id=agent_id)
    base = agent_id.split("@")
    return (
        assemble(
            contexts,
            record,
            store.fingerprint(),
            AgentIdentity(base[0], base[1] if len(base) > 1 else "1.0"),
        ),
        store,
    )


def test_deterministic_output_and_provenance():
    package, store = _package()
    assert package.retrieved_ids == ("ctx-1",)
    assert package.store_fingerprint == store.fingerprint()
    assert package.knowledge[0]["failure_mechanism"] == "turnover"
    assert package.knowledge[0]["context_fingerprint"]
    assert package.knowledge[0]["corrective_principle"] == "c"
    assert ContextPackage.from_dict(package.to_dict()) == package
    package2, _ = _package()
    assert package2.fingerprint() == package.fingerprint()


def test_context_fingerprint_stable_and_memory_included():
    package, store = _package()
    assert package.fingerprint()
    assert package.to_dict()["store_fingerprint"] == store.fingerprint()
    assert package.to_dict()["retrieval_method"] == "context-retrieve"


def test_retrieval_metadata_preserved():
    package, _ = _package()
    assert package.retrieval_method == "context-retrieve"
    assert package.retrieval_version == "v1"
    assert package.method == ASSEMBLY_METHOD


def test_assembly_rejects_non_admitted_and_mismatch():
    store = _store(_context("ctx-1"))
    contexts, record = retrieve(
        store, agent_id="volatility-threshold-benchmark@1.0"
    )
    candidate = LearnedContext(
        **{**contexts[0].to_dict(), "status": "CANDIDATE"}
    )
    with pytest.raises(ValueError):
        assemble(
            (candidate,), record, store.fingerprint(),
            AgentIdentity("volatility-threshold-benchmark", "1.0"),
        )
    with pytest.raises(ValueError):
        assemble(
            (), record, store.fingerprint(),
            AgentIdentity("volatility-threshold-benchmark", "1.0"),
        )


def _ctx_package():
    """Package built for the contextual benchmark identity."""
    from evaluation.contracts.agent import AgentIdentity

    store = _store(
        _context("ctx-1", agent_id="contextual-threshold-benchmark@1.0")
    )
    contexts, record = retrieve(
        store, agent_id="contextual-threshold-benchmark@1.0"
    )
    agent = ContextualThresholdBenchmark()
    return (
        assemble(
            contexts,
            record,
            store.fingerprint(),
            agent.identity,
        ),
        store,
    )


def test_delivery_original_unchanged_and_copy_adapted_once():
    from evaluation.diagnostics.repair.application import fingerprint_agent

    package, _ = _ctx_package()

    delivered_payloads = []

    class CountingAgent(ContextualThresholdBenchmark):
        def adapt(self, payload):
            delivered_payloads.append(payload)
            return super().adapt(payload)

    agent = CountingAgent()
    before = fingerprint_agent(agent, agent.identity)
    adapted, record = deliver(agent, package)
    assert len(delivered_payloads) == 1
    assert delivered_payloads[0][
        "context_package_fingerprint"
    ] == package.fingerprint()
    assert fingerprint_agent(agent, agent.identity) == before
    assert adapted is not agent
    assert len(adapted.learned_contexts) == 1
    assert isinstance(record, DeliveryRecord)
    assert record.agent_fingerprint_before == before
    assert record.agent_fingerprint_after == fingerprint_agent(
        adapted, adapted.identity
    )
    assert record.agent_fingerprint_before != record.agent_fingerprint_after
    assert DeliveryRecord.from_dict(record.to_dict()) == record


def test_delivery_rejects_mismatched_or_malformed():
    package, _ = _package()
    other = ContextualThresholdBenchmark()
    with pytest.raises((TypeError, ValueError)):
        deliver("not-an-agent", package)

    class Foreign:
        identity = AgentIdentity("foreign-agent", "1.0")

        def reset(self):
            return None

        def act(self, observation):
            return []

        def adapt(self, intervention):
            return None

    with pytest.raises(ValueError):
        deliver(Foreign(), package)
    with pytest.raises(TypeError):
        deliver(other, "not-a-package")


def test_unknown_fields_rejected():
    package, _ = _package()
    with pytest.raises(ValueError):
        ContextPackage.from_dict({**package.to_dict(), "zzz": 1})
