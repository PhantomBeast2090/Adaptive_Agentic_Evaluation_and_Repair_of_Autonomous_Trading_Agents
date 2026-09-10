# Indian Data Coverage Audit

> Generated from acquired artifacts and manifests. This report does not
> freeze context, discovery, re-evaluation, or OOD experiment dates.

## 1. Acquisition status

- Acquired and auditable datasets: **0**
- Pending/unavailable datasets: **0**
- Artifact read errors: **0**
- No dataset manifests exist yet; inventory entries without manifests are not treated as acquired or assigned coverage.

## 2. Dataset-by-dataset coverage

No acquired datasets were found; no empirical coverage exists yet.
## 3. Missingness

Missingness is reported per required field above. No values were forward-filled by this audit.

## 4. Duplicate analysis

Duplicate timestamps and date/identifier pairs are reported per dataset above.

## 5. Calendar analysis

Trading-day checks use a documented lightweight weekday/holiday heuristic. They are not a substitute for an official NSE holiday calendar.

## 6. Information-availability analysis

Macro and policy datasets must carry observation_date and availability_date. Values are not eligible for agent observations before availability_date.

## 7. Common intersection

- Earliest common usable date: `not computable`
- Latest common usable date: `not computable`
- Calendar duration: 0 days
- Datasets included: none
- Datasets excluded: none

## 8. Data-quality blockers

- No artifact read errors were encountered.

## 9. Leakage findings

- Confirmed leaks: 0
- Potential leaks: 0
- Mitigated issues: 0
- Unresolved issues: 0
- Gold futures must remain contract-level until a roll method is selected and independently audited.

## 10. Recommended next methodological decision

Complete official-source acquisition and release-date verification for the mandatory datasets. Then review this audit to define the longest clean common period before selecting any temporal split boundaries.
