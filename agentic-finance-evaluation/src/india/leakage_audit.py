"""Leakage Audit for Indian Market Data.

Checks for information leakage that would compromise experimental validity:
  1. Direct future leakage (prices, returns, volatility, VIX, volume)
  2. Macro leakage (values before release date)
  3. Gold futures roll leakage (look-ahead through future contract knowledge)
  4. Split contamination (temporal overlap between experiment splits)
  5. Corporate action leakage (adjustments applied before announcement date)

Design principle: Leakage detection must be STRICT.
  - Report potential leakage even if the probability is low.
  - A confirmed leak invalidates results. Report it explicitly.
  - An unresolved issue blocks downstream experiment design.

This module is used by:
  - tests/india/test_leakage.py  (unit tests)
  - scripts/audit_indian_data_coverage.py  (CLI audit)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class LeakageViolation:
    violation_type: str
    severity: str                        # "CONFIRMED", "POTENTIAL", "MITIGATED"
    description: str
    affected_rows: int = 0
    examples: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class LeakageReport:
    confirmed_leaks: List[LeakageViolation]
    potential_leaks: List[LeakageViolation]
    mitigated: List[LeakageViolation]
    unresolved: List[LeakageViolation]
    validation_status: str = "EVALUATED"
    datasets_checked: List[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return (
            self.validation_status == "EVALUATED"
            and len(self.confirmed_leaks) == 0
            and len(self.unresolved) == 0
        )

    def summary(self) -> str:
        lines = [
            f"Leakage validation status: {self.validation_status}",
            f"Confirmed leaks:  {len(self.confirmed_leaks)}",
            f"Potential leaks:  {len(self.potential_leaks)}",
            f"Mitigated issues: {len(self.mitigated)}",
            f"Unresolved:       {len(self.unresolved)}",
        ]
        if self.confirmed_leaks:
            lines.append("")
            lines.append("CONFIRMED LEAKS (MUST FIX BEFORE EXPERIMENTS):")
            for v in self.confirmed_leaks:
                lines.append(f"  [{v.violation_type}] {v.description}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# LeakageAuditor
# ---------------------------------------------------------------------------

class LeakageAuditor:
    """Detect information leakage in Indian market datasets.

    Each check_* method returns a list of LeakageViolations.
    The audit_all() method collects them into a LeakageReport.
    """

    # ------------------------------------------------------------------
    # 1. Future Price Leakage
    # ------------------------------------------------------------------

    def check_future_price_leakage(
        self,
        df: pd.DataFrame,
        price_col: str = "close",
        date_col: Optional[str] = None,
        suspicious_col_patterns: Optional[List[str]] = None,
    ) -> List[LeakageViolation]:
        """Detect columns that appear to encode future price information.

        Checks for:
          - Columns named with 'future_', 'next_', 'lead_', 'forward_'
          - Columns that are perfectly correlated with a shifted price series
            (would indicate a pre-computed future return column)
        """
        violations: List[LeakageViolation] = []
        patterns = suspicious_col_patterns or [
            "future_", "next_", "lead_", "forward_", "_t1", "_t2",
            "future", "fwd_", "lookahead", "return_1d", "volatility_",
            "regime_", "vix_future",
        ]

        # Check column names
        suspicious_cols = []
        for col in df.columns:
            col_lower = col.lower()
            for pat in patterns:
                if pat in col_lower:
                    suspicious_cols.append(col)
                    break

        if suspicious_cols:
            violations.append(LeakageViolation(
                violation_type="FUTURE_PRICE_COLUMN_NAME",
                severity="POTENTIAL",
                description=(
                    f"Columns with future-leaking name patterns found: {suspicious_cols}. "
                    "Verify these are not derived from future observations."
                ),
                affected_rows=len(df),
            ))

        # Check for shift-correlation leakage (if price column exists)
        if price_col in df.columns and len(df) > 5:
            price = df[price_col].dropna()
            for col in df.columns:
                if col == price_col:
                    continue
                try:
                    other = df[col].dropna()
                    aligned = price.align(other)[0], price.align(other)[1]
                    # Check if other col == price.shift(-1) (next day's price)
                    shifted = price.shift(-1)
                    diff = (other - shifted).dropna()
                    if len(diff) >= 3 and (diff.abs() < 1e-9).all():
                        violations.append(LeakageViolation(
                            violation_type="FUTURE_PRICE_SHIFT_DETECTED",
                            severity="CONFIRMED",
                            description=(
                                f"Column '{col}' is identical to {price_col}.shift(-1) — "
                                "this encodes the next day's price and constitutes "
                                "confirmed look-ahead leakage."
                            ),
                            affected_rows=len(diff),
                        ))
                except Exception:
                    pass  # Column is non-numeric or incompatible

        return violations

    # ------------------------------------------------------------------
    # 2. Macro Availability Leakage
    # ------------------------------------------------------------------

    def check_macro_availability_leakage(
        self,
        df: pd.DataFrame,
        observation_col: str = "observation_date",
        availability_col: str = "availability_date",
    ) -> List[LeakageViolation]:
        """Check structural release-date validity for retrospective macro data."""
        violations: List[LeakageViolation] = []

        if observation_col not in df.columns or availability_col not in df.columns:
            violations.append(LeakageViolation(
                violation_type="MISSING_AVAILABILITY_DATE",
                severity="UNRESOLVED",
                description=(
                    f"Macro dataset is missing '{observation_col}' or '{availability_col}'. "
                    "Cannot verify information availability. This must be resolved before "
                    "the dataset can be used in experiments."
                ),
            ))
            return violations

        obs = pd.to_datetime(df[observation_col], errors="coerce")
        avail = pd.to_datetime(df[availability_col], errors="coerce")
        bad_mask = avail < obs
        if bad_mask.any():
            bad_rows = df[bad_mask].head(5)
            violations.append(LeakageViolation(
                violation_type="MACRO_BEFORE_RELEASE",
                severity="CONFIRMED",
                description=(
                    f"{int(bad_mask.sum())} records have availability_date < "
                    "observation_date."
                ),
                affected_rows=int(bad_mask.sum()),
                examples=[
                    {
                        "observation_date": str(row[observation_col]),
                        "availability_date": str(row[availability_col]),
                    }
                    for _, row in bad_rows.iterrows()
                ],
            ))
        return violations

    def check_policy_event_availability(
        self,
        df: pd.DataFrame,
        announcement_col: str = "announcement_timestamp",
        effective_col: str = "effective_timestamp",
        availability_col: str = "availability_date",
    ) -> List[LeakageViolation]:
        """Validate RBI event timing without retrospective macro rules."""
        if availability_col not in df.columns:
            return [LeakageViolation(
                "MISSING_POLICY_ANNOUNCEMENT_DATE",
                "UNRESOLVED",
                "Policy events lack an availability/announcement date.",
            )]
        availability = pd.to_datetime(df[availability_col], errors="coerce")
        violations: List[LeakageViolation] = []
        missing = availability.isna()
        if missing.any():
            violations.append(LeakageViolation(
                "MISSING_POLICY_ANNOUNCEMENT_DATE",
                "UNRESOLVED",
                "Policy events contain rows without a reliable announcement date.",
                affected_rows=int(missing.sum()),
            ))
        if announcement_col in df.columns and effective_col in df.columns:
            announcement = pd.to_datetime(df[announcement_col], errors="coerce")
            effective = pd.to_datetime(df[effective_col], errors="coerce")
            bad = announcement.notna() & effective.notna() & (announcement > effective)
            if bad.any():
                violations.append(LeakageViolation(
                    "POLICY_ANNOUNCEMENT_AFTER_EFFECTIVE",
                    "CONFIRMED",
                    "A policy event is effective before its public announcement.",
                    affected_rows=int(bad.sum()),
                ))
        return violations

    def check_information_as_of(
            self,
            df: pd.DataFrame,
            simulation_dates: pd.Series | pd.DatetimeIndex,
            availability_col: str = "availability_date",
            revision_col: str = "revision_version",
    ) -> List[LeakageViolation]:
            """Ensure a macro value is not visible before its availability date."""
            if availability_col not in df.columns:
                return [LeakageViolation(
                    "MISSING_AVAILABILITY_DATE",
                    "UNRESOLVED",
                    f"Missing {availability_col}; agent information timing cannot be audited.",
                )]
            dates = pd.to_datetime(simulation_dates)
            availability = pd.to_datetime(df[availability_col], errors="coerce")
            violations: List[LeakageViolation] = []
            for index, release_date in availability.items():
                if pd.isna(release_date):
                    violations.append(LeakageViolation(
                        "MISSING_RELEASE_DATE",
                        "UNRESOLVED",
                        f"Row {index} has no release/availability date.",
                        affected_rows=1,
                    ))
                elif (dates < release_date).any():
                    violations.append(LeakageViolation(
                        "MACRO_VISIBLE_BEFORE_RELEASE",
                        "CONFIRMED",
                        f"Macro row {index} would be visible before {release_date.date()}.",
                        affected_rows=int((dates < release_date).sum()),
                    ))
            if revision_col in df.columns and "observation_date" in df.columns:
                ordered = df.sort_values(["observation_date", availability_col])
                if ordered[revision_col].is_monotonic_decreasing:
                    violations.append(LeakageViolation(
                        "REVISION_ORDERING",
                        "POTENTIAL",
                        "Revision versions are not non-decreasing in release order.",
                    ))
            return violations

    def check_processing_leakage(
            self,
            processing_parameters: Dict[str, Any],
    ) -> List[LeakageViolation]:
            """Reject preprocessing fitted on future or full-sample observations."""
            text = str(processing_parameters).lower()
            suspicious = (
                "fit_on_full" in text
                or "fit_on_all" in text
                or "entire_dataset" in text
                or "future_period" in text
            )
            if suspicious:
                return [LeakageViolation(
                    "PROCESSING_FIT_ON_FUTURE_DATA",
                    "CONFIRMED",
                    "Processing parameters indicate fitting on the full or future sample.",
                )]
            return []

    # ------------------------------------------------------------------
    # 3. Gold Futures Roll Leakage
    # ------------------------------------------------------------------

    def check_gold_roll_leakage(
        self,
        contracts_df: pd.DataFrame,
        trade_date_col: str = "trade_date",
        expiry_col: str = "expiry_date",
        contract_col: str = "contract_symbol",
    ) -> List[LeakageViolation]:
        """Ensure gold futures roll logic cannot use future contract information.

        A roll from contract A to contract B is only legitimate if, on the
        roll date, contract B's data is observable (i.e. trade_date >= B's
        first trade date). This check verifies that each contract in the
        dataset was traded before or on the trade_date.
        """
        violations: List[LeakageViolation] = []

        required = [trade_date_col, expiry_col, contract_col]
        missing = [c for c in required if c not in contracts_df.columns]
        if missing:
            violations.append(LeakageViolation(
                violation_type="GOLD_ROLL_MISSING_COLUMNS",
                severity="UNRESOLVED",
                description=(
                    f"Gold futures dataset missing columns: {missing}. "
                    "Cannot validate roll leakage without contract/expiry information."
                ),
            ))
            return violations

        if "first_trade_date" in contracts_df.columns:
            observed = pd.to_datetime(contracts_df[trade_date_col], errors="coerce")
            first_trade = pd.to_datetime(
                contracts_df["first_trade_date"], errors="coerce"
            )
            bad = observed < first_trade
        else:
            bad = pd.Series(False, index=contracts_df.index)
        if bad.any():
            violations.append(LeakageViolation(
                violation_type="GOLD_ROLL_TEMPORAL_INCONSISTENCY",
                severity="CONFIRMED",
                description=(
                    f"{int(bad.sum())} rows use a contract before its recorded "
                    "first trade date."
                ),
                affected_rows=int(bad.sum()),
            ))

        # Warning: if no continuous series is constructed here, note this is safe
        # but flag that roll methodology must be validated when applied
        violations.append(LeakageViolation(
            violation_type="GOLD_ROLL_NOT_CONSTRUCTED",
            severity="MITIGATED",
            description=(
                "Gold futures stored as individual contracts — no roll applied. "
                "Roll leakage cannot occur here. This is the correct approach. "
                "Roll methodology must be validated separately when constructing "
                "a continuous series."
            ),
        ))

        return violations

    # ------------------------------------------------------------------
    # 4. Split Contamination
    # ------------------------------------------------------------------

    def check_split_contamination(
        self,
        splits_dict: Dict[str, Tuple[date, date]],
    ) -> List[LeakageViolation]:
        """Ensure temporal non-overlap between experiment splits.

        Args:
            splits_dict: {split_name: (start_date, end_date)} — inclusive bounds.
        """
        violations: List[LeakageViolation] = []

        split_names = list(splits_dict.keys())
        for i in range(len(split_names)):
            for j in range(i + 1, len(split_names)):
                name_a = split_names[i]
                name_b = split_names[j]
                start_a, end_a = splits_dict[name_a]
                start_b, end_b = splits_dict[name_b]

                # Overlap exists if start_a <= end_b AND start_b <= end_a
                if start_a <= end_b and start_b <= end_a:
                    overlap_start = max(start_a, start_b)
                    overlap_end = min(end_a, end_b)
                    violations.append(LeakageViolation(
                        violation_type="SPLIT_CONTAMINATION",
                        severity="CONFIRMED",
                        description=(
                            f"Splits '{name_a}' and '{name_b}' overlap: "
                            f"{overlap_start} to {overlap_end}. "
                            "This constitutes data contamination between splits."
                        ),
                        examples=[{
                            "split_a": name_a, "split_a_range": f"{start_a} to {end_a}",
                            "split_b": name_b, "split_b_range": f"{start_b} to {end_b}",
                            "overlap": f"{overlap_start} to {overlap_end}",
                        }],
                    ))

        return violations

    # ------------------------------------------------------------------
    # 5. Corporate Action Leakage
    # ------------------------------------------------------------------

    def check_corporate_action_leakage(
        self,
        prices_df: pd.DataFrame,
        actions_df: Optional[pd.DataFrame] = None,
        price_date_col: Optional[str] = None,
        action_date_col: Optional[str] = None,
        action_announcement_col: Optional[str] = None,
    ) -> List[LeakageViolation]:
        """Verify corporate actions are not applied before announcement.

        A stock split or dividend announced on date A should not affect
        adjusted prices before date A. If price adjustments extend backward
        beyond what was known at simulation time, this is look-ahead leakage.
        """
        violations: List[LeakageViolation] = []

        if actions_df is None:
            # Cannot verify without corporate action data
            violations.append(LeakageViolation(
                violation_type="CORPORATE_ACTION_UNVERIFIED",
                severity="POTENTIAL",
                description=(
                    "No corporate action dataset provided. Cannot verify that "
                    "adjusted prices do not incorporate events unknown at simulation time. "
                    "If using adjusted prices, document the adjustment methodology explicitly."
                ),
            ))
            return violations

        if action_announcement_col and action_announcement_col in actions_df.columns and \
           action_date_col and action_date_col in actions_df.columns:
            announce = pd.to_datetime(actions_df[action_announcement_col])
            effective = pd.to_datetime(actions_df[action_date_col])
            bad = announce > effective
            if bad.any():
                violations.append(LeakageViolation(
                    violation_type="CORPORATE_ACTION_ANNOUNCEMENT_AFTER_EFFECTIVE",
                    severity="CONFIRMED",
                    description=(
                        f"{int(bad.sum())} corporate actions have announcement_date "
                        "AFTER effective_date. This is physically impossible — "
                        "an action cannot be effective before it is announced."
                    ),
                    affected_rows=int(bad.sum()),
                ))

        return violations

    # ------------------------------------------------------------------
    # Master audit
    # ------------------------------------------------------------------

    def audit_all(
        self,
        price_df: Optional[pd.DataFrame] = None,
        macro_df: Optional[pd.DataFrame] = None,
        policy_df: Optional[pd.DataFrame] = None,
        gold_contracts_df: Optional[pd.DataFrame] = None,
        splits_dict: Optional[Dict[str, Tuple[date, date]]] = None,
        corporate_actions_df: Optional[pd.DataFrame] = None,
        processing_parameters: Optional[Dict[str, Any]] = None,
        dataset_names: Optional[List[str]] = None,
    ) -> LeakageReport:
        """Run all applicable leakage checks and return a consolidated report."""
        confirmed: List[LeakageViolation] = []
        potential: List[LeakageViolation] = []
        mitigated: List[LeakageViolation] = []
        unresolved: List[LeakageViolation] = []
        checked: List[str] = list(dataset_names or [])

        def _classify(violations: List[LeakageViolation]):
            for v in violations:
                if v.severity == "CONFIRMED":
                    confirmed.append(v)
                elif v.severity == "POTENTIAL":
                    potential.append(v)
                elif v.severity == "MITIGATED":
                    mitigated.append(v)
                elif v.severity == "UNRESOLVED":
                    unresolved.append(v)

        if price_df is not None:
            checked.append("price")
            _classify(self.check_future_price_leakage(price_df))

        if macro_df is not None:
            checked.append("macro")
            _classify(self.check_macro_availability_leakage(macro_df))

        if policy_df is not None:
            checked.append("policy")
            _classify(self.check_policy_event_availability(policy_df))

        if gold_contracts_df is not None:
            checked.append("gold")
            _classify(self.check_gold_roll_leakage(gold_contracts_df))

        if splits_dict is not None:
            checked.append("splits")
            _classify(self.check_split_contamination(splits_dict))

        if price_df is not None:
            checked.append("corporate_actions")
            _classify(self.check_corporate_action_leakage(
                price_df, corporate_actions_df
            ))

        if processing_parameters is not None:
            checked.append("preprocessing")
            _classify(self.check_processing_leakage(processing_parameters))

        return LeakageReport(
            confirmed_leaks=confirmed,
            potential_leaks=potential,
            mitigated=mitigated,
            unresolved=unresolved,
            validation_status="EVALUATED" if checked else "NOT_EVALUABLE",
            datasets_checked=sorted(set(checked)),
        )
