"""E4-F execution-driver tests: separation, gates, determinism.

No market episodes. Heavy phase functions (run_r_branch,
run_p_branch, run_terminal_arms) are verified structurally
(signatures, branch tags, refusal paths); all scientific invariants
live in pure helpers exercised directly.
"""

import inspect
import pathlib
import subprocess
import sys

import pytest
import yaml

from evaluation.context.driver import (
    BRANCHES,
    TERMINAL_ARMS,
    DriverPlan,
    assert_branch_purity,
    fresh_delivery_agent,
    require_terminal_lock,
    run_p_branch,
    run_terminal_arms,
)
from experiments.e4f.episode_driver import run_r_branch

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def _plan(**overrides):
    params = {
        "experiment_id": "e4f-test",
        "execution_role": "SYSTEM_VALIDATION",
        "execution_instance": "001",
        "protocol_fingerprint": "proto",
        "supplement_fingerprint": "supp",
        "effective_manifest_fingerprint": "eff",
        "w1_start": "2022-11-01",
        "w1_end": "2022-11-30",
        "w2_start": "2022-12-01",
        "w2_end": "2022-12-31",
        "w3_start": "2023-01-01",
        "w3_end": "2023-01-31",
        "w1_env_fingerprint": "env1",
        "w2_env_fingerprint": "env2",
        "w3_env_fingerprint": "env3",
    }
    params.update(overrides)
    return DriverPlan(**params)


def _supplement_record():
    with open(
        ROOT / "experiments" / "protocol" / "E4-F-supplement.yaml",
        encoding="utf-8",
    ) as handle:
        return yaml.safe_load(handle)


# 1/2/3/4. Branch purity: R-sole-source, P-exclusion, distinctness.
def test_branch_purity_accepts_r_only():
    fps = assert_branch_purity(
        k2_provenance_fps={"evaluation": "r1", "diagnosis": "r2"},
        r_branch_fps={"evaluation": "r1", "diagnosis": "r2",
                      "trace": "r3"},
        forbidden_fps={"p_read": "p1"},
    )
    assert fps == {"evaluation": "r1", "diagnosis": "r2"}


def test_branch_purity_refuses_p_contamination():
    with pytest.raises(ValueError):
        assert_branch_purity(
            k2_provenance_fps={"evaluation": "p1"},
            r_branch_fps={"evaluation": "r1"},
            forbidden_fps={"p_read": "p1"},
        )


def test_branch_purity_refuses_non_r_source():
    with pytest.raises(ValueError):
        assert_branch_purity(
            k2_provenance_fps={"evaluation": "x9"},
            r_branch_fps={"evaluation": "r1"},
            forbidden_fps={},
        )


def test_branch_purity_refuses_empty_fingerprints():
    with pytest.raises(ValueError):
        assert_branch_purity(
            k2_provenance_fps={"evaluation": ""},
            r_branch_fps={"evaluation": "r1"},
            forbidden_fps={},
        )


# 5/6. Retention helpers live in cycles (wired here by reference).
def test_retention_helpers_wired():
    from evaluation.context.cycles import assert_retained, retention_proof

    assert retention_proof.__module__ == "evaluation.context.cycles"
    assert assert_retained({"a": "1"}, {"a": "1", "b": "2"}) == {
        "a": "1", "b": "2"
    }


# 7. Duplicate refusal lives at gate/admit (referenced, not duplicated).
def test_duplicate_refusal_path_exists():
    from evaluation.context.memory import MemoryStore

    assert hasattr(MemoryStore, "contains")


# 8. C2 shape enforced by store versioning.
def test_c2_shape_contract():
    from evaluation.context.memory import MemoryStore

    assert hasattr(MemoryStore(store_id="x"), "store_version")


# 9. T12 vs C1+C2 lineage differs by construction.
def test_temporary_vs_persistent_lineage_differs():
    from evaluation.context.cycles import DUAL_TEMPORARY_PROVENANCE

    assert DUAL_TEMPORARY_PROVENANCE == "temporary-no-store-dual"
    assert DUAL_TEMPORARY_PROVENANCE != "temporary-no-store"


# 10. W3 terminal gate.
def test_terminal_gate_requires_both_locks_and_order():
    lock = {
        "store_fingerprint_at_lock": "s",
        "package_fingerprint_at_lock": "p",
    }
    gate = require_terminal_lock(
        c1_lock=dict(lock),
        c2_lock=dict(lock),
        w3_start="2023-01-01",
        w2_end="2022-12-31",
    )
    assert gate["terminal_gate"] == "locked"
    with pytest.raises(ValueError):
        require_terminal_lock(
            c1_lock={},
            c2_lock=dict(lock),
            w3_start="2023-01-01",
            w2_end="2022-12-31",
        )
    with pytest.raises(ValueError):
        require_terminal_lock(
            c1_lock=dict(lock),
            c2_lock=dict(lock),
            w3_start="2022-12-31",
            w2_end="2022-12-31",
        )


# 11/12. Fresh agents, no pre-delivery context.
def test_fresh_delivery_agents_isolated_and_empty():
    first = fresh_delivery_agent()
    second = fresh_delivery_agent()
    assert first is not second
    assert tuple(first.learned_contexts) == ()
    assert tuple(second.learned_contexts) == ()
    assert first.identity.agent_id == "accumulating-threshold-benchmark"


# 13. Arm construction surface.
def test_terminal_arm_surface():
    assert set(TERMINAL_ARMS) == {"C0", "T1", "C1", "T12", "C1+C2"}
    assert set(BRANCHES) == {"R", "P", "V", "A"}
    params = inspect.signature(run_terminal_arms).parameters
    for name in (
        "plan", "store_c1", "package_c1", "store_c2", "package_c2",
        "temporary_k1_entries", "temporary_k2_entries", "w3_config",
    ):
        assert name in params, f"run_terminal_arms lacks {name}"
    r_params = inspect.signature(run_r_branch).parameters
    assert "package_c1" not in r_params
    assert "store_c1" not in r_params
    assert "package_c2" not in r_params
    # R-branch episode wiring lives outside the frozen-substrate scan
    # roots so frozen files import nothing new.
    assert run_r_branch.__module__ == "experiments.e4f.episode_driver"
    p_params = inspect.signature(run_p_branch).parameters
    assert "store_c1" in p_params and "package_c1" in p_params


# 14. Plan determinism + supplement linkage.
def test_plan_deterministic_and_supplement_linked():
    first = _plan()
    assert DriverPlan(**dict(
        experiment_id="e4f-test",
        execution_role="SYSTEM_VALIDATION",
        execution_instance="001",
        protocol_fingerprint="proto",
        supplement_fingerprint="supp",
        effective_manifest_fingerprint="eff",
        w1_start="2022-11-01",
        w1_end="2022-11-30",
        w2_start="2022-12-01",
        w2_end="2022-12-31",
        w3_start="2023-01-01",
        w3_end="2023-01-31",
        w1_env_fingerprint="env1",
        w2_env_fingerprint="env2",
        w3_env_fingerprint="env3",
    )).fingerprint() == first.fingerprint()
    plan = DriverPlan.from_supplement(
        supplement_record=_supplement_record(),
        experiment_id="e4f-test",
        execution_role="SYSTEM_VALIDATION",
        execution_instance="001",
        protocol_fingerprint="proto",
        effective_manifest_fingerprint="eff",
    )
    assert (plan.w1_start, plan.w2_start, plan.w3_start) == (
        "2022-11-01", "2022-12-01", "2023-01-01",
    )
    with pytest.raises(ValueError):
        _plan(w2_start="2022-11-15")


# 15. Cross-process fingerprint stability.
def test_cross_process_plan_stability():
    from evaluation.contracts.fingerprints import fingerprint_of_dict

    payload = {"b": [1], "a": "x"}
    local = fingerprint_of_dict(payload)
    proc = subprocess.run(
        [sys.executable, "-c",
         "from evaluation.contracts.fingerprints import "
         "fingerprint_of_dict;"
         f"print(fingerprint_of_dict({payload!r}))"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == local


# 16. Stop conditions: every refusal path.
def test_plan_rejects_bad_windows_and_empty_fields():
    with pytest.raises(ValueError):
        _plan(experiment_id="  ")
    with pytest.raises(ValueError):
        _plan(w3_start="2022-12-31", w3_end="2023-01-31")
    with pytest.raises((TypeError, ValueError)):
        DriverPlan.from_supplement(
            supplement_record={},
            experiment_id="e",
            execution_role="r",
            execution_instance="i",
            protocol_fingerprint="p",
            effective_manifest_fingerprint="m",
        )


# 17. No ML surface in the driver.
def test_driver_has_no_ml_surface():
    text = (ROOT / "evaluation" / "context" / "driver.py").read_text()
    for token in ("torch", "sklearn", "transformers", "openai",
                  "anthropic", "llm", "reinforcement", "neural_net"):
        assert token not in text.lower(), f"driver mentions {token!r}"
