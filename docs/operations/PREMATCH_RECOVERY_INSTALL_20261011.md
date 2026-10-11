# PREMATCH recovery operator package — 2026-10-11

Preparation only; the operator runs the installation. The package changes exactly four application files on the pinned PREMATCH base:
`calendar_audit.py`, `health.py`, `observer.py`, and `combo_agreement_sources.py`.
It reuses the existing reviewed runtime helpers and immutable-release approach.

Base: `/opt/goalvision-prematch-quota-reader-3d4f5c5-20261010`.
Target: `/opt/goalvision-prematch-recovery-380bcf7-20261011`.

LIVE uses a separate installed base and is protected from this installation. Actual production calendar monitoring and learning observer execute through PREMATCH, so no LIVE overlay is needed. Research fit/adapter code, artifacts, champion, model formulas, thresholds and the frozen calendar are excluded.

## Operator commands

The builder creates a checksummed package and this pinned wrapper on the VPS.

Read-only preflight:

```bash
python3 -I /home/arvis/goalvision-operations/calibration-live-recovery-20261011.py
```

Operator installation:

```bash
sudo /usr/bin/python3 -I /home/arvis/goalvision-operations/calibration-live-recovery-20261011.py --apply
```

Expected final marker: `PREMATCH_RECOVERY_DEPLOYED`.
A repeat returns `PREMATCH_RECOVERY_ALREADY_DEPLOYED` without restarting anything.

The apply path verifies package/base hashes, loaded service commands and all GoalVision unit/drop-in configuration. It assembles a separate immutable release, briefly pauses only the four PREMATCH timers, lets active oneshot services complete naturally (maximum 180 seconds), changes their release references, verifies them, then restores the same timer activity. It never enables/disables timers or starts a service manually. LIVE, ADMIN and research timers/routes remain unchanged.

A package/base/configuration drift stops installation. If failure occurs before any route write, previous timer activity is restored. If route writes have begun, there is **no automatic rollback**: affected PREMATCH timers remain paused and the command reports an operator-review journal under `/var/lib/goalvision-operator-recovery/`. Do not blindly restart or retry a partial installation; inspect its journal and loaded routes first. Existing LIVE settlement continues independently.

No production DB migration, modification of audit/settlement records, provider request, Telegram test, model activation or refit occurs in the installer.

## Learning snapshot, 2026-10-11 20:42 Riga

Authoritative read-only SQLite backup, analyzed offline:
- 4,807 retained PREMATCH observations; 4,794 eligible resolved observations from 1,504 fixtures.
- Stage `CHALLENGER_RESEARCH`; 23 covered days; automatic eligibility false.
- TRAIN: 1,804 observations / 560 fixtures.
- VALIDATION: 56 observations / 22 fixtures. Minimum 30 independent fixtures; window closes 2026-10-18 00:00 UTC / 03:00 Riga.
- SEALED_HOLDOUT: 0; window 2026-10-19 00:00 UTC through 2026-10-26 00:00 UTC. Not evaluated.
- 59 model artifacts; 133 training records (58 TRAINED, 74 REJECTED, 1 REVIEWED_BOOTSTRAP); no new activation, rollback, validation scoring or promotion.
- Latest observer 20:38 Riga; no fitting or external calls were invoked by this check.
- Champion remains `generation-aa7e535b86267741aabc967e8044de2ab94a4334b1520a829414dd55ebc7371a`.

The 346-fixture calibration experiment is frozen on its original 2026-10-10 snapshot. Its in-sample Platt Brier improvement (0.230160 to 0.229341) is small and has no independent validation yet.

The current full-database readiness projection shows only 18 FIT fixtures. We traced all 328 removed fixtures: 310 now fail the label-before-embargo check and 18 cross calendar windows. The additions are 810 SHADOW observations with settlement availability recorded at 2026-10-11T16:15:32.398158+00:00. Whole-fixture exclusion is conservative; do not remove these guards or backdate availability to inflate counts. All earlier observation fingerprints remain unchanged. The frozen 346 FIT fixtures overlap zero current VALIDATION fixtures.

Frozen experiment evidence and current dynamic readiness must be reported separately. No current-data refit or promotion is authorized. Twelve retained legacy COMBO_LEG rows are excluded from independent learning; COMBO coupon outcomes are not learning observations.

## Verification

Installer regression tests exercise exact four-file overlay, frozen asset/flag preservation, hash/symlink drift, busy-service timeout, idempotence, partial-route failure without automatic rollback, timer-state preservation, no LIVE controls, and non-root rejection. Exact-base imports and application regressions are run during package preparation. Package hashes, source commit and final results are recorded after the build.
