"""Mocked end-to-end A→E campaign proof (zero market episodes).

One public ``run_experiment()`` call with faked execution
dependencies (real frozen orchestration code paths otherwise).
Proves ordering, fresh-agent ownership, single run_repair, seal
discipline, RQ3 comparator binding, exactly-once persistence, and
fail-closed failure variants. Fake signatures mirror production calls.
"""

import hashlib
import pathlib
from types import SimpleNamespace

import pytest

from benchmarks.hold import HoldBenchmark
from evaluation.diagnostics.repair.application import fingerprint_agent
from evaluation.diagnostics.repair.results import RepairDecision, RepairResult
from evaluation.diagnostics.repair.validation import (
    ValidationReport,
    ValidationRun,
)
from experiments.harness import lifecycle
from experiments.harness.errors import IntegrityFailure, LineageError
from experiments.harness.result import ExperimentResult

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent
# Mocked orchestration campaign: the manifest mirrors the frozen
# six-test/two-hypothesis shape via fixtures (live base manifest stays
# five-test/single-hypothesis by overlay precedent).
from tests.experiments.harness.fixtures import make_manifest as _make_manifest

MANIFEST = _make_manifest()
E3D_PATH = str(
    REPO / "experiments" / "protocol"
    / "E3-D-statistical-experimental-protocol.md"
)
E3D_FP = hashlib.sha256(open(E3D_PATH, "rb").read()).hexdigest()


def _config(tmp_path, **overrides):
    from tests.experiments.harness.fixtures import make_config

    params = {
        "benchmark_id": "hold-benchmark",
        "benchmark_version": "1.0",
        "benchmark_module": "benchmarks.hold.HoldBenchmark",
        "agent_id": "hold-benchmark",
        "agent_version": "1.0",
        "e3d_fingerprint": E3D_FP,
        "environment_fingerprint": "env-fp-campaign",
        "result_dir": str(tmp_path),
    }
    params.update(overrides)
    return make_config(**params)


def _metrics(turnover):
    return {"turnover": turnover, "order_count": 3.0}


class CampaignFakes:
    """Faked execution dependencies with a global call-order log."""

    def __init__(self, monkeypatch, repair_decision="ACCEPTED"):
        from tests.experiments.harness.fixtures import make_baseline

        self.log = []
        self.agents = {}
        self.repair_decision = repair_decision
        self._make_baseline = make_baseline
        monkeypatch.setattr(lifecycle, "run_baseline", self.fake_baseline)
        monkeypatch.setattr(lifecycle, "execute", self.fake_execute)
        monkeypatch.setattr(lifecycle, "interpret", self.fake_interpret)
        monkeypatch.setattr(lifecycle, "run_repair", self.fake_repair)

    def fake_baseline(self, agent, config, *, base_dir="."):
        from tests.experiments.harness.fixtures import DIAG

        self.log.append(("baseline", config.start_date, agent))
        window = "diag" if config.start_date == DIAG[0] else "held"
        kind = "N" if len(
            [e for e in self.log if e[0] == "baseline"
             and e[1] == config.start_date]
        ) == 1 else "R"
        metrics = {
            ("N", "diag"): _metrics(2.0),
            ("N", "held"): _metrics(2.5),
            ("R", "diag"): _metrics(1.0),
            ("R", "held"): _metrics(1.5),
        }[(kind, window)]
        self.agents.setdefault(kind + "-" + window, agent)
        return self._make_baseline(
            f"E-{kind}-{window}", (config.start_date, config.end_date),
            metrics,
        )

    def fake_execute(self, *, diagnostic_state, test_id, prediction_ids,
                     target_agent, episode_config):
        self.log.append(("execute", test_id, target_agent))
        self.agents.setdefault("diagnosis", target_agent)
        return SimpleNamespace(
            episode_id=f"ep-{test_id}",
            result=SimpleNamespace(
                result_id=f"R-{test_id}",
                status=SimpleNamespace(value="COMPLETED"),
            ),
        )

    def fake_interpret(self, **kwargs):
        from evaluation.diagnostics.contracts.hypothesis_updates import (
            Compatibility,
            HypothesisUpdate,
        )
        from evaluation.diagnostics.contracts.test_results import (
            DiagnosticTestResult,
        )

        self.log.append(("interpret", kwargs.get("result_id")))
        state = kwargs["diagnostic_state"]
        result_id = kwargs.get("result_id")
        prediction_ids = list(kwargs.get("prediction_ids", ()))
        test_id = next(
            pred.test_id for pred in state.predictions
            if pred.prediction_id in prediction_ids
        )
        test = next(
            item for item in state.available_tests
            if item.test_id == test_id
        )
        state.record_result(DiagnosticTestResult(
            result_id=result_id,
            test_id=test_id,
            execution_fingerprint=f"mock-{test_id}",
            baseline_evaluation_id=state.baseline_evaluation_id,
            baseline_fingerprint=state.baseline_fingerprint,
            intervention_fingerprint=test.fingerprint(),
            record_fps=(),
            evidence_refs=("mock-episode",),
            measured=(),
            prediction_ids=tuple(prediction_ids),
            status="COMPLETED",
            provenance_method="mock-campaign",
            provenance_version="v1",
        ))
        # Mocked diagnosis supports H-turnover only, mirroring a
        # turnover-class finding; H-exposure stays PROPOSED so repair
        # targeting resolves deterministically.
        current = state.hypothesis("H-turnover")
        if current.status.value != "SUPPORTED":
            updated = current.with_status("SUPPORTED")
            state.record_update(HypothesisUpdate(
                update_id=f"U-{result_id}",
                hypothesis_id="H-turnover",
                prior=current,
                prior_fingerprint=current.fingerprint(),
                prediction_id=prediction_ids[0],
                result_id=result_id,
                compatibility=Compatibility.SUPPORTS,
                assessment="mocked turnover support",
                updated=updated,
                updated_confidence=updated.confidence,
                evidence_refs=("mock-episode",),
                method="mock-campaign",
                version="v1",
            ))
        return None

    def fake_repair(self, **kwargs):
        self.log.append(("repair", kwargs["original_agent"]))
        self.agents["repair"] = kwargs["original_agent"]
        decision = (
            RepairDecision.ACCEPTED
            if self.repair_decision == "ACCEPTED"
            else RepairDecision.FAILED
        )
        live = HoldBenchmark()
        result = RepairResult(
            repair_id="repair-D-H-turnover",
            proposal_fingerprint="p",
            candidate_id="c",
            candidate_fingerprint="cf",
            validation_fingerprint="vf",
            analysis_fingerprint="af",
            decision=decision,
            reason="mocked",
            method="m",
            method_version="v",
        )
        report = ValidationReport(
            validation_id="V",
            candidate_id="c",
            candidate_fingerprint="cf",
            baseline_evaluation_id="E-ND",
            baseline_fingerprint="bfp",
            runs=(
                ValidationRun(
                    label="candidate_diagnostic",
                    window=("2023-05-15", "2023-06-15"),
                    result_fingerprint="rfp",
                    metrics={"turnover": 1.0},
                ),
            ),
            method="e1-rerun-comparison",
            method_version="v1",
        )
        return result, report, None, live


def _run(monkeypatch, tmp_path, **overrides):
    config = _config(tmp_path, **overrides)
    return lifecycle.run_experiment(
        config=config,
        manifest=MANIFEST,
        e3d_document_path=E3D_PATH,
        environment_fingerprint="env-fp-campaign",
        benchmark_fingerprint="bench-fp",
        agent_fingerprint="agent-fp",
        base_dir=".",
        execution_role="TIER1_PRIMARY",
        execution_instance="001",
    )


def test_happy_path_order_assembly_persistence(monkeypatch, tmp_path):
    fakes = CampaignFakes(monkeypatch)
    orig_save = ExperimentResult.save
    calls = []
    monkeypatch.setattr(
        ExperimentResult, "save",
        lambda self, path: (calls.append(path), orig_save(self, path))[0],
    )
    result = _run(monkeypatch, tmp_path)
    kinds = [entry[0] for entry in fakes.log]
    assert kinds[:2] == ["baseline", "baseline"]
    assert kinds[2] == "execute"
    assert "repair" in kinds
    first_repair = kinds.index("repair")
    assert kinds.index("execute") < first_repair
    baselines_after = [
        e for e in fakes.log[first_repair + 1:] if e[0] == "baseline"
    ]
    assert len(baselines_after) == 2
    assert kinds.count("repair") == 1
    assert result.delta_heldout["turnover"]["delta"] == -1.0
    assert result.delta_diagnostic["turnover"]["delta"] == -1.0
    assert result.delta_heldout["baseline_original_heldout"] != (
        result.delta_heldout["repaired_heldout"]
    )
    assert len(calls) == 1
    loaded = ExperimentResult.load(calls[0])
    assert loaded.to_dict() == result.to_dict()
    assert loaded.fingerprint() == result.fingerprint()


def test_fresh_agent_ownership(monkeypatch, tmp_path):
    fakes = CampaignFakes(monkeypatch)
    resets = []
    monkeypatch.setattr(
        HoldBenchmark, "reset",
        lambda self: (resets.append(self), None)[1],
    )
    _run(monkeypatch, tmp_path)
    diag_id = fakes.agents["diagnosis"]
    repair_id = fakes.agents["repair"]
    assert diag_id != repair_id
    seen = {
        id(fakes.agents["N-diag"]), id(fakes.agents["N-held"]),
        id(diag_id), id(repair_id),
    }
    assert len(seen) == 4
    assert len(resets) >= 4
    assert fingerprint_agent(
        HoldBenchmark(), HoldBenchmark.identity,
    ) == fingerprint_agent(HoldBenchmark(), HoldBenchmark.identity)


def test_e2f_sole_budget_owner():
    assert lifecycle.run_repair.__module__.startswith("evaluation.")


def test_repair_failed_blocks_rd_rh_and_save(monkeypatch, tmp_path):
    fakes = CampaignFakes(monkeypatch, repair_decision="FAILED")
    with pytest.raises(LineageError):
        _run(monkeypatch, tmp_path)
    kinds = [entry[0] for entry in fakes.log]
    assert "repair" in kinds
    after = kinds[kinds.index("repair") + 1:]
    assert "baseline" not in after
    assert list(tmp_path.iterdir()) == []


def test_transcription_mismatch_fails_before_execution(
    monkeypatch, tmp_path
):
    fakes = CampaignFakes(monkeypatch)
    bad = dict(MANIFEST)
    bad["candidate_pool"] = [{"test_id": "T-null"}]
    config = _config(tmp_path)
    with pytest.raises(Exception):
        lifecycle.run_experiment(
            config=config,
            manifest=bad,
            e3d_document_path=E3D_PATH,
            environment_fingerprint="env-fp-campaign",
            benchmark_fingerprint="bench-fp",
            agent_fingerprint="agent-fp",
            base_dir=".",
            execution_role="TIER1_PRIMARY",
            execution_instance="001",
        )
    assert fakes.log == []


def test_preflight_failure_blocks_phases(monkeypatch, tmp_path):
    fakes = CampaignFakes(monkeypatch)
    config = _config(tmp_path)
    with pytest.raises(Exception):
        lifecycle.run_experiment(
            config=config,
            manifest=MANIFEST,
            e3d_document_path=E3D_PATH,
            environment_fingerprint="WRONG-FP",
            benchmark_fingerprint="bench-fp",
            agent_fingerprint="agent-fp",
            base_dir=".",
            execution_role="TIER1_PRIMARY",
            execution_instance="001",
        )
    assert fakes.log == []
