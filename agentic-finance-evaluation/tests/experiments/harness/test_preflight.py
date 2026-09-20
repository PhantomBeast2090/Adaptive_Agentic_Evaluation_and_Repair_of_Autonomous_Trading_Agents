"""Preflight dry-run: fail-closed verification with zero episodes."""

import pathlib

import pytest

from experiments.harness.errors import IntegrityFailure
from experiments.harness.preflight import ensure_preflight, preflight

from .fixtures import make_config, make_manifest

E3D_PATH = str(
    pathlib.Path(__file__).resolve().parent.parent.parent.parent
    / "experiments"
    / "protocol"
    / "E3-D-statistical-experimental-protocol.md"
)


def _good_kwargs():
    import hashlib

    digest = hashlib.sha256(open(E3D_PATH, "rb").read()).hexdigest()
    return {
        "config": make_config(e3d_fingerprint=digest),
        "manifest": make_manifest(),
        "e3d_document_path": E3D_PATH,
        "environment_fingerprint": "env-fp-fixture",
        "benchmark_fingerprint": "bench-fp-fixture",
        "agent_fingerprint": "agent-fp-fixture",
    }


def test_preflight_passes_on_matching_inputs():
    report = preflight(**_good_kwargs())
    assert report.passed
    assert report.failures() == ()
    assert len(report.checks) >= 10
    ensure_preflight(report)


def test_preflight_fails_closed_on_mismatches():
    import hashlib

    digest = hashlib.sha256(open(E3D_PATH, "rb").read()).hexdigest()
    bad_manifest = make_manifest()
    bad_manifest["temporal"] = {
        **bad_manifest["temporal"],
        "heldout_start": "2023-05-20",
    }
    report = preflight(
        config=make_config(e3d_fingerprint=digest),
        manifest=bad_manifest,
        e3d_document_path=E3D_PATH,
        environment_fingerprint="WRONG",
        benchmark_fingerprint="",
        agent_fingerprint="agent-fp-fixture",
    )
    assert not report.passed
    names = {check.name for check in report.failures()}
    assert "manifest_match" in names
    assert "environment_fingerprint" in names
    assert "benchmark_fingerprint" in names
    with pytest.raises(IntegrityFailure):
        ensure_preflight(report)


def test_preflight_rejects_wrong_protocol_fingerprint():
    kwargs = _good_kwargs()
    kwargs["config"] = make_config(e3d_fingerprint="0" * 64)
    report = preflight(**kwargs)
    assert not report.passed
    assert "protocol_fingerprint" in {
        check.name for check in report.failures()
    }


def test_preflight_rejects_missing_protocol_file():
    kwargs = _good_kwargs()
    kwargs["e3d_document_path"] = "experiments/protocol/NOPE.md"
    report = preflight(**kwargs)
    assert not report.passed
