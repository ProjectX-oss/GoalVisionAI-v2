# PREMATCH quota lock hardening

## Pre-change audit (2026-09-27)

Baseline: `23e57e9c48f321b8ee5f67bd536fbb2b264f6cb0`.
Invocation: `1149428ce2d749cb9a1335fbceb78bd9`, discovery PID 790165.
Persisted cycle start 09:00:13.994968 UTC, failure cleanup timestamp
09:00:42.937846 UTC; final journal exception 09:00:45.888665 UTC.
Seven completed HTTP requests are present in the exact invocation journal.
The failed reservation precedes transport and request-count increment.
The health row incorrectly reports provider_calls=0 (failure-path default).
Last chronological durable claim: `0cd74e2d-6d2c-4d6e-bd9b-19128632d0ad`,
SETTLEMENT, 09:00:36.106914 UTC. Last discovery claim:
`f60c0150-50e4-45f4-9d1c-92663a7864b3`, PREMATCH_REVIEW,
09:00:35.665330 UTC. Claims lack invocation attribution; these associations
use the bounded journal and categories, not a fabricated exact join.

Concurrent services proven by the 09:00:00–09:01:05 UTC user-visible journal:
- discovery: invocation above;
- settlement: `76044717be4f44c88bdadc5b9852b840`, PID 790164;
- observer: `81454113b50b4eaba4a80bde1a9e6a3a`, PID 790163.

`LOCK_HOLDER_NOT_PROVEN`. SQLite writer acquisition exhausted the configured
5000 ms busy timeout. The journal has no transaction-owner trace. It cannot
prove whether one long writer or repeated writer acquisition caused starvation.
The observer finished at 09:00:42.158370 UTC; overlap alone does not prove ownership.
The BEGIN failed before entering the transaction manager's try block: no quota
transaction began and no quota rollback ran. Later cycle_health persistence
succeeded. No partial failed claim is indicated. Process exit status and exact
systemd lifecycle are unavailable in the unprivileged journal; sudo read access
requires a password. ADMIN SERVICE_FAILURE/ANALYSIS_FAILURE/MISSING_OUTPUT are
operator-provided evidence, not independently reread from its protected database.

## Complete shared audit transaction inventory

| Boundary | Work inside the baseline writer transaction | Finding |
|---|---|---|
| repository.transaction | BEGIN/commit/rollback; nested scopes join outer transaction | BEGIN failure is outside try; nested quota can return before durability |
| repository.migrate | schema/index/trigger DDL at every writer construction | no network/await; unnecessary writer acquisition on current schema |
| repository.append | exact row lookup, replay verification/deserialization, insert | nested callers serialize/hash inside their outer lock; replays acquire writer |
| SharedQuota.claim | day/prior-minute SELECTs, JSON/hash verification, Python counting, append | avoidable growing history under writer lock |
| observations.ingest outer + inner | freeze/validate, matching history JSON query, get, source+observation append | replay loop repeatedly acquires writer; nested atomic pair |
| coordinator.shadow | exact canonical get/append | short; context/filesystem observer and prediction outside |
| automl.run | learning-cycle history comparison, champion read, serialize/append full batch | training already outside via _ResearchBuffer; history/hash work remains inside |
| automl._run | candidate training, evaluation and history | nullcontext on private buffer, not actual SQLite lock |
| governance.bootstrap | fixed evidence batch, activation pointer | validation outside; bounded model hashing inside |
| governance.promote | shadow/history hydration, eligibility, comparison/bootstrap statistics, artifact validation, activation | unbounded compute under writer lock |
| governance.rollback | history hydration, inference, comparison/bootstrap statistics, pointer mutation | unbounded compute under writer lock |
| weekly.freeze | external ledger reads, whole-week statistics, formatting, append | slow external DB/CPU work under writer lock |
| weekly.deliver | receipt/claim lookups and one claim | Telegram await occurs after commit |
| LIVE candidate | snapshot + candidate append | prediction outside; LIVE remains disabled |
| LIVE publish | prior claims/history, readiness, formatting + claim | no await inside; inactive LIVE-only scope |
| LIVE settle | settlement append + nested ingest | no network inside; inactive LIVE-only scope |
| LIVE publish_result | claim lookup + append | statistics outside; Telegram after commit |

Observer/import_canonical/after_settlement have no encompassing transaction;
individual ingest/governance/append scopes above are the applicable boundaries.
Shadow settlement fetches are awaited outside writes. cycle_health, observer_runs,
canonical_results, shadow/champion predictions and settlement rows use append.
PREMATCH context capture/snapshot/readiness/registry, publication ledger, analysis
and discovery-cache databases have separate connections/files; their transactions
do not own the adaptive audit writer. No active shared-audit write boundary contains
an await, network request, Telegram call or sleep. No source was changed before
this audit. Identified source defects are proven; historical lock ownership is not.

### Installed research route

Read-only systemd inspection found daily research still routed through
`/etc/goalvision-prematch-release.conf` to the `363f567` release. Its observation
ingestion scans the complete learning history inside each writer transaction.
This is worse than the indexed matching query in `23e57e9`. AutoML/governance
transaction structure is otherwise the same audited structure. Daily research
was not present in the bounded incident journal. This is a separate proven
writer-scope defect, not an attribution of this incident to daily research.

## Root cause conclusion and limits

The proven immediate cause is failure to acquire SQLite's single writer slot at
BEGIN IMMEDIATE under the installed 5000 ms busy-timeout configuration. This was
a local quota persistence failure before the next HTTP request. It was not an
HTTP retry exhaustion or provider quota refusal. No connection-level timeout or
lock-owner telemetry survived this invocation. The timeout is established from
verified installed code, not a retrospective PRAGMA measurement.

The code audit proves avoidable writer occupancy and repeated writer acquisition
in active observer/settlement replay and quota processing, plus potentially much
longer governance/weekly/research work. A synthetic 1,480-observation replay took
7,149 ms and acquired 1,480 writer transactions before the change. That is a
credible starvation mechanism, **not proof that it owned the incident lock**.
The exact historical causal transaction remains unproven. No claim is made that
a timeout increase or a specific service restart would fix it.

## Implementation

- `PreparedAudit` reads verified immutable evidence and serializes proposed rows
  outside the writer transaction. It watches append-only table high-water marks
  and separately records mutable champion pointers. Under BEGIN IMMEDIATE it
  checks those small dependencies, appends the prepared batch and changes any
  pointer atomically. Concurrent evidence invalidates the batch before writes.
  This relies on the existing append-only API, which never assigns/reuses rowids.
- Quota counts retain the exact day, rolling-minute, LIVE cap, provider minimum
  and reserve calculations. History decoding/hashing/counting precedes BEGIN.
  A successful claim returns only after COMMIT. Nested quota reservations are
  refused because returning from an outer transaction would not prove durability.
- Observation replay no longer takes a writer lock. New source+observation pairs
  remain atomic. Immutable append replays verify exact document bytes, stream and
  links without taking a writer lock. New writes recheck the identity under lock.
- AutoML, governance promotion/rollback/bootstrap and weekly statistics prepare
  outside the writer lock. Research/model algorithms and thresholds are unchanged.
  Governance/research return a concurrency status when prepared evidence changes;
  they cannot activate a stale champion. New ingestion conflicts fail closed.
- Existing short canonical/claim/pointer scopes retain their atomic boundaries.
  Inactive LIVE-only publication/readiness scopes were audited, not activated or
  broadened in this PREMATCH task. LIVE's normal regression suite still passes.
- The transaction manager still rolls back on BaseException, including shutdown.
  A failed rollback raises a distinct failure and cannot enter the quota retry loop.
- Discovery failure cleanup records the client's actual consumed-call count and
  retains the fixed exhausted-contention code. Existing immutable incident rows
  were not edited to repair their historical zero count.

No schema migration, WAL change, timeout increase, quota-policy change, model
change, confidence/odds threshold change, settlement rule change, publication
change, discovery cadence/coverage reduction or Official/LIVE activation occurs.

## Contention policy and HTTP boundary

One monotonic **500 ms** contention window; waits are at most **25 ms** each.
SQLite busy_timeout is temporarily **0** for each local attempt and restored
before waiting. Production authorizers use asyncio sleep; cancellation interrupts
these waits. There is no executor/background reservation that can survive task
cancellation. The synchronous reservation API has the same bounded retry budget.

Only numeric SQLite primary BUSY/LOCKED codes (including extended codes) and an
optimistic evidence conflict are retried. Constraint, schema, integrity,
programming and unknown errors fail immediately. Retry is forbidden after a
completed reservation or an unconfirmed transaction cleanup outcome. A busy
COMMIT rolls back the insert before another attempt. A saturated writer workload
may still exhaust the window; refusal is deliberate and does not spend quota or
start transport. The bound limits contention waits, not arbitrary OS stalls or
SQLite disk I/O. Normal successful local history verification is finite daily
accounting work, and is outside the writer lock.

Synthetic writer-body measurements (commit/fsync excluded): quota with 1,712
prior claims fell from maximum 17.604 ms / median 13.573 ms to maximum 0.274 ms /
median 0.207 ms. Patched replay acquired zero writer transactions for all 1,480
observations. Overall replay computation remained about 7.6 seconds outside the
writer lock. Measurements ran on this host in disposable synthetic databases;
concurrent test load means these are engineering measurements, not a performance
benchmark or historical lock reconstruction. The 500 ms policy provides brief
headroom over these short mutations while being ten times smaller than the old
single lock wait. It does not attempt to wait out model work.

`FootballClient._pace_request` awaits authorization before updating the pacing
stamp or request count. `_get` calls transport only after that return. Database
contention handling contains no HTTP call and raises a RuntimeError subtype that
is outside the HTTP transport retry catches. Each actual HTTP retry still requires
its own durable claim under the existing client policy. No HTTP request is retried
because a quota write failed.

Diagnostics are single structured stderr JSON records with only fixed code,
attempt, elapsed milliseconds, whitelisted category and stage. Codes:
`QUOTA_DB_CONTENTION_RETRY` and `QUOTA_DB_CONTENTION_EXHAUSTED`. No exception text,
SQL values, credentials or provider payloads are logged. Exhaustion is emitted
before cycle-health cleanup, so a still-busy database cannot hide the incident.

## ADMIN compatibility

Separate branch `codex/prematch-quota-admin-code-mapping`, commit
`51ab59540ef918e0ecdbdc86d767ec25f480df78`, directly on `d811177`.
Its sole runtime change maps QUOTA_DB_CONTENTION_EXHAUSTED to DATABASE_LOCK with
one-occurrence debounce. Transient retries generate no ADMIN event. Health
recognizes the structured failure through its existing adapter. Existing
SERVICE_FAILURE/ANALYSIS_FAILURE/MISSING_OUTPUT correlation is untouched. The
mapping is packaged as a separate patch and has not been installed. ADMIN sender
was never enabled and no monitor/send command was run.

## Validation

All test databases are disposable; HTTP uses fake transport. The final regression
launcher denies network syscalls to the test process and its children.

- 732 focused application tests + 8 subtests passed (93.28 s).
- After an additional completed-reservation cleanup guard: 262 focused tests +
  8 subtests passed (41.02 s).
- Final contention/database/quota set: 59 tests passed (4.70 s), including 23
  contention/failure-path cases. This includes the last diagnostic validation
  changes and failure-path call accounting.
- The installed `363f567` research lineage with only the five-file persistence
  overlay: 59 AutoML/database/metrics/governance tests passed (26.41 s).
- Separate ADMIN v1.2: 109 tests + 42 subtests passed with networking denied.
- Package verifier: 5 tests passed, including changed manifest/payload, unexpected
  files and symlink rejection.

Real SQLite coverage includes: short released writer; durable claim visible to
another connection before fake HTTP; persistent writer refusal; zero failed
transport count; constraint/schema/integrity/programming immediate failure;
actual extended SQLITE_LOCKED via shared-cache test connections; busy COMMIT with
rollback before retry; nested transaction rollback and nested quota refusal;
concurrent discovery/settlement minute and day limits; protected settlement
reserve; successful reservations exactly equal durable rows with unique IDs;
no partial claims; cancellation while locked; error after commit never reserving
again; stale prepared batch rejection; atomic pointer rollback after injected
write failure; zero writer acquisition on observation replay; history reads and
weekly computation outside writer locks; and failure health preserving seven
previously consumed calls. Saturation tests allow bounded safe refusal, then
verify every remaining slot and the exact capacity boundary.

Existing normal discovery, publication, shared settlement, API pacing/quota,
chronology, golden baseline probability, full adaptive synthetic training,
shadow/promotion/rollback, and settlement reserve paths pass. No prediction logic
changed: the adaptive synthetic governance rehearsal supplies the relevant
regression/backtest coverage. The giant historical/model suite was not run.

## Read-only host rehearsal

2026-09-27 09:48:33.772155–09:48:35.876141 UTC. One bounded DB inspection, opened
with SQLite URI `mode=ro`, query_only enabled and a one-second progress deadline.
Integrity check returned `ok`; foreign_key_check returned zero rows; schema 5;
journal mode `delete`. DB inspection took 831.475 ms. `/proc/locks` showed no lock
on the audit inode at the sample instant. No contention was manufactured on the
live database, and absence at one instant is not proof of future lock freedom.

4,766 reviewed configuration/source file hashes matched; configuration hashes
remained unchanged across the rehearsal. The older installer manifest's
expected_dropins describe its pre-upgrade state; installed bytes were correctly
validated against its hash-pinned `.proposed` files without another DB inspection.
All five PREMATCH timers were active/enabled and services were normally inactive
between runs. The four operational routes remained on `23e57e9`; daily research
remained on `363f567`. No service was stopped, paused, restarted or manually run.
The main workspace's pre-existing dirty files were not touched.

One baseline synthetic measurement accidentally generated two test-only `.pyc`
files under the installed release's tests directory. Their exact paths and
creation times identified them; both were removed. No installed application
source, configuration, model or database bytes were changed by that measurement.
Subsequent execution used `-B`; verified installed tracked files match baseline.

Privileged system journal lifecycle and ADMIN private configuration/database
remain unreadable to this session; passwordless sudo was unavailable. Exact
systemd start/exit timestamps, numeric exit status and independent sender-state
readback cannot be certified. Sender DISABLED is the operator-provided state.
The pending information request names these missing facts; no new permission or
production operation was inferred from the passage of time.

## Deployment package and handoff

Prepared payload location:
`/home/arvis/goalvision-operations/prematch-quota-lock-hardening-package-20260927`.
The package record appended below pins the final source commit and hashes.

The main payload has exactly ten persistence/client integration file changes from
`23e57e9`. The separate research payload has five persistence file changes from
`363f567`. Both complete application trees are supplied, with exact file hashes,
four current/proposed service drop-ins and an absent-before research drop-in.
Only environment routes change; commands, timers, quota settings, publication
state and sender settings are preserved. A read-only verifier rejects any changed
or added payload file. The separate ADMIN mapping does not enter PREMATCH imports.

`operations/quota-hardening/REVIEW.md` supplies the future operator procedure and
bounded rollback: fence new starts only during a separately authorized operation,
allow at most 60 seconds to drain without killing workers, abort before changing
configuration on timeout, retain old releases, restore exact prior configuration
bytes, and never restore a database or delete new claims/history. Installation,
rollback and deployment-controller fault injection were not performed. No
self-installing hook or automatic deployment is included.

**Status: PREMATCH_QUOTA_LOCK_HARDENING_BLOCKED.** Code, concurrency tests,
regressions, host readability/configuration checks and review package are prepared.
The exact incident service exit status/lifecycle and independent ADMIN disabled
readback remain unavailable. Historical lock ownership remains explicitly
LOCK_HOLDER_NOT_PROVEN; the patch fixes demonstrated contention sources without
claiming a retrospectively proven owner. Obtain the missing bounded privileged
facts before closing the incident audit or authorizing deployment.

Real development API calls: **0**. Telegram sends: **0**. Production database
writes: **0**. Production PREMATCH control operations: **0**. Deployments: **0**.
