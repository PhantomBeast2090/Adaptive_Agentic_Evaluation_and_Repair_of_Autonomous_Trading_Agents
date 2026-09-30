"""M-R9 controls audit (additive): every experiment's decoys refused/rejected.

Controls execute inside run_mr9.py through the serving path. This script
audits data/adaptive_repair/M-R9/<exp>/controls.json verdicts and fails
on any UNEXPECTED-PASS or ERROR. No environment runs; artefact-only.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, ".")

OUT_DIR = "data/adaptive_repair/M-R9"
EXPERIMENTS = ("R9-A", "R9-B", "R9-C", "R9-D", "R9-E", "R9-F")


def audit_controls(base_dir: str = ".") -> dict:
    outcomes = {}
    failures = []
    for tag in EXPERIMENTS:
        path = os.path.join(base_dir, OUT_DIR, tag, "controls.json")
        if not os.path.exists(path):
            outcomes[tag] = "MISSING"
            continue
        controls = json.load(open(path))["controls"]
        bad = [c for c in controls
               if c.get("verdict") not in ("REFUSED", "REJECTED",
                                           "NOT-APPLICABLE")]
        outcomes[tag] = ("CLEAN" if not bad else "VIOLATION")
        for control in bad:
            failures.append(f"{tag}/{control.get('control_id')}: "
                            f"{control.get('verdict')}")
    return {"outcomes": outcomes, "failures": failures}


def main() -> None:
    result = audit_controls(".")
    for tag, outcome in result["outcomes"].items():
        print(f"{tag}: {outcome}")
    if result["failures"]:
        print("VIOLATIONS:")
        for failure in result["failures"]:
            print(f"  {failure}")
        raise SystemExit(1)
    print("all M-R9 controls REFUSED/REJECTED")


if __name__ == "__main__":
    main()
