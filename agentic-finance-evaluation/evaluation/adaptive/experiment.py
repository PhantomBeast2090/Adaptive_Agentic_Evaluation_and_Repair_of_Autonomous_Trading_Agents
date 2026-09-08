"""Phase-3 Adaptive-vs-Random experiment harness.

Thin orchestration around the frozen Phase-3 primitives
(`evaluation/adaptive/runner.py`, `selector.py`, `evidence_extractor.py`).
The independent variable is scenario-selection strategy only: both arms share
one candidate pool, one budget, one seed per pair, one agent, and one
evaluation pipeline (`StaticEvaluator.evaluate_on_scenario`).

No diagnosis, repair, LLM reasoning, or Phase-4 functionality belongs here.
Dataset dates and windowing are intentionally unchanged (see adaptive config).
"""

import hashlib
import importlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import yaml

from src.schemas.scenario import StaticScenario
from src.schemas.adaptive_evaluation import AdaptiveRunRecord, SelectionRecord


FORBIDDEN_POOL_SPLITS = {"ood_validation", "re_evaluation", "holdout", "ood"}
OOD_SOURCE_SPLITS = {"ood_validation", "holdout", "ood"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

def load_adaptive_config(config_path: str = "configs/adaptive_evaluation.yaml") -> Dict[str, Any]:
    """Load the canonical Phase-3 configuration."""
    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)
    if "adaptive_evaluation" not in raw:
        raise ValueError(
            f"Config {config_path} must contain top-level key 'adaptive_evaluation'"
        )
    return raw["adaptive_evaluation"]


def validate_adaptive_config(config: Dict[str, Any]) -> None:
    """Fail loudly on invalid experimental design. No silent defaults."""
    for key in ("experiment_id", "candidate_pool", "agents", "environment", "evaluation", "output"):
        if key not in config:
            raise ValueError(f"adaptive_evaluation config missing required key '{key}'")

    pool_cfg = config["candidate_pool"]
    splits = pool_cfg.get("splits", [])
    if not splits:
        raise ValueError("candidate_pool.splits must be a non-empty list")
    forbidden = [s for s in splits if s in FORBIDDEN_POOL_SPLITS]
    if forbidden:
        raise ValueError(
            f"candidate_pool.splits must be discovery-only; forbidden splits present: {forbidden}. "
            f"Do not use re_evaluation/OOD data for Phase-3 discovery."
        )
    if not pool_cfg.get("require_discovery_only", False):
        raise ValueError("candidate_pool.require_discovery_only must be true")
    if not pool_cfg.get("require_holdout_exclusion", False):
        raise ValueError("candidate_pool.require_holdout_exclusion must be true")
    max_per_split = pool_cfg.get("max_per_split", 0)
    if not isinstance(max_per_split, int) or max_per_split < 1:
        raise ValueError(f"candidate_pool.max_per_split must be >= 1, got {max_per_split}")

    agents = config["agents"]
    if not agents:
        raise ValueError("agents must be a non-empty list")
    for a in agents:
        for k in ("agent_id", "version", "class", "module"):
            if k not in a:
                raise ValueError(f"agent entry missing required key '{k}': {a}")

    env = config["environment"]
    for k in ("initial_cash", "transaction_cost_bps"):
        if k not in env:
            raise ValueError(f"environment missing required key '{k}'")

    ev = config["evaluation"]
    budget = ev.get("budget", 0)
    initial = ev.get("initial_samples", 0)
    batch = ev.get("batch_size", 0)
    seeds = ev.get("seeds", [])
    strategies = ev.get("strategies", [])
    if not isinstance(budget, int) or budget < 1:
        raise ValueError(f"evaluation.budget must be >= 1, got {budget}")
    if not isinstance(initial, int) or initial < 1:
        raise ValueError(f"evaluation.initial_samples must be >= 1, got {initial}")
    if not isinstance(batch, int) or batch < 1:
        raise ValueError(f"evaluation.batch_size must be >= 1, got {batch}")
    if initial > budget:
        raise ValueError(f"evaluation.initial_samples ({initial}) must not exceed budget ({budget})")
    if not seeds or not all(isinstance(s, int) for s in seeds):
        raise ValueError(f"evaluation.seeds must be a non-empty list of ints, got {seeds}")
    if not strategies or not set(strategies) <= {"adaptive", "random"}:
        raise ValueError(f"evaluation.strategies must be a non-empty subset of ['adaptive','random'], got {strategies}")
    if max_per_split * len(splits) < budget:
        raise ValueError(
            f"candidate pool capacity ({max_per_split} x {len(splits)} splits) "
            f"is smaller than budget ({budget}); increase max_per_split"
        )

    if "results_dir" not in config["output"]:
        raise ValueError("output.results_dir is required")


# --------------------------------------------------------------------------- #
# Candidate pool (discovery only, reuses Phase-2 window logic)
# --------------------------------------------------------------------------- #

def build_candidate_pool(config: Dict[str, Any], base_dir: str = ".") -> List[StaticScenario]:
    """Construct the discovery-only candidate pool ONCE per experiment.

    Reuses `ScenarioLoader._create_scenarios_from_split` window logic
    (window 63 / stride 21, unchanged) with environment params from the
    adaptive config. Rejects holdout/OOD sources explicitly.
    """
    from src.data.scenario_loader import ScenarioLoader

    validate_adaptive_config(config)
    base = Path(base_dir)
    pool_cfg = config["candidate_pool"]
    env_cfg = config["environment"]

    # Minimal loader shell reusing window/regen logic without re-reading a
    # different config file.
    loader = ScenarioLoader.__new__(ScenarioLoader)
    loader.config = {"environment": env_cfg}
    loader.base_dir = base
    loader.vix_high_threshold = 25.0
    loader.vix_low_threshold = 15.0
    loader._seen_fingerprints = set()

    import pandas as pd

    pool: List[StaticScenario] = []
    for split in pool_cfg["splits"]:
        if split in FORBIDDEN_POOL_SPLITS:
            raise ValueError(f"Refusing to build discovery pool from forbidden split '{split}'")
        split_path = base / "data" / "processed" / "market_splits" / f"{split}.parquet"
        if not split_path.exists():
            raise FileNotFoundError(f"Split file not found: {split_path}")
        df = pd.read_parquet(split_path)
        scenarios = loader._create_scenarios_from_split(
            split_name=split,
            df=df,
            max_scenarios=int(pool_cfg["max_per_split"]),
            holdout=False,
        )
        pool.extend(scenarios)

    # Hard guard: pool must contain no holdout/OOD entries.
    for s in pool:
        if bool(s.holdout):
            raise ValueError(f"Pool construction produced holdout scenario '{s.scenario_id}'")
        if str(s.source_split) in OOD_SOURCE_SPLITS:
            raise ValueError(f"Pool construction produced OOD scenario '{s.scenario_id}'")

    pool.sort(key=lambda s: s.scenario_id)
    return pool


# --------------------------------------------------------------------------- #
# Fingerprints
# --------------------------------------------------------------------------- #

def candidate_pool_fingerprint(pool: List[StaticScenario]) -> str:
    """Deterministic fingerprint over ordered scenario descriptors.

    Covers logical identity only (no timestamps, UUIDs, or absolute paths).
    Both paired arms must store the same value.
    """
    entries = []
    for s in sorted(pool, key=lambda x: x.scenario_id):
        entries.append({
            "scenario_id": s.scenario_id,
            "source_split": s.source_split,
            "start_date": s.start_date,
            "end_date": s.end_date,
            "market_regime": s.market_regime,
            "difficulty": s.difficulty,
            "initial_cash": s.initial_cash,
            "transaction_cost_bps": s.transaction_cost_bps,
            "holdout": bool(s.holdout),
        })
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def dataset_fingerprint(pool: List[StaticScenario]) -> str:
    """Fingerprint of the underlying market bytes for the pool.

    Uses per-scenario `HistoricalMarket` window fingerprints when files exist;
    falls back to the pool fingerprint (prefixed) for synthetic unit-test pools
    whose market files do not exist. Never includes timestamps or UUIDs.
    """
    from environment.market.historical import HistoricalMarket

    window_fps = []
    missing = 0
    for s in sorted(pool, key=lambda x: x.scenario_id):
        try:
            market = HistoricalMarket(
                s.market_data_path, start_date=s.start_date, end_date=s.end_date
            )
            window_fps.append({"scenario_id": s.scenario_id, "market_fingerprint": market.fingerprint()})
        except Exception:
            missing += 1
    if missing and missing == len(pool):
        # Entirely synthetic pool (unit tests): bind dataset identity to pool identity.
        fallback = "synthetic-data:" + candidate_pool_fingerprint(pool)
        return hashlib.sha256(fallback.encode("utf-8")).hexdigest()
    if missing:
        # Partial miss is a construction error, not a silent fallback.
        raise ValueError(
            f"dataset_fingerprint: {missing}/{len(pool)} market windows unreadable; "
            f"check market_data_path values"
        )
    canonical = json.dumps(sorted(window_fps, key=lambda e: e["scenario_id"]), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_git_commit(repo_root: Optional[str] = None) -> str:
    """Best-effort git commit; 'unknown' outside a git checkout."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root or ".",
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return out.decode("utf-8").strip()
    except Exception:
        return "unknown"


# --------------------------------------------------------------------------- #
# Agents
# --------------------------------------------------------------------------- #

def load_agents(config: Dict[str, Any]) -> List[Any]:
    """Instantiate agents listed in the adaptive config."""
    agents = []
    for entry in config["agents"]:
        module = importlib.import_module(entry["module"])
        cls = getattr(module, entry["class"])
        agents.append(cls(agent_id=entry["agent_id"], version=entry["version"]))
    return agents


def agent_config_for(agent: Any, config: Dict[str, Any]) -> Dict[str, str]:
    """Return the config entry matching an instantiated agent."""
    for entry in config.get("agents", []):
        if entry.get("agent_id") == getattr(agent, "agent_id", None):
            return {"class": entry.get("class", ""), "module": entry.get("module", "")}
    return {"class": type(agent).__name__, "module": type(agent).__module__}


# --------------------------------------------------------------------------- #
# Single-arm execution and persistence
# --------------------------------------------------------------------------- #

def run_single_arm(
    pool: List[StaticScenario],
    agent: Any,
    seed: int,
    strategy: str,
    budget: int,
    initial_samples: int,
    batch_size: int,
    evaluate_callable: Any,
    experiment_id: str,
    description: str = "",
    configuration: Optional[Dict[str, Any]] = None,
    git_commit: str = "unknown",
    dataset_fp: str = "",
    pool_fp: str = "",
) -> AdaptiveRunRecord:
    """Run one arm (adaptive OR random) and return a persisted-ready record."""
    from evaluation.adaptive.runner import AdaptiveRunner

    if strategy not in ("adaptive", "random"):
        raise ValueError(f"Unknown strategy '{strategy}'")
    runner = AdaptiveRunner(pool, seed=seed, evaluate_callable=evaluate_callable)
    report = runner.run(
        agent,
        initial_samples=initial_samples,
        budget=budget,
        batch_size=batch_size,
        strategy=strategy,
    )

    agent_cfg = agent_config_for(agent, configuration or {})
    selection = [SelectionRecord(**s) for s in report.get("selection_history", [])]
    episodes = []
    for ep in report.get("episodes", []):
        episodes.append(ep.model_dump() if hasattr(ep, "model_dump") else dict(ep))
    vulns = []
    for v in report.get("vulnerabilities", []):
        vulns.append(v.model_dump() if hasattr(v, "model_dump") else dict(v))

    record = AdaptiveRunRecord(
        run_id=f"{experiment_id}_seed{seed}_{strategy}_{(pool_fp or 'pool')[:8]}",
        experiment_id=experiment_id,
        description=description,
        strategy=strategy,
        seed=seed,
        agent_id=getattr(agent, "agent_id", "unknown"),
        agent_version=getattr(agent, "version", "unknown"),
        agent_class=agent_cfg.get("class", ""),
        agent_module=agent_cfg.get("module", ""),
        budget=budget,
        initial_samples=initial_samples,
        batch_size=batch_size,
        dataset_fingerprint=dataset_fp,
        pool_fingerprint=pool_fp,
        pool_size=len(pool),
        scenario_sequence=list(report.get("scenario_sequence", [])),
        selection_history=selection,
        episode_evaluations=episodes,
        vulnerabilities=vulns,
        vulnerability_categories=list(report.get("unique_vulnerability_categories", [])),
        evaluated_count=int(report.get("evaluated_count", 0)),
        unique_vulnerabilities=int(report.get("unique_vulnerabilities", 0)),
        git_commit=git_commit,
        configuration=dict(configuration or {}),
    )
    return record


def validate_comparability(adaptive: AdaptiveRunRecord, random: AdaptiveRunRecord) -> None:
    """Fail loudly if a paired comparison differs in anything but strategy."""
    checks = [
        ("pool_fingerprint", adaptive.pool_fingerprint, random.pool_fingerprint),
        ("dataset_fingerprint", adaptive.dataset_fingerprint, random.dataset_fingerprint),
        ("budget", adaptive.budget, random.budget),
        ("initial_samples", adaptive.initial_samples, random.initial_samples),
        ("batch_size", adaptive.batch_size, random.batch_size),
        ("seed", adaptive.seed, random.seed),
        ("agent_id", adaptive.agent_id, random.agent_id),
        ("agent_version", adaptive.agent_version, random.agent_version),
        ("pool_size", adaptive.pool_size, random.pool_size),
        ("experiment_id", adaptive.experiment_id, random.experiment_id),
    ]
    mismatches = [name for name, a, b in checks if a != b]
    if mismatches:
        raise ValueError(
            f"Paired Adaptive-vs-Random runs are not comparable; mismatched fields: {mismatches}"
        )
    if adaptive.strategy != "adaptive" or random.strategy != "random":
        raise ValueError(
            f"Paired runs must be (adaptive, random); got ({adaptive.strategy}, {random.strategy})"
        )
    if adaptive.evaluated_count != random.evaluated_count:
        raise ValueError(
            f"Paired runs evaluated different counts: adaptive={adaptive.evaluated_count} "
            f"random={random.evaluated_count}"
        )


def save_run_record(record: AdaptiveRunRecord, output_dir: str) -> Path:
    """Persist one run record as deterministic JSON. Returns the file path."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{record.run_id}.json"
    with open(path, "w") as f:
        json.dump(record.to_dict(), f, indent=2, default=str)
    return path


def load_run_record(path: str) -> AdaptiveRunRecord:
    """Reload a persisted run record."""
    with open(path, "r") as f:
        data = json.load(f)
    return AdaptiveRunRecord(**data)


# --------------------------------------------------------------------------- #
# Paired experiment
# --------------------------------------------------------------------------- #

def run_paired_experiment(
    config_path: str = "configs/adaptive_evaluation.yaml",
    base_dir: str = ".",
    output_dir: Optional[str] = None,
    static_evaluator: Optional[Any] = None,
    evaluate_callable_factory: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run Adaptive vs Random for each configured seed on ONE shared pool.

    Both arms of each seed pair share the pool, budget, seed, agent, and
    evaluation machinery. Results are persisted and comparability is validated
    mechanically (not by documentation).
    """
    config = load_adaptive_config(config_path)
    validate_adaptive_config(config)
    ev = config["evaluation"]

    pool = build_candidate_pool(config, base_dir=base_dir)
    pool_fp = candidate_pool_fingerprint(pool)
    dataset_fp = dataset_fingerprint(pool)
    git_commit = get_git_commit(base_dir)
    agents = load_agents(config)

    out_dir = output_dir or config["output"]["results_dir"]

    # One shared evaluation pipeline for all arms (same machinery).
    shared_evaluator = static_evaluator
    if shared_evaluator is None and evaluate_callable_factory is None:
        from evaluation.static_evaluator import StaticEvaluator

        shared_evaluator = StaticEvaluator(config_path="configs/static_evaluation.yaml")

    summary: Dict[str, Any] = {
        "experiment_id": config["experiment_id"],
        "pool_fingerprint": pool_fp,
        "dataset_fingerprint": dataset_fp,
        "git_commit": git_commit,
        "pool_size": len(pool),
        "pairs": [],
    }

    for agent in agents:
        for seed in ev["seeds"]:
            arm_records: Dict[str, AdaptiveRunRecord] = {}
            for strategy in ev["strategies"]:
                if evaluate_callable_factory is not None:
                    evaluate_callable = evaluate_callable_factory(strategy, seed, agent)
                else:
                    evaluate_callable = shared_evaluator.evaluate_on_scenario
                record = run_single_arm(
                    pool=pool,
                    agent=agent,
                    seed=int(seed),
                    strategy=strategy,
                    budget=int(ev["budget"]),
                    initial_samples=int(ev["initial_samples"]),
                    batch_size=int(ev["batch_size"]),
                    evaluate_callable=evaluate_callable,
                    experiment_id=config["experiment_id"],
                    description=config.get("description", ""),
                    configuration=config,
                    git_commit=git_commit,
                    dataset_fp=dataset_fp,
                    pool_fp=pool_fp,
                )
                path = save_run_record(record, out_dir)
                arm_records[strategy] = record
                summary["pairs"].append({
                    "agent_id": record.agent_id,
                    "seed": record.seed,
                    "strategy": record.strategy,
                    "evaluated_count": record.evaluated_count,
                    "unique_vulnerabilities": record.unique_vulnerabilities,
                    "pool_fingerprint": record.pool_fingerprint,
                    "file": str(path),
                })

            # Mechanical comparability gate for the pair (when both present).
            if "adaptive" in arm_records and "random" in arm_records:
                validate_comparability(arm_records["adaptive"], arm_records["random"])

    summary_path = Path(out_dir) / f"{config['experiment_id']}_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    summary["summary_file"] = str(summary_path)
    return summary
