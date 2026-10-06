# PREMATCH evidence changes — 2026-10-06

Scope: observability and read-only research only. No deployment, provider request,
Telegram send, prediction/selection threshold change, model fit or activation.
Base: `6357a6996568731ff3c54a839aa50ac942fb25fe` (operator-deployed queue evidence).

## Changes

- Attribute an already rejected probability endpoint to `PROVIDER_ZERO_PROBABILITY`
  only when a matching API-Football raw `0%`, normalized zero, source fingerprint,
  fixture/market and single predictive family prove the cause. Retain the original
  trace and generic reason for unproven zeros. Never clamp or substitute a value.
- Extend the existing performance snapshot used by PREMATCH status, why-no-picks,
  observer and cycle health with calibration bias, frozen data-quality grouping,
  positive/non-positive EV and separate policy cohorts. Compact scheduled output
  retains totals and the full evidence fingerprint; detailed segments stay in
  persisted evidence. SENT receipts remain the accounting authority; VOID stakes
  count in the settled ROI denominator, while VOID/partial VOID do not count in
  binary hit rate. COMBO never becomes a calibration example.
- Reuse the reviewed incremental comparator and protocol from
  `20be74f9e3197032567a092c0e88574c62293b7a`. Add one common six-method 1X2 sample,
  league/competition/UTC kickoff-date/lead-time/partition groups and paired proper
  score differences. The DC model, capture plan, solver and forecast inputs are
  unchanged. These added group summaries are descriptive, not a new prospective
  promotion declaration. Market methods use the same previously frozen current
  quote book; no historical odds acquisition or new quote query occurs.
- Confidence intervals use paired kickoff-date cluster bootstrap (fixed seed,
  200 resamples), at least 30 fixtures and 7 dates. ECE is recomputed in each
  resample. Intervals are exploratory and unadjusted for multiple comparisons.
  No interval or optimized DC weight is invented for sparse evidence.
- Read-only audit scripts distinguish discovered fixtures, current odds scope,
  repeated fixture-cycle observations and independent fixtures. They keep
  delivery uncertainty visible without retrying or editing claims.

## Read-only operator audit

Run from the reviewed worktree, with an explicit shared UTC cutoff and a private
output directory outside tracked source. These commands do not install code or
start a discovery, settlement, research-capture or monitor cycle.

```bash
cd ~/goalvision-worktrees/prematch-evidence-20261006
GV_AS_OF=$(date -u +%Y-%m-%dT%H:%M:%S+00:00)
GV_AUDIT_OUT=$(mktemp -d /tmp/goalvision-evidence.XXXXXX)
nice -n 10 ~/GoalVisionAI/.venv/bin/python -B operations/watch-reconciliation/snapshot.py \
  --as-of "$GV_AS_OF" --database ~/GoalVisionAI/var/adaptive_lab/audit.db \
  --ledger ~/GoalVisionAI/var/lab_combo/ledger.db --output "$GV_AUDIT_OUT"
nice -n 10 ~/GoalVisionAI/.venv/bin/python -B operations/prematch-evidence/diagnostics.py \
  --as-of "$GV_AS_OF" --database ~/GoalVisionAI/var/lab_v2/shadow.db \
  --output "$GV_AUDIT_OUT/queue-data-disagreement.json"
nice -n 10 ~/GoalVisionAI/.venv/bin/python -B operations/prematch-evidence/publication_audit.py \
  --as-of "$GV_AS_OF" --output "$GV_AUDIT_OUT/publication-health.json"
nice -n 10 ~/GoalVisionAI/.venv/bin/python -B operations/watch-reconciliation/incremental_report.py \
  --as-of "$GV_AS_OF" --research /var/lib/goalvision-dixon-coles-forward/research.db \
  --audit ~/GoalVisionAI/var/adaptive_lab/audit.db --ledger ~/GoalVisionAI/var/lab_combo/ledger.db \
  > "$GV_AUDIT_OUT/dixon-coles-paired.json"
```

Scheduled production output will gain these diagnostic fields only after a
separately reviewed immutable operator release. No installer, timer change,
automatic training or promotion is introduced here. Do not run old apply wrappers
across newer route guards. A missing Telegram receipt requires operator
reconciliation of the original message, not a test send or automatic replay.

Tests cover raw-zero attribution and real runner persistence, unproven endpoint
rejection, authoritative accounting/cohorts, paired-sample intersection, proper
score direction, deterministic cluster intervals, holdout exclusion, audit
denominators/privacy and existing queue/publication/settlement behavior.
