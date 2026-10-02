# ADMIN incident flood — 2026-10-02

Status: code/regression/replay PASS; production deployment and subsequent natural scans NEEDS_MORE_EVIDENCE.

## Findings

The inspected window starts at 2026-10-01 22:13 Europe/Riga, after PREMATCH quality deployment. At 07:53 Riga there were **40 failed Auto-Repair jobs**, all CODEX_EXIT, 0 changed files, lasting 0.579–1.039 seconds. Their triggering rules were 20 MISSING_OUTPUT, 19 MONITORING_COVERAGE_DEGRADED and 1 ADMIN_DELIVERY_DEGRADED. These are not 40 independent PREMATCH execution failures. Exact Telegram message count was unavailable to the arvis account because the ADMIN database requires elevated read access. No permissions were changed.

1. **Observer output falsely absent.** journalctl JSON omits MESSAGE values over 4096 bytes without --all. All 19 sampled natural observer records had null MESSAGE under the old query and complete valid 6822–6913-byte JSON with --all. The fix covers both the incremental reader and exact-invocation late recovery. Existing byte/time/record bounds and invocation attribution remain enforced.
2. **Performance documents exceed the monitor contract.** One cycle_health and 19 observer_runs records exceeded 128 KiB. Full performance was correctly persisted by the quality release, but the monitor rejected it. The monitor now removes only root PERFORMANCE from an oversized valid document before applying its unchanged 128 KiB health limit. Raw JSON is independently capped at 4 MiB, scan rows at 128 and SQL retains the existing deadline. Publication, failure and other fields are preserved; large remaining payloads still fail closed. Producer documents/history are never rewritten.
3. **Codex CLI never reached an agent task.** Installed Codex 0.158.0 rejects combined --sandbox and --approve-for-me. Explicit read-only / workspace-write modes now use approval_policy="on-request" and approvals_reviewer="auto_review", with strict config validation and the existing config/rules isolation, disabled tools/network, disposable clone and diagnosis edit rejection. No bypass or fallback was added.
4. **Forward compatibility.** Structured RESEARCH_DATASET_NOT_READY and CALIBRATION_DATASET_NOT_READY are recognized as final research output. Required counts/blocking evidence are checked; calibration must explicitly show no cycle or holdout consumed.

The separate ADMIN_DELIVERY_DEGRADED incident is **NEEDS_MORE_EVIDENCE**: the sanitized job bundle has no transport code. Do not assume rate limiting or label it a false alarm. The operator command prints a bounded read-only transport diagnostic.

## Evidence and tests

- 352 ADMIN/worker tests and 79 subtests passed with a process-local network guard.
- 15 deployment/rollback/diagnostic tests passed.
- Existing natural evidence replay: all 19 exact observer invocation proofs recognized; 20 health documents produce exactly the events from their full originals. Zero coverage errors and zero real fault rules in that sampled health window; source-copy bytes unchanged. Replay took 0.0117 seconds.
- Actual installed CLI, empty stdin only: old arguments exit 2 with the conflict; both new sandbox variants pass argument parsing and exit 1 with "No prompt provided via stdin." No model task or job was launched. This proves parser compatibility, not full authenticated model execution.
- Evidence: docs/evidence/admin_compat_20261002/{incidents,read_only_replay,tests,package_preflight}.json.
- Official configuration reference: https://learn.chatgpt.com/docs/config-file/config-reference (approval_policy and approvals_reviewer, accessed 2026-10-02).

## Changed files

Runtime: app/admin_alerts/sources.py, app/admin_alerts/output_contracts.py, app/admin_autorepair/worker.py.

Operations: operations/admin-autorepair/update_compat.py, verify_compat.py and the existing offline rehearse fake CLI.

Tests: tests/admin_alerts/test_quality_compatibility.py, tests/admin_autorepair/test_worker.py, test_compat_upgrade.py. TASKS.md and the original worker runbook are updated.

## Operator handoff

The prepared, hash-validated package updates only the two ADMIN releases. It preserves prior startup/clone fixes, active timer states, source releases and rollback. It waits for in-flight ADMIN work; it never kills or retries jobs. A running job can produce ADMIN_JOB_RUNNING_RETRY_AFTER_COMPLETION; retry the same installer only after natural completion.

```bash
sudo python3 ~/goalvision-operations/admin-alert-fix.py --apply
```

Expected marker: ADMIN_COMPAT_DEPLOYED. Then ADMIN_ALERT_SUMMARY gives receipt-backed message counts and fixed transport result codes since deployment. No message bodies, credentials or recipient IDs are printed. Read-only diagnostic separately:

```bash
sudo python3 ~/goalvision-operations/admin-alert-fix.py --diagnostic
```

Rollback if separately authorized:

```bash
sudo python3 ~/goalvision-operations/admin-alert-fix.py --apply --rollback
```

After deployment inspect the next natural monitor scans and observer completion. Exact historical MISSING_OUTPUT recovery is bounded to two unresolved invocations per scan; old recovery messages may appear while the backlog clears. Existing incidents, failed jobs, outbox, delivery receipts and statistics are preserved. A future legitimate natural worker job is required to establish full Codex execution; no failed job is retried.

No production deployment was performed by the agent. PREMATCH discovery/observer/research/settlement, weekly, Official, LIVE, selection thresholds, odds policy, provider calls and champion are unchanged. No manual cycle or Telegram test send.
