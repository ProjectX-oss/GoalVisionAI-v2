# PREMATCH SINGLE floor — deployment readback, 2026-10-02

**Deployment verification: PASS.**
**Natural discovery/publication verification: NEEDS_MORE_EVIDENCE.**

Operator deployment: 11:54:48 Europe/Riga.
Read-only verification: 11:55:44–11:56 Europe/Riga.

Release: `/opt/goalvision-prematch-single-floor-f81aa2c-20261002`.
Source commit: `f81aa2c2c1aae4af8decaa9b454d182c82f74af8`.

## Verified state

- All four PREMATCH services route to the release above: discovery, observer, settlement and research.
- The pinned read-only checker returned `current_mode=ENABLED; ADMIN_CODEX_DISABLED=PASS`.
  Package, full 807-module application tree, environment and protected-route checks passed.
- `GOALVISION_LAB_SINGLE_MIN_ODDS_130=1`: new PREMATCH SINGLE odds must be >=1.30.
- `GOALVISION_LAB_ACCURACY_COMBOS=1`: COMBO total and legs retain no economic odds floor.
- `GOALVISION_LAB_TODAY_ONLY=1`: Riga same-day publication scope retained.
- `GOALVISION_LAB_EARLY_COMBO_LOSS=1`: installed settlement behavior retained.
- All four PREMATCH timers are enabled, active and waiting.
- ADMIN autorepair service is inactive with MainPID=0; its timer is inactive and disabled.
- The deployment drop-ins were written at 08:54:48 UTC, before the next natural settlement invocation.

## First natural service completion

The settlement service started at 11:55:01 and finished at 11:55:38 Europe/Riga,
with `Result=success`. This verifies a successful service exit after deployment;
this readback does not claim that every pending match has resolved.

The discovery service's last completion preceded deployment. Its next scheduled
invocation is 12:00 Europe/Riga; observer follows at 12:08. Confirmation from a new
discovery/publication cycle remains pending.

No service was manually started, stopped or retried for this verification.
Only read-only systemd properties, release files and the pinned package checker were used.
