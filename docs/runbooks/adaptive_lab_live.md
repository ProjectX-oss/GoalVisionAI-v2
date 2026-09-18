# Adaptive Lab and LIVE single engine

Status: implementation only. Not deployed, no timer installed or changed. The accepted
`0c4f316248e55f504b780cdef4e25165b800a779` discovery checkout remains authoritative until a
separate operator deployment. This feature changes no Official model, policy, bank,
statistics, credentials, destination, or source code at runtime.

## Boundaries and activation

`app.adaptive_lab` owns two independent streams, PREMATCH and LIVE. COMBO is an
analytics product, not a third calibration dataset. `app.live_lab` owns in-play
state, the reviewed remaining-goals baseline, LIVE readiness, publication and
settlement. All components are inert on import and use injected repositories,
provider clients, clocks and transports. Model artifacts contain strictly
validated JSON. There is no generated Python, eval, pickle, arbitrary import,
source rewrite, or dependency installation during learning.

The accepted discovery command behaves as before when `--adaptive-database` is
omitted. When explicitly supplied, it resolves the PREMATCH champion, runs that
probability through the existing profile/EV/readiness gates, captures shadow
opportunities and participates in shared quota governance. Default production
commands, systemd files and application startup were not changed.

The first PREMATCH or LIVE champion must be bootstrapped from a reviewed,
compatible artifact using `Governance.bootstrap` in the Test environment and
then under the separately authorized deployment. Bootstrap is never automatic
from a tiny sample. Until then PREMATCH uses the accepted engine and LIVE uses
the reviewed independent remaining-goals baseline. Research may create shadow
challengers, but promotion requires a verified previous champion for rollback.
This is a deliberate fail-closed first-activation boundary, not a sample waiver.

## Authoritative evidence and provenance audit

The authoritative current publication store is `var/lab_combo/ledger.db`, table
`evidence`, primary key `(kind, identity)`, with immutable content fingerprints.
The directory name does not imply every record is a combo.

| Field | Existing immutable source |
| --- | --- |
| Prediction identity | `single_prediction.prediction_id`; combo `prediction.prediction_id` |
| Frozen predictive opportunity | `candidate_id`, `observation_id`, `publication_key` on single or leg |
| Fixture, league, profile, kickoff | `fixture_id`, `league_id`, `competition_profile`, `kickoff_utc` |
| Market and side | `market` is a normalized side-bearing market; side is lossless parsing |
| Lane | `candidate_lane`, `evidence_lane`, `readiness_lane` |
| Actual captured odds | `captured_odds` (and combo leg `odds`) |
| Bookmaker and quote identity | `bookmaker`, `bookmaker_id`, `quote_provenance_fingerprint` |
| Origin and retrieval | `provider_origin_timestamp_utc`, `goalvision_retrieved_at_utc` |
| Model probability | `ensemble_probability`; never recomputed by the linker |
| Implied/fair/edge/EV | Frozen probability and odds plus captured `edge`/`expected_value`; pure arithmetic projection |
| Uncertainty and evidence | `uncertainty_penalty`, `predictive_families`, `predictive_family_count`, full `signals` |
| Classifier and policy | `classifier_version`, `policy`, `profile_policy_version`, `readiness_policy` |
| Artifact/generation | New explicit fields where present; legacy absence remains NULL and listed in `missing_provenance` |
| Ready / preparation time | `final_review_completed_at_utc`, `prepared_at_utc` |
| Actual publication | `receipt` at `single_prediction:<prediction_id>` / `combo_prediction:<prediction_id>` |
| Final result | `single_settlement`, or `leg_result` and aggregate `settlement` |
| Final score and source | `fulltime_home`, `fulltime_away`, `source_fingerprint`, final provider status |
| Combo leg identity | `prediction.legs[].observation_id` -> `leg_result` |

`var/lab_v2/shadow.db` stores additional candidate and `forward_selection`
evidence, but its first-ready selection can differ from the final published
quote. It is **not** substituted for the exact frozen published selection.

Legacy records can lack publication timestamps, model artifacts, classifier,
profile or independent-family identifiers. Missing critical linkage/chronology
rejects learning with `UNLINKED_SETTLEMENT`, `AMBIGUOUS_SELECTION_IDENTITY`,
`MISSING_FROZEN_EVIDENCE`, `POST_KICKOFF_LEAKAGE` or
`CONFLICTING_SETTLEMENT`. Noncritical missing provenance stays explicit NULL.
The real read-only rehearsal reports these gaps rather than filling them with
current-code estimates. No historical odds are fetched.

The dedicated audit database contains immutable source snapshots plus hashes
and original IDs. They are audit references/projections; it cannot settle or
rewrite an existing PREMATCH/combo source record. Singles are linked before
combo legs. The exact candidate/fixture/market/quote/probability opportunity key
is learned once. A combo-level WON/LOST value is never a predictive target.
Voids are retained with a null binary target and zero one-unit PnL.

## Database

The dedicated `adaptive_schema` has additive versions 1 and 2. It is separate
from the existing main schema v42 and both live production ledgers. Initialization
creates the audit graph; version-1 upgrade adds the current tables/indexes/guards
without rewriting evidence. Fresh, upgrade, replay and read-only paths are tested.
No existing production database is automatically migrated.

Tables include source records, linkage diagnostics, learning observations,
cycles, datasets, split assignments, model specs, training runs, model artifacts,
validation and holdout results, candidate comparisons/events, shadow runs,
predictions and settlements, promotion gates, champion generations, champion opportunity monitoring, activation
and rollback events, combo analytics, LIVE snapshots/candidates/claims/publications/
settlements/result claims/receipts, and shared quota claims. Parent relationships
use composite ID/stream foreign keys; split assignments also reference the exact
observation. Every evidence table blocks UPDATE and DELETE. `champion_pointers`
is the only mutable projection and switches in the same `BEGIN IMMEDIATE`
transaction as the immutable generation and activation/rollback event.

Exact replay is idempotent; conflicts reject. Artifact hashes are verified on
read, with strict schema, finite numbers, dimensions, bounds and safe probability
checks before inference. SQLite busy timeout is bounded. Reports open `mode=ro`
and `query_only=ON`, and never initialize a missing database.

## Forward metrics and diagnostics

Each stream reports resolved binary count, wins, losses, voids, hit rate, Wilson
interval, actual captured odds, probability, implied probability, edge, EV,
flat-unit PnL and ROI, expected versus realized PnL, Brier, log loss, reliability
bins, ECE, calibration bias, over/underconfidence, drawdown and both streaks.
ROI includes void stakes in its denominator; probability metrics exclude voids.
Streaks ignore voids and order results by immutable settlement time and identity.
All losses remain visible.

Segments cover profile, league, market, side, lane, generation, policy,
classifier, family count, primary family and numeric buckets, with only five
reviewed intersections. Reports cap output at 500 groups. LIVE adds minute,
score, red-card and prematch-favorite states; absent favorite data stays missing.
Minute buckets are centrally defined in `metrics.MINUTE_BANDS` (regulation
elapsed minute 45 includes first-half added time). Diagnostic HIT/MISS labels
are symmetric associations. No injury/weather/tactical explanation is invented.

Combo analytics retain all-win/lost/void/partial-void results, captured combined
odds, effective payout, PnL, ROI, leg count, losing legs, profile/market composition
and existing correlation evidence. They have no Brier/calibration target.

## Model registry and bounded search

Registry `LAB_MODEL_REGISTRY_V1` initially reviews logistic, regularized logistic,
deterministic stump ensemble and calibrated probability ensemble families.
The LIVE Poisson remaining-goals baseline is separately reviewed code; it is not
an AutoML candidate family in v1. There are no additional opaque dependencies.

The current grid has 37 candidate specs (hard maximum 50). Search varies reviewed
feature subsets, up to four interactions, regularization, history windows,
half-life, and GLOBAL/PROFILE/MARKET/PROFILE_MARKET scopes. All specs have a
fixed deterministic seed, exact key allowlist, bounded numeric hyperparameters,
150-iteration maximum, 20,000-row bound, and a 250-million estimated primitive
training-operation cycle budget including reproduction. Every successful
candidate is trained twice and must reproduce the identical artifact.

Safe inputs are explicitly frozen probabilities and context, including captured
CMI/PI/API family probabilities, optional recent form/goals/strength/rest/lineup/
xG/etc. Signal-probability features are labeled as such, not mislabeled as raw
team form. Only available inputs are projected. Missing values remain None in
source evidence; TRAIN-fitted median/scaling plus explicit missing indicators
handle them in the model. No future value or made-up zero is inserted into the
source evidence. The baseline input probability is frozen separately from
the active champion output so later training cannot silently change feature
meaning between model generations. LIVE adds its independent minute/score/time remaining/red-card
and observed goal-rate inputs; optional statistics remain missing when absent.

Scope specialists require >=200 TRAIN observations, >=60 days, >=20 examples
of each binary class and >=3 odds bands. They currently fit partially pooled
logit residuals on top of a full global classifier. They are not arbitrary new
executable per-league programs. Separate full model-family searches can be
extended only by a reviewed registry/code change. Calibrated-ensemble fitting
requires >=300 TRAIN observations.

## Chronology, holdout and comparison

Eligibility policy `LAB_ADAPTIVE_V1`:

- <100 resolved: `INSUFFICIENT_SAMPLE`.
- 100–199: `OBSERVE_ONLY`.
- 200–499 (or <90 days): research only; no automatic champion replacement.
- >=500 and >=90 days: automatic eligibility, subject to all other gates.
- >=50 newly settled binary observations and >=7 days since the previous cycle.

Voids and the other stream never contribute to these counts. Splits use 60/20/20
chronological fixture groups. Multiple opportunities on one fixture never cross
partitions. A 24-hour embargo and result-availability purge ensure earlier
labels are known before the next partition starts. Exact IDs/fingerprints are
persisted. Consumed holdout IDs cannot be reused as future sealed holdout.
They may later enter TRAIN when chronologically eligible, with that use audited.

Only validation chooses the single holdout candidate. Holdout requires >=100
fresh observations. It is never used to refit or rank alternative candidates.
There can be zero approved challengers. Mandatory gates cover predictive quality,
calibration, bootstrap uncertainty, drawdown, losing streak, ROI, selection
collapse/explosion and catastrophic profile/league/market/time/confidence groups.
No ROI-only or hit-rate-only objective. Comparisons report concentration and
fixture-clustered deterministic paired bootstrap intervals. Safety and mapping
contracts are enforced before model comparison, not learned as soft penalties.

## Shadow, promotion and rollback

The lifecycle is persisted as events alongside immutable model specs/training/
validation evidence: CREATED, TRAINED, VALIDATION_ELIGIBLE, HOLDOUT_ELIGIBLE,
CHALLENGER_APPROVED, SHADOW_RUNNING, REJECTED; immutable promotion evidence and
generations also record SHADOW_EVIDENCE_READY, PROMOTION_ELIGIBLE and ACTIVE_CHAMPION. A challenger has no
publication transport. The champion continues publishing through the same
safety shell.

Shadow stores identical frozen opportunities with both probabilities, selection
and direction disagreements, and later results. Unpublished opportunities can
be resolved through `settle_shadow_result`; they never become published-product
statistics or learning observations. Matched shadow requires >=100 resolved
opportunities spanning >=30 days. The original champion must still be active,
the holdout must pass, and both original and current global eligibility must
hold. Every promotion recomputes gates from persisted evidence, then atomically
appends a LAB generation and switches only that stream's pointer. Artifacts
are retained. Promotion replay does not create a second generation.

Artifact/probability integrity failures can restore the previous verified artifact.
Performance rollback requires >=200 observations from the active generation and
>=30 days, with significant paired Brier degradation, severe drawdown,
calibration degradation or major subgroup instability. A tiny losing streak
cannot trigger it. Incidents must reproduce against a valid input; arbitrary
reason strings cannot force rollback. Repeated rollback is idempotent. Source
files, Official state, stakes and publication thresholds never change.

## LIVE state, odds and messages

Only provider-confirmed `1H`/`2H` regulation-time fixtures qualify. State freezes
fixture ID, kickoff, provider status, minute, added time, score, teams, league,
source payload fingerprint, retrieval times, event array and event provenance,
and red-card counts from observed events. Optional feature maps can carry
reviewed statistics with their frozen source snapshot. No delayed fixture is
assumed LIVE. Extra time/penalties/halftime are not publication windows in v1.

The independent baseline estimates remaining home/away goals from actual recent
finished team matches (at least five each), current minute and score. PREMATCH
output is not a LIVE decision. A learned LIVE champion may replace this model's
probability through its own registry pointer. Raw history payloads and derived
rates are frozen with the candidate for reproduction.

LIVE supports the existing regulation-time 1X2, BTTS and 1.5/2.5/3.5 totals
settlement markets. Team totals, next goal, quarter/Asian lines and accumulators
are intentionally unsupported until normalization and settlement are reviewed.
The LIVE catalog must identify the exact live ID/name pair. Each market is
processed independently. No PREMATCH odds or historical bookmaker odds fallback.

State/score/minute/events expire after 30 seconds; LIVE quote origin and retrieval
expire after 20 seconds. Actual bookmaker identity, origin timestamp, market
identity, score/minute match, valid probability, EV>0, bounded uncertainty and
model/market divergence are mandatory. There is no LIVE decimal-odds floor
beyond a valid decimal price >1. Resolved totals/BTTS and suspended markets reject.
The provider may omit bookmaker identity or origin timestamps: the adapter
reports `LIVE_BOOKMAKER_OR_ORIGIN_UNAVAILABLE` and cannot publish that row.
There is no entitlement bypass or fabricated bookmaker attribution.

API-Football documents separate `/odds/live/bets` IDs and in-play status flags:
[official provider guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide).
Availability of those required provenance fields for the subscribed live feed
must be verified during the separately authorized Test/provider rehearsal.
No authenticated provider request was made in this implementation task.

All initial qualified LIVE selections use LIVE_EXPERIMENTAL / LIVE_EXPERIMENTAL_READY;
no unearned STANDARD/STRONG designation is forced. Tracking/rejection evidence
stays in the dedicated LIVE tables. Readiness rechecks after a fresh provider
review immediately before a durable send claim. Duplicate protection covers
opposing sides of the same market family, caps three selections per fixture and
requires goal/red-card change or >=15 minutes plus >=15% price movement for a
rebet. Uncertain delivery keeps its claim and is never retried automatically.

Every message visibly says GOALVISION LIVE, with teams, minute, score, single
selection, LIVE odds, probability, edge, EV, experimental confidence and factual
model reasoning. The existing Lab chat constant and bot validation are reused.
Settlement uses existing regulation-time score/void rules, with LIVE WON/LOST/VOID
notifications, a separate ledger and separate learning observation. No Official
or PREMATCH bankroll/statistics changes occur.

## Quota and future automation

`SharedQuota` layers durable per-attempt accounting on the existing exact-header
quota manager and client pacing/retry limits. All participating workers must use
the same audit DB. Protected category reserves: settlement 150, PREMATCH exact
review 300, LIVE state 200, LIVE odds 300, LIVE final refresh 200. Broad discovery
cannot consume these reserves. LIVE additionally has an 1,800-call daily cap.
Each attempt, including retries, consumes a durable claim before HTTP. A
rolling 60-second counter and daily counter survive restarts. The lower of
provider header capacity and local allowance wins; ambiguous headers block.
Initial account-status preflight retains the existing bounded client behavior;
it never makes an odds request. LIVE worker limits a run to 80 attempts and ten
fixtures. Shared category governance is opt-in and does not retrofit the running
accepted process until the later operator deployment.

Recommended future schedules, subject to observed provider allowance: LIVE scan
once per two minutes with demand/capacity gating; settlement can reuse the same
cycle; read-only/learning eligibility once daily; full research at most weekly
and only with 50 new resolved observations. Do not use a 15-second broad polling
loop under this quota. Final refresh is mandatory even when scans are less frequent.
Current v1 LIVE runner has no persistent history/catalog cache; its bounded calls
and cap take precedence over throughput. Adding that cache is a reviewed
optimization, never a reason to reuse a stale price.

## Operator commands and deployment procedure

Read-only commands (human output unless `--json`):

```text
python -m app.adaptive_lab learning status --database /dedicated/lab-adaptive.db
python -m app.adaptive_lab learning report --database /dedicated/lab-adaptive.db --json
python -m app.adaptive_lab learning why-not-learning --database /dedicated/lab-adaptive.db
python -m app.adaptive_lab live status --database /dedicated/lab-adaptive.db
python -m app.adaptive_lab live statistics --database /dedicated/lab-adaptive.db
```

Commands also cover eligibility, loss-review, win-review, calibration, champion,
challengers, shadow, champion-history, promotion-evidence, rollback-history,
why-not-promoted, why-rollback, unlinked-settlements, fixtures, tracking,
candidates and settlement-diagnostics. `--at <UTC>` makes eligibility output
reproducible. None of these commands loads credentials, sends or trains.

Future mutation entry point, **not executed for production in this task**:

```text
python -m app.adaptive_lab.worker initialize --database /dedicated/lab-adaptive.db --enable-lab-automation
python -m app.adaptive_lab.worker learning-cycle --database /dedicated/lab-adaptive.db --ledger /existing/lab_combo/ledger.db --enable-lab-automation
python -m app.adaptive_lab.worker live-cycle --database /dedicated/lab-adaptive.db --enable-lab-automation
```

LIVE publication additionally requires `--send`. The current PREMATCH CLI gains
only the explicit `--adaptive-database` opt-in. `LabComboService.check_results`
accepts an injected coordinator to link/reevaluate after durable settlement;
a daily learning-cycle also recovers that linkage without modifying the source.

Exact next deployment action: review the implementation commit and this report,
then perform a separately authorized **Test-environment no-send deployment**
using a disposable copied publication ledger and a new audit database. Verify
real live feed catalog/bookmaker/origin support, quota behavior, bootstrap
artifact compatibility and no-send messages before any enabled production job.
No cherry-pick, timer switch, bootstrap or activation is part of this task.

Emergency procedure after a future deployment: remove the adaptive opt-in from
the new worker invocation and stop only the newly authorized automation job;
retain the accepted discovery checkout and existing ledgers. Inspect champion
history, rollback evidence and unknown delivery claims read-only. An eligible
integrity/performance rollback uses `Governance.rollback` and the previous
verified artifact, never SQL UPDATE of historical documents. If corruption
prevents safe rollback, leave publication disabled and restore a verified audit
backup under operator control. Do not delete losing records or retry ambiguous
Telegram sends.

## Verification and limits

Tests use synthetic observed outcomes, fixed clocks and recording transports.
The high-volume rehearsal uses 600 training-era opportunities plus 140 fresh
shadow opportunities per stream and proves independent training, promotion,
rollback, retained old artifacts, and no Official tables. Real data is assessed
once through a read-only transaction and an in-memory audit projection.
`LIVE_FORWARD_SAMPLE_EMPTY` is reported when no genuine LIVE observations exist.
Synthetic gains are software verification, not evidence of football profitability.

No automatic exploration of unreviewed families, code generation, GBDT framework,
stacking, team totals or next-goal support is claimed. Current specialization is
partial pooling; advanced optional features require real source capture. Product
ROI is based on actual published selections; shadow selection metrics are
explicit counterfactual selection proxies, not bets. Performance rollback monitors published outcomes and a separate immutable
champion-opportunity monitor. Throughput rollback requires at least 200
opportunities, 30 days, 50 fixtures and 50 previous-model selections, then a
selection ratio outside 0.5–2.0; it can detect zero-publication collapse without
pretending there are settled bets. An operator should not infer real improvement from a passed
synthetic rehearsal or a tiny real forward sample.
