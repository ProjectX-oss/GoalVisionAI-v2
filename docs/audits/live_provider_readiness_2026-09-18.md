GOALVISION AI — FINAL LIVE PROVIDER NO-SEND + DEPLOYMENT READINESS AUDIT
Audit date: 2026-09-18 UTC

STARTING STATE
Implementation commit: 0ceaa7d23f9a5f49cfa47247f7370eeb53986b09
Audit branch: codex/live-provider-readiness-audit
Audit worktree: /home/arvis/GoalVisionAI-live-audit
Accepted running discovery commit: 0c4f316248e55f504b780cdef4e25165b800a779
Running discovery imports: /home/arvis/GoalVisionAI-throughput
Runtime working directory: /home/arvis/GoalVisionAI
No existing checkout was reset, cleaned, overwritten or deployed.

FINAL TEST VERIFICATION
Original exact implementation: 1930 passed, 563 subtests passed, 0 failed,
0 collection errors; 584.70 seconds. Outbound sockets denied except loopback;
synthetic credentials only. Disposable local data/goalvision.db satisfies an
existing test fixture prerequisite and was never copied from production.
The authenticated rehearsal then exposed a real refresh integration regression:
FootballClient.last_matches returns a list, whereas history_rates expects an
API response envelope. LiveRunner now wraps that observed list as response rows,
preserving its contents and fingerprintable frozen history. No inferred football
values, bookmaker evidence or timestamps are introduced. Empty history continues
to fail closed. No policy thresholds or supported market names were changed.
New regression uses the real FootballClient with httpx.MockTransport, checks the
six-request final refresh and history rates, and proves absent bookmaker/origin
still prevents candidate creation. LIVE focused tests: 23 passed in 3.96 seconds.
Final full suite: 1931 passed, 563 subtests passed in 607.76 seconds; 0 failed,
0 collection errors. This includes the new real-client history regression.
Command: /home/arvis/GoalVisionAI/.venv/bin/python
/tmp/goalvision_adaptive_offline_tests.py -q --tb=short --durations=10.
Harness runs the entire pytest repository suite with real outbound networking
blocked. Final tested code is identical to the final audit commit below.
Final audit commit: the commit containing this document; external review records its SHA.
All 918 tracked app/test file hashes were recorded for the final full run and
verified unchanged before commit; documentation changes do not change tested code.
compileall app/tests: PASS. Controlled adaptive/LIVE imports with sockets denied:
PASS. CLI help, worker help and deterministic read-only JSON: PASS.

DATABASE
Disposable audit databases only, under /tmp/gv-live-provider-audit and
/tmp/gv-live-offline-smoke; real source projection used SQLite :memory:.
No schema change was added by this audit. Existing schema version 2; 32 append-only evidence tables / 64 mutation guards.
Fresh install PASS; constructed v1-shaped upgrade missing the v2 monitor table
PASS, existing source evidence retained; migration replay twice PASS. This is a
constructed previous-schema rehearsal, not a claim that a released v1 production
database was upgraded. Exact replay idempotent; conflicting replay rejected.
UPDATE and DELETE on evidence rejected. Foreign-key stream linkage tests passed.
foreign_key_check=[]; integrity_check=ok. Only champion pointer projections are
mutable by reviewed transactions. No production adaptive database was opened as
a writer, and no source ledger migration was attempted.

BOOTSTRAP
PREMATCH and LIVE require separate reviewed, executable-free JSON artifacts.
Registry LAB_MODEL_REGISTRY_V1, feature schema LAB_FROZEN_FEATURES_V1. Supported
families: LOGISTIC, REGULARIZED_LOGISTIC, STUMP_ENSEMBLE, CALIBRATED_ENSEMBLE.
Required exact artifact keys: spec, stream, preprocessing, bias, coefficients,
stumps, specialists, training_fingerprint, artifact_fingerprint. The embedded
fingerprint is canonical SHA-256 of all fields except artifact_fingerprint;
the repository also hashes the complete artifact document. Specs enforce reviewed
features, dimensions, finite bounds, safe hyperparameters and deterministic seed.
An operator must reproduce the artifact against reviewed frozen inputs, verify
stream and external expected fingerprint, and inspect probability contracts.
Governance.bootstrap appends learning_cycles (REVIEWED_BOOTSTRAP), model_specs,
training_runs, model_artifacts, champion_generations and activation_events, then
atomically switches that stream's champion_pointers row and appends the
ACTIVE_CHAMPION candidate event. generation_id is 'generation-' plus SHA-256 of
stream, artifact_id, previous_generation, reason, evidence, created_at and
scope=LAB_ONLY. The generation retains the exact artifact FK and stream. Existing champion blocks
bootstrap. Initial generation has no predecessor; preserve the accepted service
checkout for operator rollback. Later model promotion retains that registered
artifact as the previous verified champion, enabling automatic model rollback.
The existing PREMATCH prediction ensemble and LIVE_POISSON_BASELINE_V1 are NOT
currently compatible registered baseline artifacts; no tested baseline adapter
or reviewed replacement artifact is provided by this release. Training a tiny
real sample or fabricating coefficients to fill the registry is not acceptable.
Production bootstrap and challenger activation performed: NO.

QUOTA
Central reserves: SETTLEMENT=150, PREMATCH_REVIEW=300, LIVE_STATE=200,
LIVE_ODDS=300, LIVE_REFRESH=200. LIVE daily cap=1800. Worker bound=80 attempts,
maximum 10 fixtures. Audit used a stricter aggregate ceiling of 25 attempts and
at most two fixture identities planned for inspection, with daily reserve 1500.
SharedQuota serializes per-attempt claims with BEGIN IMMEDIATE, UTC daily counts
and rolling 60-second counts, using the lower of local/provider allowance.
Other categories' reserves cannot be consumed by the claiming category. Reserves
are conservative floors, not guarantees of continuing indefinitely after they
are depleted. Restart/minute/daily/reserve tests passed. Additional offline audit:
mock status + failed/retried fixture request = three HTTP attempts, two durable
LIVE_REFRESH claims; LIVE request 1801 rejected, settlement still allowed.
CURRENT PRODUCTION SHARED QUOTA PROTECTION IS NOT ACTIVE. Discovery needs the
new release plus --adaptive-database pointing to the SAME absolute DB as LIVE's
--database. The current combo settlement CLI has no shared-quota opt-in; it needs
a reviewed client binding and SETTLEMENT categorization, preserving settlement
behavior. All consumers of the account need participation or bounded allowance.
Initial PREMATCH /status precedes binding and is not locally claimed. LIVE claims
its initial /status after the response; preflight retry attempts are not atomically
reserved. Therefore strict cross-process accounting is not proven even merely by
supplying the same DB. A reviewed preflight reservation/bootstrap protocol is
required before promising a hard shared minute limit across all workers.
The no-send worker command itself can settle and evaluate learning; audit instead
used LiveRunner with no learning callback, no publication calls, no transport.

FORWARD LEARNING
One real source snapshot at 2026-09-18T16:48:27.636838+00:00:
/home/arvis/GoalVisionAI/var/lab_combo/ledger.db, mode=ro, query_only=ON,
BEGIN read transaction. No recalculated old probabilities or old odds.
PREMATCH published settled: 13; WON=3, LOST=10, VOID=0.
Linked settled singles: 10; WON=3, LOST=7, VOID=0.
Three older singles explicitly MISSING_FROZEN_EVIDENCE; excluded from learning,
not hidden from raw product outcomes. Missing original model generation/artifact
provenance remains null rather than invented.
Combo records linked: 3; WON=0, LOST=3, VOID=0, PARTIAL_VOID=0; flat-unit PnL=-3.
Unique deduplicated PREMATCH predictive opportunities: 12 (10 singles plus two
additional combo legs); learning targets WON=4, LOST=8, VOID=0. Combo-level outcomes
never become probability calibration targets. Seven overlapping legs contribute
no second learning observation. Days covered=0. Learning state=INSUFFICIENT_SAMPLE;
automatic_eligible=false, research_due=false. No real training occurred.
LIVE observations=0. LIVE_FORWARD_SAMPLE_EMPTY. No LIVE evidence kinds in the
source snapshot and no new adaptive production DB was found in runtime paths.
The current live system may settle/publish independently after this snapshot;
those events are neither audit writes nor audit Telegram sends.

DUPLICATE / SETTLEMENT / PRESENTATION
Offline real-client regression and existing tests prove duplicate claims, same
market-family/opposing-side protection, goal/red-card transitions, joint >=15
minute and >=15% odds-change rebet rule, maximum three selections per fixture,
resolved-market rejection, EV<=0 rejection, and optional-feature missingness.
Synthetic disposable publication claims used recording transports only. Explicit
LIVE WON, LIVE LOST and LIVE VOID dry runs returned PnL +1/-1/0, rejected duplicate
publication, replayed settlement idempotently and produced correctly labeled
settlement previews. PREMATCH observations and COMBO records remained zero in
those tests. No Official store or bankroll dependency was constructed.
A synthetic candidate preview is included below, clearly marked synthetic. No
real candidate or settlement message was delivered.

LIMITATIONS / MINIMUM FIXES
- Registerable, independently reviewed PREMATCH/LIVE bootstrap artifacts are
  missing. Supply baseline-compatible registry adapters or reviewed replacement
  artifacts with reproduction evidence; do not lower learning thresholds.
- Finish shared-quota wiring for every participating worker, including settlement
  and initial status preflight accounting. Existing production is not retrofitted.
- Provider market names are not interchangeable with implemented synthetic names.
  A later reviewed adapter change must bind actual live catalog IDs/names and
  exact regulation-time semantics; retain quarter/Asian/team/next-goal exclusions.
- State freshness currently measures retrieval age, not the unknown upstream
  score/event update age. Kickoff timestamp is not an update timestamp.
- Current provider requests test availability only at the recorded audit times;
  they do not establish general league coverage or model predictive accuracy.
- Synthetic model evolution proves software mechanics, not real profitability.
Provider-specific blockers and smallest next steps are detailed in READINESS below.

PRODUCTION ISOLATION
No installed units, timers, service processes, credentials, source ledgers,
Official data or production adaptive registries were intentionally mutated.
The audit never imports/constructs a Telegram transport for real data. Offline
sockets were denied; authenticated rehearsal allowed only API-Football's host.
Provider credentials were loaded from existing secure environment/.env without
printing them. No API keys, raw provider dumps, runtime DBs, logs, caches, data/
or var/ were staged for commit. The one implementation fix is limited to LIVE
history response shape with one regression test; the rest is audit documentation.

REAL PROVIDER CAPABILITY
Authenticated audit calls: 22 total (12 initial + 10 post-fix), all GETs, no HTTP
retry attempts observed. An initial harness signature error occurred before any
request and consumed zero calls; it is not included in 22. Aggregate bound=25.
First pass: 2026-09-18T16:48:20Z–16:48:25Z; final pass:
2026-09-18T17:00:09Z–17:00:16Z. No historical bookmaker odds, scraping or provider
restriction bypass. Team history requests were finished-match results only.
/fixtures?live=all: HTTP 200, 61 fixtures initially / 54 on final pass.
/odds/live/bets: HTTP 200, 266 catalog entries.
/odds/live: HTTP 200, 54 fixture rows initially / 45 on final pass.
/odds/live?fixture=1504307: HTTP 200, one row, 32 markets.
All observed paging: current=1,total=1. No additional pagination requested.
Only two fixture identities received targeted inspection, despite feed-wide
availability counts. No claim of inspecting all 61/54 fixtures individually.
Initial quota headers: daily limit=7500, remaining=1618; minute limit=300,
remaining=299. Final headers at 17:00:16Z: daily limit=7500, remaining=1597;
minute limit=300, remaining=290. Header names:
x-ratelimit-requests-limit / x-ratelimit-requests-remaining (daily),
x-ratelimit-limit / x-ratelimit-remaining (minute). Interpretation=NORMALIZED.
Audit attempts are counted from the client, not inferred from differences in
headers while production workers continue independently. Disposable durable
quota_claims=22. The 1500-call audit daily reserve was retained throughout.

BOOKMAKER / ORIGIN VALIDATION
Inspected LIVE odds row keys: fixture, league, odds, status, teams, update.
No bookmaker object, bookmaker ID, bookmaker name or reviewed deterministic
bookmaker attribution was present in either inspected fixture row.
LIVE_BOOKMAKER_IDENTITY_UNAVAILABLE
Neither the API-Football brand nor a pre-match bookmaker was substituted.
A timestamp field DOES exist: response[].update. Example on the exact refreshed
fixture: 2026-09-18T16:59:29+00:00, ISO-8601 seconds with explicit UTC offset.
Retrieval: 2026-09-18T17:00:16.206161+00:00. Numerical age=47.206161 seconds.
Other inspected feed row: update=2026-09-18T16:59:24+00:00. Its feed retrieval
at 17:00:11.675097Z makes it 47.675097 seconds old.
The field belongs to the entire provider fixture-odds row. The accessible public
provider guide describes live update frequency, but does not establish whether
this timestamp is a per-bookmaker quote origin, per-market update, or aggregate
snapshot update. The formal documentation page returned no extractable endpoint
schema in this audit. Thus exact quote-origin semantics are NOT proven. Presence
of an ISO timestamp is not evidence of a particular bookmaker updating a quote.
LIVE_QUOTE_ORIGIN_TIMESTAMP_UNAVAILABLE (verified bookmaker quote-origin semantics;
not a claim that response[].update is absent).
Even provisionally treating update as the row update timestamp fails the existing
20-second freshness limit for both inspected rows. Retrieval time and HTTP Date
were never substituted for update. fixture.timestamp/date are kickoff time;
fixture.status.seconds is match clock, neither is a quote-origin timestamp.
Adapter blocker remains LIVE_BOOKMAKER_OR_ORIGIN_UNAVAILABLE. Mandatory provenance
was not weakened, and no real quote was admitted to publication readiness.

LIVE MARKET NORMALIZATION
The authenticated LIVE catalog, not the PREMATCH catalog, was used.
Regulation-time 1X2: ID 59, Fulltime Result; values Home/Draw/Away map deterministically
to HOME_WIN/DRAW/AWAY_WIN. Captured final odds: 1.2 / 5 / 29. Side mapping works;
zero quotes pass mandatory bookmaker/freshness evidence. GoalVision settlement
uses fulltime.home/away for FT/AET/PEN, excluding extra-time/shootout scores.
BTTS: real ID 69, Both Teams to Score; values Yes/No, observed odds 3.4/1.3.
The adapter expects Both Teams To Score (capital T), so this real name is rejected.
Intended internal identities BTTS_YES/BTTS_NO are NOT activated by this audit.
Settlement would require both regulation-time scores >0 for YES, otherwise NO.
Over 1.5 / Under 1.5: real ID 36, Over/Under Line; value Over/Under, handicap
1.5, odds 1.825/1.975, main=true. Adapter expects Goals Over/Under, so rejected.
Intended internal identities OVER_1_5/UNDER_1_5 require regulation total >1.5/<1.5.
Over 2.5 / Under 2.5: same intended half-goal normalization and regulation-time
semantics (>2.5/<2.5); no retained real 2.5 offer establishes this line in the
inspected evidence. Real ID36 name remains unsupported by the current adapter.
Over 3.5 / Under 3.5: likewise >3.5/<3.5; no verified current real offer for this
line. It is not presented as provider-supported merely because synthetic tests pass.
Other inspected actual values included handicap 1.75, 2, 0.5, 1, 1.25 and 0.75;
none was silently converted into a supported half-goal line. The normalizer's
exact line allowlist is 1.5,2.5,3.5; it also rejects main=false.
Unsupported actual markets safely excluded: ID33 Asian Handicap, ID32 Asian
Corners, ID39 Away Team Goals, ID58 Home Team Goals, ID85 Which team will score
the 2nd goal?, ID65 Next 10 Minutes Total, ID52 1x2 - 80 minutes, and ID23 Final
Score, among others. No team total, next goal, Asian or interval market was
misclassified as regulation 1X2 or total goals. No correct-score publication.
Minimum mapping work is a separately reviewed explicit ID/name/period allowlist
for real 59/69/36 and exact value/handicap semantics, with captured-shape regression
tests. Mapping alone cannot repair absent bookmaker identity or stale quotes.

REAL LIVE REHEARSAL / FINAL REFRESH
Two unique in-play fixtures inspected, both league 1087:
- 1504307, Haka vs Klubi-04: first 64', score 1–0, 2H; final exact refresh 76',
  score 1–0, 2H, added time=null, seven events, zero red cards. Profile UNKNOWN:
  provider data has no GoalVision competition_profile and no profile was invented.
  Histories: nine eligible prior FT matches per team after chronology filtering.
  LIVE probabilities generated for all 11 internal supported side/line identities.
  32 provider market definitions observed; one family / three 1X2 side identities
  mapped for diagnostic readiness checks. Strict normalized quotes=0, candidates=0,
  ready candidates=0. Final state is tracked/unpublishable, no candidate lane.
- 1504308, JäPS vs EIF: first 57', score 0–0, 2H; three events available. The first
  refresh failed at the now-fixed history-list integration. Final feed shows a
  current LIVE odds row at 68', with no bookmaker identity and update 16:59:24Z.
  No second exact fixture refresh or probability evaluation was forced for this
  fixture; its later score/readiness are not inferred from the earlier snapshot.
Fixtures with real LIVE odds=2. Fixtures with verified bookmaker identity=0.
Fixtures with a populated update field=2; verified bookmaker quote-origin
semantics=0. Real internal market-side readiness evaluations=3 (one 1X2 family,
DIAGNOSTIC ONLY). Fully provenance-qualified normalized market evaluations=0.
This distinction is used in the final count REAL LIVE MARKETS EVALUATED: 3.
Final-refresh attempts=3 across both phases; complete actual final-refresh paths=1.
The completed path fetched /fixtures?id=1504307, /fixtures/events, two team-history
responses, /odds/live/bets and /odds/live?fixture=1504307. It did not reuse the
broad discovery object or broad odds response as final evidence. The state
fingerprint and payload fingerprint were newly calculated from these exact
responses. No valid normalized bookmaker quote identity could be minted. Separate
diagnostic fingerprints retained missing bookmaker fields as null, never as a
fabricated bookmaker; these records were not passed to candidate() or publish().
Final state fingerprint:
d650417a40c75176a5056efd2b5a9282dd1904d9483bb32e6fb841a87026ae58
Exact odds payload fingerprint:
57af2ffefa765b4392aebbf0fe8ff2a9faaf8fddee5649c3da5d238e960e176b

FRESHNESS / EV / PROBABILITY
Final match-state retrieval age=2.846280 seconds; event retrieval age=2.801540
seconds. Retrieval freshness gates accepted both. Upstream state/event update
ages cannot be derived from the provider's kickoff or event elapsed times.
At evaluation +31 seconds, the identical captured evidence was rejected for stale
state/score/minute/events without rewriting its timestamps. This is a diagnostic
clock-advance check against real captured data, not another provider request.
Real odds update age=47.206161 seconds, already >20; stale odds rejected. A fresh
real quote cannot be demonstrated: no inspected quote met the freshness and
bookmaker requirements. Synthetic fresh/stale boundary tests passed separately;
they are not labeled real provider proof. No freshness thresholds changed.
Real diagnostic EV calculations (uncertainty=0.07 for zero red cards):
HOME_WIN: odds=1.2, implied=0.8333333333, GoalVision=0.8409315495,
  fair odds=1.1891574298, edge=+0.0075982162, EV=+0.0091178594.
DRAW: odds=5, implied=0.2, GoalVision=0.1414220256,
  fair odds=7.0710343456, edge=-0.0585779744, EV=-0.2928898722.
AWAY_WIN: odds=29, implied=0.0344827586, GoalVision=0.0176464249,
  fair odds=56.6687022082, edge=-0.0168363337, EV=-0.4882536767.
All fail LIVE_BOOKMAKER_OR_MARKET_PROVENANCE_MISSING and STALE_LIVE_ODDS.
DRAW/AWAY also fail NON_POSITIVE_EV. Positive home EV is insufficient. Odds 1.2
was numerically accepted (valid decimal >1); no hard LIVE minimum floor was added.
These are predictions from real observed state/history and diagnostic price
arithmetic, not betting recommendations, published selections or forward outcomes.

READINESS
LIVE_PROVIDER_BLOCKED
NOT_READY_FOR_DEPLOYMENT
Real endpoint access and a corrected no-send refresh work, but mandatory bookmaker
identity is absent, origin semantics remain unverified, inspected odds are stale,
and BTTS/totals catalog mapping is incompatible. Unit-test success cannot override
these blockers. No real challenger or production champion was activated.
The smallest provider unblock requires a genuine, documented bookmaker identity
and quote-update/origin contract in the current LIVE feed, plus actual quotes
passing <=20 seconds. Obtain provider-supported evidence/clarification or review
an authorized alternate LIVE source; never assign API-Football as bookmaker or
replace update with retrieval. Do not scrape or use historical bookmaker odds.
After that, review actual 59/69/36 mapping, bootstrap compatibility and common
quota/preflight wiring, then repeat bounded no-send proof before deployment.

PUBLIC PROVIDER REFERENCES
[API-Football official beginner guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide)
supports separate LIVE catalog IDs, LIVE status flags, kickoff timestamp semantics,
and variable update frequency. It does not prove bookmaker attribution or exact
per-quote origin semantics for the observed update field.
[Formal API-Football documentation](https://www.api-football.com/documentation-v3#tag/Odds-(In-Play))
was referenced, but no endpoint schema text was extractable in this audit.
Authenticated current responses establish the observed fields and numbers above;
no claim is made that the public documentation proves missing semantics.

SYNTHETIC PRESENTATION PREVIEW
SYNTHETIC UNIT-TEST PREVIEW — NEVER SENT
🔴 GOALVISION LIVE — Lab
⚽ Home vs Away
⏱ 60'
📊 Score: 0–0
🎯 LIVE selection: Vairāk par 1.5 vārtiem
💰 LIVE odds: 2.00
🧠 GoalVision: 59.4%
📈 Edge: +9.4%
📊 EV: +18.8%
Confidence: EXPERIMENTAL
Remaining-time goal model uses observed team scoring history, current score and minute; value is compared with captured LIVE odds.
Experimental estimate; no guaranteed outcome.

FINAL SAFETY VERIFICATION
Id=goalvision-lab-v2-discover.timer
ActiveState=active
UnitFileState=enabled

Id=goalvision-lab-combo-settle.timer
ActiveState=active
UnitFileState=enabled

Live checkout HEAD: 0c4f316248e55f504b780cdef4e25165b800a779
Live tracked diff: empty; unchanged from audit start.
Installed unit/.env SHA-256 values (all unchanged):
/etc/systemd/system/goalvision-lab-combo-discover.service  94822885338fdbe81f0950f4fbc2daa06bc87842877a8b363121b66bebe476e3
/etc/systemd/system/goalvision-lab-combo-discover.timer  5a04f4322b9b6c3f8769955e6bbd2dfbb0c65b9831b16eff7f5bb0d41a0bbf5f
/etc/systemd/system/goalvision-lab-combo-settle.service  a2250dcea9db4541f7c422650afd9b73f9ea0d370679739f25bfeb48b4ee5e2c
/etc/systemd/system/goalvision-lab-combo-settle.timer  cb07e8fa9591abfdae04d10143d7edf7f74fb71d62867ebf5c3acee72427a620
/etc/systemd/system/goalvision-lab-v2-discover.service  a318e177538a27bc2cae23fbd90c2257ff047e2474cb643206f77f0e58b4c86d
/etc/systemd/system/goalvision-lab-v2-discover.service.bak  f220b95710cc9f21a1ed257c6217fe8abfc31546601ec22e2fe47e86f086780d
/etc/systemd/system/goalvision-lab-v2-discover.timer  ef90b6425254963230eedc441acc968f466a40b3ce37c86a1291849d1d017fd7
/home/arvis/GoalVisionAI/.env  a7fd57f149512998d8617689b586c4fcae5440c66cf246b9710ae3612fc23d44
Telegram sends caused by task=0
Official publications/statistics/bankroll mutations caused by task=0
Production deployments=0
Production champion activations=0
Production adaptive DB writes=0
Timer/systemd changes=0
.env changes=0
No real bets placed. Production worker activity is independent of this audit.

EXACT FUTURE DEPLOYMENT / ROLLBACK COMMAND SEQUENCES
See [the gated operator plan](live_provider_deployment_plan.md). No commands from
that plan were executed. Missing prerequisite artifacts/wiring are explicit stop
conditions. External report: /home/arvis/goalvision_live_provider_readiness_review.txt
