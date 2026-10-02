# Disable ADMIN Codex / Auto-Repair — 2026-10-02

Operator instruction: disconnect Codex from ADMIN. Keep ordinary ADMIN monitoring and alerts.

Status: implementation and 5 isolated tests PASS. Production disconnection awaits the operator's sudo command; passwordless sudo was unavailable to the remote session. At preparation, the worker was inactive with MainPID=0, its timer active/enabled, and the ADMIN monitor timer active/enabled.

Run:

```bash
sudo python3 ~/goalvision-operations/admin-codex-off.py --apply
```

The command first writes the existing service's DISABLED marker, disables/stops its timer and stops the worker control group. It then obtains the existing ADMIN scan lock and atomically sets only autorepair.enabled=false. The monitor reloads this setting inside its scan lock. This stops new repair queue entries and Auto-Repair operator-status dispatch as well as worker execution.

The current ADMIN configuration is backed up in its root-controlled directory with mode 0600. Configuration owner/group/mode, sender credentials, ordinary monitor settings and all queued/failed-job/incident/outbox history are preserved. No Codex uninstall, auth logout, manual model call, Telegram test message, provider call, PREMATCH/Official/LIVE change, or monitor timer stop is performed. Repeating this command does not create another config backup when already disabled.

Expected marker: ADMIN_CODEX_DISABLED, followed by ADMIN_AUTOREPAIR_READBACK with autorepair_enabled=false, timer inactive/disabled, worker inactive and MainPID=0, disabled_marker=true and monitor_timer_unchanged=true.

If the monitor lock cannot be obtained within 45 seconds, the worker remains stopped and the same command can be retried. There is deliberately no automatic re-enable/rollback; future re-enablement requires a new explicit operator instruction. A successfully disabled worker must not be re-enabled as part of an unrelated release.

The earlier combined admin-alert-fix.py deployment is superseded for this request. The monitor compatibility fixes remain prepared but undeployed. Disabling Auto-Repair does not itself fix ordinary MISSING_OUTPUT/health-size alerts.

Changed code: operations/admin-autorepair/disable_autorepair.py.
Tests: tests/admin_autorepair/test_disable_autorepair.py — 5 passed (offline filesystem/systemctl fakes only).
