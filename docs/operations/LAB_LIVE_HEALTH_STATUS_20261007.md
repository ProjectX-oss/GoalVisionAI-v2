# Lab LIVE schedule confirmation and health status — 2026-10-07

Status: SMALL_GITHUB_FIX. Code prepared and tested; production deployment not performed.

## Authorization and current runtime

The user explicitly reconfirmed at 2026-10-07 21:46:55 Europe/Riga:
"Ka ieprieks runajam, no 18.00-23.00 LIVE online".
This resolves the prior audit's conflicting generic LIVE DISABLED instruction.
Retain the already installed evening Lab schedule:

- PREMATCH/SINGLE/COMBO discovery: 10:00 <= Riga time < 18:00.
- LIVE Lab discovery: 18:00 <= Riga time < 23:00.
- Existing pending-result checks continue outside the discovery windows.
- Official remains untouched; ADMIN Codex remains disabled.
- No publication thresholds, probability/odds floors, model, staking, quota
  ceilings, champion, promotion or rollback change.

At 21:59 Riga, the pinned read-only installer preflight passed with
current_mode=ENABLED and ADMIN_CODEX_SYSTEMD_DISABLED=PASS.
Installed release remains /opt/goalvision-live-evening-4f547cf-20261007.
The evening timer was loaded, active and enabled, with Result=success.
The source-only read-only health probe observed LIVE=ACTIVE and an open
18:00–23:00 Riga discovery window. No worker or manual cycle was started.

## Root cause and change

PREMATCH cycle/observer output unconditionally contained LIVE=DISABLED. The
top-level health report also probed the obsolete goalvision-live-lab.timer.
These were misleading global operational assertions after evening activation.

- Current health now reads goalvision-lab-live-evening.timer and its LoadState.
- LIVE reports ACTIVE / INACTIVE / FAILED / NOT_INSTALLED / UNKNOWN, explicitly
  scoped to LAB_EVENING_TIMER. It does not imply a quote or pick is eligible.
- The Riga discovery window and observation timestamp are separate fields.
  The timer remains ACTIVE after 23:00 for pending results.
- Nonzero/empty/unavailable systemctl output yields UNKNOWN, without raw stderr.
- Pure PREMATCH cycle and observer summaries report LIVE=NOT_EVALUATED with
  PREMATCH_CYCLE / PREMATCH_OBSERVER scope. They do not probe current systemd
  while reconstructing historical cycles, or control LIVE.
- Previously persisted immutable reports remain unchanged. Consumers must use
  current top-level health for timer state, not historical PREMATCH rows.

Only health.py and observer.py are runtime changes. No ADMIN service, timer,
environment, transport, provider client or publication code is changed.

## Verification

214 focused tests PASS (5.51 s), synthetic credentials and outbound sockets denied.
Coverage includes Riga winter/summer boundary times, 18:00 inclusive / 23:00
exclusive, result-timer continuity, failed/unavailable systemd, non-global
historical summaries, observer no-training behavior, existing calibration/de-vig,
performance, schedule and delivery-health regressions.
git diff --check PASS. Installed-release read-only preflight PASS.
Read-only candidate health probe PASS; no production DB write.

## Operator status

No new deployment package was built or applied for this small diagnostic change.
Do not edit the installed immutable release in place or rerun its installer to
activate these source changes. A later reviewed immutable update must preserve
the already enabled evening mode and existing service routes. LIVE is already
operational under the confirmed schedule; this source fix is monitoring-only.

Manual provider calls: 0. Telegram test/manual sends: 0.
Already authorized natural timers continue independently.
