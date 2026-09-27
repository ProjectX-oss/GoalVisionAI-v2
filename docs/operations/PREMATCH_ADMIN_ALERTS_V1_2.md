# PREMATCH ADMIN alerts v1.2 — invalidate legacy output assumptions

**Status: ADMIN_ALERTS_V1_2_READY_FOR_OPERATOR_PREFLIGHT. Prepared, not deployed.**

Live verification remains **LIVE_ADMIN_STATE_REQUIRES_OPERATOR_PREFLIGHT**. The current account cannot read the installed ADMIN configuration or database. This access limitation is not a software failure. No sudo, passwords, configuration changes, service control, daemon-reload, API calls or Telegram sends were used in this work.

Branch: `codex/prematch-admin-alerts-v1-2`.
Base: `cf91784f3c4618e553c57e9d0f9aebe8ec946a12` (`codex/prematch-admin-alerts-v1-1`).
Installed upgrade source: **v1 `7acdec28bb759ab89c6f0a913d0856fbe8c885c8`**.

## Why v1.1 was not deployed

V1.1 added reviewed output contracts and exact journal recovery, but deliberately retained the old settlement absence incidents OPEN. Because settlement has `StandardOutput=null`, its final stdout cannot satisfy a journal-output contract. V1.1 therefore left stale pending false alerts that could be sent if ADMIN delivery were enabled later. V1.2 includes the v1.1 code plus an explicit invalidation lifecycle. **Install directly from v1 to v1.2; do not install v1.1 first.**

The current loaded settlement route was checked again: `StandardOutput=null`, `StandardError=journal`, `NeedDaemonReload=no`. This establishes the reviewed contract, not the historical producer outcome.

## Lifecycle and audit

The generic eligibility predicate in `app/admin_alerts/invalidation.py` requires all of:

- `MISSING_OUTPUT` in OPEN, REPEATED or ESCALATED state.
- An explicit entry in the reviewed contract registry with source NONE and association UNAVAILABLE.
- The complete legacy Event evidence shape: `source=journal-output`, empty facts, `healthy=false`, debounce 1, matching service/rule/object/invocation, occurrence equal to the known invocation, and only journal-output occurrence sources.
- No independent incident for the same service/invocation. Even a later recovered independent failure conservatively vetoes invalidation.
- No existing invalidation audit record (checked by the transactional transition).

Unknown or contradictory evidence is retained for review. Discovery TIME_WINDOW_ONLY and STRUCTURED_JOURNAL_JSON incidents remain unchanged by invalidation. SERVICE_FAILURE, ANALYSIS_FAILURE, DELIVERY_UNCERTAIN, CYCLE_PERSISTENCE and all other rules retain their existing behavior. Genuine settlement failures stay actionable.

After source ingestion, before enqueue/dispatch, one ADMIN transaction appends an immutable `invalidations` record and changes only the original incident's state to **INVALIDATED**. Every other incident field remains unchanged, including evidence, timestamps, count, invocation, generation and notification history. Occurrences are preserved. The audit stores the original complete incident and outbox rows, invalidation time, and:

```json
{"reason":"OUTPUT_CONTRACT_NOT_APPLICABLE","contract_source":"NONE","contract_version":1,"invalidated_by":"ADMIN_ALERTS_V1_2"}
```

SQLite triggers reject updates/deletes of this audit. Retention excludes invalidated incidents' occurrences, outbox and attempts. Replay and healthy events cannot reopen or recover the invalidated tombstone. A transaction failure rolls back incident, audit and outbox changes together.

INVALIDATED means the old absence alert is no longer valid evidence of failure. **It does not claim producer success and is never RECOVERED.** No recovery event or notification is generated.

An outbox entry becomes SUPERSEDED only when it is PENDING, attempts=0, acknowledged=0, has no receipt and has no attempt record. Delivered, attempted or uncertain rows remain byte-identical; their original status, receipts and attempts remain visible. Dispatch excludes their invalidated parent, so no retry occurs. Enqueue explicitly allows only OPEN, REPEATED, ESCALATED and eligible RECOVERED work. Dispatch applies the same lifecycle restriction before transport validation and send selection.

The sanitized report exposes the original evidence and separate invalidation reason/time. `active_fault_count` excludes INVALIDATED and RECOVERED. `monitoring_state` depends on unresolved coverage incidents across the whole database, including those outside the bounded report list; invalidation alone cannot make it DEGRADED.

## Verification

**107 complete ADMIN tests passed**, with socket connection guards and **zero network attempts**. No historical, model, producer or full repository test suite was run.

Tests cover generic NONE invalidation, another reviewed service, strict legacy evidence, contradictory service failure, unrelated rule preservation, structured-journal absence, discovery uncertainty, original incident preservation, immutable durable audit, never-attempted superseding, fake sender enablement without validation/send, attempted/acknowledged/uncertain history, repeat scan, restart, replay, transactional failure, retention, reporting, source immutability, read-only preflight, unsafe sidecars, scan-lock contention, package tampering, sender-enabled rejection, loaded-route drift, direct v1 migration and rollback with preserved database/configuration/PREMATCH bytes.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/admin_alerts -p 'test_*.py' -q
```

The final complete run additionally patched `socket.socket.connect` and `socket.create_connection` to fail and count real networking. `git diff --check` passed. Changed paths are confined to ADMIN application code, ADMIN operations, ADMIN tests and this ADMIN documentation.

### Reconstructed direct-upgrade evidence

[Evidence summary](PREMATCH_ADMIN_ALERTS_V1_2_EVIDENCE.json). The standalone rehearsal uses the actual v1 package code to create isolated incidents from the operator-provided invocations, then scans twice with the final v1.2 package. All producer adapters are fake; no host monitor scan was performed. It preserves the original v1 cursor and incident fields, verifies two durable audits after restart, and enables a fake sender that fails if validation or sending is attempted.

| Operator-reported incident | Reconstructed v1.2 state | Outbox | Attempts |
|---|---|---|---|
| `7f2cfe2a621b163f2367ac94` | INVALIDATED | SUPERSEDED | 0 |
| `d9f68a79d28d17a4bcb88d10` | INVALIDATED | SUPERSEDED | 0 |

Reconstructed monitoring state: AVAILABLE; active faults: 0; API calls: 0; Telegram sends: 0. These are **offline results**, not observed live transitions. IDs are generated from normal v1 identities. Application eligibility contains no incident-ID special cases. Package metadata records the operator's two observed IDs solely so preflight verifies those observations using the shared generic predicate.

Reproduce into a new isolated directory:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 operations/admin-alerts/rehearse_v1_2.py --v1-package /home/arvis/goalvision-operations/prematch-admin-alerts-package-v1-final --package /home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-2-final --state /tmp/goalvision-admin-alerts-v1-2-rehearsal --invocation 98ef19a6d7cd463a8f03842c5decd889 --invocation 7e9844d0c9a54464a4fde8bd7ce6417e
```

## Direct v1 → v1.2 package

Use only `/home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-2-final`. The unsuffixed v1.2 directory is superseded. V1.1 packages must not be installed.

Archive: `/home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-2-final.tar.gz`.

Archive SHA256: `a3fee3a79fa946d877e7e95e42369154e22ea975a7b03fa2e4b4a4bde7a62287`.

`SHA256SUMS` SHA256: `e747128e373a237db2031085eef2b905af55e543488b23d7ef58e678e0e4575f`.

[Payload SHA256 manifest](PREMATCH_ADMIN_ALERTS_V1_2_PACKAGE_SHA256SUMS.txt).
V1 source manifest SHA256: `3a27a9f75996698a5576cff2f3e889d3a5c20d091fb0c891de704b462ac9b7a0`.
The builder pins and verifies that exact v1 distribution. Its ADMIN Python files were also compared against commit `7acdec28bb759ab89c6f0a913d0856fbe8c885c8`.

### Read-only operator check and sender proof

Run the following in an **existing root operator shell**. The check itself makes no files, no SQLite connections to live storage, no service changes and no network calls. Bytecode writes are disabled. It verifies:

1. Pinned package manifest and every payload file; installed v1 manifest and all files.
2. Protected PREMATCH file hashes and unchanged ADMIN unit hashes.
3. Live configuration contains literal `sender.enabled=false`; absent, true or any other value refuses.
4. Live ADMIN database exists, is not a symlink, and can be read under its existing scan lock.
5. No WAL/SHM/journal sidecars and ordinary SQLite rollback-journal format. The database bytes are deserialized into an in-memory, query-only connection; integrity is checked there.
6. Both operator-observed incidents pass the shared generic rule and have only PENDING/attempts=0/unacknowledged/unreceipted outbox work. Additional eligible incidents use the same rule.
7. No retained ADMIN delivery attempt rows, nonzero outbox attempts, receipts, acknowledgments, sent/attempting/uncertain entries or incident notification history. This checks observable durable history; it cannot reconstruct previously deleted records.
8. Loaded service/timer drift, unexpected ADMIN drop-ins, reviewed NONE stdout routing and stable ADMIN timer state.

A busy scan lock refuses safely; retry the read-only check between scans. Any changed observation or drift requires review. A successful check prints CHECKED, the eligible IDs and zero delivery attempts. Compare those IDs with the table above. The unprivileged final-package check returned `LIVE_ADMIN_STATE_REQUIRES_OPERATOR_PREFLIGHT`; live sender state, actual incident evidence/outbox/cursors and eligibility are therefore not independently certified here.

Check (one line):

```sh
cd /home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-2-final && printf '%s  SHA256SUMS\n' 'e747128e373a237db2031085eef2b905af55e543488b23d7ef58e678e0e4575f' | sha256sum -c - && sha256sum --quiet -c SHA256SUMS && /usr/bin/python3 -I ./upgrade_v1_2.py check
```

Upgrade after successful operator preflight (one line):

```sh
cd /home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-2-final && printf '%s  SHA256SUMS\n' 'e747128e373a237db2031085eef2b905af55e543488b23d7ef58e678e0e4575f' | sha256sum -c - && sha256sum --quiet -c SHA256SUMS && /usr/bin/python3 -I ./upgrade_v1_2.py upgrade
```

Rollback (one line):

```sh
cd /home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-2-final && printf '%s  SHA256SUMS\n' 'e747128e373a237db2031085eef2b905af55e543488b23d7ef58e678e0e4575f' | sha256sum -c - && sha256sum --quiet -c SHA256SUMS && /usr/bin/python3 -I ./upgrade_v1_2.py rollback
```

### Upgrade and rollback boundaries

Upgrade stages/fsyncs the complete ADMIN directory, stops only ADMIN timer/service, acquires the ADMIN scan lock, rechecks disabled configuration and live eligibility, then atomically exchanges the code directory with Linux RENAME_EXCHANGE. It restores the prior ADMIN timer activity on success. The package does not edit configuration, credentials, units, enablement or producer files. The database stays at `/var/lib/goalvision-admin-alerts/admin.sqlite`; no database restore, replacement or clearing occurs. Additive schema creation and invalidation happen on the first normal v1.2 scan. With an inactive timer, no scan occurs until a later operator start. After that scan, inspect the sanitized report for the expected lifecycle/outbox results and keep the sender disabled.

Backup: `/opt/goalvision-admin-alerts-v1-2-v1-rollback`.
Transaction: `/opt/goalvision-admin-alerts-v1-2-transaction.json`.
Stage: `/opt/goalvision-admin-alerts-v1-2-stage`.
Interrupted staging refuses further upgrades pending operator inspection; history is never wiped to retry.

Rollback verifies both trees and the unchanged disabled configuration, restores v1 code only, and **leaves ADMIN stopped with the persistent `/var/lib/goalvision-admin-alerts/DISABLED` marker**. The existing systemd condition and v1 scan guard keep it stopped across reboot. This fence is necessary because v1 can treat INVALIDATED as sendable work or regenerate false output incidents. Database history, audits, outbox and cursors remain intact. Do not remove the marker or enable the sender under v1; review a forward v1.2 reinstallation separately. An existing marker is preserved. Failure after directory exchange attempts restoration and leaves ADMIN stopped.

Unit files do not change. Neither upgrade nor rollback calls daemon-reload. The packaged ADMIN kill switch uses the persistent marker plus `systemctl stop`; it avoids `systemctl disable` and its implicit reload. Any future unit change/reload requires a separate loaded-state drift review.

## PREMATCH isolation proof

All installed v1 package hashes were verified unchanged. The read-only loaded-state drift review passed. **1,586 protected PREMATCH configuration/unit/manifest and release Python file hashes** and **18 installed ADMIN file hashes** matched before and after final verification. This measures the verification interval; running producer databases/logs are intentionally not treated as static files.

The code diff is ADMIN-only. Upgrade tests enforce that control commands target only `goalvision-admin-alerts.timer` and `.service`. No discovery, settlement, observer, learning, weekly stats, Lab publication, Official or LIVE controls were executed. No production code/configuration/database was edited. PREMATCH remained running throughout; there was no production deployment, push or merge.
