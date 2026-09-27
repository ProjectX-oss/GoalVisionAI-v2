# PREMATCH ADMIN alerts v1.3

## Handoff status

Implementation and the standalone direct-upgrade package are complete. **Final readiness is blocked on privileged live-state rehearsal.** Do not treat the synthetic projection as verification of the live database.

Branch: `codex/prematch-admin-alerts-v1-3`, directly based on ADMIN v1.2 `d811177fdd11e25b087f036584d33c0e0328906b`. No PREMATCH application branch was used. Changes are confined to ADMIN code, operations, tests and these reports. Nothing was pushed, installed or enabled. No PREMATCH service/timer was controlled. No real Telegram or API-Football calls occurred.

The installed v1.2 payload and unchanged ADMIN service/timer hashes were independently verified. The live ADMIN database and configuration are permission-restricted; `sudo -n true` requires a password. The corrected package’s read-only host rehearsal returned `HOST_REHEARSAL_BLOCKED`. Sender=false and zero historical delivery attempts are operator-provided facts, not newly verified live observations. See [host evidence](PREMATCH_ADMIN_ALERTS_V1_3_HOST.json).

The requested `ADMIN_ALERTS_V1_3_READY_FOR_OPERATOR_PREFLIGHT` status must wait for the read-only root rehearsal below and review of its actual historical group/backlog results. Until then: `ADMIN_ALERTS_V1_3_BLOCKED_HOST_REHEARSAL`.

## Ledger and weekly scan progress

The adapters persist scan state version 2 with `read_available`, `status`, `processed_this_page`, `progress`, cursor, page fingerprint and last advancement time. Normal full pages produce `SCAN_IN_PROGRESS`; final pages produce `SCAN_COMPLETED`. Neither opens an incident, enqueues a notification nor degrades monitoring. Later sweeps start normally. The sanitized report exposes progress fields without raw claim cursors.

A stalled page becomes a real coverage warning after **1,200 seconds without advancement**, allowing four normal five-minute polls. Repeated pages, nonadvancing cursors and invalid cursor/schema/read state remain observable. Each successful advancement resets the deadline. Migration of an unversioned v1.2 cursor starts its observation window on the first v1.3 page. Active-producer deferral retains its separate existing 15-minute warning threshold; a brief deferral does not fault.

Legacy ledger/weekly `MONITORING_COVERAGE_DEGRADED` incidents whose retained reason is exactly `UNRESOLVED_SCAN_IN_PROGRESS` become `INVALIDATED`, with reason `SCAN_PROGRESS_NOT_MONITORING_FAILURE`. This happens before ingesting new health so the original evidence is available for audit. It preserves IDs, count, timestamps, evidence and the complete original outbox snapshot. Never-attempted PENDING notifications become `SUPERSEDED`; attempted, uncertain, acknowledged and receipted histories remain unchanged. Invalidation generates no recovery message. A new coverage identity avoids letting an invalidated tombstone hide a future real fault, while genuine legacy coverage failures still recover normally.

## Correlation and presentation

V1.3 retains separate source incident rows and append-only `source_evidence`. New execution incidents use execution-specific identities; existing v1.2 IDs are reused only for the same source rule/service/invocation. No production incident ID is rewritten, merged or deleted.

Precedence is specific actionable cause, `SERVICE_FAILURE`, `ANALYSIS_FAILURE`, then `MISSING_OUTPUT`. `QUOTA_DB_CONTENTION` has highest precedence. Exact grouping requires the same service and known InvocationID. An UNKNOWN-invocation persisted health `ANALYSIS_FAILURE` joins only a unique same-service `SERVICE_FAILURE` within **30 seconds**, using original first-failure timestamps. Its invocation remains UNKNOWN and its association is `UNIQUE_TEMPORAL_SAME_SERVICE`. Other unknown evidence remains independent. A later competing candidate removes the temporal association from the current projection and permits an independent notification; earlier audits and superseded outbox records remain intact.

`correlation_audit` stores stable correlation ID, primary/supporting incidents, service, invocation, per-member associations, creation time, rule version and source snapshots. Database triggers prohibit audit updates/deletes. Restart reconstructs the same grouping. `notification_audit` preserves original outbox rows and the supersession reason. Existing notification bodies can be refreshed only before their first attempt.

Only the primary gets an initial automatic alert. Unattempted supporting notifications are superseded with an audit. Already-attempted support remains unchanged and is held for operator reconciliation. **Escalation policy V1: no second automatic execution-fault alert after any member was attempted.** More actionable late evidence changes the local primary/report. No automatic root-cause update or 30-minute crash reminder is sent. An eligible explicit primary recovery remains governed by the existing recovery lifecycle; invalidation never claims recovery. Independent nonexecution rules retain their previous notification behavior.

Alerts contain short Latvian descriptions, fixed machine codes, incident/invocation identifiers and Europe/Riga time. They contain no raw exceptions, credentials, payloads, environment or locals. History pruning is disabled for v1.3 so source/delivery/audit evidence is retained; future storage retention requires a separately reviewed policy.

### Historical database-lock case

Supplied invocation: `1149428ce2d749cb9a1335fbceb78bd9`. The supplied privileged evidence establishes a real database-lock crash with exit status 1. Application code contains no special case for this invocation.

The [synthetic contract projection](PREMATCH_ADMIN_ALERTS_V1_3_PROJECTION.json) creates one SERVICE_FAILURE primary with MISSING_OUTPUT exact support and ANALYSIS_FAILURE temporal support. It reports one group, no scan-progress fault, one legacy invalidation, backlog suppression and preserved delivery-attempt history. The health timestamp proximity in this fixture is synthetic. **The real UNKNOWN health association and live backlog count remain unverified** until the root snapshot rehearsal returns its JSON. If real timestamps are ambiguous or outside 30 seconds, health remains independent by design.

## Quota classification

`QUOTA_DB_CONTENTION_EXHAUSTED` maps to severity 3 `QUOTA_DB_CONTENTION`. Trusted journal attribution carries the exact invocation through machine-code parsing, so a matching service failure/output symptom becomes support. The machine code is retained in evidence.

Latvian meaning: “PREMATCH API kvotas rezervācijas datubāze bija aizņemta ilgāk par drošo 500 ms robežu. HTTP pieprasījums netika sākts.” This follows the operator-provided frozen hardening contract: HTTP transport starts only after durable quota reservation. This ADMIN work does not change or call PREMATCH quota code.

`QUOTA_DB_CONTENTION_RETRY` never notifies. `result=DEGRADED`, `quota.status=REDUCED_TO_PRESERVE_QUOTA`, `failure=null` produces no fault. Actual quota-unavailable, provider and authentication rules remain in place, including their existing debounce where applicable.

## Activation boundary

`prepare-enable` is read-only. It reports sender/config readiness without identities or token contents, active group summaries, unresolved incidents, invalidated/superseded counts, unsent backlog, attempt count and epoch state. It opens an existing ADMIN scan lock, copies ordinary SQLite bytes to memory and uses query-only SQLite there. WAL/SHM/journal sidecars or lock contention refuse inspection rather than risk modifying live storage.

`enable-sender --confirm ENABLE_PRIVATE_ADMIN_NEW_INCIDENTS_ONLY` is a separate explicit root operation. It requires the installed v1.3 hashes, unchanged ADMIN units, literal sender=false, configured identity/private destination, operator start confirmation and matching token identity. It reuses installed configuration and performs no Telegram validation or test send. Normal future dispatch retains its configured identity/private-chat checks.

Activation serializes ADMIN operations, fences ADMIN persistently, stops only ADMIN timer/service, and takes the scan lock. It commits `ADMIN_NOTIFICATION_EPOCH_V1`, records each existing incident ID, current episode and current generation in the immutable `epoch_incidents` snapshot and audits pre-epoch never-attempted PENDING notifications as `PRE_ENABLEMENT_BACKLOG_SUPERSEDED`. Then it atomically replaces/fsyncs configuration, preserving ownership/mode and every other field, and verifies it. Only the previously active ADMIN timer is restarted. Live scan re-reads config under the lock; sender=true without an epoch cannot dispatch.

**Activation suppresses the pre-enablement episode, not the incident identity.**

The activation snapshot contains `incident`, `epoch`, `episode_at_activation` and `generation_at_activation`. Update, delete and replacement guards keep it immutable. The epoch policy is `PRE_ENABLEMENT_EPISODES_SUPPRESSED_V1`; the epoch ID remains `ADMIN_NOTIFICATION_EPOCH_V1`.

For a snapshot member, the same episode stays suppressed through repeats, reminders, escalation and explicit recovery. Stronger evidence remains visible locally. Recovery of a suppressed fault does not produce a recovery notification. A later fault after `RECOVERED` uses the existing Store episode increment and becomes eligible, even with the same incident ID and historical `first_seen`. No snapshot row means normal eligibility; source timestamp age alone never suppresses an incident.

New outbox rows record their episode and retain the existing generation-based durable notification identity. Enqueue and dispatch both check the episode boundary. Old SUPERSEDED rows and notification/correlation audits remain intact. Old attempted, uncertain, acknowledged and receipted notifications remain held for operator reconciliation, even after recurrence; they neither retry nor block fresh stable-incident notification work. Exact-invocation correlation and its conservative execution escalation policy remain in force.

Migration adds nullable snapshot fields and a nullable `outbox.episode` to existing ADMIN storage without backfilling historical guesses. The reviewed v1.2 path takes a fresh complete activation snapshot. Already-activated legacy v1.3 policy, unknown snapshot episode/generation, mismatched epoch or regressed counters fail closed. `activation_review_required` in preparation/status and `activation_hold` in the incident report expose these cases. Operators must review them; do not delete an epoch or edit old notifications to permit sending. The epoch is never deleted to retry. Activation replay, including re-enablement after disable, is explicitly refused and requires review. If database preparation or enabling fails, the sender remains/restores false and ADMIN stays fenced/stopped. A failure after config replacement or timer start is covered by the same fail-closed path. If underlying storage also prevents restoring configuration, the persistent ADMIN fence is the additional protection; operator repair is required.

`disable-sender` stops future ADMIN dispatch, persists sender=false and preserves monitoring/evidence by restoring a previously active ADMIN timer when safe. An existing fence is preserved. Disable does not require readable token material or a DB preflight. An in-flight network request cannot be retracted; the fence stops subsequent sends. It never controls PREMATCH.

## Direct v1.2 upgrade and rollback

Only use `/home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-3-epoch-corrected`.

The previous `prematch-admin-alerts-upgrade-v1-3-operator-review` package is **SUPERSEDED and MUST NOT be installed**. Its original payload is preserved with an unmanifested `SUPERSEDED_DO_NOT_INSTALL.json` marker, which causes its controller to refuse package verification. Its archive was preserved byte-for-byte under `prematch-admin-alerts-upgrade-v1-3-operator-review.SUPERSEDED-DO-NOT-INSTALL.tar.gz`. See [supersession record](PREMATCH_ADMIN_ALERTS_V1_3_SUPERSEDED.json). Earlier v1.3 review/final/final-r1 directories are also superseded development artifacts.

The builder pins the reviewed installed v1.2 manifest. Upgrade stages/fsyncs the new ADMIN tree, verifies old/new manifests and unchanged ADMIN unit hashes, stops/fences ADMIN only, acquires its scan lock and exchanges complete code directories atomically. Database, config and token are retained in place. Upgrade requires sender=false and leaves it false. Additive schema creation, legacy invalidation and grouping occur in v1.3 monitoring. No unit change or daemon-reload occurs.

Preserved paths:

- `/var/lib/goalvision-admin-alerts/admin.sqlite`
- `/etc/goalvision-admin-alerts/admin-alerts.json`
- `/etc/goalvision-admin-alerts/admin-token`

Rollback uses `/opt/goalvision-admin-alerts-v1-3-v1-2-rollback`, explicitly disables the sender and restores code only. It preserves the current database and every audit/delivery record. It leaves ADMIN stopped and `/var/lib/goalvision-admin-alerts/DISABLED` present because v1.2 cannot safely interpret v1.3 notification semantics. Do not remove that fence to run old logic. Interrupted transactions refuse replay and require operator review; no state-clearing shortcut is provided.

## Validation

**148 complete ADMIN tests passed**, with socket connection guards and **zero real network attempts**. No historical/model suite or PREMATCH application test suite ran. No shared production code changed. See [test summary](PREMATCH_ADMIN_ALERTS_V1_3_TESTS.json).

Tests cover normal/final/repeated ledger and weekly sweeps; stalled/corrupt/unavailable scans; no progress incident/outbox/degradation; legacy invalidation and future real-fault recovery; exact/unique/ambiguous/competing/different-invocation associations; immutable audits and stable restart; already-sent/uncertain/attempting history; quota exhaustion/retry/protection/unavailable; read-only preparation; epoch/backlog/post-epoch delivery; config/audit/timer-start failures; explicit confirmation/replay refusal; secret-safe output; direct v1.2-shaped DB and config/token/cursor preservation; ADMIN-only control; disable with unavailable token; fenced rollback.

The focused recurrence regressions cover timer, provider, quota, coverage and execution incidents; recovery followed by a new episode with and without restart; exactly one new fake fault send; unchanged old supersession/audits; same-episode escalation; debounce; new incidents and late source evidence without snapshot membership; all attempted outbox states; actual v1.2 outbox migration; immutable snapshot replacement rejection; malformed/legacy state; and atomic activation refusal. Prediction logic is unchanged, so model backtesting is outside this patch.

Reproduce offline:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 operations/admin-alerts/test_v1_3_offline.py --output /tmp/goalvision-admin-alerts-v1-3-tests.json
```

## Package hashes

Archive: `/home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-3-epoch-corrected.tar.gz`

Archive SHA256: `1b3cff703c4c119ba62b15ead3f0dc14a45bcdf63fe2d2a918eb1d739e2cd96f`

`SHA256SUMS` SHA256: `a1439c9f61b31582af8a2908770ccd7d523f6fc973eabb7c423e81cc0d1351fc`

[Payload manifest](PREMATCH_ADMIN_ALERTS_V1_3_PACKAGE_SHA256SUMS.txt) · [package hash record](PREMATCH_ADMIN_ALERTS_V1_3_PACKAGE.json)

## Exact one-line operator commands

Use an existing root shell. These are prepared instructions, not actions executed during development. Complete the read-only rehearsal/preflight and review the results before upgrade; sender activation remains a separate later decision.

Read-only snapshot rehearsal, required to close the current evidence gap:

```sh
cd /home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-3-epoch-corrected && printf '%s  SHA256SUMS\n' 'a1439c9f61b31582af8a2908770ccd7d523f6fc973eabb7c423e81cc0d1351fc' | sha256sum -c - && sha256sum --quiet -c SHA256SUMS && /usr/bin/python3 -I ./rehearse_v1_3.py --invocation 1149428ce2d749cb9a1335fbceb78bd9
```

Check installed v1.2, read-only:

```sh
cd /home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-3-epoch-corrected && printf '%s  SHA256SUMS\n' 'a1439c9f61b31582af8a2908770ccd7d523f6fc973eabb7c423e81cc0d1351fc' | sha256sum -c - && sha256sum --quiet -c SHA256SUMS && /usr/bin/python3 -I ./control_v1_3.py check
```

Upgrade, sender remains false:

```sh
cd /home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-3-epoch-corrected && printf '%s  SHA256SUMS\n' 'a1439c9f61b31582af8a2908770ccd7d523f6fc973eabb7c423e81cc0d1351fc' | sha256sum -c - && sha256sum --quiet -c SHA256SUMS && /usr/bin/python3 -I ./control_v1_3.py upgrade
```

Status after upgrade, read-only:

```sh
cd /home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-3-epoch-corrected && printf '%s  SHA256SUMS\n' 'a1439c9f61b31582af8a2908770ccd7d523f6fc973eabb7c423e81cc0d1351fc' | sha256sum -c - && sha256sum --quiet -c SHA256SUMS && /usr/bin/python3 -I ./control_v1_3.py status
```

Prepare-enable, read-only:

```sh
cd /home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-3-epoch-corrected && printf '%s  SHA256SUMS\n' 'a1439c9f61b31582af8a2908770ccd7d523f6fc973eabb7c423e81cc0d1351fc' | sha256sum -c - && sha256sum --quiet -c SHA256SUMS && /usr/bin/python3 -I ./control_v1_3.py prepare-enable
```

Enable, separate explicit confirmation:

```sh
cd /home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-3-epoch-corrected && printf '%s  SHA256SUMS\n' 'a1439c9f61b31582af8a2908770ccd7d523f6fc973eabb7c423e81cc0d1351fc' | sha256sum -c - && sha256sum --quiet -c SHA256SUMS && /usr/bin/python3 -I ./control_v1_3.py enable-sender --confirm ENABLE_PRIVATE_ADMIN_NEW_INCIDENTS_ONLY
```

Disable:

```sh
cd /home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-3-epoch-corrected && printf '%s  SHA256SUMS\n' 'a1439c9f61b31582af8a2908770ccd7d523f6fc973eabb7c423e81cc0d1351fc' | sha256sum -c - && sha256sum --quiet -c SHA256SUMS && /usr/bin/python3 -I ./control_v1_3.py disable-sender
```

Rollback, sender false and ADMIN fenced:

```sh
cd /home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-3-epoch-corrected && printf '%s  SHA256SUMS\n' 'a1439c9f61b31582af8a2908770ccd7d523f6fc973eabb7c423e81cc0d1351fc' | sha256sum -c - && sha256sum --quiet -c SHA256SUMS && /usr/bin/python3 -I ./control_v1_3.py rollback
```
