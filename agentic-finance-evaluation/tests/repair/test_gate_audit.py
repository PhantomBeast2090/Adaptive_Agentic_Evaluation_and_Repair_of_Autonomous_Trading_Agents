"""Tier 1: gate statistics (bootstrap determinism/sanity, coverage, NSF)
and audit-chain integrity."""

import pytest

from evaluation.repair.audit import (
    AuditChain,
    read_audit_log,
    write_audit_log,
)
from evaluation.repair.gate import (
    assemble_verification,
    block_bootstrap_ci,
    coverage_precheck,
    paired_bootstrap_ci,
)


def test_paired_bootstrap_deterministic_and_sane():
    diffs = [1.0, -0.5, 2.0, 0.5, 1.5, -1.0, 0.0, 1.0]
    first = paired_bootstrap_ci(diffs, seed=99, n_boot=500)
    second = paired_bootstrap_ci(diffs, seed=99, n_boot=500)
    assert first == second
    assert first["lower"] <= first["mean"] <= first["upper"]
    assert first["method"] == "paired-bootstrap"
    shifted = paired_bootstrap_ci(diffs, seed=100, n_boot=500)
    assert shifted != first  # seed matters; documented, not hidden
    with pytest.raises(ValueError):
        paired_bootstrap_ci([], seed=1)
    with pytest.raises(ValueError):
        paired_bootstrap_ci(diffs, seed=1, n_boot=10)


def test_block_bootstrap_deterministic_and_sane():
    series = [float(i % 7) for i in range(60)]
    first = block_bootstrap_ci(series, seed=7, block_len=5, n_boot=500)
    second = block_bootstrap_ci(series, seed=7, block_len=5, n_boot=500)
    assert first == second
    assert first["lower"] <= first["mean"] <= first["upper"]
    assert first["block_len"] == 5
    assert block_bootstrap_ci([3.0], seed=1)["mean"] == 3.0


def test_coverage_precheck_and_nsf_default():
    assert coverage_precheck(10, 5)["passed"] is True
    assert coverage_precheck(2, 5)["passed"] is False
    verification = assemble_verification(
        verification_id="v-001", candidate_fingerprint="c",
        provenance={"origin": "test"})
    assert verification.verdict == "NSF"
    accepted = assemble_verification(
        verification_id="v-002", candidate_fingerprint="c",
        accepted=True, provenance={"decide": "ACCEPTED"})
    assert accepted.verdict == "ACCEPT"


def test_audit_chain_verify_and_tamper(tmp_path):
    chain = AuditChain()
    chain.append("COMPILED", {"spec": "s1"})
    chain.append("SHADOWED", {"spec": "s1", "diverged": True})
    assert chain.verify()
    path = write_audit_log(str(tmp_path / "audit.jsonl"), chain)
    loaded = read_audit_log(path)
    assert loaded.verify()
    assert [r["event"] for r in loaded.to_list()] == ["COMPILED", "SHADOWED"]
    tampered = loaded.to_list()
    tampered[0]["payload"] = {"spec": "EVIL"}
    with pytest.raises(ValueError):
        AuditChain.from_list(tampered)
    broken = AuditChain()
    broken.append("COMPILED", {"spec": "s1"})
    broken._records.append(broken._records[0])
    assert not broken.verify()
