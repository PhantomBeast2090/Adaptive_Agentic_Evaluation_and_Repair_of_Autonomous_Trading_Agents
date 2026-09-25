"""E4-F overlay manifest shape (additive; base manifest untouched).

Pins benchmarks/manifest.e4f.yaml: E4-F.1 revision, base-manifest
anchor to the frozen E3-D.1 bytes, two hypotheses, six-test pool with
the exposure-discriminating row, sequence/budget coverage, and the
overlay's canonical fingerprint. No market episodes.
"""

import hashlib
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
OVERLAY_PATH = ROOT / "benchmarks" / "manifest.e4f.yaml"
BASE_PATH = ROOT / "benchmarks" / "manifest.yaml"

OVERLAY_FINGERPRINT = (
    "e12f84da5c03d40ceb4a4013c70eb6ab4318f6123fbb4a405fd32f4c7a22d109"
)
BASE_FINGERPRINT = (
    "412deb50682d5bea5a8283278764e4e416547d09b4cf04d93141e76f230dca86"
)


def _overlay():
    with open(OVERLAY_PATH, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_overlay_file_fingerprint_pinned():
    assert _sha(OVERLAY_PATH) == OVERLAY_FINGERPRINT


def test_overlay_anchors_frozen_base():
    assert _sha(BASE_PATH) == BASE_FINGERPRINT
    overlay = _overlay()
    assert overlay["protocol_revision"] == "E4-F.1"
    assert overlay["base_manifest"] == "benchmarks/manifest.yaml"
    assert overlay["base_manifest_fingerprint"] == BASE_FINGERPRINT


def test_overlay_two_hypotheses_six_tests():
    overlay = _overlay()
    assert [h["hypothesis_id"] for h in overlay["hypotheses"]] == [
        "H-turnover", "H-exposure",
    ]
    exposure = overlay["hypotheses"][1]
    assert exposure["failure_class"] == "exposure"
    assert exposure["primary_metric"] == "gross_exposure_max"
    assert exposure["primary_direction"] == "DECREASE"
    assert [t["test_id"] for t in overlay["candidate_pool"]] == [
        "T-null", "T-cost2x", "T-cost0",
        "T-vintage-earliest", "T-uni-tcs", "T-exp-narrow",
    ]
    narrow = overlay["candidate_pool"][-1]
    assert narrow["intervention"]["type"] == "universe_restriction"
    assert "gross_exposure_max" in narrow["measures"]
    assert overlay["fixed_sequence"]["order"][-1] == "T-exp-narrow"
    assert overlay["budgets"]["max_tests"] >= 6


def test_overlay_environment_matches_base():
    import copy

    overlay = _overlay()
    base = yaml.safe_load(BASE_PATH.read_text(encoding="utf-8"))
    for section in (
        "benchmarks", "class_b_constants", "environment", "fingerprints",
    ):
        assert overlay[section] == base[section]
    assert copy.deepcopy(overlay["candidate_pool"][:5]) == (
        base["candidate_pool"]
    )
