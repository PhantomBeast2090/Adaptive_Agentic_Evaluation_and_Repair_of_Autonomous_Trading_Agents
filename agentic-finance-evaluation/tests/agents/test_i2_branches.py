"""I2 Tier-1 tests: family freeze, cell enumeration, Y-firewall, audit units.
Synthetic observations + spec assertions only (no full runs, no outcomes).
"""

import os
import sys

import pytest
import yaml

from agents.choice.multi_asset import MultiAssetChoice

BASE = os.path.join(os.path.dirname(__file__), "..", "..")
SPEC_PATH = os.path.join(BASE, "configs", "choice_agent", "i2_grid.yaml")
DESIGN_PATH = os.path.join(BASE, "docs", "I2_IDENTIFIABILITY_DESIGN.md")
sys.path.insert(0, BASE)

from scripts.run_i2 import (  # noqa: E402
    action_class,
    all_cells,
    audit,
    build_cell_policy,
    c0_regime,
    candidate_cells,
    candidate_test_key,
    candidate_windows,
    split_of,
)

REGISTERED = ({12.0, 15.0, 18.0}, {22.0, 25.0, 28.0}, {-0.05, -0.03})


def _spec():
    with open(SPEC_PATH) as h:
        return yaml.safe_load(h)


def test_family_frozen_k0_to_k3():
    spec = _spec()
    assert sorted(spec["candidates"]) == ["K0", "K1", "K2", "K3"]
    assert spec["selection_rule"]["order"] == ["K1", "K3", "K2"]
    assert spec["selection_rule"]["constraint"].startswith("K2/K3")
    assert os.path.isfile(DESIGN_PATH)


def test_completion_cells_use_registered_values_only():
    spec = _spec()
    i1_ids = {c["id"] for c in spec["i1_cells"]}
    assert len(i1_ids) == 6
    full = {(lo, hi, tm) for lo in REGISTERED[0]
            for hi in REGISTERED[1] for tm in REGISTERED[2]}
    assert len(full) == 18
    have = {(c["vix_low"], c["vix_high"], c["trend_min"])
            for c in spec["i1_cells"] + spec["completion_cells"]}
    assert have == full, "I1+completion must equal the registered factorial"
    assert len({c["id"] for c in spec["completion_cells"]}) == 12
    assert [c["id"] for c in spec["completion_cells"]] == sorted(
        c["id"] for c in spec["completion_cells"])


def test_candidate_composition():
    spec = _spec()
    assert [c["id"] for c in candidate_cells(spec, "K0")] == [
        "C0", "C1", "C2", "C3", "C4", "C5"]
    assert len(candidate_cells(spec, "K1")) == 18
    assert len(candidate_cells(spec, "K3")) == 18
    assert candidate_windows(spec, "K0") == ["W1", "W2"]
    assert candidate_windows(spec, "K1") == ["W1", "W2"]
    assert candidate_windows(spec, "K2") == ["W1", "W2E"]
    assert candidate_test_key(spec, "K1") == "TEST"
    assert candidate_test_key(spec, "K2") == "TEST_X"
    # TRAIN/VALID thirds identical across candidates (only TEST may extend)
    assert spec["splits"]["TRAIN"] == ["W1_T1", "W2_T1"]
    assert spec["splits"]["VALID"] == ["W1_T2", "W2_T2"]
    t3x = spec["splits"]["W2_T3X"]
    assert (t3x["start"], t3x["end"]) == ("2022-01-01", "2022-06-30")
    assert t3x["applies_to"] == ["K2", "K3"]


def test_gates_and_miner_unchanged():
    spec = _spec()
    gates = spec["gates"]
    assert (gates["min_paired_contrast_train"],
            gates["min_paired_contrast_valid"],
            gates["min_paired_contrast_test"]) == (15, 10, 20)
    assert gates["min_shared_action_regimes"] == 2
    assert gates["min_contrast_instruments"] == 3
    assert gates["min_second_window_contrasts"] == 10
    assert "single_pair_watch" in gates
    miner = spec["miner_frozen"]
    assert (miner["min_train_n"], miner["min_train_delta"],
            miner["max_candidates"], miner["permutation_seed"]) == \
        (15, 0.02, 5, 20260926)


def test_y_firewall():
    # I2 runner/audit must not import outcome machinery. Fail closed.
    # (a) runtime in a CLEAN interpreter (subprocess isolates the global
    #     sys.modules shared by the pytest process);
    # (b) static: AST of run_i2.py contains no such import statements.
    import ast
    import subprocess
    probe = ("import sys; sys.path.insert(0, '.'); "
             "import scripts.run_i2; "
             "hits = [m for m in sys.modules "
             "if m.split('.')[:2] in "
             "(['evaluation', 'attribution'], ['evaluation', 'ml'], "
             "['evaluation', 'context'])]; "
             "print('HITS:' + ','.join(sorted(hits)))")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                         text=True, cwd=BASE, timeout=180)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "HITS:", out.stdout
    tree = ast.parse(open(os.path.join(
        BASE, "scripts", "run_i2.py")).read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    banned = [m for m in imported if m.split(".")[:2] in
              (["evaluation", "attribution"], ["evaluation", "ml"],
               ["evaluation", "context"])]
    assert not banned, banned
    for token in ("MemoryStore", "LearnedContext", "conditional_miner"):
        assert token not in open(os.path.join(
            BASE, "scripts", "run_i2.py")).read(), token


def test_completion_cell_policies_valid_and_distinct():
    spec = _spec()

    def _base():
        with open(os.path.join(BASE, "configs", "choice_agent",
                               "g1.yaml")) as h:
            return yaml.safe_load(h)["policy"]
    base = _base()
    seen = set()
    for cell in spec["completion_cells"]:
        policy = build_cell_policy(base, cell)
        key = (policy["vix_low"], policy["vix_high"], policy["trend_min"])
        assert key not in seen
        seen.add(key)
        agent = MultiAssetChoice(policy)
        assert agent._closes == {} and agent._pfhist == []
    assert len(seen) == 12


def test_split_of_test_x():
    spec = _spec()
    assert split_of("2022-02-01", spec, "TEST") == "TEST"
    assert split_of("2022-05-01", spec, "TEST") is None
    assert split_of("2022-05-01", spec, "TEST_X") == "TEST"
    assert split_of("2020-08-01", spec, "TEST_X") == "TEST"
    assert split_of("2021-11-01", spec, "TEST_X") == "VALID"
    assert c0_regime(17.69) == "MID" and c0_regime(31.98) == "HIGH"


def test_k0_calibration_reproduces_i1():
    report = audit(BASE, "I1-20260928", "K0")
    assert report["splits"]["TRAIN"]["contrast_clusters"] == 46
    assert report["splits"]["VALID"]["contrast_clusters"] == 19
    assert report["splits"]["TEST"]["contrast_clusters"] == 18
    assert report["gate_checks"]["test>=20"] is False
