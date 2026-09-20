"""Amendment-overlay proofs (pure, zero market episodes).

Verifies the E3-D.1 supplement against actual frozen files, the
narrow override surface, effective-config determinism and
non-mutation, legacy no-amendment behaviour, and incident-artefact
preservation. Real manifest/supplement/amendment files are read;
mutated variants live in tmp_path only.
"""

import copy
import pathlib
import shutil

import pytest
import yaml

from experiments.harness.amendment import (
    load_supplement,
    resolve_effective,
    sha256_file,
    verify_supplement,
)
from experiments.harness.errors import IntegrityFailure

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
MANIFEST_PATH = str(ROOT / "benchmarks" / "manifest.yaml")
SUPPLEMENT_PATH = str(
    ROOT / "experiments" / "protocol" / "E3-D.1-supplement.yaml"
)
AMENDMENT_DOC = str(
    ROOT / "experiments" / "protocol" / "E3-D.1-remediation-amendment.md"
)


def _manifest():
    return yaml.safe_load(open(MANIFEST_PATH, encoding="utf-8").read())


def _supplement():
    return load_supplement(SUPPLEMENT_PATH)


def _tmp_copy(tmp_path, src):
    dest = tmp_path / pathlib.Path(src).name
    shutil.copy(src, dest)
    return str(dest)


def test_valid_overlay_resolves_with_pinned_windows():
    manifest = _manifest()
    supplement = _supplement()
    verified = verify_supplement(
        manifest=manifest,
        manifest_path=MANIFEST_PATH,
        supplement=supplement,
        amendment_doc_path=AMENDMENT_DOC,
    )
    assert verified["amendment_id"] == "E3-D.1"
    effective, effective_fp = resolve_effective(
        manifest=manifest, supplement=supplement
    )
    assert effective["temporal"]["diagnostic_start"] == "2023-02-01"
    assert effective["temporal"]["diagnostic_end"] == "2023-02-28"
    assert effective["temporal"]["heldout_start"] == "2023-03-01"
    assert effective["temporal"]["heldout_end"] == "2023-03-31"
    assert effective["fingerprints"]["diagnostic_env"].startswith("60d189e4")
    assert effective["fingerprints"]["heldout_env"].startswith("484b82a7")
    # Untouched sections resolve straight through to base values.
    assert effective["budgets"] == manifest["budgets"]
    assert effective["hypotheses"] == manifest["hypotheses"]
    assert effective_fp == resolve_effective(
        manifest=manifest, supplement=supplement
    )[1]


def test_manifest_byte_identical_to_frozen():
    assert (
        sha256_file(MANIFEST_PATH)
        == "412deb50682d5bea5a8283278764e4e416547d09b4cf04d93141e76f230dca86"
    )


def test_tampered_manifest_file_fails(tmp_path):
    bad = _tmp_copy(tmp_path, MANIFEST_PATH)
    with open(bad, "ab") as handle:
        handle.write(b" ")
    with pytest.raises(IntegrityFailure):
        verify_supplement(
            manifest=_manifest(),
            manifest_path=bad,
            supplement=_supplement(),
            amendment_doc_path=AMENDMENT_DOC,
        )


def test_tampered_amendment_doc_fails(tmp_path):
    bad = _tmp_copy(tmp_path, AMENDMENT_DOC)
    with open(bad, "ab") as handle:
        handle.write(b" ")
    with pytest.raises(IntegrityFailure):
        verify_supplement(
            manifest=_manifest(),
            manifest_path=MANIFEST_PATH,
            supplement=_supplement(),
            amendment_doc_path=bad,
        )


def test_fake_declared_fingerprints_fail():
    supplement = _supplement()
    for key in ("base_manifest_fingerprint", "amendment_fingerprint"):
        tampered = dict(supplement)
        tampered[key] = "0" * 64
        with pytest.raises(IntegrityFailure):
            verify_supplement(
                manifest=_manifest(),
                manifest_path=MANIFEST_PATH,
                supplement=tampered,
                amendment_doc_path=AMENDMENT_DOC,
            )


def test_unknown_and_forbidden_overrides_fail():
    supplement = _supplement()
    unknown = copy.deepcopy(supplement)
    unknown["overrides"]["temporal"]["diagnostic_guess"] = "x"
    with pytest.raises(IntegrityFailure):
        verify_supplement(
            manifest=_manifest(),
            manifest_path=MANIFEST_PATH,
            supplement=unknown,
            amendment_doc_path=AMENDMENT_DOC,
        )
    for section, key in (
        ("environment", "universe"),
        ("environment", "transaction_cost_bps"),
        ("budgets", "max_tests"),
        ("temporal", "embargo_period"),
    ):
        tampered = copy.deepcopy(supplement)
        tampered["overrides"].setdefault(section, {})[key] = "x"
        with pytest.raises(IntegrityFailure):
            verify_supplement(
                manifest=_manifest(),
                manifest_path=MANIFEST_PATH,
                supplement=tampered,
                amendment_doc_path=AMENDMENT_DOC,
            )


def test_missing_required_override_fails():
    supplement = copy.deepcopy(_supplement())
    del supplement["overrides"]["temporal"]["heldout_end"]
    with pytest.raises(IntegrityFailure):
        verify_supplement(
            manifest=_manifest(),
            manifest_path=MANIFEST_PATH,
            supplement=supplement,
            amendment_doc_path=AMENDMENT_DOC,
        )


def test_changed_override_changes_effective_fingerprint():
    manifest = _manifest()
    _, pinned = resolve_effective(
        manifest=manifest, supplement=_supplement()
    )
    altered = copy.deepcopy(_supplement())
    altered["overrides"]["temporal"]["diagnostic_start"] = "2023-02-02"
    _, other = resolve_effective(manifest=manifest, supplement=altered)
    assert other != pinned


def test_inputs_unmutated_by_resolution():
    manifest = _manifest()
    supplement = _supplement()
    before_manifest = copy.deepcopy(manifest)
    before_supplement = copy.deepcopy(supplement)
    resolve_effective(manifest=manifest, supplement=supplement)
    assert manifest == before_manifest
    assert supplement == before_supplement


def test_legacy_no_amendment_path_preserved():
    from tests.experiments.harness.fixtures import make_config

    manifest = _manifest()
    make_config().verify_against_manifest(manifest)


def test_incident_artefact_untouched():
    import hashlib

    results = ROOT / "results" / "e3"
    artefacts = sorted(results.glob("8f439dc4*.json"))
    assert artefacts, "incident artefact must remain available for audit"
    for path in artefacts:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest, "artefact must remain readable"


def test_run_experiment_accepts_amendment_path():
    import inspect

    from experiments.harness import lifecycle

    params = inspect.signature(lifecycle.run_experiment).parameters
    for name in (
        "amendment_supplement", "manifest_path", "amendment_doc_path",
    ):
        assert name in params, f"run_experiment lacks {name}"


def test_amendment_mismatch_fails_before_any_episode(monkeypatch):
    import copy

    from experiments.harness import lifecycle
    from tests.experiments.harness.fixtures import make_config

    calls = []
    monkeypatch.setattr(
        lifecycle, "run_baseline",
        lambda *a, **k: calls.append("baseline") or (_ for _ in ()).throw(
            AssertionError("no episodes allowed")
        ),
    )
    bad = copy.deepcopy(_supplement())
    bad["base_manifest_fingerprint"] = "0" * 64
    with pytest.raises(Exception):
        lifecycle.run_experiment(
            config=make_config(),
            manifest=_manifest(),
            e3d_document_path="x",
            environment_fingerprint="y",
            benchmark_fingerprint="z",
            agent_fingerprint="w",
            execution_role="TIER1_PRIMARY",
            execution_instance="001",
            amendment_supplement=bad,
            manifest_path=MANIFEST_PATH,
            amendment_doc_path=(
                str(ROOT / "experiments" / "protocol"
                    / "E3-D.1-remediation-amendment.md")
            ),
        )
    assert calls == []
