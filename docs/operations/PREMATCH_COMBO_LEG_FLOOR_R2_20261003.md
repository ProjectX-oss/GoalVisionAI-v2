# COMBO leg-floor installer after calibration observer deployment — R2

## Verified state and cause

The operator first installed the previously prepared calibration observer
release `/opt/goalvision-calibration-observer-c4daf63-20261003`. The old
COMBO package `ff55669` required all four services on de-vig `83958d1`.
Its exact-route guard therefore rejected the observer with
`PREMATCH_ROUTE_MISMATCH` before creating the COMBO release, writing a COMBO
override or pausing timers.

Independent readback confirms the intended mixed baseline: observer uses
calibration c4daf63; discovery, settlement and research still use de-vig
83958d1. The failed COMBO target and all four COMBO overrides are absent.
ADMIN Codex remains inactive with PID zero and its timer disabled/inactive.
All four PREMATCH services report their last result as success.

The latest persisted natural observer read at repair preflight is 12:08 Riga,
before the reported deployment, and has no CALIBRATION_READINESS field.
The observer timer is active and next scheduled at 12:38 Riga. Installation
is verified; a post-install natural readiness document is still pending.
No manual observer or discovery cycle is run.

## Narrow repair

Application source is byte-for-byte unchanged from the fully tested
COMBO floor implementation. Only installer/builder contracts, tests and
documentation change.

R2 declares the exact observer source separately. Both source environments
and complete source manifests are verified. The calibration source manifest
is derived from the reviewed de-vig base plus the five already reviewed
calibration files; the builder cannot simply accept and re-pin arbitrary
observed source drift. Missing plan assets, changed observer code, disabled
readiness flags, extra Python files and re-signed drift are rejected.

All existing checks remain: package pins, expected argv, protected routes,
disabled ADMIN worker, root guard files, timer state restoration, natural
45-second drain and failure recovery. Recovery restores the precise mixed
baseline if any route change fails.

The target runtime and compatible rollback are unchanged: SINGLE >=1.30,
each COMBO leg >=1.30, no additional combined floor, readiness/de-vig enabled,
today-only and early COMBO loss/remaining-leg tracking retained. Compatible
rollback disables only the COMBO leg floor. Official stays unchanged;
LIVE and ADMIN Codex remain disabled. No champion promotion.

## Verification

157 installer regressions passed, with one inherited single-route-only
inapplicable case skipped. The COMBO test rig now starts with the actual
two-source route layout; shared apply/replay/rollback, atomic-write failure,
reload failure, timer failure and busy-service tests therefore exercise that
layout. New tests cover both manifests and prohibit re-pinning source drift.

All tests ran under the network-denying offline runner, with fake service
controls and disposable source trees. The previously completed 1,147
application/integration tests remain the validation for the unchanged runtime
files and are not repeated.

See `docs/evidence/combo_leg_floor_r2_20261003/` for readback, test evidence
and package pins. No automatic deployment, manual operational cycle, provider
request or test Telegram send occurred.

## Operator action

The original wrappers and packages remain untouched. Use the new pinned R2
entry point:

```bash
sudo python3 ~/goalvision-operations/combo-leg-floor-r2.py --apply
```

Read-only preflight:

```bash
python3 ~/goalvision-operations/combo-leg-floor-r2.py
```

Compatible rollback:

```bash
sudo python3 ~/goalvision-operations/combo-leg-floor-r2.py --apply --rollback
```

Normal-user preflight verifies the source, routes and systemd disabled guard.
Root-owned ADMIN config and DISABLED marker remain mandatory at apply.
No separate calibration command is needed. After apply, verify the loaded
route and the next natural discovery/observer outputs.

## Prepared R2 package

Installer source commit: `e355b519e68ae256f8e6ece4ae314e819b36de15`.

Package:
`/home/arvis/goalvision-operations/combo-leg-floor-e355b51-20261003`.

All 15 checksum entries pass. The new pinned wrapper's read-only preflight
passes against both installed sources and reports BASE plus
ADMIN_CODEX_SYSTEMD_DISABLED=PASS. All 13 application overlay hashes match the
previous ff55669 package exactly. Earlier wrappers/package pins and protected
routes remain unchanged. Root apply and the target release remain pending.
