# Dixon–Coles incremental-information comparator — shadow only

The prospective protocol was declared at 2026-10-04T10:30:54.327577+00:00 in commit e345e3f. Only captures AND forecasts after declaration qualify; prior records are development evidence, never backfilled into the new forward cohort.

The read-only adapter verifies enrolled plans, model artifacts and exact forecast reproduction, retains one complete 1X2 vector per independent fixture, excludes reserved holdout fixtures before requesting labels, and requires exact frozen champion generation/artifact identities. Missing or incoherent champion vectors remain unavailable. A legacy ensemble is never silently relabelled champion.

Comparators: frozen champion when verifiable, the original forward plan's first complete bookmaker with multiplicative de-vig, constrained Dixon–Coles, and logarithmic pools with champion or market. This market benchmark differs from the multi-book market publication experiment. Outcomes are ordered HOME_WIN/DRAW/AWAY_WIN. RPS is normalized by two cumulative terms; multiclass Brier sums three squared errors per fixture. ECE uses ten equal-width bins on class indicators; these are not three independent fixtures. Draw, favourite, longshot calibration and total-variation disagreements are included.

A fixed 0.5 pool is descriptive only. Explicit pool fitting scans the declared 0.0–1.0 grid in steps of 0.1, minimizing CALIBRATION_FIT log loss, ties preferring zero. It requires 300 distinct fixtures and the fit window to be closed. No CLI or timer calls fit_pool. The sealed artifact retains dataset fingerprint, forecast/result references, model generation and timestamps.

Validation reproduces the immutable fit, requires its creation before validation, disjoint fixtures, the closed fixed validation window, at least 100 fixtures and all seven kickoff dates. A deterministic 200-replicate date-cluster bootstrap and both chronological halves must show log-loss benefit, with no Brier/RPS regression and weight above 0.1, before the diagnostic can suggest further holdout planning. This is a research screening rule, not proof of betting profit or promotion authorization. Near-zero, inconsistent or inconclusive contributions do not advance.

The existing forward capture plan ends at 2026-10-19T00:00Z, exactly when sealed holdout starts. Therefore this implementation DOES NOT evaluate holdout. A separately reviewed prospective holdout collection plan is required before that stage; no retroactive extension or current holdout consumption is permitted.

No publication imports this module. No timer/service change is prepared for it. Read-only reporting from the reviewed checkout:

```bash
cd /home/arvis/goalvision-worktrees/watch-reconciliation-20261004
nice -n 10 /home/arvis/GoalVisionAI/.venv/bin/python -B docs/operations/offline_test_runner.py /home/arvis/GoalVisionAI/.venv/bin/python -B operations/watch-reconciliation/incremental_report.py --as-of "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" --research /var/lib/goalvision-dixon-coles-forward/research.db --audit /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db --ledger /home/arvis/GoalVisionAI/var/lab_combo/ledger.db
```

This command reads stored evidence only. It cannot capture, fit, send, promote or deploy. Retain any desired output outside runtime databases.
