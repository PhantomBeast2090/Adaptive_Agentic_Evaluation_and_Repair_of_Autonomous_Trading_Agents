"""Phase-3 Adaptive-vs-Random pilot runner (thin CLI).

Loads the canonical adaptive config, constructs the discovery-only candidate
pool ONCE, runs paired Adaptive/Random arms per seed with identical inputs,
validates comparability mechanically, and persists provenance JSON artifacts.

Usage:
    PYTHONPATH=. python scripts/run_adaptive_vs_random.py \
        --config configs/adaptive_evaluation.yaml
"""

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase-3 Adaptive vs Random comparison")
    parser.add_argument("--config", default="configs/adaptive_evaluation.yaml")
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    # Ensure repo-root-relative imports work when invoked from the package dir.
    base = Path(args.base_dir)
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))

    from evaluation.adaptive.experiment import run_paired_experiment

    summary = run_paired_experiment(
        config_path=args.config,
        base_dir=args.base_dir,
        output_dir=args.output,
    )
    print(f"experiment: {summary['experiment_id']}")
    print(f"pool_size: {summary['pool_size']}")
    print(f"pool_fingerprint: {summary['pool_fingerprint']}")
    print(f"dataset_fingerprint: {summary['dataset_fingerprint']}")
    print(f"git_commit: {summary['git_commit']}")
    for pair in summary["pairs"]:
        print(
            f"  agent={pair['agent_id']} seed={pair['seed']} "
            f"strategy={pair['strategy']} evaluated={pair['evaluated_count']} "
            f"unique_vulns={pair['unique_vulnerabilities']} file={pair['file']}"
        )
    print(f"summary: {summary['summary_file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
