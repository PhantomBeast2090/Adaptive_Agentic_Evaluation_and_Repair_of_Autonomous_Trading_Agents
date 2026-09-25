"""E4-F accumulation execution driver (E4-owned orchestration).

Implements the approved R/P/V/A branch separation on top of frozen
primitives. Heavy phase functions call frozen code only
(``run_baseline``, harness ``phase_a/phase_b``, ``run_repair``,
E4-A–D pipeline); every scientific invariant lives in pure helpers
tested without market episodes:

* R branch objects never meet P branch objects (signature separation
  + ``assert_branch_purity`` on fingerprints).
* K2 evidence comes from the R branch exclusively.
* P observations are retention reads; they cannot enter K2 provenance.
* Terminal arms require both cycle locks (``require_terminal_lock``).
* No global mutable state: all state is threaded through returns.

The driver records evidence only and makes no success, superiority,
learning, or self-repair claims (no claim language in decision paths).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from evaluation.contracts.fingerprints import fingerprint_of_dict

DRIVER_METHOD = "e4f-driver"
DRIVER_VERSION = "v1"

E4F_RESULT_DIR = "results/e4f"

BRANCHES = ("R", "P", "V", "A")
TERMINAL_ARMS = ("C0", "T1", "C1", "T12", "C1+C2")


@dataclass(frozen=True)
class DriverPlan:
    """Validated execution plan for one E4-F campaign (pure)."""

    experiment_id: str
    execution_role: str
    execution_instance: str
    protocol_fingerprint: str
    supplement_fingerprint: str
    effective_manifest_fingerprint: str
    w1_start: str
    w1_end: str
    w2_start: str
    w2_end: str
    w3_start: str
    w3_end: str
    w1_env_fingerprint: str
    w2_env_fingerprint: str
    w3_env_fingerprint: str
    method: str = DRIVER_METHOD
    method_version: str = DRIVER_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "experiment_id",
            "execution_role",
            "execution_instance",
            "protocol_fingerprint",
            "supplement_fingerprint",
            "effective_manifest_fingerprint",
            "w1_start",
            "w1_end",
            "w2_start",
            "w2_end",
            "w3_start",
            "w3_end",
            "w1_env_fingerprint",
            "w2_env_fingerprint",
            "w3_env_fingerprint",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )
        for first_end, second_start, label in (
            (self.w1_end, self.w2_start, "W1->W2"),
            (self.w2_end, self.w3_start, "W2->W3"),
        ):
            if not second_start > first_end:
                raise ValueError(
                    f"windows not strictly ordered at {label}: refusing"
                )
        for field_name in ("method", "method_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} must be a non-empty string"
                )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "execution_role": self.execution_role,
            "execution_instance": self.execution_instance,
            "protocol_fingerprint": self.protocol_fingerprint,
            "supplement_fingerprint": self.supplement_fingerprint,
            "effective_manifest_fingerprint": (
                self.effective_manifest_fingerprint
            ),
            "w1_start": self.w1_start,
            "w1_end": self.w1_end,
            "w2_start": self.w2_start,
            "w2_end": self.w2_end,
            "w3_start": self.w3_start,
            "w3_end": self.w3_end,
            "w1_env_fingerprint": self.w1_env_fingerprint,
            "w2_env_fingerprint": self.w2_env_fingerprint,
            "w3_env_fingerprint": self.w3_env_fingerprint,
            "method": self.method,
            "version": self.method_version,
        }

    @classmethod
    def from_supplement(
        cls,
        *,
        supplement_record: Mapping[str, Any],
        experiment_id: str,
        execution_role: str,
        execution_instance: str,
        protocol_fingerprint: str,
        effective_manifest_fingerprint: str,
    ) -> "DriverPlan":
        """Build a plan from a verified supplement record (pure)."""
        if not isinstance(supplement_record, Mapping):
            raise TypeError("supplement_record must be a mapping")
        windows = supplement_record.get("windows")
        if not isinstance(windows, Mapping):
            raise TypeError("supplement_record windows must be a mapping")
        try:
            w1 = windows["w1_diagnostic"]
            w2 = windows["w2_diagnostic"]
            w3 = windows["w3_heldout"]
            return cls(
                experiment_id=experiment_id,
                execution_role=execution_role,
                execution_instance=execution_instance,
                protocol_fingerprint=protocol_fingerprint,
                supplement_fingerprint=fingerprint_of_dict(
                    dict(supplement_record)
                ),
                effective_manifest_fingerprint=(
                    effective_manifest_fingerprint
                ),
                w1_start=w1["start"],
                w1_end=w1["end"],
                w2_start=w2["start"],
                w2_end=w2["end"],
                w3_start=w3["start"],
                w3_end=w3["end"],
                w1_env_fingerprint=w1["environment_fingerprint"],
                w2_env_fingerprint=w2["environment_fingerprint"],
                w3_env_fingerprint=w3["environment_fingerprint"],
            )
        except KeyError as exc:
            raise ValueError(
                f"supplement record missing {exc}: refusing"
            ) from exc

    def fingerprint(self) -> str:
        return fingerprint_of_dict(self.to_dict())


def assert_branch_purity(
    *,
    k2_provenance_fps: Mapping[str, str],
    r_branch_fps: Mapping[str, str],
    forbidden_fps: Mapping[str, str],
) -> Dict[str, str]:
    """Prove K2 provenance derives from the R branch exclusively.

    ``k2_provenance_fps`` maps provenance role (evaluation, diagnosis,
    proposal, validation, analysis) to fingerprint. Every value must
    appear among the R-branch fingerprints, and none may appear among
    the forbidden set (P-branch retention reads, Cycle-1 W2-validation
    artefacts, terminal reads). Fail-closed otherwise.
    """
    for name, mapping in (
        ("k2_provenance_fps", k2_provenance_fps),
        ("r_branch_fps", r_branch_fps),
        ("forbidden_fps", forbidden_fps),
    ):
        if not isinstance(mapping, Mapping):
            raise TypeError(f"{name} must be a mapping")
        for key, value in mapping.items():
            if not isinstance(value, str) or not value:
                raise ValueError(
                    f"{name}[{key!r}] must be a non-empty fingerprint"
                )
    r_values = set(r_branch_fps.values())
    forbidden_values = set(forbidden_fps.values())
    for role, fingerprint in k2_provenance_fps.items():
        if fingerprint not in r_values:
            raise ValueError(
                f"K2 provenance {role!r} is not an R-branch artefact: "
                "refusing impure K2 evidence"
            )
        if fingerprint in forbidden_values:
            raise ValueError(
                f"K2 provenance {role!r} collides with a forbidden "
                "branch artefact: refusing"
            )
    return dict(k2_provenance_fps)


def require_terminal_lock(
    *,
    c1_lock: Mapping[str, Any],
    c2_lock: Mapping[str, Any],
    w3_start: str,
    w2_end: str,
) -> Dict[str, Any]:
    """Gate terminal reads on both cycle locks (pure)."""
    for name, lock in (("c1_lock", c1_lock), ("c2_lock", c2_lock)):
        if not isinstance(lock, Mapping):
            raise TypeError(f"{name} must be a mapping")
        for key in ("store_fingerprint_at_lock",
                    "package_fingerprint_at_lock"):
            if not isinstance(lock.get(key), str) or not lock[key]:
                raise ValueError(
                    f"{name} carries no {key!r}: refusing terminal reads"
                )
    if not isinstance(w3_start, str) or not w3_start:
        raise TypeError("w3_start must be a non-empty string")
    if not isinstance(w2_end, str) or not w2_end:
        raise TypeError("w2_end must be a non-empty string")
    if not w3_start > w2_end:
        raise ValueError(
            "terminal window must start strictly after the Cycle-2 "
            "window ends: refusing"
        )
    return {
        "c1_store_fingerprint": c1_lock["store_fingerprint_at_lock"],
        "c2_store_fingerprint": c2_lock["store_fingerprint_at_lock"],
        "w3_start": w3_start,
        "terminal_gate": "locked",
    }


def fresh_delivery_agent() -> Any:
    """One fresh dual-guard delivery agent (no learned context)."""
    from evaluation.context.accumulating_benchmark import (
        AccumulatingThresholdBenchmark,
    )

    agent = AccumulatingThresholdBenchmark()
    if tuple(agent.learned_contexts) != ():
        raise ValueError(
            "fresh delivery agent carries learned context: refusing"
        )
    return agent


def run_p_branch(
    *,
    plan: DriverPlan,
    store_c1: Any,
    package_c1: Any,
    heldout_config: Any,
    base_dir: str = ".",
) -> Dict[str, Any]:
    """P branch: C1 retention read on W2 (heavy: episodes).

    Delivers the locked C1 package to a fresh agent and evaluates it.
    Returns metric and lineage reads ONLY. The returned bundle is
    marked retention-only and must never enter K2 provenance (see
    ``assert_branch_purity`` with this bundle's fingerprints
    forbidden).
    """
    from evaluation.baseline.runner import run_baseline
    from evaluation.context.assembly import deliver
    from evaluation.diagnostics.repair.application import fingerprint_agent

    if not isinstance(plan, DriverPlan):
        raise TypeError("plan must be a DriverPlan")
    agent = fresh_delivery_agent()
    before = fingerprint_agent(agent, agent.identity)
    adapted, delivery = deliver(agent, package_c1, store_c1)
    outcome = run_baseline(adapted, heldout_config, base_dir=base_dir)
    after = fingerprint_agent(adapted, adapted.identity)
    from evaluation.context.experiment import collect_metric_map

    return {
        "branch": "P",
        "retention_only": True,
        "must_not_enter_k2_provenance": True,
        "evaluation_fingerprint": outcome.fingerprint(),
        "agent_fingerprint_before": before,
        "agent_fingerprint_after": after,
        "delivery_fingerprint": (
            delivery.fingerprint()
            if hasattr(delivery, "fingerprint") else ""
        ),
        "metrics": collect_metric_map(outcome),
    }


def run_terminal_arms(
    *,
    plan: DriverPlan,
    store_c1: Any,
    package_c1: Any,
    store_c2: Any,
    package_c2: Any,
    temporary_k1_entries: Any,
    temporary_k2_entries: Any,
    w3_config: Any,
    base_dir: str = ".",
) -> Dict[str, Any]:
    """Terminal arms on W3: C0/T1/C1/T12/C1+C2 (heavy: episodes).

    The C1 arm delivers the locked Cycle-1 package against the locked
    Cycle-1 store; the accumulation arm delivers the Cycle-2 package
    against the Cycle-2 store. Stores are never mutated.
    """
    from evaluation.baseline.runner import run_baseline
    from evaluation.context.assembly import deliver
    from evaluation.context.cycles import (
        apply_dual_temporary,
        build_dual_temporary_payload,
    )
    from evaluation.context.experiment import (
        apply_temporary,
        build_temporary_payload,
        collect_metric_map,
    )
    from evaluation.diagnostics.repair.application import fingerprint_agent

    if not isinstance(plan, DriverPlan):
        raise TypeError("plan must be a DriverPlan")
    arms: Dict[str, Any] = {}

    def _run(agent: Any) -> Any:
        return run_baseline(agent, w3_config, base_dir=base_dir)

    agent_c0 = fresh_delivery_agent()
    before_c0 = fingerprint_agent(agent_c0, agent_c0.identity)
    out_c0 = _run(agent_c0)
    arms["C0"] = {
        "evaluation_fingerprint": out_c0.fingerprint(),
        "agent_fingerprint_before": before_c0,
        "agent_fingerprint_after": fingerprint_agent(
            agent_c0, agent_c0.identity),
        "metrics": collect_metric_map(out_c0),
        "context": {"context": "C0"},
    }

    payload_t1 = build_temporary_payload(temporary_k1_entries)
    adapted_t1 = apply_temporary(fresh_delivery_agent(), payload_t1)
    out_t1 = _run(adapted_t1)
    arms["T1"] = {
        "evaluation_fingerprint": out_t1.fingerprint(),
        "agent_fingerprint_after": fingerprint_agent(
            adapted_t1, adapted_t1.identity),
        "metrics": collect_metric_map(out_t1),
        "context": {"context": "temporary", "persistence": "none"},
    }

    agent_c1 = fresh_delivery_agent()
    adapted_c1, delivery_c1 = deliver(agent_c1, package_c1, store_c1)
    out_c1 = _run(adapted_c1)
    arms["C1"] = {
        "evaluation_fingerprint": out_c1.fingerprint(),
        "agent_fingerprint_after": fingerprint_agent(
            adapted_c1, adapted_c1.identity),
        "metrics": collect_metric_map(out_c1),
        "context": {"context": "C1", "persistence": "validated-memory"},
    }
    _ = delivery_c1

    payload_t12 = build_dual_temporary_payload(
        temporary_k1_entries, temporary_k2_entries
    )
    adapted_t12 = apply_dual_temporary(
        fresh_delivery_agent(), payload_t12
    )
    out_t12 = _run(adapted_t12)
    arms["T12"] = {
        "evaluation_fingerprint": out_t12.fingerprint(),
        "agent_fingerprint_after": fingerprint_agent(
            adapted_t12, adapted_t12.identity),
        "metrics": collect_metric_map(out_t12),
        "context": {"context": "temporary-dual", "persistence": "none"},
    }

    agent_acc = fresh_delivery_agent()
    adapted_acc, delivery_acc = deliver(agent_acc, package_c2, store_c2)
    out_acc = _run(adapted_acc)
    arms["C1+C2"] = {
        "evaluation_fingerprint": out_acc.fingerprint(),
        "agent_fingerprint_after": fingerprint_agent(
            adapted_acc, adapted_acc.identity),
        "metrics": collect_metric_map(out_acc),
        "context": {"context": "C1+C2",
                    "persistence": "validated-memory"},
    }
    _ = delivery_acc
    return arms


__all__ = [
    "BRANCHES",
    "DRIVER_METHOD",
    "DRIVER_VERSION",
    "E4F_RESULT_DIR",
    "TERMINAL_ARMS",
    "DriverPlan",
    "assert_branch_purity",
    "fresh_delivery_agent",
    "require_terminal_lock",
    "run_p_branch",
    "run_terminal_arms",
]
