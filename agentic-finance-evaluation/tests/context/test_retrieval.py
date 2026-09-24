"""E4-D retrieval tests: deterministic, agent-scoped, append-only safe."""

import pytest

from evaluation.context.learned import ContextStatus, LearnedContext
from evaluation.context.memory import MemoryStore, StoredEntry
from evaluation.context.retrieval import (
    RETRIEVAL_METHOD,
    RETRIEVAL_VERSION,
    RetrievalRecord,
    retrieve,
)


def _context(context_id, agent_id="volatility-threshold-benchmark@1.0",
             mechanism="turnover"):
    return LearnedContext(
        context_id=context_id,
        agent_id=agent_id,
        source_evaluation_id="B-R",
        failure_mechanism=mechanism,
        observed_pattern="p",
        triggering_conditions=("candidate_diagnostic",),
        diagnostic_evidence=("E-1",),
        corrective_principle="c",
        applicability_conditions=("candidate_diagnostic",),
        contraindications=(),
        expected_effect="e",
        validation_result="ACCEPTED",
        validation_metrics={},
        held_out_evidence={},
        provenance={"proposal_fingerprint": "p"},
        status=ContextStatus.ADMITTED,
        version="v1",
    )


def _store(*contexts):
    store = MemoryStore(store_id="mem-1")
    for index, context in enumerate(contexts):
        store = MemoryStore(
            store_id="mem-1",
            entries=store.entries + (
                StoredEntry(
                    entry_id=f"mem-{index}",
                    context=context,
                    verdict_fingerprint="vfp",
                    sequence=index + 1,
                    candidate_fingerprint=f"cfp-{index}",
                ),
            ),
        )
    return store


def test_relevant_context_retrieved():
    store = _store(_context("ctx-1"), _context("ctx-2"))
    contexts, record = retrieve(
        store, agent_id="volatility-threshold-benchmark@1.0"
    )
    assert [c.context_id for c in contexts] == ["ctx-1", "ctx-2"]
    assert record.retrieved_ids == ("ctx-1", "ctx-2")
    assert record.method == RETRIEVAL_METHOD
    assert record.method_version == RETRIEVAL_VERSION
    assert RetrievalRecord.from_dict(record.to_dict()) == record


def test_irrelevant_context_excluded():
    store = _store(
        _context("ctx-1"),
        _context("ctx-2", agent_id="other-agent@9.9"),
    )
    contexts, record = retrieve(
        store, agent_id="volatility-threshold-benchmark@1.0"
    )
    assert [c.context_id for c in contexts] == ["ctx-1"]
    assert record.retrieved_ids == ("ctx-1",)


def test_applicability_preserved_not_filtered():
    # v1 retrieves by agent scope; applicability travels untouched
    # for downstream use and future versioned filtering.
    store = _store(_context("ctx-1"))
    (context,), _ = retrieve(
        store, agent_id="volatility-threshold-benchmark@1.0"
    )
    assert context.applicability_conditions == ("candidate_diagnostic",)


def test_deterministic_ordering():
    first = _store(_context("ctx-b"), _context("ctx-a"))
    second = _store(_context("ctx-b"), _context("ctx-a"))
    out1, rec1 = retrieve(first, agent_id="volatility-threshold-benchmark@1.0")
    out2, rec2 = retrieve(second, agent_id="volatility-threshold-benchmark@1.0")
    assert [c.context_id for c in out1] == [c.context_id for c in out2]
    assert rec1.fingerprint() == rec2.fingerprint()


def test_duplicate_contexts_not_duplicated_in_delivery():
    store = _store(_context("ctx-1"), _context("ctx-1-dup"))
    _, record = retrieve(
        store, agent_id="volatility-threshold-benchmark@1.0"
    )
    assert len(set(record.retrieved_ids)) == len(record.retrieved_ids)


def test_empty_memory_produces_empty_retrieval():
    store = MemoryStore(store_id="mem-1")
    contexts, record = retrieve(
        store, agent_id="volatility-threshold-benchmark@1.0"
    )
    assert contexts == ()
    assert record.retrieved_ids == ()


def test_retrieval_rejects_bad_inputs():
    store = _store(_context("ctx-1"))
    with pytest.raises(TypeError):
        retrieve("nope", agent_id="x")
    with pytest.raises(ValueError):
        retrieve(store, agent_id="  ")
    with pytest.raises(ValueError):
        RetrievalRecord(
            agent_id="x", store_fingerprint="",
            retrieved_ids=("a", "a"),
        )
