# ADMIN monitor-only compatibility follow-up — 2026-10-02

Source/package commit: `a28f2a6ef1aa7ba1e477f662950703d4cc06bca6`.

Status: code, 64 focused tests, read-only route comparison and package preflight PASS. Monitor deployment awaits the operator. ADMIN Codex disconnection is already verified.

## What happened

The operator attempted the earlier combined admin-alert-fix.py package. Its guard compared the complete systemctl ExecStart display, including start_time, stop_time, PID and exit status. The daemon-reload reset these transient fields to n/a / 0 even though the configured executable and arguments stayed unchanged. This incorrectly raised PREMATCH_ROUTE_CHANGED.

The transaction rolled back both ADMIN drop-ins successfully. Direct readback confirms:
- Monitor remains /opt/goalvision-admin-alerts-releases/admin-io-startup-0a3e42a-20261001.
- Worker remains /opt/goalvision-admin-autorepair-releases/admin-worker-clone-eebed21-20261001.
- Both attempted zzzz-admin-compat drop-ins are absent.
- All five PREMATCH/weekly WorkingDirectory, EnvironmentFiles, DropInPaths and configured ExecStart values match the prepared baseline.
- No PREMATCH route was changed; immutable staged ADMIN releases remain as unused evidence.

The subsequent admin-codex-off.py command succeeded. Operator readback confirms autorepair.enabled=false; direct checks confirm the DISABLED marker, worker inactive/MainPID=0, timer inactive/disabled, and monitor timer still active/enabled. Natural monitor completion at 08:10:03 Riga returned success/exit 0. This is service-status evidence, not proof that all monitoring alarms have recovered.

## Correction

The route guard now compares only configured executable, argv and ignore_errors. It strictly rejects unknown or multiple-command formatting. Regression tests reproduce daemon-reload's timestamp/PID reset and still reject a genuine argv change with rollback.

A separate monitor-only wrapper applies the existing reviewed journal --all, bounded health projection and research-output contract fixes. It requires Codex to remain disabled, protects the worker route, and never installs worker code, starts its service/timer, changes autorepair configuration or retries a job. The failed combined package is superseded.

Changed files:
- operations/admin-autorepair/update_compat.py
- operations/admin-autorepair/update_monitor_compat.py
- tests/admin_autorepair/test_compat_upgrade.py
- TASKS.md and operations/evidence documentation

Monitor runtime modules are exactly the already-tested app/admin_alerts/sources.py and output_contracts.py from 813f33c. No new selection/model/provider behavior is introduced.

## Validation

64 focused tests passed in 1.49 seconds: route transactions, real drift versus runtime metadata, monitor-only apply/rollback with worker disabled, disconnection guards, oversized observer journal/health and exact historical recovery.

The earlier evidence replay remains applicable: 19 observer invocation proofs and 20 persisted health documents. No new manual scan, provider, model, research or Telegram call occurred.

## Operator command

```bash
sudo python3 ~/goalvision-operations/admin-monitor-fix.py --apply
```

Expected: ADMIN_MONITOR_COMPAT_DEPLOYED, ADMIN_CODEX_STILL_DISABLED, ADMIN_ALERT_SUMMARY.

The summary reads receipt-backed message counts and fixed transport codes without message bodies or credentials. The separate ADMIN_DELIVERY_DEGRADED cause remains unverified until this root-only diagnostic is returned.

After deployment inspect natural monitor scans/observer output. Historical false MISSING_OUTPUT incidents recover only on exact invocation proof, up to two per scan. Some recovery notifications can therefore appear while the old backlog clears. No incident/job/receipt history is deleted.

Rollback only if separately needed:
```bash
sudo python3 ~/goalvision-operations/admin-monitor-fix.py --apply --rollback
```

Codex must remain disabled during rollback as well.
