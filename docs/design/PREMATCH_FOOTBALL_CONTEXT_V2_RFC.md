# PREMATCH Football Context V2 — semantic RFC

Date: 2026-09-23. Status: implementation-ready **for Phase A only**.
Decision: seven football features; rest and all additional candidate scalars deferred.
No runtime implementation, capture, training, deployment, activation or migration is
part of this RFC. Predictive benefit is a research hypothesis, not an established result.

## 1. Authority, lineage and evidence

Engineering/product rules: `AGENTS.md`, `PRODUCT_RULES.md`, `ROADMAP.md`, `TASKS.md`.
Reviewed source: `89477a139746657e33dbcb4ac12a67438b151677`.
This documentation branch starts at that exact commit. It does not cherry-pick
runtime changes. Integration must preserve the separately completed split hardening
`25f536199fd893bd681a82ae586e62b545e28d23`.

The full audit and adjacent JSON were reviewed before feature selection:

- Commit `209de6c`, `docs/audits/prematch_football_context_feature_chain_audit_2026-09-21.md`.
- Same commit/path with `.json`: sanitized production aggregates, timestamp spans,
  artifact preprocessing and fingerprints. These files are on the audit branch,
  not assumed to exist on the baseline documentation branch.
- Split-hardening audit at commit `25f5361`,
  `docs/audits/prematch_split_hardening_2026-09-21.md`.

Audit verdict `NEEDS_SEMANTIC_DESIGN_FIRST` is accepted. All nine legacy scalar
names lack semantics; none is silently populated or renamed in V1. Eight audited
contextual artifacts have nine all-missing columns, including nonzero missing-bit
coefficients. Supplying new values would change old inference even when the value
coefficients are zero. Version isolation is therefore a correctness requirement.

This RFC uses the audit's **2026-09-21T12:25:03.828332Z** read-only evidence, not a
new production DB inspection. Counts below are historical availability indicators,
not September 23 measurements. No live API, bookmaker-history acquisition, sealed
outcome analysis or retrospective feature reconstruction was performed.

### Source trace and reuse decisions

| Reviewed source | Actual quantity / limitation | V2 use |
| --- | --- | --- |
| `app/lab_v2_shadow/runner.py:_histories` | Same-competition current-season last-99 response; conditional previous-season supplementation; profile horizon; normalized objects discard retrieval identity | Reuse existing fetched response bytes and normalized result facts, preserving bindings before that loss; no additional calls |
| `_team_goal_rates` | Last eight observed team games; venue selection; exponential weights; minimum three | Reuse pure weighted-mean primitive after separating selection/provenance; V2 explicitly selects both venues |
| `_history_market_probabilities` | Mixes opponent attack/defence, then form, availability and Poisson floor | Do not expose these adjusted parameters as observed rates |
| `context_signals.py:opponent_adjusted_form` | WDL residual against current replayed Pi state, margin term, rank weights | Reuse arithmetic under the exact support/window rules below; never describe as historical pre-game surprise |
| `pi_ratings.py:PiRatingAdapter` | Local Decimal rational-error update, same-competition state, designated home/away dimensions | Reuse update equations, not a generic published Pi algorithm or textual strength |
| CMI `normalization.py:history_context`, `features.py:derive_features` | Last-ten points fraction, season/venue means and competition-limited integer rest | Semantic comparisons only; not interchangeable adapters |
| `/predictions`, lineups, injuries | Provider estimates and availability intermediates; partial coverage | Retain existing probability signal; no new scalar features |
| Match snapshots / Feature Store / model input | Separate snapshot and 78-position contracts | Reuse validation patterns; never presume feature equivalence |
| Current caches / legacy TeamCache / standings | Append-only cache versions or mutable memory; latest readers unbounded by retrieval cutoff | New bounded reader and immutable pins; mutable memory cannot be replay evidence |
| `adaptive_lab/{features,coordinator,observations,models,repository}.py` | Signals → first opportunity → frozen observation → TRAIN transform | Future explicit V2 adapter; old path unchanged |

## 2. Normative shared semantics

“MUST” in this RFC defines a future contract, not authorization to implement or
operate it now. All seven definitions inherit every rule in this section.

### Identity, scope and sample universe

- Home/away means the **target fixture's provider-designated team IDs**, never the
  selected betting side. DRAW, totals and away-win vectors keep the same orientation.
- Identity namespace is `(provider, competition_id, team_id)` with pinned gender,
  age group, team category and competition classification evidence. Club, national,
  women, men, youth and reserve identities never share state through name matching.
- Initial source adapter: API_FOOTBALL current `/fixtures(results)` cache responses
  from the existing finished-match collector. No automatic alternative-provider
  fallback. A different adapter requires a reviewed contract revision.
- A pool consists of one explicitly selected current-season response for
  `{league: C, season: S, status: FT, last: 99}` and, if already present and valid,
  one previous-season response with `season: S-1`. The current response is required;
  previous is optional and its absence is recorded. Each response contains at most
  99 result entries; combined unique pool at most 198. Unexpected oversized or
  wrong-query responses invalidate that response; do not silently truncate it.
- This defines **last N eligible observed results**, not a guarantee of the team's
  actual last N fixtures. The league last-99 feed can omit team fixtures. Envelope
  `history_scope=OBSERVED_COMPETITION_QUERY`, `complete_team_history=false` are
  mandatory. Never use this pool to certify cross-competition rest.
- Include only exact target competition, current/previous season, both team IDs
  valid and distinct, regulation scores integer 0–30, finished status FT/AET/PEN,
  and prior fixture kickoff in `[T-H days,T)`. Target fixture ID is always excluded.
  A prior result must have been observed completed by T; kickoff before T alone
  is insufficient. Each result carries the response's trustworthy known-at time.
- Duplicate identical facts collapse by provider fixture ID. Conflicting identities,
  scores or seasons within selected response versions are quarantined and excluded
  from **all** calculations, with every conflict recorded. A later correction is a
  separate version (§8), never last-write-wins inside a pinned pool.
- Sorting is UTC kickoff, then numeric fixture ID. Latest-N uses descending order;
  Pi replay ascending. Equal-time ordering is part of the contract.
- Season-boundary carry is allowed only for the same competition/team IDs within
  H; no season reset inside this finite replay. Previous season absence never
  triggers a new API call by the context service. Promoted/relegated/new teams get
  no borrowed prior-division rating or league-average pseudo-observation.

### Profile policy: `FC_OBSERVED_HISTORY_POLICY_V1`

The following constants are copied explicitly from reviewed profile policy;
**do not dynamically resolve a future global policy under this version**.
H is maximum history age and L the scoring-weight half-life, in exact 86,400-second days.

| Profile | H | L |
| --- | ---: | ---: |
| SENIOR_MEN_PRO, SENIOR_WOMEN_PRO, LOWER_DIVISION_OR_SEMIPRO | 365 | 120 |
| DOMESTIC_CUP, INTERNATIONAL_CLUB, INTERNATIONAL_SENIOR | 365 | 120 |
| YOUTH_U17_U18, YOUTH_U19_U20, INTERNATIONAL_YOUTH | 120 | 30 |
| YOUTH_U21_U23 | 120 | 45 |
| RESERVE_OR_B_TEAM, FRIENDLY | 180 | 60 |
| UNKNOWN | unavailable | unavailable |

Classification version, reason, flags and fingerprint are pinned. Unknown profile
means all seven null with `UNSUPPORTED_PROFILE`; no silent senior default. The
mapping is a descriptive research policy, not an admission/publication policy.

All supported profiles require explicit evidence that the competition's regulation
period is 90 minutes (including stoppage time); store the provider field or reviewed
competition-format registry ID/hash for each included competition-season, including
the previous season when present. Unknown duration gives `REGULATION_UNVERIFIED`;
80-minute youth and other formats give `UNSUPPORTED_REGULATION`. Never multiply
shorter-game goals to invent a 90-minute statistic. Cup/international results use
only their own competition pool; no domestic-strength transfer. Group, qualifying
and knockout phases sharing a competition ID remain included, with phase metadata
recorded, not interpreted as interchangeable strength across competition IDs.

For FT, prefer explicit fulltime score; fall back to `goals` only with verified
90-minute format and FT status. For AET/PEN, explicit regulation fulltime scores
are mandatory. Extra-time goals, shootouts, aggregate ties, administrative awarded
scores, abandoned, suspended, postponed, cancelled and ongoing fixtures are
excluded. A regulation draw remains a draw despite advancement on penalties.

### Time, freshness, missingness and arithmetic

- T = immutable prediction-input capture cutoff; K = pinned target scheduled kickoff.
  Every source retrieval **completed**, durable registration and known-at timestamp
  must be `<= T`, and `T < K`. UTC microseconds; equality at T is allowed only when
  registration evidence proves source availability before the capture transaction.
  Equality at K is rejected. Target identity/status snapshot must say not started.
- Current-season response retrieval age at T must be `0 <= age < 6h`; previous-season
  response `0 <= age < 24h`; both also require T strictly before any stored expiry.
  Target fixture identity/status response age must be `< 15min`. These limits apply
  to collection freshness, not claims that the provider updates instantly.
- The most recent eligible game for each target team must be no older than
  `min(H,120)` days at T. Older evidence makes that side's rates/form missing;
  Pi difference is missing if either target team fails this recency rule.
- Provider update time may be absent. Then `provider_updated_at=null`,
  `provider_freshness=UNKNOWN`, `known_at=retrieval_completed_at` (or later durable
  registration). Retrieval proves observation time, not true provider update time.
  If supplied, provider update must be `<= retrieval_completed_at <= T`; future or
  inconsistent timestamps invalidate the source. Old completed fixture update
  times do not themselves expire a freshly retrieved result-history response.
- Missing values are JSON null, never 0, .5, an average or a neutral Pi state.
  Every key exists with `status`, ordered `reasons`, counts and dependencies.
  `AVAILABLE` iff numeric value is non-null and all required checks pass. Zero
  goals and zero Pi difference are legitimate supported values.
- Source/identity/hash/cutoff violations invalidate the envelope; normal unavailable
  inputs yield a partial envelope. Per-feature reason precedence: unsupported
  profile, unverified/unsupported regulation, source unavailable, stale source,
  conflicting facts, stale team history, insufficient sample, unsupported Pi state.
  Keep all applicable reasons in that order. Excluded rows alone do not null a
  feature if remaining sample/support suffices; reasons describe exclusions separately.
- Decimal precision 28, ROUND_HALF_EVEN, explicit local context for every operation;
  no intermediate quantization. Time deltas use integer microseconds divided by
  86,400,000,000, never float `total_seconds()` conversions. Summations follow the
  specified order. Decimal power uses correctly rounded `exp(exponent*ln(2))` at
  precision 28. Serialize final feature values as fixed six-place decimal strings,
  normalize negative zero to `0.000000`. No clipping of valid raw features.
  Nonfinite/out-of-range results are calculation failures, not imputation inputs.
- Pin arithmetic implementation version and golden vectors. Changes in precision,
  weighting, support, scope, rounding or exclusion rules require a new contract
  identity; prose-compatible guesses are not allowed.

## 3. Final core: seven exact field contracts

| Order | Canonical field | Meaning and exact formula | Unit / valid range |
| ---: | --- | --- | --- |
| 1 | `home_team_observed_weighted_scoring_rate` | Weighted regulation goals scored by target home team over its selected all-venue observed sample: R(home,GF) below | goals per observed 90-minute fixture, [0,30] |
| 2 | `home_team_observed_weighted_conceding_rate` | Same home-team sample, goals conceded: R(home,GA) | goals per observed 90-minute fixture, [0,30] |
| 3 | `away_team_observed_weighted_scoring_rate` | Target away team's own all-venue sample: R(away,GF) | goals per observed 90-minute fixture, [0,30] |
| 4 | `away_team_observed_weighted_conceding_rate` | Same away-team sample, goals conceded: R(away,GA) | goals per observed 90-minute fixture, [0,30] |
| 5 | `home_team_current_pi_adjusted_form` | Target home team's rank-weighted result residual and margin against **decision-time** Pi state: F(home) below | dimensionless performance score, [0,1] |
| 6 | `away_team_current_pi_adjusted_form` | Same F for target away team, independent selected sample | dimensionless performance score, [0,1] |
| 7 | `pi_designated_side_rating_difference` | Decision-time target-home designated-home Pi rating minus target-away designated-away Pi rating: r(home,H) − r(away,A) | local Pi rating units, [-79.2,79.2] |

All seven use the shared competition/profile/season/AET/provenance rules above.
Counts and freshness are metadata, not additional learning columns. Feature values
are per fixture/cutoff; probability features remain per market.

### 3.1 Four observed weighted rates

Select each team's latest min(8, eligible count) games from the pinned pool, both
home and away. Minimum three, maximum eight. Home/away here labels target teams,
**not venue-filtered samples**. For game i let d_i be kickoff, d_0 the latest
selected kickoff, GF_i and GA_i goals oriented to this team.

```
w_i = exp(ln(2) * -(d_0-d_i in exact days) / L)
R(team, X) = sum_i(w_i * X_i) / sum_i(w_i), X in {GF, GA}
```

Anchor is latest observed match, not target kickoff; normalized weights would be
unchanged by a common cutoff offset. Minimum/sample count applies to valid score
pairs: a missing concession invalidates that game for both rates. No opponent,
form, availability, baseline probability, xG or league-average adjustment. Neutral
historical/target venues need no special treatment because both venues are pooled.
This gives direct attack/defence context and better small-sample availability than
splitting each side's history into venues. It deliberately differs from the runner's
nonneutral venue-restricted sample; never label it an unchanged runner output.

Record selected ordered IDs/hashes, GF/GA pairs, kickoffs, weights, H/L, N,
effective sample size `(sum w)^2/sum(w^2)`, oldest/latest kickoff and exclusions.
Effective sample size is diagnostic, not an additional minimum or feature.
One team's unavailable sample does not remove the other team's two rates.

### 3.2 Two current-Pi-adjusted form scores

Choose the same all-venue latest-eight observed sample as rates, minimum three.
Do not drop games merely to remove a difficult opponent or unsupported rating.
Use the Pi state at T from §3.3, including the sampled games themselves. This is a
**current-strength re-evaluation of recent results**, not a residual against the
opponent's rating immediately before that historical game. It cannot look beyond T.

For each selected game, select team/opponent Pi dimensions by that game's provider
home/away designations. Let x = r(team,designation) − r(opponent,other designation).

```
expected_i = 0.5 + x / (2 * (1 + abs(x)))
actual_i = 1 for regulation win, 0.5 for draw, 0 for loss
margin_i = clamp(0.025 * (GF_i-GA_i), -0.10, 0.10)
performance_i = clamp(0.5 + actual_i - expected_i + margin_i, 0, 1)
a_i = N-i, for latest-first zero-based i
F(team) = sum_i(a_i * performance_i) / (N*(N+1)/2)
```

The expected function is a bounded **rational approximation**, not sigmoid,
calibrated win probability or expected league points. Frozen current state avoids
pretending the runner supplies per-historical-fixture pre-game ratings.

Support: target team and **every selected opponent** must have at least four
observed Pi updates and at least one update in the dimension used in that game.
If any fails, the entire side's form is null `UNSUPPORTED_PI_STATE`; preserve
selected N and unsupported opponent IDs. No zero-rating fallback. This additional
support guard is deliberate V2 semantics, not a change to the current runner.
Each side can pass/fail independently. Maximum eight form games; state maximum 198
competition games. No additional temporal weighting beyond rank weights.

Record for every game: designation, actual, expected, margin, performance, rank
weight, rating components/support counts and Pi state hash. Neutral matches retain
provider designation for this *algorithmic* expectation, not a claim of physical
home advantage. A future neutral-aware Pi variant would have a different contract.

### 3.3 Pi difference and exact state algorithm

Algorithm ID: `GV_PI_RATIONAL_REPLAY_V1`. This is the repository's independent
algorithm at reviewed commit, not an assertion of equivalence to any external
library or paper. Initialize both dimensions of every team to zero, then replay
all valid unique pool games in ascending `(kickoff,fixture_id)` order. No persisted
state from outside the pool and no hidden warm start.

For a result between designated home h and away a, read both old rating pairs:

```
e = (GF_h-GF_a) - (r(h,H)-r(a,A))
u = e / (1 + 0.75*abs(e))
r'(h,H) = r(h,H) + 0.15*u
r'(h,A) = r(h,A) + 0.10*u
r'(a,H) = r(a,H) - 0.10*u
r'(a,A) = r(a,A) - 0.15*u
```

Assignments are simultaneous from old state. Update total and designated-side
counts. Neutral games also use provider-designated sides; physical venue is not
inferred. State timestamp is T; maximum included kickoff/known-at and source
refresh timestamps are recorded separately. There is no league-to-league transfer,
season decay, goal-cap adjustment beyond input validation, or sigma-based outcome
probability in this scalar. Existing Pi probability signal is a separate output.

Difference is available only when both target teams have total count >=8, target
home has designated-home count >=3, target away designated-away count >=3, and both
pass recency/freshness checks. LOW_SAMPLE/default/INSUFFICIENT → null. Internal zero
initialization is an algorithm seed, never proof of supported team strength.
Maximum 198 updates per team. Since |u|<4/3, any component moves by <0.2 per game;
|difference|<79.2, with inclusive validation bounds [-79.2,79.2]. Do not clip.

At a neutral target this remains **designated-side** difference, with neutral status
(TRUE/FALSE/UNKNOWN) recorded. It must not be described as physical venue advantage.
No switch to averages depending on uncertain neutral metadata: that would create a
second meaning for the same scalar. This choice preserves reproducible current Pi
information while disclosing its neutral-match limitation. Study this limitation
in profile/neutral ablations before any challenger research conclusion.

Freeze all team rating pairs/counts, zero-state seed, sorted update manifest, exact
coefficients, Decimal policy, pool fingerprint and state fingerprint. Replay must
verify the state from pinned facts. A non-null string in an old prediction alone
is insufficient to generate this V2 feature.

## 4. Rate-stage decision

| Quantity | What it measures | V2 decision |
| --- | --- | --- |
| Raw observed mean | Unweighted GF/N or GA/N | Useful diagnostic golden comparator; not a second correlated feature |
| Venue-filtered/adjusted mean | Select designated-home/away games or apply a venue factor | Excluded from rates; smaller samples and target neutral ambiguity |
| Weighted observed mean | Own observed goals, recency weighting only | **Selected**, four independent team/direction values |
| Opponent-adjusted attack/defence | Runner averages own scoring with opponent conceding | Excluded; target-match construction rather than own-team observed fact |
| Form-adjusted rate | Runner multiplies by capped ±15% adjustment | Excluded; duplicates selected form plus baseline |
| Availability-adjusted rate | Additional absence-impact multiplier | Excluded; mixes partial usage/count evidence into rates |
| Final Poisson parameter | Adjusted/floored home/away match lambda, then score distribution | Excluded; too close to baseline reconstruction and not observed goal rate |

No rate is xG. Reuse the fetched evidence and pure arithmetic, not an inverse of
market probabilities. Shared future helper extraction must preserve old runner
results byte-for-byte in V1 mode, including its current float-time conversion;
V2's deterministic arithmetic is separately versioned. Do not “fix” the baseline
while exposing context. If the helper cannot be safely shared, a small pure V2
calculation is preferable to altering the existing caller; do not duplicate fetching.

## 5. Form alternatives and other candidates

| Candidate | Decision and reason |
| --- | --- |
| Current opponent-adjusted form | Selected as two explicitly named residual scores; opponent support and current-state interpretation are mandatory |
| CMI points fraction, points/(3N) | Clear, but ignores opponent difficulty and draw=.333 differs from selected draw=.5; not added as a correlated second form pair |
| Venue form | Not selected: thinner samples, overlap with Pi's designated dimensions and ambiguous physical venue |
| Legacy win-rate form | Rejected: discards draws and opponent difficulty; no aliases recent_form/home_form/away_form |
| Pi home/away/average ratings as four scalars | Defer: difference contains desired relative strength; extra coordinates increase correlation and unsupported state surface |
| Raw/effective sample sizes | Required envelope metadata and coverage diagnostics, not football performance inputs in this V2 |
| Lineup availability | Defer: confirmation is useful operational evidence but highly cutoff-dependent and may teach collection timing; no proven same-opportunity coverage |
| Injury/suspension impact | Defer: count fallback is not impact; usage window, denominator and completeness are not uniformly established |
| Lineup continuity | Defer: requires consistently identified confirmed starters and pinned comparable past lineups; not demonstrated |
| Season/venue aggregates | Defer: alternate windows and mutable provider aggregates, high redundancy with observed rates; no additive evidence yet |
| Standings-derived information | Defer: mutable legacy memory and no audited current endpoint chain; competition normalization not defined |
| Provider goal/comparison estimates | Defer: provider-defined opaque model outputs; already partly represented by signal_api_probability |
| Additional xG, congestion, travel or strength labels | Excluded: unavailable provenance/semantics or duplicate constructs; text labels never converted to numbers |
| CMI/Feature Store scalar passthrough | Rejected as automatic mapping; schema names do not prove formula/window/source equivalence |

### Rest decision: both sides not V2-ready

`home_team_rest_days` and `away_team_rest_days` are **not members of V2**, not
reserved always-null model columns. Existing competition-local last-99 history
cannot prove the latest team fixture across domestic league/cup, continental and
national-team schedules. CMI's floored kickoff gap and legacy capped advantage
are not verified actual rest.

A future separately reviewed rest contract would measure **kickoff-to-kickoff
elapsed days**, `(target_K - prior_K)/86400`, not hours since physical final whistle,
using the latest verified completed prior team fixture known at T. No floor/cap or
missing→14 substitution. It must disclose that the reference is target kickoff,
not capture. A prior game between T and K cannot be used. A known ongoing or
scheduled team fixture between that prior and K makes an “actual upcoming rest”
claim unavailable, since its completion cannot be known yet.

Before including rest, source evidence must certify an exhaustive fixture listing
for the exact team entity across all its competitions over at least the preceding
90 days through T, pagination completed, cancellations/statuses verified, and a
completed prior fixture within that interval. Zero rows is not proof of no match.
National-team appearances of club players are player workload, not club-team rest.
Unknown coverage, conflicting identity, or absence of a verified prior → missing.
AET/PEN completion is allowed for selecting the prior fixture but does not alter
kickoff gap. These are admission requirements for a future RFC, not authorization
for extra provider calls or a present claim of rest coverage.

## 6. `PREMATCH_FOOTBALL_CONTEXT_V1` envelope

This is version 1 of a new immutable **envelope**, containing semantic contract
`PREMATCH_FOOTBALL_CONTEXT_V2_SEMANTICS_1`. It is independent of Telegram, market
selection, settlement and product bankrolls. Envelope and learning-vector versions
are distinct. No field relies on a mutable global schema constant.

| Group | Required fields / exact responsibilities |
| --- | --- |
| Identity | context_schema, semantic_contract_id/hash, calculation_policy_id/hash, arithmetic_version, stream=PREMATCH, provider namespace, fixture/team/competition IDs, season, profile and format evidence hashes |
| Cutoff | prediction_capture_at=T, target_kickoff_at=K, target status, target identity source ref, neutral_status, capture_request_id |
| Values | all seven ordered named feature records: decimal string or null, status, reasons, unit, sample count, latest/oldest sample time, support counts, freshness status |
| Scope | current/previous season query identities; history_scope and completeness flags; H/L; source inclusion/exclusion decisions; ordered selected IDs per side |
| Provenance | source store namespace + immutable row ID; endpoint/query hash; full sanitized football-payload hash; normalized-facts hash; parser/version; retrieval start/end, registered_at, provider_updated_at or null, known_at; expiry; per-record completion evidence |
| Calculation | weights/form components, Pi state/manifest/hash, selected dependency refs per feature, missing and invalid-source diagnostics |
| Integrity | semantic manifest fingerprint, source-bundle fingerprint, snapshot fingerprint; format/classification/code version identities |

Store the required sanitized source payload/facts in immutable evidence storage;
IDs plus hashes alone are not replayable if a cache is garbage-collected. No API
credentials, authorization headers, bot IDs/tokens, local absolute paths or raw
unneeded player payloads in the bundle. Retain relevant football response fields
and query metadata. Hash the exact retained representation, not discarded secrets.
The immutable bundle includes input records rejected from the eligible pool and
why, so sample selection can be independently reproduced.

Conceptual API (future, not code added now):

```
select_sources(fixture_identity, cutoff, readonly_reader) -> PinnedSourceBundle
calculate_context(pinned_bundle, semantic_manifest, cutoff) -> ContextSnapshot
project_v2(snapshot, frozen_market_inputs) -> FrozenVectorV2
replay(snapshot_id, immutable_evidence_reader) -> VerifiedSnapshot
```

Feature statuses are exactly `AVAILABLE` or `MISSING`; freshness statuses are
`FRESH_COLLECTION`, `STALE_COLLECTION`, `UNAVAILABLE`, with provider freshness
reported independently as `TIMESTAMP_KNOWN` or `UNKNOWN`. Missing reason codes are
`UNSUPPORTED_PROFILE`, `REGULATION_UNVERIFIED`, `UNSUPPORTED_REGULATION`,
`SOURCE_UNAVAILABLE`, `STALE_SOURCE`, `CONFLICTING_FACTS`, `STALE_TEAM_HISTORY`,
`INSUFFICIENT_SAMPLE`, `UNSUPPORTED_PI_STATE`; transport/parser details are nested
source diagnostics. Market projection additionally permits `SIGNAL_UNAVAILABLE`
and `AMBIGUOUS_SIGNAL`. Invalid source identity/hash/as-of and nonfinite calculation
results are hard validation errors, not missing-feature reasons. For unavailable
source, sample_count is null (not observed zero); a valid empty pool has count 0.
Counts are integers, never inferred from an unavailable response.

`capture_request_id` is the SHA-256 content identity of canonical
(provider, fixture_id, T, semantic_hash, source_bundle_hash), not a random UUID or
wall-clock write time. Original opportunity retry resolves the existing request
before attempting source selection. Operational attempt IDs stay outside the hash.

Calculation and projection have no network, writer, ambient clock or Telegram
dependency. Capture orchestration obtains T **after** source collection and before
inference, validates T<K, persists evidence/snapshot, then passes exactly the same
snapshot to inference and future frozen observation. Record inference completion
and guard it before K too; a prediction completed after kickoff is not PREMATCH
learning evidence. This may yield missing V2 evidence without changing V1 decisions.
No later settlement code may generate or enrich context.

## 7. Canonical fingerprints

Canonical format `FC_CANONICAL_JSON_V1`: UTF-8 JSON, sorted object keys, compact
separators, no ASCII escaping requirement differences (use ensure_ascii=false),
Unicode NFC, booleans/null native, identifiers/counts integers, no JSON floats,
UTC timestamps `YYYY-MM-DDTHH:MM:SS.ffffffZ`, decimal quantities fixed six places
for outputs and normalized plain exact decimal strings for intermediates (no
exponents, trailing fractional zeros removed; zero is `0`). Unknown object keys
rejected except explicitly versioned metadata. Ordered feature/update/selection
arrays stay ordered; diagnostic reason sets use the specified order.

Hash = SHA-256 of domain tag + newline + canonical bytes; domain tags:
`FC_SEMANTICS_V1`, `FC_SOURCE_BUNDLE_V1`, `FC_PI_STATE_V1`, `FC_SNAPSHOT_V1`,
`LAB_VECTOR_V2`, `LAB_ARTIFACT_V2` respectively. Self-hash fields excluded. The
semantic manifest includes every field, formula, constant, profile table, source
adapter, normalization, freshness, support, missingness and arithmetic rule above,
plus ordered vector and transformer contracts. Phase A must encode that manifest
and publish its generated literal hash with golden cases; no made-up hash here.
This RFC is the normative specification; manifest omissions are Phase A failures.

Snapshot hash covers all semantic envelope content including cutoff, source hashes,
immutable source IDs/namespaces and feature diagnostics. Operational write receipt
time after capture and database surrogate snapshot row ID live outside hashed
content; `snapshot_id` is content-addressed from the hash. Same bundle, T and policy
reproduces exactly; a new retrieval with identical scores has distinct evidence
identity and snapshot hash. Vector hash includes schema, semantic hash, snapshot
hash, opportunity/market identity, ordered values, missing mask/reasons and frozen
market-input fingerprint. Artifact hash includes registry/transformer/semantic
identities, spec, ordered features, preprocessing, parameters and training lineage.

## 8. As-of source binding, corrections and failure behavior

Use **both** bounded selection and explicit pins. A new reader, separate from the
old `cached()`, takes a required T. For exact endpoint/query/namespace identity,
select a valid immutable row with retrieval_completed_at<=T, registered_at<=T,
known_at<=T and T<expiry, satisfying freshness. Order descending retrieval end,
then registered_at, then ascending content hash and stable row ID. Store the entire
candidate-selection decision and exact winning ID/hash. No unbounded latest reads.
If a selected response is malformed, return unavailable; do not silently search
older responses for a convenient value. A new provider collection is outside the
pure service and cannot fill historical evidence.

For old cache rows whose timestamp means request start rather than response
completion, or registration time cannot be proven, mark `ASOF_UNPROVEN`; do not
retroactively interpret their timestamp as completion. Phase B must verify actual
collector timestamp semantics before admitting rows. A freshness TTL alone is
never availability proof.

| Situation | Required action |
| --- | --- |
| No provider timestamp | Preserve null; use proven local completion/registration as known-at; collection freshness only |
| Retrieved after T / after K | Exclude; provider's older timestamp cannot make it previously known |
| Request starts before K, ends at/after K | Entire response unusable for that PREMATCH capture; final guard rejects capture if T>=K |
| Source stale at T | Dependent values null; no live replay refresh; previous stale pool is omitted with reason, current stale pool makes history unavailable |
| Newer cache data exists | Bounded selection excludes it for old T; replay reads original pins only |
| Provider corrects an old result | Append new source version for future captures; preserve old facts/state/snapshot/labels; correction learned after T cannot rewrite T |
| Selected versions contradict each other | Exclude conflicting fixture from pool and recalculate using remaining eligible records; no arbitrary winner |
| Pinned cache row disappears | Read retained immutable bundle; verify hashes. If bundle also missing/corrupt, hard `EVIDENCE_UNAVAILABLE` replay failure, never provider fallback |
| Fixture rescheduled or teams changed | New identity/version for future attempt; original K/team binding stays immutable; never overwrite first canonical opportunity |
| Network timeout/empty data | Preserve error/empty-response identity and missing reasons; healthy-team, zero-goal or default-strength inference prohibited |

Append-only future context tables contain source bundles, snapshots and links.
Opportunity capture uses the existing first-fixture/market canonical key. In one
adaptive-store transaction append bundle/snapshot/link plus V2 opportunity; unique
key retry returns the original record, changed material is an immutable conflict.
Capture from a separate cache store copies required facts into the adaptive bundle
before committing the link; readers never require a cross-DB atomic snapshot.
Orphan copied bundles may remain auditable; a linked opportunity cannot reference
an incomplete bundle. A crash after commit returns the original binding on retry,
not a new latest source. No database update/delete cleanup of historical evidence.

## 9. `LAB_FROZEN_FEATURES_V2`

PREMATCH only. Full contextual order is exactly:

1. `prior_probability`
2. `implied_probability`
3. `uncertainty`
4. `signal_cmi_probability`
5. `signal_pi_probability`
6. `signal_api_probability`
7. `family_count`
8. `home_team_observed_weighted_scoring_rate`
9. `home_team_observed_weighted_conceding_rate`
10. `away_team_observed_weighted_scoring_rate`
11. `away_team_observed_weighted_conceding_rate`
12. `home_team_current_pi_adjusted_form`
13. `away_team_current_pi_adjusted_form`
14. `pi_designated_side_rating_difference`

The seven existing signal/base inputs are retained for residual learning, not
counted as seven new football facts. Their exact V2 meanings:

| Input | Definition / source / range |
| --- | --- |
| prior_probability | Frozen accepted-baseline market probability before adaptive replacement; pinned `baseline.context` + artifact/policy identity; 0<p<1; missing baseline means no trainable V2 opportunity, never current champion fallback |
| implied_probability | 1 / exact frozen current offered decimal odds, odds>1, 0<p<1; pinned quote for this fixture/market at T; not de-vigged, no historical odds fetch; missing valid quote means context may persist but no trainable market vector |
| uncertainty | Frozen `evaluate_profile` policy.uncertainty + sum of its captured missing-feature penalties (weight*0.005), nonnegative finite probability-point penalty; not statistical variance; null if exact evidence absent |
| signal_cmi_probability | Sole matching-market CURRENT_MATCH_INTELLIGENCE signal with nonempty provenance; [0,1]; may originate from runner result-history/form/availability or pinned CMI snapshot, exact producer policy recorded |
| signal_pi_probability | Sole matching-market PI_RATINGS probability with provenance, [0,1]; separate from V2 stricter-support Pi difference |
| signal_api_probability | Sole matching-market API_FOOTBALL_PREDICTION probability with provenance, [0,1]; no replacement with today's estimate |
| family_count | Cardinality of frozen distinct predictive independence groups from evaluate_profile; exclude CURRENT_MARKET_CONSENSUS; include only non-null provenance-bearing predictive signals; integer >=0, <=captured qualifying signal count |

For each signal, zero matching signals → null; multiple matches → null
`AMBIGUOUS_SIGNAL`, never first/last wins. Market inputs bind exact source signal,
producer version and known-at<=T. Quote time and underlying signal-source pins must
pass as-of validation; freezing a probability alone does not prove raw source
history. Inference and observation use the same pure projection, never top-level
arbitrary `adaptive_features` injection. Baseline identity is frozen, not resolved
again from a changing champion. Formula/ranges apply independently of V1's permissive
numeric checks. Preserve full precision input evidence; vector outputs use six-place
rounding, with open-interval validation rejecting rounding to 0 or 1 for required
probabilities rather than silently clipping.

Vector envelope requires explicit schema, PREMATCH stream, ordered names/values,
mask (1 missing/0 present), per-field reasons, semantic hash, context hash, market
source hash, arithmetic/transformer identity and vector hash. Missing optional
keys are invalid serialization; explicit null is valid missing data. No ambiguous
legacy nine fields, congestion/lineup/xG placeholders or LIVE fields are copied.
Unknown schema/order/hash/stream is a hard failure, even if width matches.

Transformer `LAB_MEDIAN_SCALE_MASK_V2`: validate before fitting; convert serialized
finite decimals to binary64 under a pinned runtime; TRAIN-only available median
(even count mean of middle two), impute, TRAIN population mean/std of imputed values,
zero std→1; emit `[clip((value_or_median-mean)/scale,-10,10),missing_bit]` per feature.
Full vector → 28 coordinates. All-missing TRAIN feature: median=mean=0, scale=1,
transform [0,1]. Such an artifact **rejects a later present value in that feature**
with `UNSUPPORTED_FEATURE_COVERAGE`; it cannot silently gain support. Partial
supported columns accept present/missing according to fitted transform. Record
all-missing and constant flags and runtime/algorithm versions in artifact.
No interactions in initial V2 specs. Scope residuals/model families may reuse
reviewed algorithms with V2-bound entry points; they do not change these meanings.

## 10. `LAB_MODEL_REGISTRY_V2` and migration compatibility

Dispatch by **artifact version**, stream, feature schema, semantic fingerprint,
ordered selected feature list and transformer version. Keep V1 validator, projection,
preprocessing and baseline adapter accessible unchanged. Legacy rows lacking a schema
are recognized only in explicit V1 repository adapters, not treated as V2 by default;
their original documents/hashes are never rewritten. V1 artifacts receive only V1
frozen payloads; no V2→V1 bridge or name/width-based coercion. V1 all-missing fields
remain exactly absent/null on old evidence. Existing LIVE dispatch is unchanged.

V2 candidate specs bind registry version, schema and semantic/transformer hash in
addition to existing model/search parameters. Initial research feature subsets:
seven base/signals; seven plus rates (11); full 14. They are prespecified ablations,
not a larger feature lottery. Preserve current family/search budgets and governance
thresholds; model eligibility/promotion policy is not modified by this RFC.
V2 training datasets contain only V2 prospective evidence, never mixed V1/V2 rows.
No training occurs during this task or Phase A.

Descriptions must report declared count **and**, on TRAIN only, per-column non-null
N/fraction, unique observed values after quantization, all-missing flag, observed
variance, varying missing-bit flag, supported count (N>0), varying-value count
(>=2 distinct values), and effective varying transformed-coordinate count. Report
profile/competition/market/cutoff-age slices on permitted development evidence.
Do not read sealed holdout features to choose columns or rank candidates. Constant
or all-missing columns cannot be marketed as additional football information.
A V2 all-missing column is reportable, not an automatic change to promotion thresholds.

Database changes later are additive: context/source/link tables and explicit V2
schema/registry metadata in new records. Allocate migration number only against
the then-current merged lineage. No ALTER rewriting historical JSON, no V1 backfill,
no production migration in this task. Rollback disables the new adapter/collector;
it keeps immutable V2 evidence and leaves V1 resolver/champion behavior intact.
Old artifacts reproduce in their pinned V1 execution environment. New artifact
fingerprints include all contract IDs and training dataset/split lineage.

Split hardening is a required integration prerequisite before Phase E/F/G: fixture
grouping, fixed sealed boundary, protected prior sealed/consumed identities and
strict 24h prediction/label embargo remain unchanged. TRAIN fits transforms/models;
VALIDATION ranks; sealed holdout is not development evidence. Infeasible partitions
stay blocked. No threshold changes (including holdout 100 and automatic 500/90 days).
Schema rollout does not reset holdout reservations for the same fixture identities.

## 11. Availability and honest prospective coverage

The audited 242 observations represent **68 fixtures**, across 42 competitions;
market rows are correlated duplicates, not 242 independent coverage samples.
241/242 rows have a nonempty bounded candidate history response (~99.6%), and
227/242 have a frozen history/CMI probability (~93.8%). Neither proves the proposed
sample/support/duration rules. 241/242 numeric Pi payloads include low-support
states; only 80/242 have the Pi probability (~33.1%). Provider probability exists
on 72/242 (~29.8%). These are source proxies, not promised V2 percentages.

| Proposed feature(s) | Source availability evidence | Semantic readiness | As-of readiness today | Prospective coverage estimate / gaps |
| --- | --- | --- | --- | --- |
| Home scoring + conceding | Existing history and rate producer; no audited scalar handoff | Defined here | Needs pinned responses and verified completion/registration | Likely strongest pair for established 90-minute leagues; exact fraction unknown, cannot exceed admitted history/format/support coverage |
| Away scoring + conceding | Same source class; per-side sample counts not audited | Defined here | Same missing binding | Likely similar but not assumed equal to home; sparse team last-99 appearances can fail |
| Home current-Pi form | Existing form arithmetic; no per-opponent support counts in audit | Defined here with stricter support | Needs complete selected pool and state binding | Expected below home rates; numerical estimate unsupported |
| Away current-Pi form | Same, independently gated | Defined here | Same | Expected below away rates; no count extrapolation from non-null rate signals |
| Pi designated-side difference | Numeric Pi fields 241/242; Pi probability 80/242 | Exact algorithm/support defined here | Frozen output exists, exact state inputs unproven | Potentially substantially below raw 99.6%; 33.1% signal presence is a useful caution, not a bound or forecast |
| Both rest fields (deferred) | CMI rest numbers exist in a separate cohort | Cross-competition coverage unproven | No eligible completeness binding | 0 admitted V2 rest features; real prospective availability unknown |

**Verified existing V2-compatible frozen context coverage: zero** (contract not yet
implemented). Do not pretend a current evidence payload meets a future contract.
Expected feature coverage cannot honestly be a single percentage without inspecting
selected samples/format support prospectively. This does not block offline Phase A;
it blocks claims of model readiness and any promise of high coverage.

The audit's 423 CMI snapshots/45 fixtures had zero overlap with the affected cohort;
363 home and 364 away derivatives do not establish V2 availability. All 1,320 CMI
non-odds cache records lacked provider timestamps. Lab V2 had 2,930 history cache
records, but pins for the original opportunity were absent. Presence is not replay.

Profile gaps: source cohort senior men 225 rows, lower/semipro 12, international
club 1, reserve 1, women 2, youth 1. No meaningful coverage estimate for those tiny
subgroups, domestic cups, national teams or friendlies. Youth duration and roster
turnover, promoted teams, season openings, last-99 truncation in large leagues,
rare international/cup meetings and absent previous-season fetches can sharply
reduce support. Women are a distinct identity scope with the same formula, not
pooled with men. Reviewed 90-minute-format metadata coverage is **unmeasured**;
Phase B must report it explicitly rather than assuming all supported profiles qualify.

Phase F report denominator: every eligible PREMATCH fixture/cutoff attempt, including
missing source/quote/no-selection attempts, plus unique fixtures separately. Report
by side/feature/profile/competition, source present, semantic valid, as-of valid,
stale, N/support, reason, neutral status and final non-null rate. Compare initial
and later capture ages separately; count canonical market vectors separately.
No opportunistic complete-case sampling to advertise coverage. Phase F exit requires
an offline replay audit of every collected bundle and a reviewed coverage report;
Phase G additionally requires existing split/evidence gates and a separate research
request. No new arbitrary promotion minimum is set here.

## 12. Implementation sequence (not performed)

| Phase | Concrete work / likely files | Migration and compatibility | Tests / failure and rollback |
| --- | --- | --- | --- |
| A: typed contracts and pure calculations | New `app/prematch_football_context/{contracts,policy,calculations,fingerprint}.py`; semantic manifest; `tests/test_prematch_football_context.py`; extract/reuse primitives from `context_signals.py`, `pi_ratings.py`, runner only if no baseline change; document APIs | None; no runner/coordinator wiring, network, persistence or active registry changes | Semantic goldens and deterministic/hash validation; compare any extracted V1 helper results; import inertness; revert isolated module on failure |
| B: bounded sources and immutable evidence | New source adapter; `lab_v2_shadow/{repository,runner}.py` fetch-result metadata; audit cache completion/registration semantics; regulation-format evidence registry; read-only as-of reader | Add source bundle table only in disposable Test DB initially; exact migration number allocated later; old cache API remains unchanged | Future/stale/cross-kickoff sources, missing provider time, duplicate/correction, duration coverage; unproven metadata stays unavailable; no extra provider requests |
| C: decision-time snapshot | New service/repository under context package; optional runner sidecar using already collected responses; shared pure API | Add append-only snapshots/source refs; feature flag off by default; Test first, no model selection changes | Same cutoff/order gives identical snapshot; atomic capture, crash, replay without network; failed sidecar reports V2 unavailable and preserves current decision |
| D: frozen V2 projection | `adaptive_lab/{features,coordinator,observations,repository}.py`, new version dispatch/projection module | Add V2 links/records alongside V1, preserve canonical opportunity deduplication; no enrichment at settlement | Full producer→freeze→dataset tests, same inference/learning vector, first-opportunity conflict/restart; disable V2 writes, retain rows |
| E: V2 registry/transformer | `adaptive_lab/{models,automl,datasets}.py`, coverage reporting; separate V2 validators | Explicit schema/version artifacts; split hardening prerequisite; V1/LIVE untouched | Synthetic TRAIN transform/coverage, artifact isolation, old reproduction, sealed spies; mismatches fail closed for V2 research only; no production training |
| F: prospective Test then Lab evidence | Context capture diagnostics/runbook and opt-in Lab-only composition | Separately authorized collection; append-only current evidence, no old-row population; no sends/activation | Offline replay and source/format/support coverage report; no-selection denominator; bounded failure/quota tests; disable collection on failure |
| G: controlled challenger research | Existing permitted adaptive research pipeline, V2 schema-specific datasets/ablation report | Only separately authorized after sufficient prospective evidence and unchanged governance gates; no automatic promotion | Predictive/calibration/profile/neutral/missingness ablations on permitted splits, existing embargo/holdout tests; blocked evidence stays blocked; current champion remains authoritative |

Do not request new endpoints merely to improve coverage during A–E. Phase B/C reuse
existing collector output and cache rows with valid times. If source metadata or
format proof cannot be exposed, report missing and return for source review before
Phase F; never silently relax the semantic contract. No historical bookmaker odds
collection/backtesting is proposed. Future evaluation uses authorized frozen
prospective evidence; predictive improvement and calibration must be demonstrated
before any separate deployment proposal.

## 13. Complete acceptance-test plan

Each row requires a deterministic assertion, not just a happy-path smoke test.
Use synthetic Test data and temporary databases; future production checks are
read-only and separately scoped. Existing tests are reference coverage, not proof
that this new contract already passes.

| ID | Required acceptance case / expected result | Phase |
| --- | --- | --- |
| T01 | Rates: three games at d0,d0−L,d0−2L, GF=(2,1,0), GA=(0,1,2), weights=(1,.5,.25): scoring=1.428571, conceding=.571429; swap target sides without altering team facts | A |
| T02 | Distinguish all-venue from venue-only, raw mean from weighted, attack from concession, total from mean; eight-game limit, ninth ignored, 2→null/3→present | A |
| T03 | Form with pinned supported equal ratings: win/draw/loss margins +1/0/−1 yield performance 1/.5/0 and latest-first weights 3/2/1 → .666667; x=1 yields expected .75 (not logistic sigmoid) | A |
| T04 | Pi one 1–0 update from zero: u=4/7; h.H=.085714..., h.A=.057142..., a.H=−.057142..., a.A=−.085714...; scalar null for insufficient support; supported zero remains zero | A |
| T05 | Pi/form goldens at support boundaries 3/4, 7/8 totals and 0/1, 2/3 designated counts; opponent unsupported invalidates full selected form, no cherry-picking replacement | A |
| T06 | Horizon inclusive lower bound, strict upper bound, latest-game recency boundary, profile H/L table, season crossing and missing optional previous season | A/B |
| T07 | Future-known/retrieved/registered source rejected even if kickoff/provider timestamp old; equality at T with durable ordering allowed; unproven cache start-time cannot act as completion | B |
| T08 | Target result, future fixture, ongoing game and game completing after T excluded; collection ending at/after K and inference crossing K cannot become PREMATCH evidence | B/C |
| T09 | Mutable provider response/new latest cache/corrected old score leaves old snapshot/vector unchanged; future capture selects new version; within-bundle conflict quarantined | B/C |
| T10 | Randomize response order and duplicate identical fixtures: same normalized pool, selected IDs, state, values and hash; deterministic same kickoff/ID tie handling | A/C |
| T11 | Hash goldens: Unicode, timezone, null/zero, negative zero, decimal precision; change cutoff/source/policy/schema/order/value alters relevant hash; receipt/row surrogate does not | A/C/D |
| T12 | Replay with network clients configured to raise; pinned cache removal succeeds from retained bundle; missing/corrupt bundle fails EVIDENCE_UNAVAILABLE, never API fallback | C/D |
| T13 | Missing/timeout/empty/malformed data and absent provider timestamps remain explicit; no invented rest/goals/healthy team/default Pi; duplicate signals become AMBIGUOUS_SIGNAL | B/D |
| T14 | Current age=6h, previous=24h or target identity=15min is stale; provider timestamp future invalid; old completed-result update with fresh retrieval allowed | B/C |
| T15 | One side sparse: preserve other side rates; form may fail independently; Pi requires both supported; partial values and reasons survive persistence/training | A/D |
| T16 | New/promoted/relegated teams never inherit another division/team-name state; previous-season same-ID evidence inside H allowed, youth shorter H enforced | A/B |
| T17 | Rest trap: league game five days ago but cup game two days ago; no rest column admitted; local history never certifies completeness; ongoing/scheduled intervening match blocks future rest proof | A/B |
| T18 | Neutral TRUE/FALSE/UNKNOWN: all-venue rates same, Pi/form use designated convention consistently; no physical home assumption or covert average switch | A |
| T19 | Women/youth/reserve identities separate; cup/national/international own competition only; unverified/80-minute formats null; 90-minute verified format accepted | A/B |
| T20 | AET/PEN use fulltime only, regulation draw stays draw; absent fulltime invalid; FT fallback only under explicit policy; awarded/abandoned matches excluded | A/B |
| T21 | Settlement/result correction cannot modify source snapshot, values, vector or original result history; labels remain outside features | C/D |
| T22 | Representative V1 all-missing artifacts reproduce original probabilities and [0,1] missing pairs in pinned environment, including nonzero missing-bit coefficient effect | D/E |
| T23 | Unknown/mismatched V2 schema, order, semantic hash, stream, transformer or snapshot linkage rejected even at equal width; V2 never dispatched into V1 | D/E |
| T24 | TRAIN-only median/population scaling; available zero distinct from missing; all-missing and constant support reports; V2 all-missing-trained column later present rejected; no validation-fitted transform | E |
| T25 | Fourteen values produce 28 ordered coordinates; prescribed 7/11/14 subsets deterministic; artifact serialization/fingerprint and old artifact reproduction golden checks | E |
| T26 | Crash before/after bundle/snapshot/opportunity transaction; restart exact retry returns original binding; different request content conflicts; no refresh reselection after commit | C/D |
| T27 | Append-only UPDATE/DELETE guards, foreign-key and stream/identity validation, atomic rollback, concurrent duplicate capture; read-only reader never creates/migrates database | B/D |
| T28 | Real runner with deterministic provider fixture → context → inference projection → first opportunity → frozen settled observation → dataset → model input; every selected field has declared producer; no parity-injected scalars | C/E |
| T29 | Coverage reports include missing/no-selection fixtures, separate market rows from fixtures, supported/varying count vs declared count; no holdout reads for feature selection | E/F |
| T30 | Split-hardening 24h strict embargo (equality purged), fixture siblings, fixed holdout, prior sealed/consumed exclusion across schema versions, infeasible split blocked before model specs | E/G |
| T31 | Baseline probabilities byte-identical with sidecar on/off and missing/error contexts; Official publication/odds/bankroll/statistics/settlement, Telegram and LIVE spies unchanged | C/F |
| T32 | Imports inert, flags default off, no added provider calls when existing inputs available, source failures do not crash baseline; no deployment/activation/promotion side effects | A/F |
| T33 | Future permitted ablations compare seven-base vs +rates vs full; disclose shared baseline information, profile/neutral/sparsity, calibration, source coverage and outcome uncertainty; no benefit claim before evidence | G |

Carry forward the audit's relevant regression suites:
`tests/adaptive_lab` (including split branch's `test_dataset_hardening.py`),
`tests/test_prematch_production_integration.py`, `tests/test_lab_v2_prematch.py`,
`tests/test_current_match_intelligence.py`, `tests/test_form_features_foundation.py`,
`tests/test_rest_days_engine.py`, `tests/test_feature_store.py`,
`tests/test_model_input_builder.py`, plus Official/bankroll isolation suites.
Specifically retain `test_baseline_input_stays_stable_after_model_replacement`,
`test_exact_frozen_linkage_and_replay`, registry/serialization, readonly/append-only,
cache after-start and canonical opportunity crash tests. New contract tests must
exercise real producer projection instead of relying on old parity-injected features.
Phase G evaluation/backtesting is future authorized research over frozen evidence,
not a runtime change or historical-odds acquisition in this design task.

## 14. Non-interference, review boundary and checks

Only this RFC is added. No app/test/config/unit files changed. Shared dirty checkout
is untouched; design lives on `codex/prematch-context-v2-rfc` in an isolated worktree
based on 89477a1. No DB was opened during this design task, no credentials read,
no provider calls, Telegram sends, runtime capture, retraining, promotion, deployment,
activation or production migration executed. No production/champion state was changed.
Official behavior/bankroll/statistics, PREMATCH publication/minimum odds, split
hardening, 24h embargo/holdout rules, champion/promotion thresholds, settlement,
Lab V2 current behavior and LIVE disabled/current behavior remain untouched.

Design validation: source trace against the baseline; complete audit review and
sanitized JSON consistency checks; formula golden calculations; ordered-feature
and acceptance-matrix completeness; Markdown whitespace and docs-only diff checks.
No runtime tests are claimed to implement or validate an unimplemented contract.
The prior audit's 461-test and split audit's 2,213-test results are prior evidence,
not tests executed for this RFC. Phase A and all later phases remain unimplemented.

The semantic gate is satisfied for pure Phase A contracts/calculations. Source
pinning, verified format metadata and measured prospective coverage remain explicit
Phase B/F gates; readiness here does not authorize collection, training or activation.

READY_FOR_PHASE_A_IMPLEMENTATION
