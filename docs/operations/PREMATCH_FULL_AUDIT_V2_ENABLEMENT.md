# PREMATCH full audit and V2 enablement

Status: AUDIT_COMPLETED with confirmed defects and explicit unverified checks; ENABLEMENT_BLOCKED. Deployment NOT performed.

## Scope and safety

Operator authorization: full deployed PREMATCH audit, bounded proven fixes, prospective context observation, truthfully attributed existing Lab V2 publication, separate statistics, gated reversible rollout. No Official/LIVE, historical bookmaker odds, model invention/training/promotion, money transactions, or synthetic live sends.

## Initial deployment evidence

Audit opened at 2026-09-25T13:45:26.976236+00:00 UTC. Reference checkout starts at 8dfc0e0067435bfaff7cd6ca212fedbad4e5dbda; working branch codex/prematch-full-audit-v2-enablement.

Installed services read /etc/goalvision-prematch-release.conf, which specifies PYTHONPATH=/home/arvis/GoalVisionAI-prematch-release-363f567. All five services use /home/arvis/GoalVisionAI/.venv/bin/python with -P and WorkingDirectory=/home/arvis/GoalVisionAI. Deployed worktree is clean. Main working directory has extensive pre-existing user modifications; preserved.

Discovery: goalvision-lab-v2-discover.service, app.lab_v2_shadow controlled-cycle --send --max-calls 400 --settlement-reserve 100 --adaptive-database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db. Last observed run 2026-09-25 13:30:18–13:31:17 UTC, exit 1. Timer remains active, every 30 minutes.

Settlement: app.lab_combo settle --send with shared adaptive database, every ten minutes; last inspected run succeeded. Learning observer every 30 minutes; research daily; weekly report Sunday 22:30 Europe/Riga.

Permission gate: sudo -n true returns “a password is required”. Privileged rollout UNVERIFIED/BLOCKED, not PASS. No installed configuration changed. Disk 38% used, inodes 1% used.

Other Codex processes: unrelated MarketEdgeAI cwd; two existing processes in /tmp/goalvision-regulation-evidence; this session in /tmp/goalvision-national-league-evidence. Their deployment activity is not yet established. No competing implementation/deployment session started.

Persistent private evidence directory: /home/arvis/goalvision-operations/prematch-audit-20260925 (database snapshots must never be committed).

## Confirmed investigation evidence (progressive)

- Deployed lineage has fixes 50a73ce (invalid baseline probability guard) and 363f567 (expired canonical shadow chronology) absent from reference checkout. Both merged without conflicts; preserved alongside observation injection.
- Consistent SQLite backup API used from mode=ro sources. Snapshots stored outside git: adaptive.sqlite (schema 5, 47 MB), ledger.sqlite (56 MB), analysis.sqlite (schema 43, 620 MB), shadow.sqlite (9.3 GiB). SQLite journal mode DELETE; no WAL-only copy. First three quick_check OK. Snapshots are individually consistent, not a globally atomic multi-database snapshot. Live services continue ordinary writes.
- Audit windows fixed to [2026-09-24T13:00:00Z, 2026-09-25T13:00:00Z) and [2026-09-18T13:00:00Z, 2026-09-25T13:00:00Z). Later snapshot records must be explicitly labelled outside these windows. User-visible journal only; system/root journal unavailable (not complete service invocation denominators).
- Seven-day visible discovery journal: 162 traceback markers, 93 database-locked exception lines, 65 MODEL_INTEGRITY_PUBLICATION_BLOCKED lines, 1 SHADOW_CHRONOLOGY_INVALID. These are exception occurrences, not unique failed runs; cleanup can add another exception. Settlement: 182 traceback markers, 180 database-locked lines, 2 dedicated-audit-database rejection lines. Observer: 3 traceback markers, 2 lock failures, 1 dedicated-database rejection.
- Deployed quota authorizer reads and verifies all 32,710 retained claims under BEGIN IMMEDIATE for each provider request. Read-only copy benchmark 0.657 seconds for retained scan/filter; only 387 claims from current UTC day. This is confirmed avoidable writer-lock work, not proof it alone explains every timeout.
- Observer ingest replays every resolved canonical sample, scanning all learning observations inside each writer transaction. Cross-service contention and writer starvation require a bounded regression and replay benchmark.
- Baseline champion is generation-aa7e535b86267741aabc967e8044de2ab94a4334b1520a829414dd55ebc7371a, bootstrap 2026-09-18T19:53:42.075830Z; no promotion, rollback, validation, holdout consumption or shadow-run records. Research cycle 2026-09-21 has TRAIN=15, VALIDATION=0, SEALED_HOLDOUT=59, PURGED=168. 21 challenger artifacts trained; none validated/promoted. Empty validation is a readiness blocker, never a reason to loosen it.
- Ledger snapshot: 114 claims and 114 receipts; 67 prepared singles, 50 single settlements; 11 prepared combos, 7 combo settlements. Prepared != published. Exact confirmed counts and window cohorts follow.
- Critical code-path defect: experimental transport claims by prediction ID only. Different paths/versions can have different prediction IDs for the same fixture:market and race past preparation-only deduplication. Needs atomic economic-identity claim at the existing transport boundary before enabling new labels.
- Critical code-path defect: publish_experimental settlement branch lacks its own confirmed-original-publication check (CLI filters, but service can be called directly). Fix at the common service boundary.
- Football Context V2 is observation/snapshot/proof only; no independent validated seven-feature inference path found. Independent model publications remain zero.

## Completed observation windows and publication accounting

All windows are half-open UTC intervals ending 2026-09-25 13:00 UTC. Results are available by that cutoff. Cohorts are publication-time cohorts; counts below are not reused chat totals. Hypothetical units only, not user betting or cash profit.

| Measure | Last completed 24h | Last completed 7d |
|---|---:|---:|
| Confirmed singles | 7 | 37 |
| Single pending | 0 | 0 |
| Single net units | -3.60 | -16.31 |
| Single ROI (settled incl VOID denominator) | -0.5142857142857142857142857143 | -0.4408108108108108108108108108 |
| Confirmed combos | 1 | 4 |
| Combo net units | -1 | -4 |
| Persisted completed discovery summaries | 6 | 113 |
| Distinct provider-discovered fixtures | 2433 | 6023 |
| Distinct evaluated fixtures | 79 | 1363 |
| Repeated evaluated market rows | 1606 | 63137 |
| Repeated READY market rows | 19 | 142 |

24h singles: 1 WON / 6 LOST / 0 VOID, hit rate 14.29%; seven days: 8 WON / 29 LOST / 0 VOID, hit rate 21.62%. Combos: 1 LOST in 24h and 4 LOST in seven days. These weak samples provide no predictive-performance success claim.

24h: 2,433 distinct discovered fixtures, 79 evaluated fixtures and 1,606 repeated market rows. Seven days: 6,023 distinct discovered fixtures, 1,363 evaluated fixtures and 63,137 repeated market rows. Discovered/evaluated spans differ when failed cycles persist discovery before evaluation. Do not divide repeated market rows by unique fixtures as a pick rate. Completed-cycle summary sums (9,558 / 199,661 fixture appearances) repeat fixtures across ticks. Provider availability outside retained discovery responses is UNVERIFIED.

24h has 6 persisted publication cycles: 8 confirmed bet sends (7 singles + 1 combo), 4 FINAL_REVIEW_EXPIRED delivery outcomes and 1 NO_READY_SELECTIONS cycle. Seven days has 111 publication cycles: 41 confirmed bet sends, 86 NO_READY_SELECTIONS, one kickoff-window rejection. These are separate denominators; a cycle may prepare several candidates. Failed cycles may not persist a publication-cycle record.

Last confirmed single: 2026-09-24T17:37:22.228239Z, Lab message 122. Last confirmed combo: 2026-09-24T15:36:45.071812Z, message 118. Last complete discovery summary: 2026-09-24T18:30:18.074803Z; its 2 READY rows yielded an expired final review at the send boundary at 18:37:20Z. Freshness guard correctly refused the stale candidate; slow cycle processing is an operational bottleneck.

Retained ledger snapshot (longer period, not seven-day totals): 50 confirmed singles, 11 WON / 39 LOST, -22.21u; 7 confirmed combos, all LOST, -7u. Historical existing-selector segment: 47 V2-ID singles, 11 WON / 36 LOST, -19.21u, ROI -40.8723%, and 7 combos. These are NOT new Football Context model selections. New forward labelled cohort: 0; independent context model: 0. Date bounds and provenance validation follow below.

No unresolved original delivery claims in the retained snapshot: 114 claims and 114 receipts, zero unknown-delivery events, no duplicate confirmed fixture:market singles. One fixture (1551463) has DRAW and BTTS_NO singles; these are correlated but not opposing logical outcomes. 19 single economic keys also occur in published combo legs; never add those as independent selections or learning matches. Existing combo selection/exposure behavior remains unchanged.

## Learning state and provenance

At the cutoff: 975 resolved learning observations; 185 newly resolved in 24h and 963 in seven days. The later snapshot has 977 across only 314 distinct fixtures: 47 SINGLE, 2 COMBO_LEG, 928 SHADOW. The two additional resolutions are outside the fixed audit windows. Learning observations are market rows, not independent matches or public bets. 733 are genuinely new since the previous research cycle, with 6 calendar days covered. Research is in CYCLE_COOLDOWN, next eligible 2026-09-28T02:15:00.831204Z if other unchanged gates pass; scheduled daily check is 05:15 Europe/Riga. Automatic eligibility remains false (90-day gate).

Confirmed diagnostic defect: observer after_settlement omitted the previous cycle when calling eligibility, showing research_due=true and all rows as new, while the daily learning job correctly reported cooldown. Correction supplies the latest persisted non-bootstrap cycle to the report calculation only; it does not change training/promotion/rollback behavior. Regression prohibits AutoLearner.run during train=False.

Champion family EXISTING_PREMATCH_BASELINE_V1; signal ensemble policy LAB_V2_BROAD_COVERAGE_ENSEMBLE_V4, profile policy LAB_COMPETITION_POLICY_V2, accepted baseline reference 0c4f316248e55f504b780cdef4e25165b800a779. Actual active code is the deployed 363f567 lineage. Registered artifact ID is an outer document digest; its embedded artifact_fingerprint is a different inner-payload digest, not a corruption by itself. Baseline signals supply probabilities; this is not seven-feature Context V2 inference.

Research: 21 trained challengers (13 LOGISTIC, 8 REGULARIZED_LOGISTIC), feature schema LAB_FROZEN_FEATURES_V1. Eight have nine all-missing feature positions. TRAIN=15 / VALIDATION=0 / SEALED_HOLDOUT=59 / PURGED=168. Zero validation_results, holdout_results, consumed holdouts, candidate_comparisons, shadow_runs, promotion_gates, champion_predictions or rollback_events. No validated challenger or fitted deployed calibration is evidenced. Chronological label purge and 24h embargo are enforced by code; empty validation blocks advancement. No training, promotion or rollback invoked by this audit.

Learning-only as-of diagnostics (not public performance): {"resolved": 975, "wins": 340, "losses": 635, "brier": 0.22075633028160455, "log_loss": 0.6343819829302488, "ece": 0.1341677781595794, "flat_unit_pnl": -138.56, "flat_unit_roi": -0.1421128205128205, "calibration_bias": 0.13414431329860588}.

## Runtime and source-path audit

The discovery unit runs Type=oneshot, 30-minute timeout, UMask=0077, NoNewPrivileges=true; no restart policy. Its timer is persistent, `09..22:00,30 Europe/Riga`. The settlement unit timeout is ten minutes. The same systemd unit cannot overlap itself; manual/other entrypoints are not protected by that fact. Combo CLI has a nonblocking flock at ledger.lock; discovery does not share it. The new database-level economic claim serializes competing publisher paths without a second worker or scheduler. SQLite locks release on process close; no permanent lock file is assumed stale merely because its path exists. No active/stuck service was observed at first inspection.

Visible journal invocation grouping (IDs, not traceback counts): 24h discovery 28 invocations / 22 with traceback; 7d 234 / 123. Settlement 24h 144 / 48; 7d 611 visible invocations / 182 with traceback. Successful silent settlement ticks are not all represented in user-visible journal; 826 retained seven-day ledger run documents are a separate denominator. Observer 24h 48 / 0 and 7d 321 / 3. Maximum visible discovery logging span 513.46s over seven days, below 30-minute timeout; this is not a precise service duration. Root/system journal access is unavailable. Current services have StandardOutput=null except research/observer; retained cycle evidence is necessary for healthy/no-pick diagnosis.

The normal 2026-09-25 14:00:11 UTC discovery tick was observed during audit and failed at 14:01:07 UTC on unchanged deployed release. This is pre-rollout runtime evidence, NOT an enabled V2 tick. No additional manual discovery cycle was invoked.

Runtime import check reproduced `-P` and installed PYTHONPATH with the service interpreter Python 3.13.14. app.lab_v2_shadow.cli, runner, adaptive coordinator, lab_combo.cli, adaptive weekly_cli and football.client all resolved beneath /home/arvis/GoalVisionAI-prematch-release-363f567. Runtime traceback paths independently corroborate this import lineage. No live process import-memory inspection was possible when services were inactive. Credentials remain lazily loaded from existing service WorkingDirectory via trusted configuration helpers; neither env files nor process environments were dumped or sourced. getMe only verified the existing bot identity with logging disabled.

Host memory: 11,960MiB total, 10,993MiB available at inspection; 24MiB swap in use. Disk 38% used, inode 1% before backups. Readable user journals 63.6MiB; root journal/log totals UNVERIFIED. Shadow DB is 9.3GiB; repeated immutable evidence/cache growth is measurable, but this audit does not delete/cache-prune historical records. Source/cache records carry no invented provider completion times.

### Discovery, coverage and final decisions

Reachable path: installed CLI -> FootballClient (shared quota authorizer per actual attempt) -> LabV2ShadowRunner -> UTC date fixture discovery/capability catalogue -> classification/priority/fair scheduling -> pending exact review before broad current-odds pagination -> independent signal/profile evaluation -> tracked final review -> adaptive baseline resolution -> canonical non-public learning observation -> existing publication preparation -> service gate -> atomic claim -> existing Lab transport -> receipt. Settlement uses the existing shared fixture response cache for singles and combo legs, then retained results for canonical/shadow observations. Weekly CLI reads confirmed publications and settles no bets itself.

Budget remains active maximum 400/cycle, 100 protected result calls and existing daytime quota pacing (28 Riga half-hour slots); provider hard limits remain 7,500 daily/300 minute and retry accounting remains per attempt. The 40-call manual rehearsal default is NOT used in continuous composition. No new provider client, TARGET/history call, polling loop or timer is introduced. Optional capture wraps only existing completed responses.

Priority class ordering is intentional; `fair_order` rotates least-served categories inside classes and persists service history. Exact review filtering uses the first resource class; starvation of lower classes is a plausible improvement hypothesis, not a quantified policy defect in this audit. Seven-day candidates cover 1,363 of 6,023 distinct discovered fixtures; missing current quotes/quota/unfinished cycles are different causes. No quota expansion or profile/odds threshold lowering was made.

Date odds pagination retains page cursors, advertised totals and skipped/unvisited coverage rather than treating incomplete pages as definitive no-odds evidence. Exact quote refresh supersedes broad quotes, including absent markets; stale provider-origin timestamps remain stale even if HTTP retrieval is fresh. Exact fixture refresh verifies fixture/team identity and upcoming status; started/postponed/cancelled fixtures cannot receive a new READY final review. Full provider-competition availability cannot be reconstructed from evidence not retained.

Canonical learning identity is fixture:market, frozen on the first eligible positive-value input, which can precede READY. It is independent of final-review tracking and therefore does not itself prevent the later publication review. It DOES intentionally prevent later context evidence replacing the first canonical snapshot; deployed chronology fix also diagnoses old kickoff replays without rewriting them. New observation will count old canonicals as OLD_CANONICAL_NOT_ATTEMPTED. A context link is included only when the snapshot has the exact current candidate identity and matching teams; an early different candidate snapshot is not relabelled as final-decision evidence. Missing context never blocks an otherwise valid existing selector. A redesigned multiple-decision snapshot identity is separately scoped, not a retrospective repair.

Current/previous history assumption uses season and season-1. A biennial competition can therefore have unavailable previous-season evidence; this task does not broaden source scope or invent season history. Regulation verification remains exact competition/season and strict decision cutoff. Unknown duration and unsupported age/profile remain explicit missing reasons. No fresh provider history/odds were requested by this audit.

### Settlement, accounting and limitations

Publication singles require APPROVED/READY, supported market, exact current quote and final review within the existing freshness limit, existing risk/lane gates and 09:00–23:00 Riga send/kickoff window. Labels/policy versions never enter the economic claim identity. Unknown delivery remains permanently claimed pending reconciliation; an exception is not proof of non-delivery. Atomic economic claims cover both legacy and current combo identities, while combos and singles remain different products. Existing combo ranking, limits, correlation rules and historical metric definitions are preserved.

Result resolution uses score.fulltime for FT/AET/PEN, never goals or extra-time/penalty totals. Void status policy and partial-void combo multiplier semantics are preserved. Backlog of confirmed public predictions/results is zero in the ledger snapshot; prepared but unconfirmed predictions are excluded. There are 299 unresolved canonical market opportunities in the later adaptive snapshot (1,261 minus 962); these are not 299 overdue public bets and include future kickoffs. Exact due subset is reported separately below.

Original source-response fingerprints and regulation scores are retained, but the entire original provider response is not stored in the public settlement row. Independent upstream score correctness/corrections cannot be certified without additional retained provider evidence. There is no automated append-only terminal-result correction workflow in the deployed Lab path; terminal historical rows are immutable. No correction or historical rewrite was attempted. Existing update/delete guards and conflicting-settlement regressions preserve old evidence. A provider-supported correction mechanism remains a separately reviewed improvement, not an invented corrected score.

The analysis DB contains 1,200 CONTROLLED_SYNTHETIC_STAGING_SOURCE matches and a legacy OFFICIAL_GLOBAL-named model registry copied into the dedicated Lab analysis store. Those are synthetic calibration/model-chain fixtures, NOT operational learning evidence or actual Official state. They were not retrained, promoted or used for historical bookmaker-odds backtesting here. Runtime adaptive baseline champion is stored separately in adaptive_lab/audit.db.


## Findings register

Each reproduction below is offline against disposable stores/snapshots unless explicitly a read-only command. No live repair was used. “Corrected” means reviewed source/tests; the installed code remains unchanged until the privileged rollout.

| ID / severity / category | Evidence, impact and root cause | Reproduction and correction / regression |
|---|---|---|
| F01 HIGH — confirmed operational defect | 22/28 daily discovery invocations with traceback; 48/144 settlement invocations with traceback. Adaptive quota verifies all 32,710 claims under writer lock; canonical import scans 977 observations for every replay. Slow, repeated writer transactions compete across workers. | Read-only journal grouping and disposable 962-row replay: deployed 66.282s vs corrected 7.727s, both zero new rows and integrity OK. Narrow verified lookups replace full Python history scans; quota retains exact prior-minute/UTC-day semantics. Tests: test_quota_cli, test_forward_metrics, test_prematch_autonomy. This does not establish that every possible lock source is eliminated; live gate pending. |
| F02 CRITICAL — confirmed publication defect | Claims used strategy-specific prediction IDs. Two prepared, valid candidates with distinct IDs and identical fixture:market could both send. Existing preparation scans are non-atomic. No duplicate confirmed singles found historically. | Concurrent real-SQLite regression and alternate-version/legacy-claim/unknown-timeout replay. Common ComboRepository economic claim is atomic with existing delivery claim; model/label/quote IDs excluded. Combo economic groups include all sorted fixture:market legs, preserving product separation. Corrected in source; new enablement blocked until deployed. |
| F03 HIGH — confirmed result-boundary defect | Common experimental service accepted a settlement without a confirmed original receipt; CLI filtering alone did not protect all callers. Existing synthetic tests relied on this unsafe behavior. | Direct service call now refuses missing/wrong-chat/invalid original receipt; current outcome tests and result-image fake fixtures include genuine synthetic publication receipts. New attributed W/L/VOID outcomes retain label and original t.me reference. No old outcomes edited. |
| F04 MEDIUM — confirmed diagnostic defect | Observer reports research_due=true and every row as new despite a persisted research cycle. after_settlement omitted previous=; actual daily research correctly enforced cooldown. | Fixed only diagnostic eligibility input. Snapshot cutoff gives 733 new of 975, cooldown until September 28; regression forbids training when train=False. Learning policy, thresholds, automatic actions unchanged. |
| F05 HIGH — confirmed release integration risk | Accepted reference omitted deployed invalid-baseline and expired-shadow guards. Blind deployment would regress known production fixes. | Merged exact 363f567 lineage, preserving 50a73ce and chronology regression files. Invalid probabilities stay rejected; future prepared-time conflicts fail; expired canonical entries get append-only diagnostics. |
| F06 HIGH — measured throughput bottleneck / improvement hypothesis | Four retained READY delivery outcomes expired after slow final-review-to-send processing. Last complete cycle exceeded seven minutes. 9.3GiB shadow evidence repeatedly scanned in scheduling helpers. | Reproduce from completed cycle/publication timestamps and FINAL_REVIEW_EXPIRED. Freshness refusal is correct. Narrow lock fix is tested; broader scheduling/query optimization and live latency attribution remain follow-up. No freshness threshold relaxed or extra review requests added. |
| F07 HIGH — intended model restriction / data limitation | Last research split has 15 TRAIN, zero VALIDATION, 59 holdout and 168 purged. Eight trained artifacts have 9 all-missing features. No validated/promoted challenger. | Read persisted assignments/artifacts; split code groups fixtures and purges unavailable labels plus 24h embargo. Do not train/promote to create picks or change gates. More genuinely independent temporal coverage is needed. |
| F08 MEDIUM — intended evidence restriction | First canonical fixture:market input can be EARLY; old canonicals cannot accept later context. season-1 may be unsupported for biennial competition. | Existing snapshot/canonical replay regressions; historical bindings remain immutable. New context links require exact candidate/teams, source reproduction and complete retained registry proof. Missing context is disclosed and never suppresses existing selector. |
| F09 MEDIUM — data/provenance limitation | 3 old singles lack frozen learning evidence; analysis DB includes controlled synthetic historical model/calibration rows. Public history and valid learning sample differ. | 3 immutable linkage diagnostics preserved; no fake repair or historical relabelling. All 50 public singles remain in public statistics; 47 valid SINGLE source learning observations are separate. |
| F10 MEDIUM — unimplemented correction workflow / unverified upstream score accuracy | Public results retain fulltime and source fingerprint, not every raw provider response; no Lab terminal correction-event consumer. No specific wrong historical score proved. | Resolve FT/AET/PEN using regulation score; synthetic W/L/VOID/partial-void and immutable conflict tests. Do not overwrite historical rows. Future provider correction workflow needs separately defined append-only evidence and public correction handling. |
| F11 HIGH — permission blocker | sudo -n true requires password. Root journal unavailable. Cannot install service overrides or certify privileged installed-state transition. | Keep all healthy timers/services running. Prepare exact versioned operator package; no workaround mutates a deployed checkout/shared release conf. Root install and first tick remain UNVERIFIED, not PASS. |
| F12 LOW — observation/model attribution improvement now implemented | Existing app/lab_v2_shadow selector is distinct from seven-feature Football Context capture; no independent Context V2 predictor exists. | Explicit origin/version, policy/model IDs and optional observation-only snapshot link are frozen before claim/send. Independent Context model publication/statistics count fixed at zero for this implemented contract. Existing previews never relabelled; need a new current decision. |

## Source changes and safety gates

Continuous composition uses one ProspectiveObservation for the current FootballClient/runner/LearningCoordinator in the existing controlled-cycle. Explicit `--football-context-root` and optional `--football-context-registry`; defaults are disabled. Observers fail open to the unchanged valid selector on absent/corrupt/expired/conflicting proof, source store failure or snapshot failure. New selection labels use independent `--label-v2-selections`. A policy claiming to depend on seven Context features was not created. No V1 input mutation; existing parity regressions compare exact outputs and provider request sequences.

The stable prepared observation root is `/home/arvis/goalvision-operations/football-context-v2` (operator-owned directory 0700/files 0600): sources.db, snapshots.db and attempts.db are empty initialized stores. reviewed-regulations.sqlite contains four verbatim verified records copied through the existing append-only Registry API from the prior National League and renewed UCL Test stores. Original real/synthetic stores remain untouched. No records were renewed, backdated or broadened. These remain AI-reviewed source records, not a claim of human certification. Exact current-season competition IDs 43/2026 and 2/2026 resolve REVIEWED_INCORPORATED_LAW at preparation time; others/previous seasons remain unverified. NL joint interval: (2026-09-25T12:36:32.437646Z, 2026-10-02T12:36:32.436588Z). Stored UCL interval is respected independently.

Registry inventory is read-only and pinned before DecisionReceipt cutoff. Snapshot creation retains full proof. Publication linking additionally reproduces the snapshot and verifies the exact retained acquisition/view/decision/proof chain offline without reopening the current registry. Missing or corrupt retained proof omits the optional link. It never invents explanatory contributions or calls the provider.

New singles display “🧪 GoalVision AI Lab · V2 atlase”, experimental/uncalibrated wording, retained predictive families and edge, captured odds, Riga date/time, probability and stable prediction ID. Optional context line reports available features /7 for observation only. No confidence inflation, guaranteed-return wording or correct-score picks. New label origin includes schema version, actual selector/profile policy, model artifact/generation where present, probability kind/families, frozen time and optional exact snapshot/hash/cutoff; no ambiguous is_v2 flag.

Settlement remains in the existing sweep. New attributed single outcomes carry frozen origin and link the confirmed original message. Weekly reporting adds a forward V2 singles segment, keeping historical totals, combos and non-public learning separate. One flat hypothetical unit per confirmed published single; settled WON=odds-1, LOST=-1, VOID=0. ROI uses all settled single units including VOID; pending excluded. Hit rate WON/(WON+LOST); zero denominator N/A. Cohort overlap is explicitly a subset of the union, never added to total bets. Duplicate confirmed economic keys produce a diagnostic and suppress the combined forward total rather than hiding them. Historical selector segment is dated 2026-09-17T20:17:41.500043Z–2026-09-24T17:37:22.228239Z (47 singles), not retrospective Context-model performance.

No existing runtime schema migration is necessary: economic_claim and frozen attribution use the existing extensible immutable evidence documents. New context stores are separate. Existing schema initialization/upgrade/idempotency/immutability regression selection runs on disposable stores. Prepared database copies remain outside Git. No live PRAGMA mode change, repair, vacuum, destructive action or history deletion.

Unresolved canonical snapshot subset: 299 market opportunities without results; 16 were due by the 13:00 UTC cutoff, covering 4 distinct fixtures, oldest kickoff September 22 18:45 UTC. These are non-public pending observations and are constrained by the existing shared settlement fallback maximum, not public result-notification failures. Public ledger snapshot has zero pending confirmed bets and zero claims awaiting receipts.

## Remaining live gates and rollout boundary

Deployment state: ENABLEMENT_BLOCKED. Before/after installed release remains 363f567; prepared source release is recorded in the final operator manifest. No production unit, timer, shared PYTHONPATH file, interpreter, dependency, credential, champion or bankroll was changed. Stable initialized observation files are inert until the existing service receives explicit flags. Observation state NOT_ENABLED; new labelled V2 publication state NOT_ENABLED; independent model NOT_IMPLEMENTED. No enabled tick has occurred, so neither ENABLED_AWAITING_FIRST_TICK nor RUNNING_* is claimed.

The prepared installer uses a clean pinned release and four service-specific EnvironmentFile overrides: discovery, settlement, learning observer and weekly stats. Existing daily research unit remains on its installed release and cadence; unchanged schema and contracts preserve compatibility. No shared `/etc/goalvision-prematch-release.conf` edit. The installer checks original service/timer/release-conf fingerprints, pauses only those timer triggers, waits for running services to complete (bounded 30 minutes), installs all compatible overrides together, verifies units, reloads systemd and restores previously active timers. It never starts a discovery/send/settlement cycle manually. On preflight/installation failure it restores prior overrides and active timers.

`disable-data-labels` removes only new context/label flags from discovery while keeping fixes and compatible settlement/report readers. `disable-new-picks` removes discovery --send while keeping context observation and settlement active. Full rollback refuses once any new attributed prediction has a confirmed receipt; then keep compatible result/report code and disable new work. No rollback deletes evidence. Actual privileged execution remains unverified because sudo is unavailable.

Next naturally scheduled post-install cycle must verify imported release paths, unit result, RUN/END and captures, request/quota accounting, genuine READY/no-pick state and any actual receipt. No eligible selection should report RUNNING_WAITING_FOR_ELIGIBLE_PICK; only a confirmed Lab receipt permits RUNNING_WITH_CONFIRMED_LAB_PUBLICATIONS. An installed configuration without a observed tick is ENABLED_AWAITING_FIRST_TICK. None of those post-install states applies to this audit run.

## Ranked follow-ups (maximum five)

1. Roll out and measure the verified narrow lock/claim fixes (high operational usefulness, low implementation cost; 22/28 daily discovery failures and 66s replay bottleneck). First-cycle verification must precede any reliability success claim.
2. Profile and reduce discovery-to-send latency without relaxing freshness (high qualified-throughput usefulness, medium cost; four FINAL_REVIEW_EXPIRED outcomes, 9.3GiB store and >7-minute cycles).
3. Measure priority-class coverage and exact quote availability by distinct fixtures before changing allocation (high data-coverage usefulness, medium cost; only 79 evaluated of 2,433 discovered in 24h, with several independent failure causes).
4. Collect temporally spread complete forward inputs and diagnose all-missing feature mappings (high selection-evaluation usefulness, medium cost; zero validation rows and nine missing feature positions in eight challengers). Keep all readiness thresholds.
5. Define retained-source, append-only provider correction handling and public correction receipts (integrity usefulness, medium cost; original full provider result payload not retained in public settlement records, no correction consumer). No historical rewriting.


## Final offline validation

- Final affected-path selection: **1,287 passed, 0 failed, 42 subtests passed**, 39 files, 138.15s. Collection errors: 0. Exact files/exclusions/results: `docs/operations/PREMATCH_TEST_SELECTION.json`. Subtests and reruns are not added to the test count.
- Deployed baseline 363f567, exported into an isolated archive outside production: **764 passed, 0 failed, 8 subtests passed**, 212.44s. Only files present at that deployed revision were selected; no new Context tests falsely treated as missing baseline failures.
- Focused validation preceded broader testing. Initial development run stopped at 5 failures (118 passed): new stats attempted unrelated legacy rows, and old schedule tests allowed unconfirmed result sends. Corrected the cohort filter and explicit synthetic receipt setup. Next focused run had 3 failures (152 passed): a test prepared a new candidate after an already blocking legacy claim, wrapper test returned an object instead of the actual dict contract, and a timing-test ledger lacked the new atomic claim interface. Test fixtures corrected without weakening production gates. A subsequent focused selection passed 249.
- First broader run: 1,272 passed / 2 failed / 42 subtests; failures were the old optional-image tests sending unconfirmed results. They now supply confirmed synthetic original receipts. Intermediate full run 1,277 passed; after adding offline retained-proof-link verification and installer rehearsals, the final 1,287-test run above supersedes it. No failures remain in the final selection.
- Final focused selections included 125 passed (publication/settlement/schedule/quota), 58 passed (origin plus registry proof/link reproduction) and 6 installer tests. All are covered in the final broader selection, not additional test counts.
- Test coverage includes disabled/enabled/failed observation, exact output/request parity, no V1 input mutation, absent/expired/conflicting/corrupt registries, retained proof/source/snapshot failures, truthful origin, final READY/current quote/window guards, exact bot/chat gates, economic dedup across versions and legacy records, concurrent SQLite claims, interrupted claim/unknown delivery no retry, W/L/VOID and combo partial-void semantics, statistics zero/pending/VOID/as-of/overlap behavior, immutable conflicting corrections, historical metrics and shared LIVE boundary regression.
- Correction-event support is limited to rejecting conflicting historical settlement overwrites. No automated terminal correction-event workflow was added or claimed tested; see F10.
- Installer tests use disposable paths and fake systemctl/systemd-analyze calls, including failure restoration, privilege rejection and compatibility-safe disablement. These prove script behavior, NOT actual privileged deployment success.
- Kernel seccomp denied socket/connect/send syscalls for broader/baseline/final-proof/rollout selections. Test football, odds, transport and model-fitting samples are synthetic fixtures only. No real Telegram test sends, live provider fixture/odds calls, operational model training, historical bookmaker-odds acquisition/use/backtest, Official/LIVE activation or real-money action. A read-only Telegram getMe identity check was the sole audit Telegram API operation.
- `git diff --check` passed. Service interpreter/dependencies unchanged. Quota timestamp-column/document consistency: 0 mismatches among retained claims. Read-only final live ledger count remains 114 receipts and 0 new attributed predictions; prepared observation ledger remains 0 events.

The final code-health result is not predictive-performance success. Genuine published outcome metrics remain those reported above, including every loss.

## Pinned release, operator action and read-only verification

Reviewed source/tests/report commit: `e120f1b81f37c8774291e82c952378ce467fb139`, branch `codex/prematch-full-audit-v2-enablement`. Clean detached release: `/home/arvis/GoalVisionAI-prematch-release-e120f1b`. This report's final handoff documentation is committed separately; it does not change the tested source release. Prepared import verification resolved eight affected modules to that release using the existing service interpreter, `-P`, and actual service working directory. This was an isolated environment check, not evidence of installed systemd imports.

Concrete operator package: `/home/arvis/goalvision-operations/prematch-v2-release-e120f1b`. Its `manifest.json` pins the commit, original installed configuration fingerprints, exact unchanged quota arguments and affected services. Four `*.service.dropin-preview` files expose the proposed configuration for review; `import-verification.json` records prepared module paths/hashes. `pre-enable-observation-report.json` records NO_PROSPECTIVE_EVIDENCE with zero snapshots. No production configuration references this package yet.

Minimal operator action (requires root; this session's `sudo -n true` was denied because a password is required):

```bash
sudo /home/arvis/GoalVisionAI/.venv/bin/python /home/arvis/goalvision-operations/prematch-v2-release-e120f1b/install_prematch_v2.py /home/arvis/goalvision-operations/prematch-v2-release-e120f1b/manifest.json apply
```

Authorization has already been supplied; unavailable Unix privileges are the blocker. The installer must reject changed release/configuration fingerprints rather than overwrite intervening operational work. After installation, observe the next normally scheduled allowed tick; do not manually invoke discovery or readiness `cycle`. Installation alone does not prove successful capture or publication. Any later expired registry evidence remains unavailable rather than automatically renewed.

Use the same command with final argument `disable-data-labels` to stop new observation/labels while retaining compatible code; `disable-new-picks` to stop new public picks while settlement continues; or `rollback` to restore original service-specific configuration before any new labelled receipt. The installer refuses full rollback after confirmed new attributed publications. These commands preserve all evidence and never roll back the champion.

Read-only checks, without exposing process environments or credentials:

```bash
systemctl show goalvision-lab-v2-discover.service goalvision-lab-combo-settle.service goalvision-adaptive-learning-observer.service goalvision-lab-weekly-stats.service -p ActiveState -p Result -p ExecMainStatus -p ExecMainStartTimestamp -p ExecMainExitTimestamp -p EnvironmentFiles -p DropInPaths
systemctl list-timers 'goalvision-*' --all --no-pager
env PYTHONPATH=/home/arvis/GoalVisionAI-prematch-release-e120f1b /home/arvis/GoalVisionAI/.venv/bin/python -P -m app.prematch_football_context.readiness --root /home/arvis/goalvision-operations/football-context-v2 verify
```

Final installed observation: original `/etc/goalvision-prematch-release.conf`, no service drop-ins, production release still `363f567a5b9d74e4b8da152a5139d0726c64bea6`. Existing services continue; the most recently inspected discovery result remains exit-code 1. New context capture and labelled publication are NOT_ENABLED. Actual new Telegram sends by this work: **0**. Independent Football Context V2 model publications: **0**. First post-rollout tick, actual installed imports, capture/quota behavior, genuine receipt and result/report execution remain pending privileged rollout. Root-only journal evidence remains UNVERIFIED. Automated append-only terminal correction handling remains an explicitly unimplemented improvement, not a completed feature.

Stable secret-free operator summary: `/home/arvis/goalvision-operations/PREMATCH_V2_OPERATOR_SUMMARY.md`. Private retained evidence and exact test output remain under `/home/arvis/goalvision-operations/prematch-audit-20260925`; database copies and logs are excluded from Git. No push or merge into unrelated branches was performed.
