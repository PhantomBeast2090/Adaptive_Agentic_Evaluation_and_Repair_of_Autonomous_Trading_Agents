"""E4-F supplement verification tests (structural only, no episodes)."""

import copy
import pathlib

import pytest
import yaml

from evaluation.context.supplement import verify_e4f_supplement

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SUPPLEMENT_PATH = (
    ROOT / "experiments" / "protocol" / "E4-F-supplement.yaml"
)
OVERLAY_PATH = ROOT / "benchmarks" / "manifest.e4f.yaml"
PROTOCOL_PATH = (
    ROOT / "experiments" / "protocol" / "E4-F-accumulation-cycles.md"
)
E3D1_SUPPLEMENT = (
    ROOT / "experiments" / "protocol" / "E3-D.1-supplement.yaml"
)


def _supplement():
    with open(SUPPLEMENT_PATH, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_valid_supplement_resolves():
    resolved = verify_e4f_supplement(
        supplement=_supplement(),
        manifest_e4f_path=str(OVERLAY_PATH),
        protocol_doc_path=str(PROTOCOL_PATH),
    )
    windows = resolved["windows"]
    assert [w["start"] for w in (
        windows["w1_diagnostic"], windows["w2_diagnostic"],
        windows["w3_heldout"],
    )] == ["2022-11-01", "2022-12-01", "2023-01-01"]
    assert windows["w1_diagnostic"]["nse_sessions"] == 21
    assert windows["w2_diagnostic"]["nse_sessions"] == 22
    assert windows["w3_heldout"]["nse_sessions"] == 21
    envs = [w["environment_fingerprint"] for w in windows.values()]
    assert envs[0].startswith("87bbe286")
    assert envs[1].startswith("9c30824e")
    assert envs[2].startswith("1b70c9df")


def test_overlay_placeholder_temporal_cannot_govern():
    overlay = yaml.safe_load(OVERLAY_PATH.read_text(encoding="utf-8"))
    resolved = verify_e4f_supplement(
        supplement=_supplement(),
        manifest_e4f_path=str(OVERLAY_PATH),
        protocol_doc_path=str(PROTOCOL_PATH),
    )
    for key, window in resolved["windows"].items():
        assert (window["start"], window["end"]) != (
            overlay["temporal"]["diagnostic_start"],
            overlay["temporal"]["diagnostic_end"],
        ), key
    assert "must never govern an E4-F execution" in (
        overlay["temporal"]["selection_basis"]
    )


def test_stale_linkage_refused():
    supplement = copy.deepcopy(_supplement())
    supplement["base_manifest_fingerprint"] = "0" * 64
    with pytest.raises(ValueError):
        verify_e4f_supplement(
            supplement=supplement,
            manifest_e4f_path=str(OVERLAY_PATH),
            protocol_doc_path=str(PROTOCOL_PATH),
        )
    supplement = copy.deepcopy(_supplement())
    supplement["protocol_fingerprint"] = "0" * 64
    with pytest.raises(ValueError):
        verify_e4f_supplement(
            supplement=supplement,
            manifest_e4f_path=str(OVERLAY_PATH),
            protocol_doc_path=str(PROTOCOL_PATH),
        )


def test_overlap_and_minima_refused():
    supplement = copy.deepcopy(_supplement())
    supplement["windows"]["w3_heldout"]["start"] = "2022-12-15"
    with pytest.raises(ValueError):
        verify_e4f_supplement(
            supplement=supplement,
            manifest_e4f_path=str(OVERLAY_PATH),
            protocol_doc_path=str(PROTOCOL_PATH),
        )
    supplement = copy.deepcopy(_supplement())
    supplement["windows"]["w2_diagnostic"]["nse_sessions"] = 12
    with pytest.raises(ValueError):
        verify_e4f_supplement(
            supplement=supplement,
            manifest_e4f_path=str(OVERLAY_PATH),
            protocol_doc_path=str(PROTOCOL_PATH),
        )
    supplement = copy.deepcopy(_supplement())
    del supplement["windows"]["w2_diagnostic"]
    with pytest.raises(ValueError):
        verify_e4f_supplement(
            supplement=supplement,
            manifest_e4f_path=str(OVERLAY_PATH),
            protocol_doc_path=str(PROTOCOL_PATH),
        )


def test_e3d1_supplement_untouched():
    import hashlib

    assert hashlib.sha256(
        E3D1_SUPPLEMENT.read_bytes()
    ).hexdigest() == (
        "45a2f425a5a502b60fdf93bdb14b03bd84aea4bc9e21c6bdb5be72428dbfcc35"
    )


def test_forbidden_windows_excluded():
    resolved = verify_e4f_supplement(
        supplement=_supplement(),
        manifest_e4f_path=str(OVERLAY_PATH),
        protocol_doc_path=str(PROTOCOL_PATH),
    )
    starts = [w["start"][:7] for w in resolved["windows"].values()]
    for forbidden in ("2023-02", "2023-03", "2023-05", "2023-06",
                      "2023-07", "2023-08"):
        assert forbidden not in starts
