# Post-guard PREMATCH production health audit — 2026-09-29

## Finding

**PREMATCH is doing useful work and no recurrence of the discovery/settlement
contention problem was observed in accessible evidence. A complete production
health sign-off is blocked by missing privileged evidence.** Discovery is not
operating at full data coverage: all eight persisted health reports say
`DEGRADED`. The main remaining constraints are odds coverage, provider quote
freshness, and guarded publication quality. This audit establishes neither a
new implementation defect nor permanent elimination of contention.

No runtime behavior was changed or repaired. No service was started, stopped,
restarted, enabled or deployed. No provider call or Telegram send was made by the
auditor. ADMIN configuration, LIVE, thresholds, policies and historical records
were untouched. The production services continued their normal scheduled work.

## Window, lineage and evidence

- Start: **2026-09-29T10:07:25.396888+00:00**, the validated installation time.
- Fixed end: **2026-09-29T14:09:00+00:00**, selected at initial capture. Latest
  completed application evidence: observer output at **14:08:39.553253 UTC**.
- The next settlement at 14:15 was outside the window and excluded. Current unit
  properties were also sampled at 14:15:10 UTC and are labelled separately.
- No pre-install throughput comparison: the short window already answers the
  bounded question, without mixing different fixture populations or clocks.
- Implementation `ec0fa32789476d5fad497c05cbf93e3c78e09d18`; recovery v1
  `9ff50c2380280c8343833bd08658600e64937d83`; recovery v2
  `26391232cb2e31a1d636ea20b6198af0a452c4ae`; documentation base
  `a02673bb6572d9bd0ab683ae89f28913e8c235e5`.

The [structured summary](post_guard_prematch_health_2026-09-29.json) contains
per-cycle metrics, per-invocation application timestamps, guard outcomes,
delivery linkage, database checks and exact unavailable fields (`null`).
Sources are the installed systemd units, 1,969 accessible journal records,
`/var/log/goalvision-prematch/discovery-output.log`, and persisted evidence in:

- `/home/arvis/GoalVisionAI/var/lab_v2/shadow.db`: eight exact `rehearsal` keys
  taken from stdout, plus their 5,925 candidate primary keys.
- `/home/arvis/GoalVisionAI/var/lab_combo/ledger.db`: runs, predictions, claims,
  receipts and settlements.
- `/home/arvis/GoalVisionAI/var/adaptive_lab/audit.db`: health, quota and observer
  records, restricted to PREMATCH and the window.
- `var/lab_combo/analysis.db` and `data/goalvision.db`: bounded integrity checks
  and existing Official publication evidence.

Installed source was read under
`/opt/goalvision-prematch-quota-557d5af2-f24738b05fef/application` to interpret
persisted fields; no application module or CLI was executed. Live databases were
opened with SQLite URI `mode=ro`, `PRAGMA query_only=ON`, short connections and
bounded checks. `immutable=1` was avoided because these are live databases;
ignoring an active rollback journal would undermine consistency. Database
snapshots are independently timed, not one atomic cross-database snapshot.

Raw logs, databases and provider payloads are not committed. JSON source keys,
invocation IDs and scratch capture hashes support traceability; scratch hashes
are not a substitute for an archived raw production export. The historical
[validated closeout](../rehearsals/DISCOVERY_PRIORITY_SETTLEMENT_GUARD_CLOSEOUT_2026-09-29.md)
remains unchanged and retains its distinct operator-supplied evidence window.

## Systemd and guard health

| Unit | Calendar slots in window | Observed application invocations | Persisted completed application reports | Historical manager successes / exits |
| --- | ---: | ---: | ---: | --- |
| `goalvision-lab-v2-discover.service` | 8 | 8 | 8 | Unavailable |
| `goalvision-lab-combo-settle.service` | 24 | 24 | 18 executions; 6 deferrals | Unavailable |
| `goalvision-adaptive-learning-observer.service` | 9 | 9 | 9 | Unavailable |

The loaded calendars are discovery at :00/:30 during its Riga daytime schedule,
settlement at :05/:15/:25/:35/:45/:55, and observer at :08/:38. Every expected
slot has corresponding application evidence. These counts were obtained from
actual invocation IDs and persisted records, independently of the calendars.
**Alignment is not proof of timer causation.** Root system-manager records were
not visible: all 1,969 journal rows have UID 1001, and a bounded `_PID=1` query
returned no rows. Therefore exact scheduled starts, manager completions,
historical exit codes, failed starts, missed jobs and crash/restart loops cannot
be certified as zero. No such problem appears in the readable application data.

Latest completed in-window samples from `systemctl show`:

| Service | Actual start UTC (seconds precision) | Exit UTC | Runtime from monotonic properties | Result / exit |
| --- | --- | --- | ---: | --- |
| Discovery | 14:00:08 | 14:04:35 | 266.903426 s | success / 0 |
| Settlement | 14:05:21 | 14:05:59 | 37.469627 s | success / 0 |
| Observer | 14:08:08 | 14:08:39 | 31.675725 s | success / 0 |

At the completed samples all three services were inactive/dead with
`NRestarts=0` and `NeedDaemonReload=no`. At the later 14:15:10 snapshot discovery
and observer remained inactive/dead, settlement was activating/start in its next
ordinary run, its timer was running, and the other timers were active/waiting.
That in-flight run is not claimed as a completed success. Current `NRestarts=0`
is not a historical proof.

Discovery application durations (evaluation start to persisted health completion)
were 208.818–601.778 seconds. The 11:00 cycle took about ten minutes; the guard
correctly deferred the 11:05 settlement. JSON retains all eight durations and
all first/last application log spans. Log spans are not full service runtimes.

| Exact marker in readable service journals | Count |
| --- | ---: |
| `SETTLEMENT_EXECUTED` | 18 |
| `SETTLEMENT_DEFERRED_DISCOVERY_ACTIVE` | 6 |
| `SETTLEMENT_DEFERRED_DISCOVERY_IMMINENT` | 0 |
| `SETTLEMENT_DEFERRED_DISCOVERY_STATE_UNAVAILABLE` | 0 |
| `QUOTA_DB_CONTENTION_RETRY` | 0 |
| `QUOTA_DB_CONTENTION_EXHAUSTED` | 0 |
| `DATABASE_LOCK` | 0 |
| `SERVICE_FAILURE` | 0 |
| `database is locked`, `Traceback`, `ERROR`, `WARNING` | 0 each |

All six deferred invocations contain only their guard record, with
`api_calls=0`, `database_writes=0`, `telegram_sends=0`. No settlement run record
corresponds to a deferred slot. The installed wrapper returns before executing
the settlement argv on deferral. Deferrals at 10:35, 11:05, 11:35, 12:35, 13:05
and 13:35 are each followed by an executed marker and persisted completed run
at the next ten-minute slot. All 18 executed markers have a corresponding
completed ledger run. This supports continued settlement without doing work in
deferrals; historical process exit success still needs manager evidence.

The installed wrapper matches the recovery-v2 package byte-for-byte:
`4ab82ae534403e2a3d8f7e1b589220b555b8f3cfac63bb7c878337eea53ea5ff`.
Its loaded route and 180-second guard match the validated design. Protected
transaction metadata and full pins could not be reread. The supplied
`guard_installed=true`, `phase=installed`, pins PASS and installation/recovery
time remain prior validated facts, not newly obtained receipt fields.

## Discovery throughput

Each cycle retained **497 fixtures across 112 leagues**, with 496 provider
fixture rows in that cycle's report. The unique fixture union across all eight
cycles is also 497; the 3,976 cycle-fixture total does not represent new fixtures.
Examples include Friendlies (45), UEFA U21 qualifying (20), AFCON qualifying
(19), Liga Alef (18), UEFA Nations League (18) and Reserve League (18).

| Evaluation start UTC | Considered fixtures | Current-odds fixtures | Market evaluations | EARLY | TRACKING | Review later | READY | REJECTED | Exact odds calls | New sends |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10:30 | 456 | 101 | 1,017 | 194 | 105 | 0 | 8 | 710 | 44 | 3 |
| 11:00 | 451 | 132 | 1,320 | 245 | 126 | 2 | 2 | 945 | 45 | 0 |
| 11:30 | 451 | 139 | 1,391 | 242 | 186 | 1 | 3 | 959 | 45 | 1 |
| 12:00 | 442 | 14 | 148 | 17 | 32 | 0 | 0 | 99 | 45 | 0 |
| 12:30 | 440 | 22 | 229 | 45 | 33 | 0 | 0 | 151 | 46 | 0 |
| 13:00 | 433 | 46 | 468 | 97 | 49 | 0 | 0 | 322 | 45 | 0 |
| 13:30 | 433 | 65 | 665 | 124 | 66 | 0 | 2 | 473 | 45 | 1 |
| 14:00 | 427 | 67 | 687 | 121 | 67 | 0 | 7 | 492 | 46 | 2 |
| **Sum of cycle observations** | **3,533** | **586** | **5,925** | **1,085** | **664** | **3** | **22** | **4,151** | **361** | **7** |

Candidate evaluations cover **171 unique fixtures and 1,735 unique fixture/market
pairs**. PENDING is not a literal candidate stage here: EARLY, TRACKING and
FINAL_REVIEW_REQUIRED together account for **1,752 review-later observations**.
There are zero literal NO_SELECTION candidate records in these eight cycles;
three cycles report NO_READY_SELECTIONS and four cycles make no new send.
Candidate states are mutually exclusive; overlapping reason counts are not.

Global fixture tracking decreases from 454 to 426 as fixtures move into result
tracking or other lifecycle states. The last tracked market projection has 568
EARLY, 4 ODDS_STALE, 10 PUBLICATION_CLOSED, 7 READY, 10 REJECTED and 1 TRACKING
records (600 market records, not 600 fixtures). No FIXTURE_INVALID or EXPIRED
state appears in that last report. Eight discovery-date sweeps report complete
fixture discovery; this does not mean complete odds coverage.

Repeated fixture/market evaluation is intentional rechecking. All candidate
primary keys resolved and all new delivered selections link to APPROVED,
READY_TO_PUBLISH candidate records. No duplicate new single economic key or
Telegram message ID was found. Exact counts of every suppressed deduplication
attempt are not persisted in these compact outputs and are unavailable.

## Odds, context and no-pick reasons

**Exact refresh runs, but usable odds are a substantial bottleneck.** There are
361 recorded exact fixture-odds calls. The separately logged priority retry
subset has 160 fixture-cycle attempts and 20 recoveries. The tracked exact
review subset has 33 distinct fixture-cycle reviews: 12 AVAILABLE and 21
ODDS_STALE. These subsets overlap and must not be added. A complete outcome
breakdown for all 361 calls is unavailable; HTTP 200 is not evidence of a usable
quote. All 1,928 logged HTTP responses in the service window were 200.

All 22 READY candidates have `fixture_refreshed=true`, `odds_refreshed=true`
and exact `odds_status=AVAILABLE`. No READY candidate reuses odds after an
unsuccessful exact review. Installed `runner.py:_exact_review` bypasses cache
for the exact pair and replaces broad quote evidence even for an empty or
failed exact response. Observed stale exact results stay non-READY. This verifies
the observed cases and source boundary; it is not an injected failure test.

Broad odds collector counters before final fixture-state projection:

| Cycle UTC | No current odds | Stale current odds | Incomplete page coverage |
| --- | ---: | ---: | ---: |
| 10:30 | 26 | 34 | 297 |
| 11:00 | 121 | 39 | 152 |
| 11:30 | 268 | 37 | 0 |
| 12:00 | 19 | 101 | 307 |
| 12:30 | 21 | 125 | 277 |
| 13:00 | 115 | 133 | 147 |
| 13:30 | 19 | 122 | 241 |
| 14:00 | 18 | 118 | 241 |

These counters repeat fixtures across cycles and reflect collection-time coverage;
subsequent exact recovery can change the final state.

The tracked shortlist contains 2–5 fixtures per cycle. Recorded exact fixture,
injury and lineup review outcomes show rechecks taking place; lineup outcomes
include NOT_YET_PUBLISHED rather than fabricated availability. The last cycle
rechecks fixtures 1639142, 1350171, 1640508, 1641856 and 1641857. At noon,
tracked exact reviews returned stale provider quotes, explaining part of the
zero-READY interval. A complete due-queue deadline/SLA proof is unavailable.

### A. Quality, timing and policy filters

- NON_POSITIVE_VALUE appears on **4,150 market evaluations**, the dominant
  market rejection. One MARKET_REVIEW_TERMINAL observation also appears.
- INVALID_MODEL_PROBABILITY appears on **45** evaluations; all have probability
  exactly zero (`0E+1`), and none is READY. This is observed input/model quality
  rejection, without evidence here of a parsing or calculation defect.
- Future review windows account for 1,085 EARLY observations. Quality tracking
  accounts for 664 more. Missing optional signals, absent calibration and
  insufficient independent evidence appear in the gate evidence and must not
  each be counted as a separate rejected candidate.
- Publication reviews contain seven SEVERE_MODEL_MARKET_CONTRADICTION and seven
  ENSEMBLE_MARKET_DIVERGENCE_TOO_LARGE reasons, plus two
  PUBLICATION_DECISION_EVIDENCE_STALE reasons. These overlap across eight blocked
  candidate reviews. Stale decisions were held rather than sent.
- Legitimate publication closure increases from 41 to 70 fixture observations
  per cycle as matches approach/start. Unsupported-current-market counts are
  zero in the eight reports. No odds-below-minimum reason was observed in these
  rejection totals; no policy change is proposed.

### B. Technical/data availability limits

- Every health row reports `DEGRADED`, with `failure=null`.
- Reserve-limited pagination affects 290 fixtures at 10:30, 307 at 12:00 and
  276 at 12:30 (final fixture-reason projections). These are intentional bounded
  collection limits, not exhausted daily quota.
- Provider page-count drift affects 152 fixtures at 11:00, 147 at 13:00,
  241 at 13:30 and 240 at 14:00. At 14:00 the September 30 sweep advertises
  both 6 and 7 pages; October 1 advertises both 2 and 3. The system correctly
  reports incomplete coverage even after requesting the known pages.
- Final fixture-reason ODDS_STALE counts range from 34 to 130. The last cycle
  has 114 stale fixture reasons, 240 page-drift reasons and 17 complete-sweep
  no-record reasons. These are different projections from the broad odds
  collector counters retained in JSON; do not combine them.
- Provider quote age and absent provider records are observable limitations.
  They are not evidence that local refresh failed: 21 tracked exact reviews
  still received stale quotes. No HTTP error, quota-contention error, malformed
  market normalization, guard-state failure or application crash was observed.
- Context diagnostics record 170 SOURCE_CAPTURED, 1,579
  SOURCE_UNAVAILABLE_UNSCOPED_QUERY, 74 TARGET_SOURCE_UNAVAILABLE / unavailable
  snapshots, and 147 missing qualifying regulation-evidence observations.
  These are event counts, not unique fixtures. Installed capture logic
  intentionally refuses unscoped queries; it must not label broad/cached rows
  as exact target evidence. No capture/write exception marker appears in the
  observed summaries. Context collection is active with explicit gaps; universal
  context completeness cannot be claimed.

Among markets that reach evaluation, legitimate value rejection dominates.
Across the whole fixture population, odds acquisition/freshness materially limits
volume. It would be inaccurate to explain every no-pick cycle solely by betting
filters, or to attribute these data gaps to recurring DB contention.

Quota remains bounded: 1,782 reported discovery calls, all below their effective
272–287 cycle ceilings. There are 1,907 persisted PREMATCH quota claims across
status/discovery/review/settlement, with daily remaining-before values
3,296–5,202 and minute remaining-before values 199–300. Claims and call counters
have different semantics and are not forced to reconcile. Daily quota was not
exhausted in these records; the empty quota-observations table supplies no extra
proof. The historical worst-case configured ceiling is not actual daily usage.

## Persistence and settlement continuity

| Database | Read-only quick_check | Foreign-key check | Immutability triggers |
| --- | --- | --- | ---: |
| `var/lab_combo/ledger.db` | ok | No violations | 2 |
| `var/adaptive_lab/audit.db` | ok | No violations | 80 |
| `data/goalvision.db` | ok | No violations | 2 |
| `var/lab_v2/shadow.db` (12.64 GB) | Interrupted at 2-second query budget | No violations; evidence tables have no declared FKs | 4 |
| `var/lab_combo/analysis.db` (619.8 MB) | Interrupted at 2-second query budget | Interrupted at 2-second query budget | 342 |

Interrupted checks are incomplete, not failed integrity results. No full
`integrity_check`, write attempt, migration, checkpoint, VACUUM or repair was
performed. Recent append-only records and complete candidate lookup/linkage
support continuity; one read cannot prove historical immutability by itself.

The 18 executed settlement runs append **five single results and one combo
result**, with corresponding receipts. After the last run only three published
singles remain pending: fixture 1350174 (14:00 kickoff), 1350171 (15:00) and
1639142 (15:00), consistent with the 14:09 cutoff. Published combos have no
pending result. All 231 historical ledger claims have receipts; no orphan claim
was found. No post-window settlement is counted.

Nine observer reports increase linked singles from 90 to 95 and resolved
observations from 1,534 to 1,540, with zero observer API calls/sends. Three
MISSING_FROZEN_EVIDENCE diagnostics recur unchanged for legacy predictions
created September 13–14. These are pre-existing linkage gaps, not new
post-guard orphan predictions. The audit does not repair or rewrite them.
An exhaustive historic stuck-record proof remains outside this bounded scan.

## Publication, ADMIN and LIVE

The window contains **13 successful LAB receipts**: six single predictions,
one combo prediction, five single results and one combo result (message IDs
235–247). All have claims and existing prediction/result records. Every new
single and all three new combo legs resolve to persisted APPROVED/READY
candidates. No repeated single economic key, repeated message ID, unknown
receipt or unexpected destination was found. New-send attempts total seven;
all seven record acknowledgement and receipt persistence. Six existing result
sends also have receipts. Historical application HTTP logs were only read.

The inspected Official publication tables are empty; no unexpected Official
publication appears in this PREMATCH evidence. LAB's experimental combo and
LAB odds are not Official publications and do not alter Official statistics.
This is not a global audit of every Telegram sender or database on the host.

ADMIN service was inactive/dead with its timer active/waiting. Its protected
sender configuration could not be read; sender-OFF is known from the validated
closeout but cannot be freshly certified here. No ADMIN setting was changed.
All eight discovery health rows and all nine observer reports say LIVE DISABLED;
no LIVE control or mutation was performed.

## Answers and disposition

| Question | Evidence-based answer |
| --- | --- |
| Is discovery technically healthy? | Eight completed application cycles and successful latest systemd sample; data coverage is DEGRADED. Historical manager success/failed-start proof is missing. |
| Is settlement technically healthy? | 18 completed application runs, six clean deferrals, six published results, successful latest in-window systemd sample. Full historical exit proof is missing. |
| Has contention recurrence been eliminated? | No recurrence observed in this window: zero retries/exhaustion/lock markers. Permanent elimination and inaccessible-manager error absence are not established. |
| Are current odds/context refreshes functioning? | Yes in observed exact calls and READY evidence, with stale provider quotes, incomplete pages and context gaps explicitly reported. |
| Is candidate volume meaningful? | Yes: 497 fixtures, 112 leagues, 5,925 market evaluations, 22 READY observations, seven new LAB prediction sends. This says nothing about future profitability. |
| Why few/no picks? | Predominantly value/quality rejection among evaluated markets; meaningful odds availability limits across the fixture pool and stale exact reviews during the noon no-pick period. |
| Any blocker before ADMIN console sender-OFF deployment? | Evidence sign-off is blocked: obtain manager history and fresh guard/ADMIN pins. No new runtime defect requiring a fix was established. This audit grants no deployment authorization. |

## Exact unavailable evidence and read-only operator commands

`sudo -n -l` returned `sudo: a password is required`. Protected guard/stagger
state directories and ADMIN configuration are unreadable to this account. No
sudoers change, access-control workaround or interactive prompt was attempted.

Still missing: historical manager starts/completions, exit statuses/durations,
failed/missed starts and restart history; fresh protected guard transaction/full
pins and ADMIN sender state; full large-database checks; outcomes for every exact
odds call; complete due-queue and historic orphan/SLA proof. Accessible evidence
supports bounded activity, not these unavailable stronger claims.

An authorized operator can run these two read-only commands. They do not start
any GoalVision service or send a message. Use an already authorized root shell
if noninteractive sudo is unavailable. Preserve the results as a separate dated
addendum; do not modify this report or the validated closeout.

```bash
sudo -n /usr/bin/python3 -I -B /home/arvis/goalvision-operations/prematch-settlement-guard-recovery-v2-20260929/control.py status --manifest-sha256 b32966e45f178e0f74ff005b25adbe684933bf372b62c4da16cd4b22a32c7cc7
```

This existing reviewed status command reads guard provenance, full pins and the
protected ADMIN sender-OFF prerequisite. A later result describes capture-time
state, not a replacement historical snapshot.

```bash
sudo -n journalctl --no-pager --utc -o json \
  --since '2026-09-29 10:07:25.396888 UTC' \
  --until '2026-09-29 14:09:00 UTC' _PID=1 \
  -u goalvision-lab-v2-discover.service \
  -u goalvision-lab-v2-discover.timer \
  -u goalvision-lab-combo-settle.service \
  -u goalvision-lab-combo-settle.timer \
  -u goalvision-adaptive-learning-observer.service \
  -u goalvision-adaptive-learning-observer.timer
```

This retrieves manager evidence for the fixed window without application HTTP
payloads. Match its start/success/failure records to the invocation table in JSON.
If timer-causation records were never retained, state that limitation explicitly.
No privileged database scan is required now; the large checks were deliberately
bounded to avoid extending production read locks.

## Documentation and validation

Only this Markdown, its JSON summary, a SHA-256 sidecar and an appended TASKS.md
entry are changed, on `audit/post-guard-prematch-health-20260929` based on the
exact production closeout. The original dirty workspace is untouched. Validation
checks JSON syntax, count reconciliation, 5,925 candidate stages, 24 guard
outcomes, 18 completed run matches, delivered candidate linkage, documentation
links, checksums and Git diff scope/whitespace. Runtime tests/backtests are not
run for a documentation-only audit. No push or next development phase is started.
The local commit SHA is reported in the final handoff (it cannot be embedded in
its own committed content).

POST_GUARD_PREMATCH_HEALTH_BLOCKED_INSUFFICIENT_EVIDENCE
