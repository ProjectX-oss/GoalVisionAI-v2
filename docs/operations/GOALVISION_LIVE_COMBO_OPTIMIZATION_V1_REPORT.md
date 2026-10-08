# GOALVISION_LIVE_COMBO_OPTIMIZATION_V1_REPORT

**Completion re-review — 2026-10-08 23:13:06 Europe/Riga**

The user requested a second pass through the entire task. All **64 traceable requirements** across the 12 priorities, safety rules and earlier operator evidence were checked. This is **not a claim that every requested research algorithm is complete**: 37 findings are PASS, six NO_CHANGE, five SMALL_GITHUB_FIX, four DATA_QUALITY_LIMITATION and 12 BLOCKED_NEEDS_MORE_EVIDENCE. The full matrix is appended in section 19.

Latest source commit: `d642f72d579ab45d622459befea5b4c55e7813d8`. Machine-readable re-review:
[GOALVISION_LIVE_COMBO_REQUIREMENTS_REVIEW.json](../evidence/live_combo_optimization_20261008/review_2313/GOALVISION_LIVE_COMBO_REQUIREMENTS_REVIEW.json).

Latest fixed-cutoff facts, superseding the earlier snapshot's current-state counts:
- LIVE: **9 confirmed publications; 1 WON, 6 LOST, 2 pending**. Sixty discovery cycles and three results-only cycles; discovery correctly closes at 23:00 Riga while the enabled timer continues results. 1,770 natural provider calls; zero initiated by this audit.
- COMBO: 199 published, 194 settled, **69 W / 125 L / five pending**, P/L −20.350797u, ROI **−10.4901%**. Double remains zero. V2 descriptive ROI remains +9.77%; no statistical winner.
- SINGLE: 506 published, 501 settled, 281 W / 219 L / one VOID / five pending; P/L −37.22u, ROI −7.4291%.
- Learning: 2,883 retained observations, 2,870 resolved eligible / 1,164 independent fixtures; **CALIBRATION_FIT 297/300**. TRAIN remains 1,804/560; validation/holdout remain zero. Fit still requires the October 10 03:00 Riga window close.
- DC: **29 paired fixtures / five dates**, still below the unchanged 30/seven CI gate. Brier: champion 0.553948, multiplicative market 0.589684, DC 0.607375. No incremental gain established.

Corrections completed in this second pass:
1. LIVE odds movement previously grouped by a state fingerprint containing retrieval time. It now compares identical observable score/minute/cards/events and quote source/market, preserving original snapshot fingerprints. Nine comparable pairs are present; all have zero observed movement. This does not establish executable prices or broader price stability.
2. Future diagnostic capture now distinguishes fixture `goals` from LIVE quote `teams.*.goals`. Missing score/minute values remain unknown instead of appearing as observed mismatches.
3. Disagreement now includes model generation and explicit context-quality segments. Of 3,886 rows, 3,862 name the bootstrap generation and 24 name the deterministic ensemble; all 24 provider-zero cases occur in the latter group. All context ratings are NOT_EXPLICITLY_RATED. No rating is invented.
4. Coupon publication readiness is kept separately from context quality.
5. The quality auditor now verifies frozen cycle, tracked-refresh and candidate hashes before aggregation.

**635 tests PASS**; all three core exports reproduce byte-for-byte. Earlier immutable JSON is preserved. Reviewed historical PREMATCH commits are present; ADMIN `ab327dd` is on its separate verified remote branch, and installed DC repair `ebd0924` contains the previously missing JSON file.

Still incomplete/unavailable: C's calibrated ranker/artifact contract, a validated correlation-adjusted joint model, isolated HTTP-boundary timing and historical rejected raw quote payloads, calibration fitting before legal readiness, and statistically supported strategy ranking. These are explicitly not marked done. No live pipeline reorder, model change, deployment or capture-sink activation was performed.

The timestamped **original 22:06 snapshot** below is retained for provenance. For latest counts and completion status use this re-review and the section 19 matrix.

---

Evidence cutoff: **2026-10-08 19:06:10.302493 UTC / 22:06:10 Europe/Riga**.
Runtime preservation recheck: 19:34:49 UTC.
Research source commit: `b716db64fd365892937a871b28cf945a50305336`.
Branch: `research/live-combo-optimization-20261008`.
Machine-readable index: [GOALVISION_LIVE_COMBO_OPTIMIZATION_V1_EVIDENCE.json](../evidence/live_combo_optimization_20261008/GOALVISION_LIVE_COMBO_OPTIMIZATION_V1_EVIDENCE.json).

This is a fixed-cutoff, read-only audit plus isolated research implementation. All counts below refer to that cutoff or the explicitly stated window. Natural timers continued normally while the audit ran. No production deployment, restart, publication, provider request, training, activation, promotion or rollback was initiated by this work.

## 1. EXECUTIVE_SUMMARY

- **PASS — LIVE does publish:** 49 natural evening cycles produced five confirmed prediction publications; one was LOST and four were pending at cutoff. Six SENT delivery events include a result notification, not six predictions.
- **NO_CHANGE — actual LIVE policy:** the operator already installed the quote-age-diagnostic V2 release. The task's older 20-second production-cap description is obsolete. No cap was reinstated or changed.
- **DATA_QUALITY_LIMITATION — LIVE bottlenecks:** 145 state/quote mismatches, 49 unsupported-market diagnostics and nine final-refresh quote-missing deliveries. Candidate versions also frequently have non-positive model EV. Old evidence does not retain enough raw state/quote data or HTTP timing to distinguish minute mismatch, score mismatch and request sequencing causally.
- **BLOCKED_NEEDS_MORE_EVIDENCE — COMBO winner:** 199 confirmed coupons, 192 settled, 69 W / 123 L, P/L −18.350797u and ROI −9.5577%. V2 has positive descriptive ROI, but tiny connected samples and nonpaired cohorts do not establish superiority. Double has no confirmed coupons.
- **SMALL_GITHUB_FIX — completed:** opt-in LIVE observability, immutable original-candidate A/B replay, fail-closed C diagnostics, coupon/leg failure analysis, probability-dependence diagnostics and reproducible performance evidence. Existing components were reused.
- **BLOCKED_NEEDS_MORE_EVIDENCE — AI:** calibration is 289/300 independent fixtures and its fit window is still open. Validation/holdout are zero. Six-method DC comparison has 28 fixtures over five kickoff dates. No calibrator, joint model or new classifier was fitted.

## 2. REPOSITORY_STATE

**PASS.** GitHub base and source checkout agree at `2b93f574b39906df92b6cae1c4274756c9728ee0` on the existing reviewed LIVE-quote-age branch. The new worktree is:

`/home/arvis/goalvision-worktrees/live-combo-research-20261008`

The original `/home/arvis/GoalVisionAI` checkout had 220 pre-existing dirty paths. Its porcelain status is unchanged; these files were neither staged nor incorporated. No production-branch history was rewritten. The new branch contains the reviewed source commit above and the documentation/evidence commit containing this report. Resolve the latter with `git rev-parse HEAD`; the report does not embed its own recursive commit hash.

Changed implementation files:

- `app/adaptive_lab/combo_evidence.py`
- `app/adaptive_lab/combo_research.py`
- `app/live_lab/runner.py`
- `app/live_lab/research.py`
- `operations/live-combo-research/audit.py`
- `operations/live-combo-research/offline_tests.py`
- `tests/test_live_combo_research.py`

Additional tracked changes: this report, `TASKS.md`, and the sanitized JSON bundle under `docs/evidence/live_combo_optimization_20261008/`. No databases, environment files, credentials, raw journal logs or runtime `var/` files are included.

The branch is intended for reviewed research-only publication to GitHub, not production merge/deployment. The final delivery message records the verified push and clean-worktree status.

## 3. VPS_RELEASE_AND_RUNTIME

**NO_CHANGE.**

| Component | Actual installed state |
|---|---|
| PREMATCH/SINGLE/COMBO | `/opt/goalvision-live-evening-4f547cf-20261007` |
| LIVE | `/opt/goalvision-live-quote-age-42a441f-20261008` |
| LIVE timer before/after | enabled, active; discovery allowed 18:00–23:00 Riga |
| LIVE timer schedule | every five minutes, minute pattern `:02/5`; wakes outside discovery for results |
| PREMATCH discovery | 10:00–18:00 Riga; result settlement continues 24h |
| Quote age | V2 diagnostic-only; no maximum-age veto |
| ADMIN Codex | autorepair timer disabled, service inactive |
| Shared limits | 7,500/day and 300/min; existing result reserve retained |

Read-only `live-quote-age.py` preflight passed with `current_mode=ENABLED` and `ADMIN_CODEX_SYSTEMD_DISABLED=PASS`. No `--apply` was used.

Hashes of **142 protected GoalVision systemd files/routes match before and after**. Official received zero mutations; this preservation check covers protected routes and our changes, not a newly audited Official database. LIVE's actual enabled timer takes precedence over an obsolete global health field saying DISABLED.

PREMATCH champion, SINGLE 1.50, private SINGLE ≥1.70 / 70–80%, DC COMBO leg floor 1.30, Double leg floor 1.70 / 70–80%, today-only, early COMBO loss, result replies, exposure rules and staking remain unchanged. Market V1 new publications remain disabled.

## 4. LIVE_ROOT_CAUSE

**PASS for diagnosis; DATA_QUALITY_LIMITATION for missing detailed provenance.**

The premise “no LIVE predictions” is no longer true at cutoff. The five publications are confirmed by stored receipts, with zero unmatched LIVE claims. The current pipeline does not have a general transport outage.

| Stage | Recorded evidence | Interpretation |
|---|---:|---|
| Natural cycles | 49, all LIVE_SCAN_COMPLETE | Worker runs |
| Fixture discovery exposures | 1,112 | Repeated fixtures across cycles; not unique games |
| Broad LIVE odds rows | 969 | Feed has data |
| Eligible-feed fixture exposures | 287 | Policy-dependent counter; old cycles did not uniformly record every key |
| Reviewed fixture exposures | 180 | Exact fixture path is reached |
| Stored candidate versions | 261 | Repeated market/time versions |
| State/quote mismatch diagnostics | 145 | Score/minute alignment guard rejects |
| Unsupported market diagnostics | 49 | No verified supported mapping |
| Fixture-review unavailable diagnostics | 4 | Review did not produce usable evidence |
| Final-refresh quote-missing delivery events | 9 | Initial readiness does not guarantee final readiness |
| Final readiness blocked delivery events | 1 | Guard retained |
| Confirmed prediction receipts | 5 | One LOST, four PENDING |
| Unmatched LIVE claims | 0 | No known unresolved claim without receipt |

Current V2 candidate rejection counts overlap: NON_POSITIVE_EV 117; duplicate opportunity 7; suspended market 7; probability/odds contract 5; severe model-market contradiction 6. Older V1 had 43 non-positive-EV and three severe-contradiction rejections, plus 64 stale-quote flags. These are not counts of independent lost betting opportunities.

The runner reads fixture state, events, cached-per-cycle historical match context, market catalog and then exact LIVE odds. A time gap between state and quote is plausible, but elapsed upstream timing was not stored. It would be speculation to say all 145 mismatches are provider latency, or to remove the alignment guard.

No unsupported market ID or unknown bookmaker was silently reinterpreted. API-Football indicative feed prices are explicitly not guaranteed executable bookmaker prices.

## 5. LIVE_FRESHNESS_ANALYSIS

**PASS — offline counterfactual only.** Buckets below count saved candidate versions; the full discarded broad-feed population is unavailable.

| Quote age | Older V1 | Current diagnostic V2 |
|---|---:|---:|
| 0–10 s | 0 | 7 |
| >10–20 s | 12 | 68 |
| >20–30 s | 29 | 68 |
| >30–45 s | 35 | 21 |
| >45–60 s | 0 | 21 |
| >60 s | 0 | 0 |
| Total | 76 | 185 |

The upper bound belongs to each bucket. Provider-origin age is measured at the captured candidate's preparation time.

| Offline age cap | V1 initially ready versions | V2 initially ready versions |
|---|---:|---:|
| 20 s | 5 | 21 |
| 30 s | 19 | 43 |
| 45 s | 33 | 51 |
| Actual recorded policy | 5 | 56 |

V1 has **28 versions blocked only by age**. V2 has zero age-only rejections because age is already diagnostic. Counterfactuals retain all other captured blockers, including invalid/future timestamps, and do not rerun or bypass final refresh, exposure or delivery. They cannot be interpreted as additional guaranteed publications.

Quote-retrieval-to-preparation time: median 0.066685 s, mean 0.087114 s, maximum 0.353167 s across 261 versions. This is **not HTTP response latency** and not total state-to-quote elapsed time. HTTP latency remains NOT_CAPTURED. No same-state successive-quote pair was available for an odds-movement estimate; price stability and actual execution availability therefore remain unknown.

**NO_CHANGE:** no freshness policy change is proposed from this counterfactual. The optional observer records client/quota call elapsed time separately from HTTP latency, which stays null until measured at the HTTP boundary.

## 6. LIVE_QUOTA_EFFICIENCY

**NO_CHANGE / BLOCKED_NEEDS_MORE_EVIDENCE.** The 49 natural cycles consumed 1,125 recorded provider requests (22.96/cycle, 225 per confirmed publication). This descriptive ratio includes discovery, rejected candidates and settlement; it is not a marginal “cost per profitable pick.” Agent-initiated production requests: zero.

Existing catalog/per-cycle history caching, broad-feed filtering, exact refresh, result reserve and cycle ceilings are retained. The optional diagnostic sink adds no requests and is not wired into any running worker. Request reordering could change which fixture state matches the quote and needs measured timing first; no speculative reordering was shipped.

PREMATCH current-odds context, 24 cycles: 2,395 fixture exposures / 222 unique fixtures; fresh 839 (35.03%), no-record 685 (28.60%), stale 545 (22.76%). Other categories include bookmaker filters and changing sweep pages. Exact refresh used 392 calls, date sweeps 269. There were 194 known fresh outcomes among 323 recorded exact outcomes (60.06%); 392/194 = 2.02 exact calls per known successful fresh fixture. Incomplete outcome coverage prevents treating this as full provider yield. Tracked exact refresh: 130/212 (61.32%); 82 failed outcomes lack detailed reasons.

Repeated no-yield occurred in 61/99 attempts with prior failed evidence. Small league samples and missing failure causes do not establish an improvement from reordering. No API ceiling or refresh priority was changed. League/competition/country/lead-time breakdowns and best/worst observed yields remain in `odds_yield.json`; they are observational, not a league whitelist.

## 7. CURRENT_COMBO_PERFORMANCE

**PASS — authoritative confirmed-publication ledger, one-unit coupon stake.**

199 published; 192 settled; 69 WON; 123 LOST; zero VOID/PARTIAL_VOID; seven pending. Mean combined odds 9.1973, median 2.6271. Flat P/L −18.350797u; settled-stake ROI −9.5577%; binary hit rate 35.9375%.

Naive joint-probability Brier 0.212406, log loss 0.609561, ECE 0.052827, bias (prediction minus outcome) −0.026984. Mean scored naive probability 33.2391%; realized binary hit rate 35.9375%. This overall average does not establish leg calibration or independence. Frozen leg probability retains its original provenance; market-inclusive ensemble estimates must not be mistaken for an independently calibrated champion forecast. The per-leg probability_kind field is preserved. Maximum known publication-order losing streak: 13; pending entries break the known streak.

Results are receipt-backed and retain the original frozen odds, leg order, policy and settlement. Missing labels remain missing. VOID is excluded from binary probability scoring; partial VOID is separately flagged and uses recorded/frozen remaining-leg payout. Exact Decimal and VOID behavior have regression coverage.

SINGLE context (not pooled with coupons): 506 published, 493 settled, 273 W / 219 L / 1 VOID, 13 pending, P/L −42.24u, ROI −8.5680%, Brier 0.227261, log loss 0.645865, ECE 0.054560. Current 1.50 cohort: 257 published, 245 settled, 147 W / 97 L / 1 VOID, 12 pending, P/L −11.60u, ROI −4.7347%, ECE 0.012790. Full odds medians, reliability bins and policy/market/league/timing/quality segments are in `performance.json`.

## 8. COMBO_COHORT_COMPARISON

**BLOCKED_NEEDS_MORE_EVIDENCE — descriptive comparison, no ranking.**

| Cohort | Published | Settled | W / L | Pending | Mean odds | Median odds | P/L u | ROI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Legacy | 19 | 19 | 1 / 18 | 0 | 72.2258 | 39.2126 | -5.572924 | -29.33% |
| Singles V1 | 68 | 66 | 32 / 34 | 2 | 2.0604 | 1.7161 | -6.243887 | -9.46% |
| Singles V2 | 53 | 51 | 21 / 30 | 2 | 2.7807 | 2.6991 | 4.983138 | 9.77% |
| Market V1 | 39 | 39 | 10 / 29 | 0 | 2.7708 | 2.6277 | -10.524984 | -26.99% |
| DC agreement | 20 | 17 | 5 / 12 | 3 | 3.1213 | 2.9732 | -0.992140 | -5.84% |
| Double 1.70 / 70–80% | 0 | 0 | 0 / 0 | 0 | — | — | 0.000000 | — |

| Cohort | Scored n | Predicted joint | Hit rate | Brier | Log loss | ECE | Bias |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Legacy | 19 | 11.46% | 5.26% | 0.053825 | 0.216521 | 0.062009 | 0.062009 |
| Singles V1 | 66 | 44.98% | 48.48% | 0.231774 | 0.654673 | 0.108195 | -0.035018 |
| Singles V2 | 51 | 31.80% | 41.18% | 0.256337 | 0.709421 | 0.115654 | -0.093789 |
| Market V1 | 39 | 29.01% | 25.64% | 0.197110 | 0.583475 | 0.117409 | 0.033644 |
| DC agreement | 17 | 26.02% | 29.41% | 0.217744 | 0.633962 | 0.061195 | -0.033932 |
| Double 1.70 / 70–80% | 0 | — | — | — | — | — | — |

All cohorts have zero full/partial VOID in this snapshot. Probabilities are scored on binary settled coupons only; “predicted” in the second table uses the scored sample. Missing Double metrics are null / INSUFFICIENT_EVIDENCE.

V2 has the highest observed ROI among these cohorts, but there is no statistically supported winner for forecast quality, calibration or risk-adjusted return. Legacy's low Brier is largely influenced by its low event frequency; it is not proof of a better model. Cohorts use different candidates, dates and odds.

The descriptive CI screen requires ≥30 settled coupons and ≥7 independent day/fixture-connected clusters and refuses an immature cohort. Current connected clusters: Legacy 10, V1 3, V2 2, Market 3, DC 5, Double 0. None qualifies. No CI, Sharpe ranking or paired score delta is fabricated. These are research evidence gates, not publication thresholds.

## 9. COMBO_FAILURE_ANALYSIS

**PASS — all 123 losing coupons are represented.** 67 had one known losing leg, 43 had two and 13 had three. The per-coupon output preserves losing legs, frozen probabilities, odds, market, league, lead time, odds age, disagreement findings and source/result fingerprints. Fourteen leg outcomes across all published coupons remain unknown; they are not imputed.

All confirmed coupons in this snapshot have three legs. Double has zero published coupons, so a two-versus-three-leg performance comparison is unavailable. Existing market, combined-odds, lead-time and per-leg calibration segments are provided without selecting new thresholds.

Examples of descriptive concentration:
- V2 mixed-market coupons: 7 W / 6 L, ROI +46.36%; V2 totals: 14 W / 24 L / two pending, ROI −2.75%.
- Market V1 mixed: 3 W / 12 L, ROI −40.19%; totals: 7 W / 17 L, ROI −18.73%.
- DC mixed: 3 W / 5 L, ROI +28.41%; totals: 2 W / 7 L / three pending, ROI −36.28%.
- Legacy 1X2 coupons: eight losses; mixed: one win / ten losses.

These small, selected slices are not out-of-sample rules. They do not justify banning totals or promoting mixed markets. No unique dominant erroneous producer is established by co-occurring soft findings alone.

## 10. JOINT_PROBABILITY_AND_CORRELATION

**SMALL_GITHUB_FIX — COMBO_JOINT_PROBABILITY_RESEARCH_V1.**

The exporter retains the independent product, the mathematical Fréchet lower/upper bounds and shared-risk flags. Bounds are `max(0, sum(p) − n + 1)` and `min(p)`; they are not fitted joint predictions. Correlation-adjusted probability and empirical joint calibrator remain null with INSUFFICIENT_EVIDENCE.

Across 199 coupons: shared league flag 83, shared market family 193, shared signal family 199; no shared fixture/team flags. Shared model family can produce correlated estimation errors even across different games, but a flag does not quantify outcome correlation. No arbitrary coefficient, independence claim, Monte Carlo “edge” or simulated precision was introduced.

There is insufficient prospective, independent coupon evidence for a separate joint fit. A scenario model would require validated marginal forecasts and a justified dependence structure. Existing DC match-score scenarios do not by themselves model cross-fixture errors.

**BLOCKED_NEEDS_MORE_EVIDENCE:** C remains a diagnostic no-selection screen until an immutable as-of calibrated-leg and validated-joint evidence contract exists. Its ranking function is explicitly not implemented; this is a documented incomplete research prerequisite, not a hidden production rule.

## 11. CALIBRATION_READINESS

**BLOCKED_NEEDS_MORE_EVIDENCE.**

Champion: `generation-aa7e535b86267741aabc967e8044de2ab94a4334b1520a829414dd55ebc7371a`; family EXISTING_PREMATCH_BASELINE_V1; unchanged bootstrap activation from 2026-09-18 19:53:42 UTC. Registry schema LAB_MODEL_REGISTRY_V1; feature schema LAB_FROZEN_FEATURES_V1; learning stage CHALLENGER_RESEARCH.

Total observations 2,875; resolved eligible 2,862; independent resolved fixtures 1,156. Twelve historical COMBO_LEG source records remain retained and excluded from independent PREMATCH research. This work produces zero learning observations.

| Partition | Observations | Independent fixtures |
|---|---:|---:|
| TRAIN | 1,804 | 560 |
| CALIBRATION_FIT | 289 | 289 |
| VALIDATION | 0 | 0 |
| SEALED_HOLDOUT | 0 | 0 |
| PURGED | 760 | 298 |
| EXCLUDED | 22 | 20 |

Counts are governed partition assignments and need not sum like disjoint fixture totals. Calibration requires ≥300 independent examples **and** the frozen fit window to close on **2026-10-10 03:00 Riga**. Validation begins October 11 03:00 Riga; holdout begins October 19 03:00 Riga. No window was opened early.

Dataset fingerprint: `560b38a16ab45b5063799baf5f6e7040642903c9cd3b52e485745ee506440833`.
Calendar-plan fingerprint: `9b154abc5b1ca4f18187150c2ca0a8d4d37b93b9c3893e97b2e61457329ca439`.

Next legal fit is research-only after both gates pass: reuse the existing identity/Platt/temperature comparator and only admit isotonic under its sufficient-sample gate. Preserve model generation, schema, frozen partition and data fingerprint. Current calibration slope/intercept, calibrated extremes and league-level fitted comparisons are unavailable because no fit was legally due. Published raw forecast reliability is reported separately, without calling it a fitted calibrator.

## 12. MARKET_AND_DEVIG_EVIDENCE

**NO_CHANGE — reuse existing current-quote research.** Multiplicative, Shin, Power and OO-EPC already exist; no duplicate math package was introduced. A retained current capture from 2026-10-08 14:33:49 UTC, fixture 1644617, includes bookmaker margins, complete market probabilities, method parameters and quote/consensus fingerprints. It is an illustrative availability check, not representative OOS proof. See `devig_example.json`.

C diagnostics expose raw model probability, fair market probability, probability difference and raw EV. Coupon legs expose odds age and kickoff lead time. A de-vig probability is a method-dependent market estimate, not demonstrated truth. Raw model edge is not a calibrated edge.

**BLOCKED_NEEDS_MORE_EVIDENCE — DC incremental information:** existing six-method comparator uses exactly the same 28 resolved fixtures / five kickoff dates:

| Method | Brier (3-way sum) | RPS | Log loss | ECE |
|---|---:|---:|---:|---:|
| CHAMPION | 0.555553 | 0.175553 | 0.932186 | 0.076313 |
| MARKET | 0.593954 | 0.188158 | 0.983997 | 0.059072 |
| SHIN | 0.594060 | 0.187929 | 0.981728 | 0.092795 |
| POWER | 0.594837 | 0.187918 | 0.981903 | 0.093014 |
| OO_EPC | 0.594716 | 0.188014 | 0.980546 | 0.099476 |
| DIXON_COLES | 0.607106 | 0.189928 | 1.016908 | 0.127751 |

DC minus champion: Brier +0.051553, log loss +0.084722, RPS +0.014376. DC is descriptively worse than champion and all four market methods here. DC draw bias is −0.108101 versus champion +0.005196. Favourite/longshot and league/competition/time/lead-time segments are in `dixon_coles.json`.

The frozen confidence minimum remains 30 fixtures and seven kickoff dates. No weight fit, algorithm change, dynamic DC, publication activation or promotion was performed. No stable incremental contribution is established; optimal forward pool weight remains unavailable, not guessed to be zero.

## 13. MODEL_DISAGREEMENT

**NO_CHANGE.** Last 12 PREMATCH cycles contain 3,886 candidate-market-cycle rows / 77 unique fixtures. Mean absolute ensemble-market divergence is 0.059364. Overlapping reason counts: severe contradiction 189; material disagreement 1,487; excessive ensemble-market divergence 118; insufficient independent signals 2,977; provider raw zero 24; no independent non-market evidence 1,238; non-positive value 2,655.

Domestic cups show 41 severe flags among 418 rows (9.81%); lower/semi-pro divisions 52/1,280 (4.06%); reserve/B teams 16/218 (7.34%). Repeated fixtures prevent treating rows as independent samples. Full market/probability/odds/lead-time/freshness/provider-completeness segments are retained. These associations cannot separate model error from provider completeness causally without paired outcome evidence.

Provider raw zero remains rejected as PROVIDER_ZERO_PROBABILITY; nothing is clamped. Double's diagnostic-only disagreement policy is unchanged. With no published Double coupons, claims of either adequate calibration or systematic realized Double overconfidence would be unsupported.

## 14. GITHUB_AND_FORUM_RESEARCH

**NO_CHANGE — no external prediction algorithm copied.** Public material was reviewed on 2026-10-08. Reproducible source code is not equivalent to independently reproduced GoalVision performance.

| Source | Technical basis / reproducible code | OOS evidence and data/API cost | Fit, complexity and incremental verdict |
|---|---|---|---|
| [scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html), [temperature issue #28574](https://github.com/scikit-learn/scikit-learn/issues/28574) | Established held-out calibration; maintained code and issue/implementation history | General ML methodology; no football-profit guarantee. Existing stored predictions suffice; zero added API requests | Reuse existing calibrators after chronology gate. Low integration cost. Potential reduction of miscalibration, to be measured |
| [Guo et al. 2017](https://proceedings.mlr.press/v70/guo17a.html) | Temperature scaling research with neural-network experiments | OOS calibration evidence in other domains, not this football baseline | Supports a comparator, not a claimed sports edge. No need for a new classifier |
| [penaltyblog](https://github.com/martineastwood/penaltyblog), [implied probabilities](https://penaltyblog.readthedocs.io/en/master/implied/implied.html), [issues](https://github.com/martineastwood/penaltyblog/issues) | Public implementation of margin removal and football score models | Software examples are not independently verified COMBO OOS returns. Math can use existing current quotes without API calls | Methods already present. Useful reference/testing; adding another architecture has no demonstrated gain |
| [footymodel](https://github.com/tanamsethi31/footymodel), [RESULTS](https://github.com/tanamsethi31/footymodel/blob/main/RESULTS.md) | Public source, walk-forward and failed-hypothesis reporting | Repository-reported pooled O/U yield −7.3% on 6,182 selections, 1X2 −13.3%; not reproduced here. Rich lineup inputs would need new coverage | Useful evidence discipline, not proof of profitability. README reserves rights; no code copied. Player-model expansion is unjustified here |
| [soccer-betting-models](https://github.com/pabsanamono/soccer-betting-models) | MIT repository with synthetic quickstart, walk-forward/calibration/market pipeline concepts | No verified transferable GoalVision OOS result established; synthetic examples are not validation | Audit concepts fit, new full pipeline does not. Historical-odds/staking parts are outside scope; no adoption or extra calls |
| [Dixon–Coles original paper](https://academic.oup.com/jrsssc/article-abstract/46/2/265/6990546) | Statistical score model; existing local implementation | Historical 1990s study does not establish a current-market edge | Keep current forward comparison. New dynamic variant deferred until incremental evidence |
| [r/algobetting discussion](https://www.reddit.com/r/algobetting/comments/1s1j93x/following_up_on_my_earlier_post_here_first_plate/) | Practitioner discussion of calibration/tails/dependence, not a validated algorithm | Anecdotal; no independently reproducible football result established | No bucket-specific isotonic fitting on the current small sample; zero implementation adopted |
| [r/sportsbook correlated parlays](https://www.reddit.com/r/sportsbook/comments/13wg33l/how_ev_are_these_correlated_parlays/), [futures discussion](https://www.reddit.com/r/sportsbook/comments/fd1gxf/correlative_parlays_in_the_mlb_futures_market/) | Illustrations of shared-event dependence | Sport-specific anecdotes/simulations; not football cross-fixture correlation estimates | Motivation for risk flags only. No coefficients copied, no assumed improvement |

The [API-Football documentation](https://www.api-football.com/documentation-v3) retrieval did not expose a usable latency/update SLA in this audit. No undocumented provider refresh frequency is asserted. Forum recommendations are hypotheses; technical decisions rest on local evidence and established calibration/probability methods.

## 15. IMPLEMENTED_RESEARCH_MODULES

**SMALL_GITHUB_FIX — source commit b716db64fd365892937a871b28cf945a50305336.**

A — LIVE_DIAGNOSTICS_V1:
- Frozen reason counts, policy-separated quote buckets, funnel, claims/receipts/settlement, 20/30/45 counterfactual and request-efficiency report.
- Optional injected diagnostic sink records sanitized provider timestamps, expected/observed minute and score, client-call elapsed time and failure type without secret exception text.
- Sink is default-off, uncoupled from production worker construction, cannot add provider requests, and sink failure cannot change the underlying provider result. HTTP latency is never substituted with client-call elapsed time.

B — COMBO_QUALITY_RESEARCH_V1:
- A calls the current Double selector with an in-memory ledger; B reuses the V2 Singles-Based selector. Neither can send.
- Identical original candidate pools, original Decimal quotes, source fingerprints, known exposure state and separate per-strategy hypothetical carry-forward.
- Labels are attached only after selection; missing/contradictory result evidence remains pending/excluded.
- C implements quality/value evidence diagnostics and a fail-closed no-selection verdict. **A calibrated ranking algorithm is not completed or enabled.**
- Mathematical joint bounds and risk flags are explicitly separate from a learned joint model.

C — COMBO_PERFORMANCE_COMPARISON_V1:
- Extends `app/adaptive_lab/combo_evidence.py`, preserving its ledger and frozen settlements.
- Cohort metrics, medians, losing-streak diagnostics, all losing-coupon leg evidence, segmentation and bounded cluster CI eligibility.
- No artificial paired scores for different coupon targets; no ranking of unmatched cohorts.

Replay result, last 12 cycles: A zero selections; B 11 hypothetical triples (six already LOST, five pending); C zero. B's settled-subset ROI is −100% at this immature cutoff and is strongly subject to early-loss availability bias. It is neither prospective performance nor a fair mature comparison against A's no-picks.

The captured preparation-end timestamp is used because exact selector-call microseconds were not recorded. Every candidate must exist before that observed boundary. This is a bounded retrospective comparator, **not an exact reconstruction of every original publication decision**. No retrospective replacement of losing legs occurs.

## 16. VALIDATION_AND_TEST_RESULTS

**PASS: 619 tests in 38.16 seconds.** The committed offline harness denies outbound socket connections, supplies fake provider/Telegram credentials and runs the 25-file focused/adjacent matrix in `tests.json`.

Coverage includes LIVE pipeline and policy compatibility; diagnostic sink failure and request-count parity; quota reserve/contention; calibration chronology and no-leakage; no COMBO learning; de-vig; probability/age boundaries; exact Decimal aggregate/replay; early loss; VOID/PARTIAL_VOID; delivery duplication/integrity/replies; same-cycle queue duplicates; correlation flags; no-selection; SQLite read-only behavior; immutable-output conflicts; fingerprint verification and future-append as-of stability.

The fixed-cutoff LIVE/COMBO/replay audit was run twice. Outputs are byte-identical:

| File | SHA256 |
|---|---|
| combo.json | `7f4de534fbac0ba2a6cfe4d7ec01c7daf7c7bc656777005aa6126385adc53bbc` |
| live.json | `cbd3894b8238f377c7426ad7c5f9a4d862d66c364178887836218e4e96d6cb6f` |
| replay.json | `268db547119a4db36a944eae1b859536aa5717315e7605a86a8eebde333711f6` |

No provider/Telegram transport was exercised against production. All SQL input paths use read-only/query-only access or existing read-only in-memory ledger backup. The new audit entry point also denies outbound socket connections. No production DB backup or raw source database was committed.

Reproduce on the authorized VPS from this branch:

```bash
# Original 22:06 snapshot: use its source commit, not the later branch HEAD.
git -C /home/arvis/goalvision-worktrees/live-combo-research-20261008 worktree add --detach \
  /home/arvis/goalvision-worktrees/live-combo-original-replay-b716db6 \
  b716db64fd365892937a871b28cf945a50305336
cd /home/arvis/goalvision-worktrees/live-combo-original-replay-b716db6
/home/arvis/GoalVisionAI/.venv/bin/python -I -B operations/live-combo-research/offline_tests.py

nice -n 10 /home/arvis/GoalVisionAI/.venv/bin/python -I -B \
  operations/live-combo-research/audit.py \
  --audit /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db \
  --shadow /home/arvis/GoalVisionAI/var/lab_v2/shadow.db \
  --ledger /home/arvis/GoalVisionAI/var/lab_combo/ledger.db \
  --as-of 2026-10-08T19:06:10.302493+00:00 \
  --live-since 2026-10-08T15:00:00+00:00 \
  --cycles 12 \
  --output /home/arvis/goalvision-operations/live-combo-audit-20261008/v3
```

The output path is immutable: an identical repeat succeeds; different contents fail rather than overwrite evidence. Journal retention/source availability limits future reproduction; retained JSON and fingerprints remain reviewable. Other read-only source auditors and their inputs are listed in the evidence index; they are not worker or provider invocations.

## 17. PROSPECTIVE_EVIDENCE_REQUIREMENTS

**BLOCKED_NEEDS_MORE_EVIDENCE.**

1. Capture natural LIVE state/quote alignment and client/HTTP timing separately before changing call order. Do not weaken score/minute, state/event freshness, final-refresh or transport guards.
2. Wait for ≥300 calibration fixtures and October 10 fit-window close, then fit research-only with existing frozen chronology. No activation follows automatically.
3. Keep independent Double coupon evidence; zero current publications cannot justify quality claims. Complete joint calibration only with a justified prospective sample and cross-fixture error analysis.
4. Compare strategies from the same as-of pool and a closed, mature outcome window. Different selected coupons do not yield paired probability-score deltas merely by sharing a discovery cycle.
5. DC needs at least the unchanged confidence minimum and subsequent validation/holdout evidence; current descriptive losses do not justify a new dynamic model or a promoted pool weight.

Governance snapshot: 133 historical training runs, 59 model artifacts (58 challenger / one bootstrap), three learning cycles, zero calibration artifacts, validation results, holdout results, governance shadow runs/predictions/settlements, candidate comparisons, promotion gates and rollback events. The one activation event is bootstrap. **PROMOTION_ELIGIBILITY = NOT_ELIGIBLE.**

Keeping the champion is a governance decision, not a claim that it is proven optimal. Current evidence supports calibration and better observability before any new model.

## 18. OPERATOR_DECISIONS

**NO_CHANGE:** keep current running policies, schedules, budgets, champion, Official and ADMIN Codex state. No deployment command is supplied because no production package was authorized or created.

**OPERATOR_APPROVAL_REQUIRED:** wiring the optional LIVE sink into a deployed worker requires a separately reviewed release and operator approval. The source commit alone does not activate it. First collect diagnostics; only then decide whether a request-order change has a concrete same-budget benefit.

**PASS — final-review queue:** 12 cycles, 103 attempts, maximum ten reviews per cycle; deadline/least-recent ordering, invalid/duplicate filtering and carry-forward checks pass. No queue change.

**NO_CHANGE / DATA_QUALITY_LIMITATION — runtime:** accessible 24h journals contain no DB-lock, quota-contention exhaustion/retry, protected-reserve, missing-package or service-failure matches. This is scoped evidence, not proof about unavailable logs. PREMATCH's DEGRADED statuses reflect data quality. UTC-day quota-claim count 4,198 is not a verified remaining daily HTTP quota.

Public/private ledgers have zero current claims without receipts. One historical delivery-unknown marker remains retained after reconciliation. Last 24h publication-cycle evidence has 44 SENT / receipt-persisted deliveries and no transport failures or reconciliation-required events. Ten historical same-policy SINGLE fixture repeats predate current policy (nine legacy, one October 1 V1); zero exact COMBO duplicates.

Nine published items were more than six hours beyond frozen last kickoff, which is a review flag rather than measured result-provider delay. Last retained settlement diagnostic has seven postponed rows, two not-started and five nonterminal rows, including a moved kickoff; rows may share fixtures. Do not manufacture VOID/WON/LOST outcomes or delete old pending records.

## 19. NEXT_ACTIONS

| Classification | Action |
|---|---|
| PASS | Review this source commit, report and immutable JSON bundle on the research branch |
| NO_CHANGE | Continue existing natural discovery/settlement and retain actual LIVE-enabled state |
| OPERATOR_APPROVAL_REQUIRED | Decide whether to prepare a diagnostics-only LIVE capture release; do not change selection |
| BLOCKED_NEEDS_MORE_EVIDENCE | Recheck calibration count after frozen fit-window close; fit only if all existing gates pass |
| BLOCKED_NEEDS_MORE_EVIDENCE | Gather mature Double and common-pool forward COMBO results; no winner or joint model claim yet |
| DATA_QUALITY_LIMITATION | Preserve postponed/missing-coverage cases and diagnose provider timing from future natural evidence |
| NO_CHANGE | Keep DC shadow, champion, odds floors, publication gates, API budget and staking unchanged |

Delivery invariants: **zero production deployments, restarts, timer changes, provider calls initiated, Telegram calls/sends, Official mutations, bankroll mutations, champion activations, promotions or rollbacks**. Existing natural services generated their own calls/publications while this work read their evidence. Research worktree changes are isolated; original dirty checkout remains untouched.


### Full requirement-by-requirement review

Latest source: `d642f72d579ab45d622459befea5b4c55e7813d8`. Full machine-readable requirements and hashes are in `docs/evidence/live_combo_optimization_20261008/review_2313/GOALVISION_LIVE_COMBO_REQUIREMENTS_REVIEW.json`.

“PASS” means the named audit/test requirement has evidence; it does not mean a profitable or production-ready strategy. “BLOCKED” is an unfulfilled condition or incomplete implementation, not a success label. The C ranker is explicitly incomplete.

| ID | Requirement | Classification | Finding |
|---|---|---|---|
| S01 | Official, champion, bankroll and staking preservation | PASS | No writes or production policy changes; protected routes and original checkout retained. |
| S02 | No deployment, restart, timer toggle, promotion or rollback | PASS | All changes remain source/research; operator controls untouched. |
| S03 | Preserve actual LIVE-enabled state and operator quote-age V2 | NO_CHANGE | Later operator evidence supersedes obsolete LIVE=DISABLED and 20-second-cap text. |
| S04 | No production provider requests, Telegram traffic, purchases or historical-odds acquisition | PASS | Offline transports denied; existing stored current quotes only. |
| S05 | COMBO exclusion from champion learning and immutable history | PASS | Research outputs are non-learning; old COMBO_LEG sources remain retained/excluded. |
| 1.1a | LIVE fixture discovery, status and minute | PASS | Cycle funnel and frozen candidate/state inspection; no fabricated missing matches. |
| 1.1b | Odds discovery, market/provider ID and bookmaker attribution | PASS | Saved quote identity/provenance retained; unknown bookmaker remains unknown. |
| 1.1c | Provider quote timestamps and age | PASS | Origin/retrieval/preparation clocks and policy-specific age buckets. |
| 1.1d | Exact HTTP response latency | DATA_QUALITY_LIMITATION | Not present in old records. Client/quota elapsed observer is implemented, but isolated HTTP-boundary instrumentation is not implemented or deployed. |
| 1.1e | Raw normalization, model inference, EV, uncertainty and disagreement | PASS | Code path and stored rejection evidence audited; baseline/gates unchanged. |
| 1.1f | Final refresh, duplicate/exposure, claims, receipts and settlement | PASS | Receipt-backed lifecycle and separate failure stages; no manual sends or cycles. |
| 1.1g | Exact producer of state/quote mismatches | DATA_QUALITY_LIMITATION | Reason counts exist; rejected raw quote/state pairs were discarded. Optional future observer is uninstalled. |
| 1.2a | All six quote-age buckets and freshness-only blockers | PASS | Candidate-version counts with explicit denominators and missing/future-time handling. |
| 1.2b | 20/30/45-second offline counterfactual | PASS | Retains all non-age blockers; not a promise of final publications or executable prices. |
| 1.2c | Full broad-feed update-age distribution | DATA_QUALITY_LIMITATION | Discarded broad-feed rows cannot be reconstructed from eligible-candidate records. |
| 1.2d | Odds movement under identical observable state | SMALL_GITHUB_FIX | Compare same score/minute/cards/events/source, not a retrieval-time-dependent state hash; nine retained comparable pairs have no price movement. |
| 1.2e | Execution-price availability or slippage proof | BLOCKED_NEEDS_MORE_EVIDENCE | Indicative feed with unknown bookmaker; no execution claim, API/betting integration or price guarantee. |
| 1.3 | Ordering, history-cache/filter and quota throughput review | NO_CHANGE | Existing cache/broad-feed filter reviewed; no measured same-budget gain supports request reordering. |
| 2.1a | All six COMBO cohorts and requested coupon metrics | PASS | Confirmed receipts, W/L/VOID/partial/pending, odds mean/median, flat P/L/ROI, probability scores and reliability. |
| 2.1b | Double performance | BLOCKED_NEEDS_MORE_EVIDENCE | Zero confirmed Double coupons; no substituted retrospective or legacy results. |
| 2.2a | Every losing coupon and losing/unknown legs | PASS | Per-coupon leg outcomes and original probability/quote provenance retained; no hidden losses. |
| 2.2b | Markets, leagues, leg count, odds, lead time, freshness and shared risks | PASS | Coupon/leg segments and failure/risk flags; flags are not causal conclusions. |
| 2.2c | Dominant wrong signal or causal quality attribution | BLOCKED_NEEDS_MORE_EVIDENCE | Co-occurrence, selected samples and shared forecasts do not establish a causal producer error. |
| 2.2d | Two-leg versus three-leg realized comparison | BLOCKED_NEEDS_MORE_EVIDENCE | All confirmed coupons currently have three legs; Double sample is empty. |
| 3A | Current Double baseline replay | PASS | Existing selector, original candidates, exact 1.70/70–80% rules and in-memory ledger; no production change. |
| 3B | V2 Singles-Based replay | PASS | Existing V2 selector reused on identical candidate pools; real V2 publication is not reactivated. |
| 3C | Quality/value-first Double ranker | BLOCKED_NEEDS_MORE_EVIDENCE | Only fail-closed evidence/no-pick screen exists. Calibrated-leg/joint artifact contract and ranking algorithm are not completed. |
| 4a | Naive product and joint probability provenance | PASS | Product calculated from frozen Decimal inputs; explicit independent-assumption label. |
| 4b | Fixture/team/league/market/shared-signal risk | PASS | Shared-risk screening, dependency clusters and mathematical Fréchet bounds; no invented coefficient. |
| 4c | Empirical/scenario/Monte Carlo correlation-adjusted joint forecast | BLOCKED_NEEDS_MORE_EVIDENCE | Not fitted or implemented as a validated model; inadequate independent prospective data. |
| 5a | Champion, learning, frozen calendar and 300-fixture readiness | PASS | Latest read-only counts; both sample and closed-window gates required. |
| 5b | Identity/Platt/temperature/isotonic fit and immutable calibration artifact | BLOCKED_NEEDS_MORE_EVIDENCE | Reuse existing comparator only after frozen readiness. No fit, artifact or activation now. |
| 5c | Fitted calibration slope/intercept, league/market curves and extremes | BLOCKED_NEEDS_MORE_EVIDENCE | Published raw reliability is available; new fitted calibrator metrics would be premature. |
| 5d | TRAIN/CALIBRATION/VALIDATION/HOLDOUT leakage isolation | PASS | No held-out fitting, calendar relaxation, current-data relabeling or automatic training. |
| 6a | Multiplicative/Shin/Power/OO-EPC reuse and overround | PASS | Existing complete-current-quote captures and six-method comparator reused; no duplicate implementation. |
| 6b | Probability difference, EV, odds age, lead time and market evidence | PASS | Frozen per-leg/C diagnostic features and market-method evidence exported. |
| 6c | Statistically stable incremental gain against market/champion | BLOCKED_NEEDS_MORE_EVIDENCE | DC sample remains 29 fixtures/five dates; no validated pooled weight or winning strategy established. |
| 7a | Six named signal/rejection families and existing segments | PASS | Counts segmented by market, league/competition, p/odds, lead time, freshness and provider completeness. |
| 7b | Model-generation and context-quality segments | SMALL_GITHUB_FIX | Added missing dimensions; unknown generation and unrated context remain explicit. |
| 7c | Publication readiness versus context quality | SMALL_GITHUB_FIX | Exporter now preserves readiness separately; READY is never relabeled as a context-quality grade. |
| 7d | Double diagnostic-only disagreement performance | BLOCKED_NEEDS_MORE_EVIDENCE | Policy audited unchanged; no published Double outcomes to demonstrate realized calibration. |
| 8a | Four requested GitHub projects | PASS | Official project docs/source availability/results/license reviewed; no unverified code copied. |
| 8b | Issues/discussions, Reddit and statistics material | PASS | References and methodological limitations recorded; forum anecdotes are not OOS proof. |
| 8c | Technical basis/code/OOS/data/cost/fit/incremental-gain/complexity assessment | PASS | Research matrix answers all eight decision criteria; no paid provider or speculative model import. |
| 9a | Common immutable candidate pool, original odds and source fingerprints | PASS | A/B/C receive the same retained pool; integrity checks fail closed. |
| 9b | Exact original selector-call timestamp reproduction | DATA_QUALITY_LIMITATION | Unavailable; replay uses observed preparation-end with strict preceding-input checks. Exact production-decision reproduction is not claimed. |
| 9c | No future labels, retrospective replacement or duplicate exposure | PASS | Selection precedes label attachment; independent hypothetical carry-forward and original exposure guards. |
| 9d | Reproducible early-loss/VOID/partial-VOID settlement | PASS | Only retained verified regulation facts; absent/conflicting results remain unknown. |
| 9e | Selected/no-pick/settled/ROI/probability metrics and losing streak | PASS | Descriptive results with immature-cohort bias disclosed; no prospective-performance label. |
| 9f | Paired probability-score deltas across three strategies | BLOCKED_NEEDS_MORE_EVIDENCE | Different/empty selected coupons have different targets; no fabricated paired score delta. |
| 9g | Confidence intervals and ranking | BLOCKED_NEEDS_MORE_EVIDENCE | Evidence gates not met; no relaxed sample minimum or holdout tuning. |
| 10A | LIVE diagnostics implementation block | SMALL_GITHUB_FIX | Offline report and optional observer implemented. Raw HTTP timing, rejected-row history and production persistence remain unavailable/unwired. |
| 10B | COMBO quality research implementation block | SMALL_GITHUB_FIX | A/B replay and joint-risk diagnostics implemented; C ranker/joint model explicitly incomplete. |
| 10C | Coupon performance comparison implementation block | PASS | Existing combo_evidence extended; all cohorts shown, no unjustified ranking. |
| 11a | Focused and adjacent full requested regression matrix | PASS | 635 tests pass, including 16 additions since original 619; fake transports and network denial. |
| 11b | Read-only isolation, exact replay, probability boundaries and source corruption | PASS | Regression coverage and real read-only smoke; no learning/publication side effects. |
| 11c | Isolated worktree, reviewed commit/push, secrets and runtime exclusions | PASS | Only reviewed source/docs/evidence; original dirty checkout preserved. |
| 12a | LIVE final verdict | PASS | LIVE publishes; negative EV and alignment/coverage failures remain; HTTP causal attribution unresolved. |
| 12b | COMBO final verdict | PASS | No proven best calibrated/risk-adjusted strategy. V2 descriptive ROI is insufficient; Double and C lack evidence. |
| 12c | AI/ML final verdict | PASS | Calibration not ready; champion preserved; promotion NOT_ELIGIBLE; no reason established for a new classifier. |
| H01 | Earlier Dixon–Coles packaging repair | NO_CHANGE | ebd0924 is in reviewed history; installed forward application contains reviewed_competitions.json with verified hash. |
| H02 | Earlier PREMATCH/de-vig/calibration/queue/settlement/Double/evening changes | NO_CHANGE | Reviewed commits checked as ancestors; installed flags preserved; no repetition of completed implementations. |
| H03 | Separate ADMIN mixed-delivery branch | NO_CHANGE | ab327dd is an ancestor of verified remote ea94dfec on separate fix/admin-mixed-delivery-20261004; no missing PREMATCH history. |
| H04 | Final-review queue regression and odds-yield review | NO_CHANGE | Existing queue PASS and coverage analysis reused; no proven priority/budget improvement was invented. |

### Reproduce the 23:13 re-review

Use the reviewed branch containing source `d642f72d579ab45d622459befea5b4c55e7813d8`. These are offline/read-only commands, not deployment commands.

```bash
cd /home/arvis/goalvision-worktrees/live-combo-research-20261008
/home/arvis/GoalVisionAI/.venv/bin/python -I -B operations/live-combo-research/offline_tests.py
nice -n 10 /home/arvis/GoalVisionAI/.venv/bin/python -I -B \
  operations/live-combo-research/audit.py \
  --audit /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db \
  --shadow /home/arvis/GoalVisionAI/var/lab_v2/shadow.db \
  --ledger /home/arvis/GoalVisionAI/var/lab_combo/ledger.db \
  --as-of 2026-10-08T20:13:06.987380+00:00 \
  --live-since 2026-10-08T15:00:00+00:00 \
  --cycles 12 \
  --output /home/arvis/goalvision-operations/live-combo-audit-20261008/requirements-review/final
```

The original source in the section 16 worktree reproduces the old schemas/snapshot; the later source emits LIVE_DIAGNOSTICS_V2 and LAB_COMBO_COUPON_EVIDENCE_V3. Do not overwrite the old immutable output directory with a new schema.

Latest safety readback: 142 protected systemd files unchanged; original 220 dirty paths unchanged; LIVE timer enabled/active before and after. Official/champion/staking untouched; zero agent production requests, Telegram calls/sends, deployments, timer changes, restarts, promotions or rollbacks.
