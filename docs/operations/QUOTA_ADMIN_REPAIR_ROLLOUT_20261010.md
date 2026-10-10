# Quota reader + ADMIN correlation — operator rollout, 2026-10-10

## Scope and authorization

Operator explicitly requested preparation and installation on 2026-10-10.
This package includes only reviewed source fixes:

- Reader: 3d4f5c541c79873208ec2bb8ca8c83a0118f546b.
- ADMIN correlation: 9e321c397337e38f994b2dc424621af414acd58b.

It does not change prediction logic, champion, odds/probability floors, quotas,
500 ms lock guard, scheduling policy, bankroll, settlement rules or any Official
route. No manual cycle, monitor scan, provider request or Telegram test is run.

## Installed bases and targets

| Scope | Base | New target |
|---|---|---|
| PREMATCH, observer, settlement, learning | /opt/goalvision-live-evening-4f547cf-20261007 | /opt/goalvision-prematch-quota-reader-3d4f5c5-20261010 |
| LIVE | /opt/goalvision-live-final-review-budget-a4cdfa1-20261009 | /opt/goalvision-live-quota-reader-3d4f5c5-20261010 |
| ADMIN | /opt/goalvision-admin-alerts-releases/admin-mixed-delivery-ab327dd-20261004 | /opt/goalvision-admin-alerts-releases/admin-quota-correlation-9e321c3-20261010 |

The same reader fix is overlaid onto the two distinct Lab bases. LIVE therefore
keeps its 60–70% band, EV-off policy, diagnostic quote age and nine-attempt
final-review reserve. PREMATCH keeps SINGLE 1.50, private SINGLE 1.70/70–80%,
DC legs 1.30 and exactly two Double legs 1.70/70–80%.

All regular runtime files, including JSON resources and other assets, are copied
and hashed. Only the intended module changes; PYTHONPATH points to the new
release. ADMIN retains its existing run.py and refreshes its Python manifest.

## Transaction and fail-closed guards

- Source commits and patch parents must match the installed module bytes.
- Pinned scripts, overlays, base manifests and full target manifests are checked.
- All 144 existing GoalVision unit/drop-in files are fingerprinted.
- Loaded command, user/group, environment and working-directory snapshots are pinned.
- Timer configuration and enablement are unchanged; LIVE must remain active.
- ADMIN Codex must be disabled in systemd and, under root, in config plus DISABLED marker.
- Two existing operations locks protect PREMATCH and ADMIN installation.
- Three immutable releases are assembled before any timer is paused.
- Only the six affected Lab/ADMIN timers are paused, ADMIN first.
- Services are never stopped/restarted. Allow up to 180 seconds for natural completion.
- Six new drop-ins are written, followed by daemon-reload and exact route verification.
- Restore prior timer active/inactive states, ADMIN last; never enable a disabled timer.
- A partial installation error restores only this transaction's prior configuration.
  This is installation recovery, not model rollback.
- Unknown partial deployment or external drift fails closed for operator review.
- Re-running the successful package only validates; it does not repeat routing.

If an active discovery needs longer than 180 seconds, the package exits after
restoring timer states. Retry after natural completion; do not kill the service.

## Tests and reproducibility

Source regressions were already reviewed: reader adjacent matrix 872 PASS,
ADMIN 193 PASS. Their counts overlap earlier focused suites.

New operator transaction suite: 22 PASS. It covers immutable assembly/assets,
unchanged flags, idempotence, source/script/asset drift, symlinks, partial routes,
unrelated systemd changes, disabled-Codex guard, inactive LIVE refusal, drain
timeout, mid-write failure, daemon-reload failure and timer-resume failure.

Assembled runtime smoke: PREMATCH 7 PASS, LIVE 7 PASS, ADMIN 14 PASS with the
actual runtime interpreters. Each import is checked to originate in the assembled
release. Network sockets are denied; synthetic databases and fake transports only.

    cd /home/arvis/goalvision-worktrees/quota-admin-release-20261010
    /home/arvis/GoalVisionAI/.venv/bin/python -I -B operations/live-combo-research/offline_tests.py tests/test_quota_admin_repair_operations.py

After committing the installer, build from its exact reviewed HEAD:

    python3 -B operations/quota-admin-repair/build.py --output /home/arvis/goalvision-operations/quota-admin-repair-REVIEWED-20261010 --reader-tests-root /home/arvis/goalvision-worktrees/quota-reader-lock-20261010 --admin-tests-root /home/arvis/goalvision-worktrees/admin-quota-correlation-20261010

The builder runs offline release smoke, writes a deterministic manifest and
SHA256SUMS, and performs a read-only preflight. An output directory must be new.
No production route changes occur during build.

## Operator commands

The prepared wrapper pins the updater and metadata SHA-256 before execution.
Use the final prepared wrapper, not an older deployment package:

    python3 ~/goalvision-operations/quota-admin-repair.py
    sudo python3 ~/goalvision-operations/quota-admin-repair.py --apply

Do not share the sudo password in chat. A normal-user preflight explicitly prints
ROOT_GUARD=CHECKED_AT_APPLY; root verifies the protected ADMIN config and marker
before any deployment.

Successful output: QUOTA_ADMIN_REPAIR_DEPLOYED followed by three release paths.
Re-run the first command to verify current_mode=ENABLED.

## Natural acceptance after operator apply

Read-only verify the loaded release paths, file manifests, restored timers,
disabled ADMIN Codex and protected configuration. Then observe natural schedules:

1. PREMATCH and observer overlap without the old reader blocking a quota COMMIT.
2. LIVE retains its evening window and final-review reserve.
3. A uniquely correlated quota failure has one execution notification; supporting
   incidents and all historical receipts remain present.
4. No new missing receipts, settlement failure or quota-budget change.

Do not force an error or run a manual provider cycle to test the monitor.
Four observed quota failures matched observer startup in the earlier audit, but
the historical lock-holder PID was not captured. Synthetic reproduction proves
the fixed reader defect; natural post-install verification is still required.

At preparation: no deployment, no provider/Telegram calls, no production DB writes,
no Official/champion changes. Root installation is pending the operator's sudo
credential, which is unavailable to the assistant.
