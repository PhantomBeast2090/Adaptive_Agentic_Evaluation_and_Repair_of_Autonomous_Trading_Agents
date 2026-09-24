"""E4-E controlled context-repair experiment (orchestration only).

This module adds the four-arm E4-E comparison on top of the frozen
substrate without modifying it:

* ARM A (C0 baseline): fresh agent, empty context, no ``adapt()``.
* ARM B (diagnosis-only): validated repair artefacts exist for
  provenance, but the agent receives no corrective context.
* ARM C (temporary context): equivalent corrective knowledge delivered
  ephemerally via one provisional ``adapt()`` on an isolated copy.
  Never touches ``MemoryStore``, ``retrieve()``, ``assemble()`` or
  ``deliver()``; never persists.
* ARM D (persistent C1): the real E4-A to E4-D pipeline
  (``extract_candidate`` → ``adjudicate`` → ``admit`` → ``retrieve`` →
  ``assemble`` → store-bound ``deliver``) with C1 locked before any
  held-out execution.

All helpers are deterministic: no wall-clock, UUID, PID, randomness,
or hidden counters enter any fingerprinted identity. Heavy episode
execution lives in :func:`run_e4e` (lazy imports, real environment);
every other helper is pure and covered by cheap tests.
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.context.benchmark import ContextualThresholdBenchmark
from evaluation.contracts.agent import AgentIdentity
from evaluation.contracts.fingerprints import fingerprint_of_dict, thaw

EXPERIMENT_METHOD = "e4e-controlled-context-repair"
EXPERIMENT_VERSION = "v1"

EXECUTION_METHOD = "e4e-execution"
EXECUTION_VERSION = "v1"

# Active E3-D.1 temporal pair (diagnostic strictly before held-out).
DIAGNOSTIC_START = "2023-02-01"
DIAGNOSTIC_END = "2023-02-28"
HELDOUT_START = "2023-03-01"
HELDOUT_END = "2023-03-31"
DIAGNOSTIC_ENV_FINGERPRINT = (
    "60d189e4d17310f0ec12b46c20a7411e17b44833700e6a1757b6d1f7a2d33acd"
)
HELDOUT_ENV_FINGERPRINT = (
    "484b82a73c8eef6837f1a0227edee869bbd5a8594ba233fe7b875fa268254437"
)
BASE_MANIFEST_FINGERPRINT = (
    "412deb50682d5bea5a8283278764e4e416547d09b4cf04d93141e76f230dca86"
)
SUPPLEMENT_FINGERPRINT = (
    "01544896cbe2aa62f688d354d4b75ea402ca68b342980ff7bce99c42d0e86baf"
)

TEMPORARY_PROVENANCE = "temporary-no-store"

# Knowledge entries must carry these non-empty string fields, mirroring
# the contextual benchmark's admission contract.
_REQUIRED_ENTRY_KEYS = (
    "context_id",
    "failure_mechanism",
    "corrective_principle",
)

# Store-lineage keys that must never appear in a temporary payload.
_FORBIDDEN_TEMPORARY_KEYS = (
    "entry_id",
    "verdict_fingerprint",
    "candidate_fingerprint",
    "store_fingerprint",
    "retrieval_method",
    "context_package_fingerprint",
)

# Validity count metrics where zero -> positive is a hard regression.
_VALIDITY_COUNTS = (
    "invalid_order_count",
    "universe_violation_count",
    "no_price_count",
    "calendar_gate_count",
    "unavailable_info_session_count",
)

ARMS = ("A", "B", "C", "D")
WINDOWS = ("diagnostic", "heldout")
COMPARISONS = ("A_vs_D", "A_vs_C", "C_vs_D", "B_vs_C")


def check_window_order(diagnostic_end: str, heldout_start: str) -> None:
    """Refuse unless the held-out window starts strictly after diagnosis."""
    if not isinstance(diagnostic_end, str) or not diagnostic_end:
        raise TypeError("diagnostic_end must be a non-empty string")
    if not isinstance(heldout_start, str) or not heldout_start:
        raise TypeError("heldout_start must be a non-empty string")
    if not heldout_start > diagnostic_end:
        raise ValueError(
            "held-out window must start strictly after the diagnostic "
            f"window ends ({diagnostic_end!r} vs {heldout_start!r}): "
            "temporal separation is what keeps generalisation evidence "
            "independent"
        )


def _checked_entries(entries: Any) -> Tuple[Dict[str, Any], ...]:
    if isinstance(entries, str) or not isinstance(entries, (tuple, list)):
        raise TypeError("entries must be a tuple/list of mappings")
    entries = tuple(entries)
    if not entries:
        raise ValueError("entries must be non-empty: empty context is C0")
    cleaned = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise TypeError("context entries must be mappings")
        for key in _REQUIRED_ENTRY_KEYS:
            value = entry.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"context entry lacks {key!r}: refusing malformed "
                    "knowledge"
                )
        for key in _FORBIDDEN_TEMPORARY_KEYS:
            if key in entry:
                raise ValueError(
                    f"temporary entry must not carry store lineage "
                    f"{key!r}: refusing persistent-memory masquerade"
                )
        for key, value in dict(entry).items():
            if isinstance(value, str) and value.startswith("mem-"):
                raise ValueError(
                    "temporary entry must not carry mem-* store "
                    "identifiers: refusing persistent-memory masquerade"
                )
        cleaned.append(dict(entry))
    return tuple(cleaned)


def build_temporary_payload(entries: Any) -> Dict[str, Any]:
    """Build an explicitly provisional temporary-context payload.

    Pure function of the supplied entries. Creates no ``MemoryStore``,
    no admission verdict, and no ``mem-*`` identifiers; the payload
    self-identifies as ``provisional`` with ``temporary-no-store``
    provenance so arm C can never be mistaken for arm D lineage.
    """
    cleaned = _checked_entries(entries)
    return {
        "entries": [dict(entry) for entry in cleaned],
        "provisional": True,
        "provenance": TEMPORARY_PROVENANCE,
    }


def temporary_payload_fingerprint(payload: Mapping[str, Any]) -> str:
    """Deterministic fingerprint of a temporary payload."""
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    return fingerprint_of_dict(dict(payload))


def apply_temporary(agent: Any, payload: Mapping[str, Any]) -> Any:
    """Deliver a temporary payload to an isolated agent copy.

    Validates the provisional marker and tag, deep-copies the agent,
    invokes ``adapt()`` exactly once on the copy, and returns it. The
    original agent is never mutated and nothing persists beyond the
    returned copy. This is the only ``adapt()`` call in this module.
    """
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    if payload.get("provisional") is not True:
        raise ValueError(
            "temporary delivery requires provisional=True: refusing "
            "non-provisional payloads on the temporary path"
        )
    if payload.get("provenance") != TEMPORARY_PROVENANCE:
        raise ValueError(
            f"temporary delivery requires provenance "
            f"{TEMPORARY_PROVENANCE!r}: refusing foreign payloads"
        )
    cleaned = _checked_entries(payload.get("entries", ()))
    identity = getattr(agent, "identity", None)
    if not isinstance(identity, AgentIdentity):
        raise TypeError("agent must expose an AgentIdentity")
    if not callable(getattr(agent, "adapt", None)):
        raise TypeError("agent must expose a callable adapt()")
    if not callable(getattr(agent, "reset", None)):
        raise TypeError("agent must expose a callable reset()")
    isolated = copy.deepcopy(agent)
    # Deep-thaw (mirrors store-bound delivery): entries derived from
    # frozen package knowledge may carry immutable proxies that policy
    # snapshotting cannot traverse. Values are preserved; only ordinary
    # containers reach the agent's mutable policy state.
    delivery = dict(payload)
    delivery["entries"] = [thaw(dict(entry)) for entry in cleaned]
    isolated.adapt(delivery)
    return isolated


def lock_c1(store: Any, package: Any) -> Dict[str, Any]:
    """Record the locked C1 lineage (pure; no mutation, no time)."""
    store_fp = getattr(store, "fingerprint", None)
    package_fp = getattr(package, "fingerprint", None)
    if not callable(store_fp) or not callable(package_fp):
        raise TypeError("lock_c1 requires a MemoryStore and ContextPackage")
    store_fingerprint = store.fingerprint()
    package_fingerprint = package.fingerprint()
    if not store_fingerprint or not package_fingerprint:
        raise ValueError("cannot lock empty fingerprints")
    retrieved = getattr(package, "retrieved_ids", ())
    return {
        "store_fingerprint_at_lock": store_fingerprint,
        "package_fingerprint_at_lock": package_fingerprint,
        "retrieved_ids_at_lock": [str(item) for item in tuple(retrieved)],
    }


def attest_leakage(
    *,
    diagnostic_end: str,
    heldout_start: str,
    lock: Mapping[str, Any],
) -> Dict[str, Any]:
    """Attest temporal separation and pre-held-out C1 locking."""
    check_window_order(diagnostic_end, heldout_start)
    if not isinstance(lock, Mapping):
        raise TypeError("lock must be a mapping")
    store_fp = lock.get("store_fingerprint_at_lock", "")
    package_fp = lock.get("package_fingerprint_at_lock", "")
    if not isinstance(store_fp, str) or not store_fp:
        raise ValueError("lock carries no store fingerprint: refusing")
    if not isinstance(package_fp, str) or not package_fp:
        raise ValueError("lock carries no package fingerprint: refusing")
    return {
        "diagnostic_end": diagnostic_end,
        "heldout_start": heldout_start,
        "store_fingerprint_at_lock": store_fp,
        "package_fingerprint_at_lock": package_fp,
        "retrieved_ids_at_lock": list(
            lock.get("retrieved_ids_at_lock", ())
        ),
        "temporal_order_ok": True,
        "c1_locked_before_heldout": True,
    }


def collect_metric_map(source: Any) -> Dict[str, Optional[float]]:
    """Collect ``{metric_name: value}`` preserving ``None`` (undefined).

    Accepts a ``BaselineResult`` (reads ``.metrics`` entries with
    ``.name``/``.value``) or a plain mapping. Never converts ``None``
    to zero.
    """
    if isinstance(source, Mapping):
        result: Dict[str, Optional[float]] = {}
        for key, value in source.items():
            if not isinstance(key, str) or not key:
                raise ValueError("metric names must be non-empty strings")
            if value is not None and not isinstance(value, (int, float)):
                raise TypeError(
                    f"metric {key!r} must be a number or None"
                )
            result[key] = None if value is None else float(value)
        return result
    metrics = getattr(source, "metrics", None)
    if metrics is None:
        raise TypeError(
            "source must be a BaselineResult or a metric mapping"
        )
    collected: Dict[str, Optional[float]] = {}
    for metric in metrics:
        name = getattr(metric, "name", None)
        if not isinstance(name, str) or not name:
            raise ValueError("metric entries must carry non-empty names")
        value = getattr(metric, "value", None)
        if value is not None and not isinstance(value, (int, float)):
            raise TypeError(f"metric {name!r} must be a number or None")
        collected[name] = None if value is None else float(value)
    return collected


def paired_delta(
    map_a: Mapping[str, Optional[float]],
    map_b: Mapping[str, Optional[float]],
) -> Dict[str, Optional[float]]:
    """Matched ``B - A`` deltas; ``None`` when either side is undefined."""
    if not isinstance(map_a, Mapping) or not isinstance(map_b, Mapping):
        raise TypeError("paired_delta requires two metric mappings")
    names = sorted(set(map_a) | set(map_b))
    deltas: Dict[str, Optional[float]] = {}
    for name in names:
        first = map_a.get(name)
        second = map_b.get(name)
        if first is None or second is None:
            deltas[name] = None
        else:
            deltas[name] = float(second) - float(first)
    return deltas


def check_guards(
    map_c0: Mapping[str, Optional[float]],
    map_ctx: Mapping[str, Optional[float]],
) -> Dict[str, Any]:
    """Descriptive regression guards (C0 vs a context arm, same window).

    Flags only; no thresholds invented, no success adjudicated:

    * ``validity_regression``: any validity count zero in C0 and
      positive under context.
    * ``inactivity_collapse``: context arm fully inactive while C0 was
      active.
    * ``mechanism_opposite``: turnover strictly increases under a
      turnover-decrease corrective principle.
    """
    if not isinstance(map_c0, Mapping) or not isinstance(map_ctx, Mapping):
        raise TypeError("check_guards requires two metric mappings")
    validity_hits = sorted(
        name
        for name in _VALIDITY_COUNTS
        if (map_c0.get(name) == 0.0 or map_c0.get(name) == 0)
        and isinstance(map_ctx.get(name), (int, float))
        and float(map_ctx.get(name)) > 0
    )
    base_inactivity = map_c0.get("inactivity_rate")
    ctx_inactivity = map_ctx.get("inactivity_rate")
    inactivity_collapse = (
        isinstance(base_inactivity, (int, float))
        and isinstance(ctx_inactivity, (int, float))
        and float(ctx_inactivity) == 1.0
        and float(base_inactivity) < 1.0
    )
    base_turnover = map_c0.get("turnover")
    ctx_turnover = map_ctx.get("turnover")
    mechanism_opposite = (
        isinstance(base_turnover, (int, float))
        and isinstance(ctx_turnover, (int, float))
        and float(ctx_turnover) > float(base_turnover)
    )
    return {
        "validity_regression": bool(validity_hits),
        "validity_hits": validity_hits,
        "inactivity_collapse": bool(inactivity_collapse),
        "mechanism_opposite": bool(mechanism_opposite),
        "any_guard": bool(
            validity_hits or inactivity_collapse or mechanism_opposite
        ),
    }


def compare_arms(
    metrics_by_arm: Mapping[str, Mapping[str, Optional[float]]],
) -> Dict[str, Dict[str, Optional[float]]]:
    """Matched deltas for the four required comparisons (one window)."""
    if not isinstance(metrics_by_arm, Mapping):
        raise TypeError("metrics_by_arm must be a mapping")
    for arm in ARMS:
        if arm not in metrics_by_arm:
            raise ValueError(f"metrics_by_arm missing arm {arm!r}")
        if not isinstance(metrics_by_arm[arm], Mapping):
            raise TypeError(f"arm {arm!r} metrics must be a mapping")
    return {
        "A_vs_D": paired_delta(metrics_by_arm["A"], metrics_by_arm["D"]),
        "A_vs_C": paired_delta(metrics_by_arm["A"], metrics_by_arm["C"]),
        "C_vs_D": paired_delta(metrics_by_arm["C"], metrics_by_arm["D"]),
        "B_vs_C": paired_delta(metrics_by_arm["B"], metrics_by_arm["C"]),
    }


def execution_id(
    experiment_id: str, role: str, instance: str
) -> str:
    """Deterministic execution identity (no clock, UUID, or PID)."""
    for name, value in (
        ("experiment_id", experiment_id),
        ("role", role),
        ("instance", instance),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
    return fingerprint_of_dict(
        {
            "method": EXECUTION_METHOD,
            "version": EXECUTION_VERSION,
            "experiment_id": experiment_id,
            "role": role,
            "instance": instance,
        }
    )


def e4e_result_path(repo_root: str, experiment_id: str, exec_id: str) -> str:
    """Deterministic artefact path under ``results/e4/`` only."""
    if not isinstance(repo_root, str) or not repo_root.strip():
        raise ValueError("repo_root must be a non-empty string")
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise ValueError("experiment_id must be a non-empty string")
    if not isinstance(exec_id, str) or not exec_id.strip():
        raise ValueError("execution id must be a non-empty string")
    return (
        f"{repo_root.rstrip('/')}/results/e4/"
        f"{experiment_id}/{exec_id}.json"
    )


@dataclass(frozen=True)
class E4EResult:
    """Fingerprinted record of one E4-E four-arm comparison."""

    experiment_id: str
    execution_role: str
    execution_instance: str
    protocol_fingerprint: str
    base_manifest_fingerprint: str
    supplement_fingerprint: str
    amendment_fingerprint: str
    effective_manifest_fingerprint: str
    diagnostic_start: str
    diagnostic_end: str
    heldout_start: str
    heldout_end: str
    diagnostic_env_fingerprint: str
    heldout_env_fingerprint: str
    agent_id: str
    agent_version: str
    arms: Mapping[str, Any]
    lineage: Mapping[str, Any]
    leakage: Mapping[str, Any]
    method: str = EXPERIMENT_METHOD
    method_version: str = EXPERIMENT_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "experiment_id",
            "execution_role",
            "execution_instance",
            "protocol_fingerprint",
            "base_manifest_fingerprint",
            "supplement_fingerprint",
            "amendment_fingerprint",
            "effective_manifest_fingerprint",
            "diagnostic_start",
            "diagnostic_end",
            "heldout_start",
            "heldout_end",
            "diagnostic_env_fingerprint",
            "heldout_env_fingerprint",
            "agent_id",
            "agent_version",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        for field_name in ("arms", "lineage", "leakage"):
            if not isinstance(getattr(self, field_name), Mapping):
                raise TypeError(f"{field_name} must be a mapping")
        for field_name in ("method", "method_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        check_window_order(self.diagnostic_end, self.heldout_start)
        unknown_arms = set(self.arms) - set(ARMS)
        if unknown_arms:
            raise ValueError(f"unknown arms: {sorted(unknown_arms)}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "execution_role": self.execution_role,
            "execution_instance": self.execution_instance,
            "execution_id": execution_id(
                self.experiment_id,
                self.execution_role,
                self.execution_instance,
            ),
            "protocol_fingerprint": self.protocol_fingerprint,
            "base_manifest_fingerprint": self.base_manifest_fingerprint,
            "supplement_fingerprint": self.supplement_fingerprint,
            "amendment_fingerprint": self.amendment_fingerprint,
            "effective_manifest_fingerprint": (
                self.effective_manifest_fingerprint
            ),
            "diagnostic_start": self.diagnostic_start,
            "diagnostic_end": self.diagnostic_end,
            "heldout_start": self.heldout_start,
            "heldout_end": self.heldout_end,
            "diagnostic_env_fingerprint": self.diagnostic_env_fingerprint,
            "heldout_env_fingerprint": self.heldout_env_fingerprint,
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "arms": json.loads(json.dumps(dict(self.arms))),
            "lineage": dict(self.lineage),
            "leakage": dict(self.leakage),
            "method": self.method,
            "version": self.method_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "E4EResult":
        if not isinstance(payload, Mapping):
            raise TypeError("E4EResult payload must be a mapping")
        known = {
            "experiment_id",
            "execution_role",
            "execution_instance",
            "execution_id",
            "protocol_fingerprint",
            "base_manifest_fingerprint",
            "supplement_fingerprint",
            "amendment_fingerprint",
            "effective_manifest_fingerprint",
            "diagnostic_start",
            "diagnostic_end",
            "heldout_start",
            "heldout_end",
            "diagnostic_env_fingerprint",
            "heldout_env_fingerprint",
            "agent_id",
            "agent_version",
            "arms",
            "lineage",
            "leakage",
            "method",
            "version",
        }
        extra = set(payload) - known
        if extra:
            raise ValueError(
                f"unknown E4EResult fields: {sorted(extra)}"
            )
        try:
            return cls(
                experiment_id=payload["experiment_id"],
                execution_role=payload["execution_role"],
                execution_instance=payload["execution_instance"],
                protocol_fingerprint=payload["protocol_fingerprint"],
                base_manifest_fingerprint=payload[
                    "base_manifest_fingerprint"
                ],
                supplement_fingerprint=payload["supplement_fingerprint"],
                amendment_fingerprint=payload["amendment_fingerprint"],
                effective_manifest_fingerprint=payload[
                    "effective_manifest_fingerprint"
                ],
                diagnostic_start=payload["diagnostic_start"],
                diagnostic_end=payload["diagnostic_end"],
                heldout_start=payload["heldout_start"],
                heldout_end=payload["heldout_end"],
                diagnostic_env_fingerprint=payload[
                    "diagnostic_env_fingerprint"
                ],
                heldout_env_fingerprint=payload["heldout_env_fingerprint"],
                agent_id=payload["agent_id"],
                agent_version=payload["agent_version"],
                arms=dict(payload["arms"]),
                lineage=dict(payload["lineage"]),
                leakage=dict(payload["leakage"]),
                method=payload.get("method", EXPERIMENT_METHOD),
                method_version=payload.get("version", EXPERIMENT_VERSION),
            )
        except KeyError as exc:
            raise ValueError(
                f"E4EResult payload missing {exc}"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


def save_e4e_result(
    result: E4EResult, repo_root: str
) -> str:
    """Persist one result under ``results/e4/``; refuse overwrite.

    Returns the artefact path. Any path outside ``results/e4/`` is
    refused, so E3 artefacts can never be overwritten from here.
    """
    if not isinstance(result, E4EResult):
        raise TypeError("result must be an E4EResult")
    exec_id = execution_id(
        result.experiment_id,
        result.execution_role,
        result.execution_instance,
    )
    path = e4e_result_path(repo_root, result.experiment_id, exec_id)
    if "/results/e4/" not in path.replace("\\", "/"):
        raise ValueError(
            f"refusing artefact path outside results/e4/: {path!r}"
        )
    if os.path.exists(path):
        raise ValueError(
            f"refusing to overwrite existing artefact: {path!r}"
        )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                result.to_dict(), sort_keys=True, separators=(",", ":")
            )
        )
    return path


def run_e4e(
    *,
    experiment_id: str,
    execution_role: str = "SYSTEM_VALIDATION",
    execution_instance: str = "001",
    proposal: Any,
    result: Any,
    report: Any,
    analysis: Any,
    diagnostic_config: Any,
    heldout_start: str = HELDOUT_START,
    heldout_end: str = HELDOUT_END,
    heldout_env_fingerprint: str = HELDOUT_ENV_FINGERPRINT,
    protocol_fingerprint: str,
    effective_manifest_fingerprint: str,
    base_dir: str = ".",
) -> Tuple[E4EResult, Dict[str, Any]]:
    """Execute one E4-E four-arm campaign (heavy: real environment runs).

    ``proposal``/``result``/``report``/``analysis`` are already-validated
    E2-F artefacts from the diagnostic window only. The pipeline
    extracts K1, admits it, locks C1, attests the leakage lock, then
    evaluates arms A/B/C/D on both windows via frozen
    ``run_baseline``. Fresh agent instances per arm per window; arm C
    uses the provisional path; arm D uses store-bound delivery.
    """
    from evaluation.baseline.config import BaselineConfig
    from evaluation.baseline.runner import run_baseline
    from evaluation.context.assembly import assemble, deliver
    from evaluation.context.extraction import extract_candidate
    from evaluation.context.gate import AdmissionDecision, adjudicate
    from evaluation.context.memory import MemoryStore
    from evaluation.context.retrieval import retrieve
    from evaluation.diagnostics.repair.application import fingerprint_agent

    if not isinstance(diagnostic_config, BaselineConfig):
        raise TypeError("diagnostic_config must be a BaselineConfig")
    check_window_order(diagnostic_config.end_date, heldout_start)
    if heldout_end < heldout_start:
        raise ValueError("held-out window end must not precede its start")

    candidate = extract_candidate(
        proposal=proposal, result=result, report=report, analysis=analysis
    )
    store_c0 = MemoryStore(store_id=f"e4e-{experiment_id}")
    transitioned, verdict = adjudicate(
        candidate=candidate,
        result=result,
        report=report,
        analysis=analysis,
        store=store_c0,
        proposal=proposal,
    )
    if verdict.decision is not AdmissionDecision.ADMITTED:
        raise ValueError(
            "K1 was not admitted "
            f"(decision={verdict.decision.value}): refusing to run "
            "arms on unvalidated knowledge"
        )
    store_c1 = store_c0.admit(transitioned, verdict)

    probe = ContextualThresholdBenchmark()
    if not isinstance(probe.identity, AgentIdentity):
        raise TypeError("agent factory product lacks an AgentIdentity")
    agent_id_str = str(probe.identity)
    contexts, record = retrieve(store_c1, agent_id=agent_id_str)
    package = assemble(
        contexts, record, store_c1.fingerprint(), probe.identity
    )
    lock = lock_c1(store_c1, package)
    leakage = attest_leakage(
        diagnostic_end=diagnostic_config.end_date,
        heldout_start=heldout_start,
        lock=lock,
    )

    heldout_config = BaselineConfig(
        evaluation_id=f"{diagnostic_config.evaluation_id}-heldout",
        start_date=heldout_start,
        end_date=heldout_end,
        universe=dict(diagnostic_config.universe),
        transaction_cost_bps=diagnostic_config.transaction_cost_bps,
        initial_cash=diagnostic_config.initial_cash,
        strict_pit=diagnostic_config.strict_pit,
        vintage_policy=diagnostic_config.vintage_policy,
        budget=diagnostic_config.budget,
        seed=diagnostic_config.seed,
    )
    window_configs = {
        "diagnostic": diagnostic_config,
        "heldout": heldout_config,
    }

    temporary_entries = [dict(entry) for entry in package.knowledge]
    temporary_payload = build_temporary_payload(temporary_entries)

    arms_record: Dict[str, Any] = {}
    lineage = {
        "proposal_fingerprint": proposal.fingerprint(),
        "repair_result_fingerprint": result.fingerprint(),
        "validation_fingerprint": report.fingerprint(),
        "analysis_fingerprint": analysis.fingerprint(),
        "candidate_fingerprint": candidate.fingerprint(),
        "verdict_fingerprint": verdict.fingerprint(),
        "store_c0_fingerprint": store_c0.fingerprint(),
        "store_c1_fingerprint": store_c1.fingerprint(),
        "retrieval_fingerprint": record.fingerprint(),
        "package_fingerprint": package.fingerprint(),
        "temporary_payload_fingerprint": temporary_payload_fingerprint(
            temporary_payload
        ),
    }
    for arm in ARMS:
        arms_record[arm] = {}
        for window, config in window_configs.items():
            if arm in ("A", "B"):
                agent = ContextualThresholdBenchmark()
                before = fingerprint_agent(agent, agent.identity)
                outcome = run_baseline(agent, config, base_dir=base_dir)
                after = fingerprint_agent(agent, agent.identity)
                context_desc: Dict[str, Any] = (
                    {"context": "C0", "corrective_context_delivered": False}
                    if arm == "A"
                    else {
                        "context": "diagnosis-provenance-only",
                        "corrective_context_delivered": False,
                    }
                )
                delivery_fp = ""
            elif arm == "C":
                agent = ContextualThresholdBenchmark()
                before = fingerprint_agent(agent, agent.identity)
                adapted = apply_temporary(agent, temporary_payload)
                outcome = run_baseline(adapted, config, base_dir=base_dir)
                after = fingerprint_agent(adapted, adapted.identity)
                context_desc = {
                    "context": "temporary",
                    "provisional": True,
                    "provenance": TEMPORARY_PROVENANCE,
                    "persistence": "none",
                    "payload_fingerprint": (
                        temporary_payload_fingerprint(temporary_payload)
                    ),
                }
                delivery_fp = ""
            else:
                agent = ContextualThresholdBenchmark()
                before = fingerprint_agent(agent, agent.identity)
                adapted, delivery = deliver(agent, package, store_c1)
                outcome = run_baseline(adapted, config, base_dir=base_dir)
                after = fingerprint_agent(adapted, adapted.identity)
                context_desc = {
                    "context": "C1",
                    "persistence": "validated-memory",
                    "package_fingerprint": package.fingerprint(),
                    "delivery_fingerprint": delivery.fingerprint()
                    if hasattr(delivery, "fingerprint")
                    else "",
                }
                delivery_fp = (
                    delivery.fingerprint()
                    if hasattr(delivery, "fingerprint")
                    else ""
                )
                lineage[f"delivery_fingerprint_{window}"] = delivery_fp
            arms_record[arm][window] = {
                "evaluation_id": outcome.evaluation_id,
                "evaluation_fingerprint": outcome.fingerprint(),
                "agent_fingerprint_before": before,
                "agent_fingerprint_after": after,
                "metrics": collect_metric_map(outcome),
                "context": context_desc,
            }

    comparisons = {
        window: compare_arms(
            {arm: arms_record[arm][window]["metrics"] for arm in ARMS}
        )
        for window in window_configs
    }
    guards = {
        window: {
            "C_vs_C0": check_guards(
                arms_record["A"][window]["metrics"],
                arms_record["C"][window]["metrics"],
            ),
            "D_vs_C0": check_guards(
                arms_record["A"][window]["metrics"],
                arms_record["D"][window]["metrics"],
            ),
        }
        for window in window_configs
    }
    arms_record["_comparisons"] = comparisons
    arms_record["_guards"] = guards

    result_obj = E4EResult(
        experiment_id=experiment_id,
        execution_role=execution_role,
        execution_instance=execution_instance,
        protocol_fingerprint=protocol_fingerprint,
        base_manifest_fingerprint=BASE_MANIFEST_FINGERPRINT,
        supplement_fingerprint=SUPPLEMENT_FINGERPRINT,
        amendment_fingerprint=SUPPLEMENT_FINGERPRINT,
        effective_manifest_fingerprint=effective_manifest_fingerprint,
        diagnostic_start=diagnostic_config.start_date,
        diagnostic_end=diagnostic_config.end_date,
        heldout_start=heldout_start,
        heldout_end=heldout_end,
        diagnostic_env_fingerprint=DIAGNOSTIC_ENV_FINGERPRINT,
        heldout_env_fingerprint=heldout_env_fingerprint,
        agent_id=probe.identity.agent_id,
        agent_version=probe.identity.version,
        arms=arms_record,
        lineage=lineage,
        leakage=leakage,
    )
    return result_obj, {
        "store_c1": store_c1,
        "package": package,
        "retrieval_record": record,
        "lock": lock,
    }
