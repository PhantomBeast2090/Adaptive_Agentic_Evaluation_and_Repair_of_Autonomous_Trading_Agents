"""M2 persistence contract (mirrors the M1/_m1 convention).

Each cell persists under ``data/frozen_traces/_m2/<experiment_id>/``:
config, metrics, predictions, hypotheses, permutation evidence,
manifest (fingerprint + code SHA + data SHA). Fail-closed: never
silently overwrite. Blocked cells (e.g. TabPFN weights unreachable)
persist their blocker evidence instead of predictions.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Mapping

REGISTRY_SUBDIR = ("data", "frozen_traces", "_m2")
FOUNDATION_SUBDIR = ("data", "frozen_traces", "_ml_foundation")
SEQUENCE_SUBDIR = ("data", "frozen_traces", "_ml_sequence")


def fingerprint_artefacts(artefacts: Mapping[str, Any]) -> str:
    payload = {k: v for k, v in artefacts.items() if k != "fingerprint"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def save_m2(base_dir: str, experiment_id: str,
            artefacts: Mapping[str, Any],
            code_sha: str, data_sha: str,
            overwrite: bool = False,
            subdir: tuple = REGISTRY_SUBDIR) -> str:
    out_dir = os.path.join(base_dir, *subdir, experiment_id)
    if os.path.exists(out_dir) and not overwrite:
        raise FileExistsError(f"refusing to overwrite {out_dir}")
    os.makedirs(out_dir, exist_ok=True)

    def write(name: str, payload: Any) -> None:
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as h:
            json.dump(payload, h, sort_keys=True, separators=(",", ":"))
            h.write("\n")

    for name in ("config", "metrics", "model", "predictions",
                 "hypotheses", "permutation"):
        if name in artefacts:
            write(f"{name}.json", artefacts[name])
    write("manifest.json", {
        "experiment_id": experiment_id,
        "fingerprint": artefacts.get("fingerprint"),
        "code_sha": code_sha, "data_sha": data_sha,
        "status": artefacts.get("status", "COMPLETE")})
    return out_dir


def save_foundation(base_dir: str, run_id: str,
                    artefacts: Mapping[str, Any],
                    provenance: Mapping[str, Any],
                    environment: Mapping[str, Any] | None = None,
                    overwrite: bool = False) -> str:
    """Persist one foundation run under _ml_foundation/<run_id>/.

    JSON artefacts are written as ``<name>.json``; ``forecast_outputs``
    and ``diagnostic_table`` (list-of-dict rows) additionally persist
    as parquet. The manifest fingerprint covers deterministic content
    only (artefacts + provenance); volatile ``environment`` readings
    (RSS, wall-clock) persist unfingerprinted for audit, never for
    identity.
    """
    out_dir = os.path.join(base_dir, *FOUNDATION_SUBDIR, run_id)
    if os.path.exists(out_dir) and not overwrite:
        raise FileExistsError(f"refusing to overwrite {out_dir}")
    os.makedirs(out_dir, exist_ok=True)

    def write(name: str, payload: Any) -> None:
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as h:
            json.dump(payload, h, sort_keys=True, separators=(",", ":"),
                      default=str)
            h.write("\n")

    file_fps = {}
    for name, payload in artefacts.items():
        if name in ("forecast_outputs", "diagnostic_table") \
                and isinstance(payload, list):
            import pandas as pd
            frame = pd.DataFrame(payload)
            frame.to_parquet(os.path.join(out_dir, f"{name}.parquet"),
                             index=False)
            file_fps[f"{name}.parquet"] = sha256_of_file(
                os.path.join(out_dir, f"{name}.parquet"))
        write(f"{name}.json", payload)
        file_fps[f"{name}.json"] = sha256_of_file(
            os.path.join(out_dir, f"{name}.json"))
    manifest = dict(provenance)
    manifest.update({"run_id": run_id, "files": file_fps,
                     "environment": dict(environment or {}),
                     "fingerprint": fingerprint_artefacts(
                         {**{k: v for k, v in artefacts.items()
                              if k not in ("forecast_outputs",
                                           "diagnostic_table")},
                          **dict(provenance)})})
    write("manifest.json", manifest)
    return out_dir


def sha256_of_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
