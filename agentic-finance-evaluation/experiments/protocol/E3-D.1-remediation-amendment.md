# E3-D.1 Amendment — Incident Remediation and Fresh Window Freeze

**Amends:** E3-D (commit `2e4c245`), which remains otherwise byte-identical
and authoritative.
**Status:** frozen pending review. Restarts the claim clock (see §8).
**Scope:** incident record, window replacement, role-separated identity
reference. No endpoint, criterion, methodology, or budget change.

## 1. Incident

The E3-E integrity campaign and the attempted Tier-1 T1-F campaign ran
identical frozen configuration, producing one deterministic experiment
identity (`8f439dc4…`). The Tier-1 attempt overwrote the integrity
artefact with byte-identical content (`a3dc7a8c…`). The integrity report
had already published outcome values, so outcome-blind Tier-1 execution
on the original pair became irrecoverable given determinism.

## 2. Scientific consequence

Frozen *criteria* were never redefined (E3-D byte-identical throughout —
git-provable). The damage is confined to outcome-blindness and
artefact-role separation on the original window pair. No RQ conclusion
was drawn from the contaminated artefact at any point.

## 3. Retirement

The original Tier-1 pair (diagnostic 2023-05-15→06-15, held-out
2023-07-10→08-10) is RETIRED for scientific analysis. It remains valid
as frozen E3-C history and as the integrity-gate configuration. The
contaminated artefact (`8f439dc4…` + sidecar registry entry) is
permanently excluded from Tier-1 n, tables, deltas, and conclusions.

## 4. Blind replacement rule (applied without outcome inspection)

The replacement pair is the latest consecutive calendar-month pair
strictly before May 2023 satisfying, per month: ≥20 NSE_CM
OPEN/SPECIAL sessions, 0 UNKNOWN rows, ≥20 GOLDAUG2023 trade dates
(presence only — no prices, returns, volatility, or repair outcomes
inspected at any step). Scan proceeded backward from April 2023:
(Mar, Apr) rejected (April: 17 sessions); (Feb, Mar) accepted
(Feb: 20/0/20; Mar: 21/0/23).

## 5. New frozen windows

- Diagnostic: 2023-02-01 → 2023-02-28 (20 sessions).
- Held-out: 2023-03-01 → 2023-03-31 (21 sessions).
- Strictly later, non-overlapping, disjoint from the retired pair.
- Environment fingerprints (configuration fingerprinting only —
  no agents, episodes, or metrics executed):
  - diagnostic: `60d189e4d17310f0ec12b46c20a7411e17b44833700e6a1757b6d1f7a2d33acd`
  - held-out: `484b82a73c8eef6837f1a0227edee869bbd5a8594ba233fe7b875fa268254437`
- Universe, costs, cash, PIT/vintage, pool, sequence, budgets,
  hypotheses, constants: unchanged from E3-C.2 (GOLDAUG2023 alive
  across both new windows, so no universe change was required).

## 6. Unchanged criteria

RQs, endpoints, operational guards (validity, inactivity-collapse,
mechanism direction), missingness policy, Tier-1 descriptive-only
scope, Tier-2 gate, RQ4 limitation, F/A vocabulary, success/
inconclusive/regression/invalid/failed taxonomy, reporting schema:
all verbatim from E3-D. The only scientific delta in this amendment
is the window pair (§5) and the blindness restoration it provides.

## 7. Engineering companion (separate commit scope)

Role/instance-separated identity (`ExecutionRole`, `execution_id`,
role-pathed artefacts, fail-closed `save()`, incident sidecar,
Tier-1 allowlist) is implemented in `experiments/harness/` with pure
tests. Scientific identity (`experiment_identity`) is byte-for-byte
unchanged. Engineering and scientific changes are reviewed and
committed separately; neither smuggles the other's content.

## 8. Claim-clock restart

The clock restarts at this amendment's freeze. Eligible claims
require: fresh T1-F + T1-A on §5 windows (TIER1_PRIMARY role,
distinct instances), integrity audits, and frozen Tier-1 assembly —
all still in the future. No RQ interpretation until then. The retired
pair's values must never inform window, endpoint, or framing choices
beyond what this amendment states.
