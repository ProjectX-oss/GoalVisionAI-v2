# PREMATCH ADMIN alerts v1

Status: **ADMIN_ALERTS_V1_READY_FOR_REVIEW** — software and standalone package prepared. Sender configuration is incomplete; monitor is **not installed or running**. No production deployment, sudo, football API request or Telegram send occurred.

## Verified baseline and scope

Worktree: `/home/arvis/goalvision-operations/prematch-admin-alerts`.
Branch: `codex/prematch-admin-alerts`, created from verified application `23e57e9c48f321b8ee5f67bd536fbb2b264f6cb0`. Accepted public-message operations lineage remains `f5ae4750ec6d303e98e4a72af712ecd67dfb1322`. No LIVE branch was used.

The loaded discovery, settlement, observer and weekly services use `/home/arvis/GoalVisionAI-prematch-release-public-message-v2-20260926`. Nightly learning separately uses the release configured through `/etc/goalvision-prematch-release.conf`, currently `363f567`. Discovery's loaded command proves `new_picks=true`, `observe=true`, `labels=true`. These are configured capabilities, not proof that every invocation succeeds.

Initial inventory found discovery's last completed invocation failed on 26 September at 21:30 CEST; no root cause was inferred. By the single rehearsal at 27 September 06:00 UTC, scheduled daytime invocations were active. This transition was caused by the existing timers. The monitor did not operate any PREMATCH unit.

[Recorded host inventory](PREMATCH_ADMIN_ALERTS_V1_HOST.json) contains loaded safe properties, source permissions, capability checks and SHA-256 fingerprints of PREMATCH unit files, drop-ins, release environments and the existing deployment manifest. No existing manifest was changed. Installed application `git diff --name-only` was empty.

| Service | Loaded timer schedule | Loaded start timeout |
| --- | --- | --- |
| `goalvision-lab-v2-discover.service` | `*-*-* 09..22:00,30:00 Europe/Riga` | 30 minutes |
| `goalvision-lab-combo-settle.service` | `*-*-* *:00/10:00` (host timezone) | 10 minutes |
| `goalvision-adaptive-learning-observer.service` | `*-*-* *:00/30:00` (host timezone) | 10 minutes |
| `goalvision-adaptive-learning.service` | `*-*-* 04:15:00` (host timezone) | 30 minutes |
| `goalvision-lab-weekly-stats.service` | `Sun *-*-* 22:30:00 Europe/Riga` | 2 minutes |

Discovery/settlement/observer/learning timers have one-minute accuracy; weekly accuracy is one second. Random delay was zero. The monitor reads these values each scan. It does not encode discovery's cadence into another service's rules.

## Existing functionality and reuse decision

Narrow inventory covered configuration key names, Telegram helpers, compact-output projection, persisted health and operational monitoring candidates. `app/services/telegram_service.py` provides bounded Telegram receipt semantics but imports the Telegram dependency and cannot pin both bot identity and private-chat type. No compatible dedicated ADMIN operational outbox or command-handling integration was found. Existing model/forward-test monitoring concerns predictive evaluation and would write to producer-owned stores.

The sidecar reuses the deployed `goalvision-lab-v2-operator-cycle-v1` contract, existing health schema/indexes, immutable claim/receipt identities, and the existing transport's acknowledgement validation convention. It does not import or execute producer repositories, runners, migrations, health aggregation or secret-loading modules with startup side effects. The standard-library transport and ADMIN outbox are isolated because the available components do not provide that boundary.

No explicit ADMIN token, expected username/ID, private recipient or `/start` confirmation was found in the narrowly inspected configuration. The inspection printed key names/presence only. Generic, Lab and LIVE tokens are never borrowed. This is an enablement prerequisite, not an invented destination.

## Independent runtime and evidence

`app/admin_alerts/` has no producer integration. The oneshot reads evidence, commits ADMIN occurrences and cursors, closes producer connections, then optionally delivers ADMIN messages. PREMATCH never calls it or waits for it. There are no producer `OnFailure`, wrappers, pre/post hooks, dependencies, publication switches, schema changes or repair actions.

Sources:

- Loaded systemd properties for precisely the five services and their timers: completion/result/status, invocation, monotonic execution timestamps, timeout, activity, schedule, deadlines, accuracy, delay and pending reload flag.
- Journald for those five units, including systemd manager `UNIT` records. Cursor, boot and invocation identity are retained. Before trusting an empty response, the final adapter checks readable system-journal files. No global unfiltered message query is used.
- `/var/log/goalvision-prematch/discovery-output.log`, interpreted through the existing compact contract. Analysis/delivery status, terminal failure, cycle persistence, per-prediction transport/acknowledgement/receipt/reconciliation facts are evaluated separately.
- `/home/arvis/GoalVisionAI/var/adaptive_lab/audit.db`: indexed PREMATCH `cycle_health` and `observer_runs`, plus exact weekly claim/receipt identities.
- `/home/arvis/GoalVisionAI/var/lab_combo/ledger.db`: primary-key claim pages and exact matching receipt lookups, including old unresolved claims.

The initial log window is at most one MiB; stdout evidence older than monitor start minus 15 minutes is not paged as new. Current failed systemd state is inspected immediately, regardless of age. Existing unresolved claim evidence remains an explicit current issue. Historical claim enumeration is paged; coverage remains incomplete until a pass finishes.

A claim lacking a receipt proves uncertainty, not that Telegram was called. Claims are reviewed only while all allowlisted producers are known inactive, avoiding a race with in-progress publication. Temporary deferral is reported as UNKNOWN; deferral lasting 15 minutes raises coverage degradation. This also means an old unresolved claim can be discovered later than the first scan.

### Read and resource bounds

| Work | Bound |
| --- | --- |
| Whole scan | Python alarm 40 seconds; service timeout 45 seconds; network phase stops before 35 seconds |
| External read subprocess | 3 seconds, 1 MiB stdout, no shell; release lookup 1 second/128 bytes |
| Stdout | 1 MiB/scan, 512 records, 128 KiB/record; two extra 64-byte offset anchors |
| Rotation lookup | At most 64 directory entries; previous inode drained first |
| Journal | First 256 entries after cursor; 15-minute initial window; 1 MiB subprocess cap |
| SQLite | `mode=ro`, `query_only=ON`, 100 ms busy wait, 300 ms progress deadline |
| Health query | Existing `(stream,created_at,id)` index, 128 rows/table; 128 KiB/document ceiling |
| Claim query | Existing primary keys, 128 claims/page and bounded exact receipt lookups |
| Database polling | At most once every five minutes |
| Pending completion association | 25 sanitized entries; overflow is an explicit coverage gap |
| Notification queue preparation | Up to 1,000 eligible incidents/scan; pending rows do not starve later incidents |
| Transport | Three-second socket timeouts, whole-scan deadline, at most 5 messages/scan and 20/hour |
| Process limits | CPU 20%, memory 128 MiB, 16 tasks, nice 15, idle I/O |

Producer connections are short and closed before network activity. No migrations, integrity sweeps, checkpoint, vacuum, journal-mode change or `immutable=1` is used. **Live WAL reads require a read-only mount and existing SHM.** `mode=ro` alone is insufficient to prevent SHM writes. The prepared service supplies read-only producer mounts; development skips WAL sources unless this guarantee is present. Missing schemas/indexes/access yield coverage incidents. No substitute writable repository is opened.

Stdout cursor state contains device/inode, byte offset, a hash of the partial tail, and a hash of the preceding offset bytes; it does not retain raw partial content. Small partial records are reread from their start. Blank lines are harmless. Partial tails become incomplete evidence only after the producer is not running and the bytes remain unchanged for three minutes. Oversized records are discarded in bounded chunks until newline, with a coverage gap. Rename rotation drains the previous inode; a stale incomplete old tail eventually yields to the replacement with a reported gap. Truncation, replacement, lost inodes and detected in-place rewrites are explicit gaps. An unbounded historical record cannot consume unbounded memory.

## Rules, severity, debounce and recovery

Rules are version 1. Severity 3 is critical; severity 2 is warning. A rule identifier provides the normalized error category. Signatures include service, rule version/category and affected object, excluding timestamps. Each ingestion occurrence is separate from notification attempts and source cursors.

| Evidence | Rule / severity | Eligibility and recovery |
| --- | --- | --- |
| Completed nonzero exit, signal, timeout, core dump | `SERVICE_FAILURE`, warning | Immediate; recover only after a later completed successful invocation |
| OOM completion | `SERVICE_FAILURE`, critical | Immediate; same explicit completion recovery |
| Terminal/FAILED analysis | `ANALYSIS_FAILURE`, warning | Immediate; recover on explicit later completed healthy analysis |
| FAILED/DEGRADED/UNKNOWN publication | `DELIVERY_FAILURE`, warning | Immediate; object-specific receipt evidence required for object recovery |
| Transport without receipt, acknowledged without receipt, explicit reconciliation, claim without receipt | `DELIVERY_UNCERTAIN`, critical | Immediate; exact prediction/report receipt resolves it; unrelated successful sends never do |
| Cycle/receipt persistence failure | `CYCLE_PERSISTENCE`, critical | Immediate; no inferred recovery from later unrelated cycles |
| Explicit schema/identity/integrity or settlement/statistics blocker | `INTEGRITY_FAILURE`, critical | Immediate; remains open absent authoritative resolution |
| Observation construction or finish failure | `OBSERVATION_FAILURE`, critical | Immediate from deployed `football_context_observation` diagnostics; no guessed recovery |
| Explicit authentication failure | `AUTH_FAILURE`, critical | Immediate; no endless authentication retries |
| Recoverable provider/rate-limit failure, database lock, unusable quota/data | Corresponding warning | Two distinct successive affected completed runs; explicit usable health resets the streak |
| Cached timer deadline passes without trigger/start | `MISSING_START`, warning | Actual deadline + accuracy + random delay + 3 minutes; explicit subsequent start resolves |
| Running longer than loaded timeout + 1 minute | `RUNNING_LONG`, warning | Never uses short discovery assumptions; completed invocation resolves |
| Completed invocation lacks expected evidence after 3 minutes | `MISSING_OUTPUT`, warning | Discovery uses compact evidence window; other services use invocation-linked structured journal output; no guessed retrospective resolution |
| Unexpected inactive/disabled/masked timer | `TIMER_INACTIVE`, warning | Outside maintenance/startup grace; explicit active enabled state resolves |
| Unavailable, malformed, oversized or missing evidence | `MONITORING_COVERAGE_DEGRADED`, warning | Actual successful read resolves recoverable access problems; historical coverage gaps remain recorded |
| ADMIN transport degradation | `ADMIN_DELIVERY_DEGRADED`, warning | One local incident; transport restoration supplies explicit recovery evidence |

Journal recoverable errors are held until the same invocation is observed completed; they do not count unfinished runs toward the debounce. Unprovable completion stays unknown. Fixed machine codes and specific deployed diagnostics are recognized; arbitrary error text is not interpreted as a diagnosis. Unknown exceptions can still produce a service/analysis failure without an invented cause.

A normal completed oneshot is `inactive/dead`. While it is running, `Result=success` and status 0 are not completion evidence. Missing-run detection uses systemd's own resolved next deadline, so Europe/Riga, DST, daytime/nighttime, weekly and nightly schedules remain systemd's responsibility. No historical cadence is guessed at installation. Boot/monitor-start grace is three minutes. A reboot produces monitoring-gap evidence, not an assumed application failure. Temporarily missing NextElapse during a running invocation does not page; absent deadlines after completion must persist for three minutes before degradation.

No incident is created merely for zero READY, `NO_READY_SELECTIONS`, zero transport, valid policy/freshness rejection, unfinished-match settlement, insufficient learning sample or a losing prediction. Zero READY makes no statement about overall pipeline correctness. Expected quota preservation alone is informational.

### Maintenance

Monitor-owned expiring suppression records have scope (`all` or one allowlisted service), reason reference and expiry, capped at 24 hours. They suppress notifications/evaluation in that scope without changing PREMATCH flags or timers. Reasons are stored as a digest, so arbitrary operator text cannot leak through reports. Keep the human reason in the operator's change record.

Example, run as the ADMIN service account after a separately approved installation:

`/usr/bin/python3 -I /opt/goalvision-admin-alerts/run.py --config /etc/goalvision-admin-alerts/admin-alerts.json --suppress-service goalvision-lab-v2-discover.service --suppress-hours 1 --reason approved-maintenance-ticket-123`

## Durable lifecycle, traffic and retention

Lifecycle: `PENDING` for debounced first occurrences, then `OPEN`, `REPEATED` or `ESCALATED`, then `RECOVERED` only on explicit corresponding evidence. A new recurrence starts another episode. Replayed source events do not inflate counts. Unchanged snapshots do not append a new occurrence every minute. Exact invocation and cycle identities correlate journal, stdout and systemd. If identity cannot be proven, sources remain separate and their association is UNKNOWN; the monitor never joins unrelated latest rows.

The first actionable occurrence is eligible immediately. Repeats update counts/evidence. Persistent reminders are at least 30 minutes apart. Escalation is promptly eligible. Recovery is sent once, when a fault was previously sent or transport was attempted. An unsent obsolete alert is superseded. Normal success produces no message.

Outbox identity is committed before transport. `ATTEMPTING`, `UNCERTAIN`, `SENT`, `PERMANENT` and `EXHAUSTED` remain distinct. SENT requires Telegram `ok=true`, the expected positive private chat, a positive message ID, and a committed local receipt. A crash after transport but before that commit leaves uncertainty. Retries preserve incident/outbox identity: **duplicates are possible; exactly-once delivery is not claimed**.

Retry delays start at 30 seconds and double to a 30-minute cap, with at most five transport attempts. Telegram `retry_after` takes precedence. Permanent auth/destination/identity failures open a persisted circuit; validation retries also stop after five failures. Operators must review corrected configuration and the existing ADMIN outbox before resetting this circuit. V1 deliberately has no automatic reset or PREMATCH resend command.

An outage stops queue draining for that scan. Recovery with more than five pending notifications, or notifications older than 30 minutes, sends one Latvian summary per bounded batch of at most 1,000 rows. It lists up to 20 incident IDs and points to the full local report/store. Rate-limited entries remain durable. ADMIN delivery failure creates one local incident, avoiding recursive failure messages. With Telegram unavailable, incident collection continues.

Retention keeps open incidents and pending/permanent/exhausted notifications. Sent/superseded outbox history and attempt details expire after 90 days in batches; first/last seen, counts and latest incident evidence survive. Detail occurrences are compacted toward the newest 100 per incident, ten incidents per scan. Resolved incident tombstones and source cursors remain for replay protection. The forwarding report is capped at 200 incidents and marks truncation; full evidence remains in the ADMIN store. Reports replace the previous snapshot atomically. PREMATCH logs are never rotated or deleted by this package. An unbounded number of distinct unresolved incidents can still consume disk; host disk monitoring remains necessary.

## Private sender prerequisites

Configuration template: `operations/admin-alerts/admin-alerts.json`, sending disabled.

Before enabling sending, the operator must establish all of:

1. The existing dedicated ADMIN bot's token file, expected numeric bot ID and exact username. No token may be pasted into a report or chat. Token file must be readable by the ADMIN account and mode 0600.
2. A fixed positive numeric private-chat ID. Channels/groups, log-provided destinations and negative IDs are rejected.
3. Operator-confirmed `/start` with that exact bot, recorded by setting the explicit confirmation flag after the human action. The sidecar never reads updates, consumes commands or deletes a webhook.
4. Dedicated account read access, service sandbox review, and separately approved deployment/enabling.

Before a pending send, `getMe` and `getChat` validate bot and private recipient. No production identity validation or real test message was performed here. Setting `enabled=true` later is a separate reviewed operator action and can deliver the pending backlog. Existing ADMIN command handling is left untouched.

## Forwardable examples

Normal alert (fictional IDs):

```text
🚨 GoalVision ADMIN • PREMATCH
Kļūda: Publikācijas piegāde nav droši apstiprināta
Serviss: goalvision-lab-v2-discover.service
Posms: DELIVERY_UNCERTAIN
Ietekme: Nav apstiprināta
Darbība: Pārbaudīt sanitizēto incidenta pārskatu; piegādi saskaņot pēc prognozes ID.
Incidents: 75cae996ce184b49bde80f48
Cikls / prognoze: cycle-example / prediction-example
Versija: skartajai izpildei UNKNOWN
Laiks: 2026-09-27 09:15:00 EEST (Latvija)
Atkārtojumi: 1
```

Recovery heading: `✅ GoalVision ADMIN • Darbība atjaunota`. Recovery does not claim all services or statistics are healthy.

Sanitized report excerpt (fictional):

```json
{
  "schema": "goalvision-admin-incidents-v1",
  "configured_release_now": "23e57e9c48f321b8ee5f67bd536fbb2b264f6cb0",
  "affected_invocation_release": "UNKNOWN",
  "evidence": {
    "source": "stdout:2049:1887417:8192",
    "invocation": "UNKNOWN",
    "cycle": "cycle-example",
    "facts": {
      "transport_attempted": true,
      "acknowledgement_received": true,
      "receipt_persisted": false,
      "reconciliation_required": true
    }
  }
}
```

Reports retain rule version through the schema/signature, incident/cycle/prediction IDs, timestamps, safe observed facts, source references, journal cursor/boot/invocation where available, and up to five allowlisted application stack frames (module, line, function). No raw exception text, locals, environment, token, authorization header, full payload or message body is retained. Partial bytes are hashed before state retention. Logs cannot select recipients, execute commands or supply automatic repair instructions.

The report includes a bounded read procedure: inspect at most 100 journal entries for the stated unit/invocation, compare the exact prediction/report receipt, and inspect loaded configuration plus the relevant immutable release manifest. The configured release now is never assigned to an older failure without proof. V1 conservatively leaves affected-invocation release UNKNOWN.

## Validation and the single host rehearsal

- **72 new offline monitor tests passed**. All Telegram transports are fake; synthetic SQLite and log fixtures exercise normal/fault states, timeout/signal/OOM, failed delivery with exit 0, persistence/receipt ambiguity, schedules/DST, startup/maintenance, lifecycle and repeated recovery, exact-source deduplication, partial/oversized/rotated/copy-truncated input, restart/atomic rollback, private identity, redaction, retries/backoff/429/circuit/limits, storms, receipt-commit failure, storage failure, producer immutability and ADMIN-only disable isolation.
- **66 directly relevant existing regressions passed**: `tests/test_lab_v2_operator_output.py` and `tests/test_lab_probability_delivery_hardening.py`. No model, historical-data or full-platform audit ran. Prediction backtesting is inapplicable: prediction logic did not change.
- `systemd-analyze verify` passed for the two new templates. The final standalone package check passed all file hashes and found no pending loaded configuration drift across loaded services/timers.
- [Synthetic benchmark](PREMATCH_ADMIN_ALERTS_V1_BENCHMARK.json): an 8.58 MB log containing an old oversized record and 1,000 compact records, 10,000 rows per health table and 10,000 claims. The scan read under one MiB of log data and bounded query pages. Exact elapsed time/RSS are in the JSON; observed scan time was well below one second and process peak RSS below 40 MiB, including fixture generation.
- **Exactly one no-send host scan** ran with a 45-second outer deadline and isolated state `/home/arvis/goalvision-operations/prematch-admin-alerts-rehearsal`. [Saved rehearsal evidence](PREMATCH_ADMIN_ALERTS_V1_REHEARSAL.json): 0.0845 seconds, zero stdout bytes (log was empty), zero football API calls, zero Telegram sends, no protected-file hash changes.
- That scan read systemd, journal and indexed health evidence. Receipt review was deferred because scheduled producers were active. It cannot prove unresolved-claim coverage for the actual host, or permissions of the not-yet-created ADMIN account.
- The rehearsal exposed conservative warnings for temporarily missing timer deadlines during running invocations and the immediate claim-review deferral. Final code debounces these conditions as described above. Recorded-host replay and synthetic tests verify the correction. **No second host monitor scan was performed.** The saved rehearsal is the original observation, not a rewritten claim that final coverage was complete.

Reproduce offline tests from the isolated worktree:

`cd /home/arvis/goalvision-operations/prematch-admin-alerts && /usr/bin/python3 -m unittest discover -s tests/admin_alerts -v`

`cd /home/arvis/goalvision-operations/prematch-admin-alerts && /home/arvis/GoalVisionAI/.venv/bin/python -m pytest -q tests/test_lab_v2_operator_output.py tests/test_lab_probability_delivery_hardening.py`

## Standalone package and permission boundary

**Review/install only the final package:** `/home/arvis/goalvision-operations/prematch-admin-alerts-package-v1-final`.

`/home/arvis/goalvision-operations/prematch-admin-alerts-package-v1` is a superseded development package and must not be installed.

Final `SHA256SUMS` SHA-256: `3a27a9f75996698a5576cff2f3e889d3a5c20d091fb0c891de704b462ac9b7a0`.
All 17 payload hashes are in [the committed package manifest](PREMATCH_ADMIN_ALERTS_V1_PACKAGE_SHA256SUMS.txt).

Prepared files include `goalvision-admin-alerts.service`, `goalvision-admin-alerts.timer`, `admin-alerts.json`, `run.py`, the isolated Python package, `package_check.py`, `install_package.py`, `disable-admin-alerts`, and a snapshot of existing PREMATCH fingerprints. The package needs system Python's standard library; it does not need a PREMATCH release upgrade, dependency install or shared PYTHONPATH change.

Intended locations:

| Purpose | Fixed path |
| --- | --- |
| Read-only application | `/opt/goalvision-admin-alerts` |
| Dedicated config | `/etc/goalvision-admin-alerts/admin-alerts.json` |
| Dedicated token | `/etc/goalvision-admin-alerts/admin-token` |
| ADMIN state | `/var/lib/goalvision-admin-alerts/admin.sqlite` |
| Forwardable report | `/var/lib/goalvision-admin-alerts/incident-report.json` |
| Last bounded scan | `/var/lib/goalvision-admin-alerts/last-scan.json` |
| ADMIN-only kill marker | `/var/lib/goalvision-admin-alerts/DISABLED` |

Account prerequisite: dedicated non-root `goalvision-admin-alerts`. The operator must grant only read/traverse access to the named producer paths, release metadata and their necessary parent directories. If existing modes do not suffice, use an ACL for this account on those paths; also review future rotated-log and WAL/SHM readability. No producer write permission or sudo permission is needed. None was granted during development.

Journald does not provide a per-unit file ACL: its journal files contain multiple units. A read ACL on the necessary system journal files/directories (including future rotated files), or approved `systemd-journal` membership for the dedicated account, exposes more journal data than the five-unit query. Review that unavoidable permission boundary explicitly. The monitor itself queries only the allowlist. If that grant is unacceptable or unavailable, leave journal coverage degraded; do not describe it as healthy. No unrestricted sudo or existing user's group change is proposed.

### Review and check — one-line commands, no mutation

Verify the anchored checksum manifest and all payload files:

`printf '3a27a9f75996698a5576cff2f3e889d3a5c20d091fb0c891de704b462ac9b7a0  /home/arvis/goalvision-operations/prematch-admin-alerts-package-v1-final/SHA256SUMS\n' | /usr/bin/sha256sum --check --status && cd /home/arvis/goalvision-operations/prematch-admin-alerts-package-v1-final && /usr/bin/sha256sum --check SHA256SUMS`

Check existing PREMATCH fingerprints and pending loaded systemd drift:

`/usr/bin/python3 -I /home/arvis/goalvision-operations/prematch-admin-alerts-package-v1-final/package_check.py`

Do not refresh an old PREMATCH deployment manifest to make this check pass. Any drift requires a new review. The check inventories pending drift across all loaded services/timers because daemon-reload could apply unrelated changes. Development's final check reported `FILES_AND_LOADED_STATE_MATCH`.

### Installation — prepared, not executed

Installation and sending require a later reviewed operator action. The following commands are for that future action in a root operator session, after checksum verification and permission review. They do not use sudo or invoke any PREMATCH stop/drain/start/restart/reset/disable action.

Create only the dedicated account if absent (operator confirms absence first):

`/usr/sbin/useradd --system --home-dir /var/lib/goalvision-admin-alerts --shell /usr/sbin/nologin goalvision-admin-alerts`

Grant the reviewed narrow read permissions, then run the installer:

`/usr/bin/python3 -I /home/arvis/goalvision-operations/prematch-admin-alerts-package-v1-final/install_package.py --reviewed-install-disabled-sender`

The installer rechecks payload/host fingerprints and all loaded-unit drift; requires the dedicated account and producer read access; refuses to overwrite existing ADMIN installation/config/units; copies only new ADMIN files; performs one daemon-reload; enables only `goalvision-admin-alerts.timer`. Sending stays disabled in the copied template. Existing PREMATCH units, drop-ins, environment, release and deployment manifests are not rewritten. A partial ADMIN installation must be inspected manually before resuming; no blind overwrite is provided.

After installation, inspect ADMIN's own report and sandbox access. Review actual unresolved-claim enumeration and journal coverage. Configuring/validating the real bot, confirming private `/start`, enabling `sender.enabled`, and any real test alert are separate reviewed actions. They were not performed in this task.

### ADMIN-only disable and removal

Future root operator command, after verifying the installed kill-switch hash:

`printf '9b2e82e1871c3a3c0844f42df22a947ca1e6bc9b0869d9dc0ab3d57393c47853  /opt/goalvision-admin-alerts/disable-admin-alerts\n' | /usr/bin/sha256sum --check --status && /opt/goalvision-admin-alerts/disable-admin-alerts`

This writes the ADMIN kill marker, disables/stops only the ADMIN timer and stops only the ADMIN service. It preserves incident evidence. A request already accepted by Telegram cannot be retracted; an interrupted send remains uncertain. PREMATCH continues independently. Removing the monitor later means disabling it first, preserving `/var/lib/goalvision-admin-alerts`, and removing only the two ADMIN unit files and `/opt/goalvision-admin-alerts` after a separate review. No PREMATCH unit references this monitor.

## Blind spots and remaining prerequisites

A local monitor cannot alert during total VPS failure or total network loss. It cannot prove a send was absent after a timeout, fix broken producer persistence, restore missing logs, or identify an affected invocation's release from current configuration alone. Unknown error formats remain coverage gaps or generic service failures. No source state is used to claim statistics were unaffected. Unproven integrity/persistence recovery stays open for operator diagnosis; v1 has no manual pretend-recovery command.

Remaining prerequisites are the real dedicated ADMIN identity/token/private recipient, human `/start`, dedicated account/read-access grants, reviewed installation, and later review of actual sender validation and host coverage under the service sandbox. Software readiness does not imply any of these steps has happened.
