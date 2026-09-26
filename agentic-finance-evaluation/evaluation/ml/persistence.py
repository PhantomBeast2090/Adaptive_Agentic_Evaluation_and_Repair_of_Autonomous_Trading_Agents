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


def fingerprint_artefacts(artefacts: Mapping[str, Any]) -> str:
    payload = {k: v for k, v in artefacts.items() if k != "fingerprint"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def save_m2(base_dir: str, experiment_id: str,
            artefacts: Mapping[str, Any],
            code_sha: str, data_sha: str,
            overwrite: bool = False) -> str:
    out_dir = os.path.join(base_dir, *REGISTRY_SUBDIR, experiment_id)
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
