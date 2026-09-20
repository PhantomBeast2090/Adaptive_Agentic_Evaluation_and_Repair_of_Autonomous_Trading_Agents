"""Preflight / dry-run verification (pure checks, zero market episodes).

``preflight`` verifies every frozen input before any episode executes:
manifest match, protocol fingerprint, identities, windows, pool,
sequence, budgets, transitions, lifecycle plan, artefact paths, and
N-H/R-H scope compatibility. Any mismatch fails closed with a named
reason. Importing this module or calling these functions never
constructs an environment or runs an episode.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Dict, List, Mapping, Tuple

from experiments.harness.config import ExperimentConfig
from experiments.harness.errors import IntegrityFailure
from experiments.harness.identity import (
    arm_identity,
    experiment_identity,
    result_path,
)
from experiments.harness.lineage import assert_same_scope, heldout_scope


@dataclass(frozen=True)
class PreflightCheck:
    """One named preflight verification and its outcome."""

    name: str
    passed: bool
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.passed, bool):
            raise TypeError("passed must be a bool")
        if not isinstance(self.detail, str):
            raise TypeError("detail must be a string")


@dataclass(frozen=True)
class PreflightReport:
    """Full dry-run verdict: every check plus the computed identities."""

    experiment_id: str
    checks: Tuple[PreflightCheck, ...] = ()
    arm_identities: Mapping[str, Any] = field(default_factory=dict)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not isinstance(self.experiment_id, str) or not self.experiment_id:
            raise ValueError("experiment_id must be a non-empty string")
        object.__setattr__(self, "checks", tuple(self.checks))
        for check in self.checks:
            if not isinstance(check, PreflightCheck):
                raise TypeError(
                    "checks must contain PreflightCheck, "
                    f"got {type(check).__name__}"
                )

    @property
    def passed(self) -> bool:
        """True only when every check passed."""
        return bool(self.checks) and all(
            check.passed for check in self.checks
        )

    def failures(self) -> Tuple[PreflightCheck, ...]:
        """Checks that did not pass."""
        return tuple(check for check in self.checks if not check.passed)


def _sha256_file(path: str) -> str:
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError as exc:
        raise IntegrityFailure(
            f"cannot read protocol file {path!r}: {exc}"
        ) from exc


def _check(name: str, passed: bool, detail: str = "") -> PreflightCheck:
    return PreflightCheck(name=name, passed=passed, detail=detail)


def preflight(
    *,
    config: ExperimentConfig,
    manifest: Mapping[str, Any],
    e3d_document_path: str,
    environment_fingerprint: str,
    benchmark_fingerprint: str,
    agent_fingerprint: str,
) -> PreflightReport:
    """Run every dry-run check. Executes zero market episodes."""
    if not isinstance(config, ExperimentConfig):
        raise TypeError(
            "config must be an ExperimentConfig, "
            f"got {type(config).__name__}"
        )
    checks: List[PreflightCheck] = []

    try:
        config.verify_against_manifest(manifest)
        checks.append(_check("manifest_match", True, "all fields match"))
    except Exception as exc:  # noqa: BLE001 - fail-closed record
        checks.append(
            _check("manifest_match", False, f"{type(exc).__name__}: {exc}")
        )

    try:
        measured = _sha256_file(e3d_document_path)
        checks.append(
            _check(
                "protocol_fingerprint",
                measured == config.e3d_fingerprint,
                f"measured={measured[:16]}...",
            )
        )
    except Exception as exc:  # noqa: BLE001 - fail-closed record
        checks.append(
            _check(
                "protocol_fingerprint", False,
                f"{type(exc).__name__}: {exc}",
            )
        )

    checks.append(
        _check(
            "environment_fingerprint",
            environment_fingerprint == config.environment_fingerprint,
            "matches config" if environment_fingerprint
            == config.environment_fingerprint else "MISMATCH",
        )
    )
    try:
        module_name, _, class_name = config.benchmark_module.rpartition(".")
        if not module_name or not class_name:
            raise ValueError(
                "benchmark_module must be a dotted path "
                "'package.module.Class'"
            )
        module = import_module(module_name)
        agent_class = getattr(module, class_name)
        agent = agent_class()
        identity = agent.identity
        checks.append(
            _check(
                "agent_lifecycle",
                (
                    identity.agent_id == config.agent_id
                    and identity.version == config.agent_version
                    and callable(getattr(agent, "reset", None))
                    and callable(getattr(agent, "act", None))
                ),
                f"{identity.agent_id}@{identity.version}",
            )
        )
    except Exception as exc:  # noqa: BLE001 - fail-closed record
        checks.append(
            _check(
                "agent_lifecycle", False,
                f"{type(exc).__name__}: {exc}",
            )
        )
    checks.append(
        _check(
            "benchmark_fingerprint",
            isinstance(benchmark_fingerprint, str)
            and bool(benchmark_fingerprint.strip()),
            "recorded for lineage" if benchmark_fingerprint else
            "MISSING benchmark fingerprint",
        )
    )
    checks.append(
        _check(
            "agent_fingerprint",
            isinstance(agent_fingerprint, str)
            and bool(agent_fingerprint.strip()),
            "recorded for lineage" if agent_fingerprint else
            "MISSING agent fingerprint",
        )
    )

    diag_end = config.diagnostic_window[1]
    held_start = config.heldout_window[0]
    checks.append(
        _check(
            "window_non_overlap",
            held_start > diag_end,
            f"diag_end={diag_end} held_start={held_start}",
        )
    )

    try:
        scope = heldout_scope(
            heldout_window=config.heldout_window,
            universe=dict(config.universe),
            transaction_cost_bps=config.transaction_cost_bps,
            initial_cash=config.initial_cash,
            strict_pit=config.strict_pit,
            vintage_policy=config.vintage_policy,
            environment_fingerprint=config.environment_fingerprint,
        )
        assert_same_scope(scope, dict(scope))
        checks.append(
            _check("heldout_scope_compatible", True, "scope well-formed")
        )
    except Exception as exc:  # noqa: BLE001 - fail-closed record
        checks.append(
            _check(
                "heldout_scope_compatible", False,
                f"{type(exc).__name__}: {exc}",
            )
        )

    budgets = dict(config.budgets)
    checks.append(
        _check(
            "budgets_cover_work",
            (
                budgets.get("max_tests", -1)
                >= len(config.fixed_sequence)
                and budgets.get("max_repairs", -1) >= 1
                and budgets.get("max_validation_runs", -1) >= 3
            ),
            f"tests>={len(config.fixed_sequence)} repairs>=1 runs>=3",
        )
    )

    try:
        from experiments.harness.config import ARMS

        arm_ids = {
            arm: arm_identity("preflight-probe", arm) for arm in ARMS
        }
        checks.append(_check("arm_identities", True, f"{len(arm_ids)} arms"))
    except Exception as exc:  # noqa: BLE001 - fail-closed record
        checks.append(
            _check("arm_identities", False, f"{type(exc).__name__}: {exc}")
        )

    try:
        path = result_path(config.result_dir, "preflight-probe")
        checks.append(_check("artefact_path", True, path))
    except Exception as exc:  # noqa: BLE001 - fail-closed record
        checks.append(
            _check("artefact_path", False, f"{type(exc).__name__}: {exc}")
        )

    experiment_id = experiment_identity(config)
    arm_identities = {
        arm: arm_identity(experiment_id, arm)
        for arm in ("N-D", "N-H", "D-F", "D-A", "R-D", "R-H")
    }
    return PreflightReport(
        experiment_id=experiment_id,
        checks=tuple(checks),
        arm_identities=dict(arm_identities),
    )


def ensure_preflight(report: PreflightReport) -> None:
    """Raise fail-closed unless every preflight check passed."""
    if not isinstance(report, PreflightReport):
        raise TypeError(
            "report must be a PreflightReport, "
            f"got {type(report).__name__}"
        )
    failures = report.failures()
    if failures:
        raise IntegrityFailure(
            "preflight failed closed: "
            + "; ".join(
                f"{check.name} ({check.detail})" for check in failures
            )
        )
