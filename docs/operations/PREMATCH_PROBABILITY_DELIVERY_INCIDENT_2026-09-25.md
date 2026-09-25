# PREMATCH probability and delivery incident — 2026-09-25

Prepared offline on `codex/prematch-probability-delivery-hardening`, based on
`3d99f7dd5348e1440cb6c41eb9d91106c2a0b815`. No deployment or enablement.

## Deployed state and investigation boundary

The installed release `/home/arvis/GoalVisionAI-prematch-release-installer-v2-20260925`
was clean at exactly the reference commit. Work was performed in the separate
worktree `/home/arvis/goalvision-operations/prematch-probability-delivery-hardening`.
The active checkout, installed release files, services and production records were
not edited. No sudo, authenticated API calls, Telegram probes/messages, migrations,
training, promotion, historical-odds acquisition or installer apply were performed.

Effective systemd configuration, verified before investigation and again afterward:

- Working directory `/home/arvis/GoalVisionAI`; interpreter its `.venv/bin/python -P`.
- Environment file `/home/arvis/goalvision-operations/prematch-v2-installer-v2-20260925/release.env`
  sets `PYTHONPATH` to the installed release above.
- Discovery: `app.lab_v2_shadow controlled-cycle --max-calls 400 --settlement-reserve 100`
  with `--adaptive-database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db`,
  `--football-context-root /home/arvis/goalvision-operations/football-context-v2`,
  `--football-context-registry /home/arvis/goalvision-operations/football-context-v2/reviewed-regulations.sqlite`,
  and `--label-v2-selections`. **No `--send`: new publication is disabled.**
- Installed drop-in mtime: `2026-09-25T18:22:12.238046820Z`. This establishes the
  configuration file time, not proof of which operator command changed it.
- Discovery, adaptive observation and settlement timers remain scheduled.
  Settlement retains its existing `app.lab_combo settle --send --adaptive-database …`.
  Existing result delivery is intentionally distinct from enabling new picks.

The rollout log confirms configuration installation around 17:14Z, without a
manual cycle. The fixed publication audit window is **17:14:00Z–18:25:00Z** on
September 25. State checks after that cutoff are identified separately below.

SQLite evidence was queried using `mode=ro`, read transactions, bounded fixture,
kind, identity and time predicates, row limits and a progress deadline for the
candidate query. No live SQLite main file was copied. SQLite's normal read
transaction sees committed WAL content consistently within each database; these
were not a simultaneous cross-database backup. Evidence joins use immutable IDs,
hashes and retained timestamps, with the fixed cutoff. Small query results were
exported locally for offline replay; no production repair was attempted.

## Morocco–Gabon: actual publication lineage

**Verdict: correctly parsed provider probability outlier + intentional experimental
policy admission. No demonstrated percentage-parser or identity/market-mapping
cause in this publication. Confidence is high for this software lineage; it is not
a claim that the provider's 50% estimate was statistically valid.** No eventual
match result was used in investigation, admission thresholds or tests.

| Identity | Retained value |
|---|---|
| Fixture | API-Football `1545826` |
| Competition | `36`, Africa Cup of Nations - Qualification, World |
| Season / round | `2027`, Group Stage - 1 |
| Orientation | HOME Morocco `31`; AWAY Gabon `1503` |
| Kickoff | `2026-09-25T19:00:00Z` = `22:00 Europe/Riga` |
| Selection / bookmaker | DRAW; Bet365 `8` |
| Captured odds | `9.00` |
| Provider quote update | `2026-09-25T16:41:19Z` |
| Quote retrieval | `2026-09-25T18:00:36.924270Z` |
| Final review | `2026-09-25T18:00:37.423603Z`; NS, exact fixture/odds refreshed |
| Publication preparation/origin freeze | `2026-09-25T18:04:04.326548Z` |
| Confirmed receipt | `2026-09-25T18:04:04.715403Z`, message `129`, Lab chat `-1003510920417` |

Prediction:
`lab-v2-single-3810568e7053f6f9f0c3ab7890ed00f3341c04cfdd6e807e33616dc6bb51379b`.
Candidate:
`lab-v2-candidate-bfb5868b9f45700470470dcd1c07be15201659e7fc698721f184abb0e6d2d57f`.
Quote fingerprint:
`ef190343ffc0edf729509f44162a04f041004d69b4bdd660106cf91df1b31a0d`.
Original message: <https://t.me/c/3510920417/129>.

1. **Retained provider response.** Cache
   `lab-v2-cache-eac607bd7a800d08220c6042295d15cc80e39af0641d56b8d3ab72ed4ee8c534`,
   endpoint `/predictions`, query `{"fixture":1545826}`, retrieval
   `18:01:19.562783Z`. Full payload fingerprint:
   `96fdee8d44d1dd388d375580260a7a6331b8625d08f70ec77c25ddbe0f1e949a`.
   `parameters.fixture` and response league/season/team IDs match. The earlier
   `17:32:29.685119Z` response has the same full fingerprint. Neither is a new
   investigation fetch. The prediction source does not provide a prediction
   generation timestamp; retrieval is not presented as generation time.
2. **Percentage parsing / mapping.** `percent.home="50%"`, `draw="50%"`,
   `away="0%"` become `HOME_WIN=0.5`, `DRAW=0.5`, `AWAY_WIN=0`, sum `1`.
   Old and corrected parsers agree. Winner is Morocco `31`, comment “Win or draw”,
   `win_or_draw=true`; advice is “Double chance : Morocco or draw”. These fields
   did not replace the explicit draw percentage. Both goal fields and under/over
   are null. No goals-derived probability was involved.
3. **Odds / market.** Cache
   `lab-v2-cache-96d62a9594afd8747546633a05865f5391a4131a92b4a005b767443bf2fea468`,
   full payload hash
   `68249eeb2829774dabecc7f42c8a43b6a68a2b25e351c0e26fd457348e30eb67`.
   Same fixture, competition, season and kickoff; provider bet `id=1`, name
   `Match Winner`, Bet365 values **Home 1.11, Draw 9.00, Away 21.00**.
   This is the adapter's regulation Match Winner mapping, not first-half,
   qualification, double-chance or another team selection. The raw odds endpoint
   does not repeat team IDs; orientation is tied to the exact retained fixture
   and prediction team metadata. This proves provider market mapping, not a
   separately acquired bookmaker rulebook. Exact quote fingerprint reproduces.
4. **Signal construction and independent grouping.** DRAW has API prediction
   `0.5`, reliability `0.75`, provenance `CURRENT_/PREDICTIONS`, family
   `API_FOOTBALL_PREDICTION`; market consensus is
   `0.1173795291597921035268705692`, reliability `0.90`, provenance
   `CURRENT_API_FOOTBALL_QUOTES_ONLY`, family `CURRENT_MARKET_CONSENSUS`.
   Both selection labels are HOME_WIN (the provider HOME/DRAW tie resolves to
   HOME_WIN); the selected-market numeric probability is still DRAW `0.5`.
   Pi is unavailable, with zero team observations. There is **one predictive
   family**, not five: the five eligible bookmaker markets are price observations.
   Profile weights for these two sources are 1, and relevance weights are
   `0.95` for API and `1.00` for market. The one-family profile deliberately uses
   the API probability alone. The retained model-generation/artifact IDs do not
   establish a second independently contributing probability.
5. **Profile evaluation.** `LAB_V2_BROAD_COVERAGE_ENSEMBLE_V4`,
   `LAB_COMPETITION_POLICY_V2`, profile INTERNATIONAL_SENIOR. Implied probability
   `1/9=0.1111111111111111111111111111`; final probability `0.5`; edge
   `0.3888888888888888888888888889` (displayed 38.9 percentage points).
   Uncertainty penalty `0.03275`; experimental edge requirement `0.04275`.
   Findings include both severe-disagreement reasons, insufficient independent
   signals, material signal disagreement and low weighted agreement. They were
   soft findings. Result: APPROVED, LOW, EXPERIMENTAL; no hard failures.
6. **Final READY / publication.** `LAB_V2_FINAL_REVIEW_READINESS_V5` admitted
   EXPERIMENTAL_READY after exact refresh, with lineups not yet published and
   injuries not requested. The quote's provider timestamp was within the existing
   prematch source-age allowance and the final review was under five minutes old
   at sending. The economic claim is `SINGLE:1545826:DRAW`; publication claim and
   SENT receipt both exist at `single_prediction:` plus the prediction reference.
   The receipt confirms message 129. No inference from a preview is needed.

All three actual final 1X2 candidate values are retained:

| Outcome | Provider/one-family probability | Five-book market fair probability | Best captured odds | Final decision |
|---|---:|---:|---:|---|
| HOME_WIN | 0.5 | 0.8333950934237347282559678042 | 1.13 | REJECTED |
| DRAW | 0.5 | 0.1173795291597921035268705692 | 9.00 | APPROVED / READY |
| AWAY_WIN | 0 | 0.0492253774164731682171616266 | 22.00 | REJECTED |

The old candidate retains normalized signals and generic source provenance, not
an explicit `/predictions` payload hash. The source-to-candidate link is reconstructed
from the exact fixture query, unique response in that cycle, matching values and
chronology; the earlier response is byte-content-equivalent. This is a lineage
limitation, not missing original-source evidence. New candidates freeze the
normalization version and full source fingerprint explicitly.

## Confirmed independent parser defect and source contract

The old helper returned `1% → 1` and `0.5% → 0.5`. It used magnitude to infer units.
The corrected helper returns `0%, 0.5%, 1%, 50%, 100% → 0, .005, .01, .5, 1` using
Decimal arithmetic. Malformed, negative, >100%, boolean, nonfinite and ambiguous
inputs are rejected. Internal normalized probabilities require `unit='probability'`
and are not divided again. An explicitly declared bare percentage unit maps `1`
to `.01`; a normalized unit maps `1` to `1`.

The provider-facing adapter conservatively accepts percent-suffixed strings only,
including comparison fields. Bare wire numbers/strings are unavailable, rather
than silently interpreted as internal normalized probabilities. The official
[API-Football guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide)
identifies `/predictions` as fixture-specific, describes the three `percent`
outcomes and the comparison block. The detailed
[official reference](https://www.api-football.com/documentation-v3#tag/Predictions)
and its API-Sports documentation mirror yielded empty browser content/HTTP 403
challenges during bounded unauthenticated reads. A broader bare-number wire
contract could **not** be verified and is not enabled. Retained original responses
confirm the percent-string representation used by this cohort. No different
vendor's similarly named API documentation was substituted.

Complete HOME/DRAW/AWAY evidence is mandatory. The existing local rounding
allowance, sum `0.98–1.02`, remains explicit; accepted complete distributions are
rescaled only within that allowance. This tolerance is a local policy, not a
claimed provider guarantee. Materially invalid or incomplete distributions remain
unavailable; winner/advice cannot rescue them. Comparison pairs are retained only
when both sides parse; zero/zero comparison categories are not invented into a
probability distribution or used as independent outcome probabilities.

Goal recommendations, signed bounds and unsigned numeric goal fields have no
verified Poisson-rate contract. The adapter no longer manufactures totals/BTTS
probabilities from them. No replacement statistical model was introduced.
Normalization version `API_FOOTBALL_PERCENT_UNITS_V2`, source fingerprint, full
normalized 1X2 distribution and verified team orientation are frozen into future
candidate material and signal provenance. Historical sources, publications,
canonical features, learning inputs and statistics are not rewritten.

## Forward cohort and offline comparison

At the fixed cutoff there are **3 confirmed labelled singles and 1 confirmed V2
combo** in the rollout cycle (messages 129–132). The combo itself uses the existing
combo schema, without a new single-origin label; its three legs are the same three
selections. One additional labelled Türkiye–France preview from the failed cycle
has no claim/receipt and is not counted as published.

| Confirmed single | Fixture / selection | Odds | Old / corrected probability | Edge | New publication decision |
|---|---|---:|---:|---:|---|
| Morocco–Gabon, msg 129 | 1545826 / DRAW | 9.00 | .5 / .5 | .3888888888888888888888888889 | BLOCK |
| Türkiye–France, msg 130 | 1528882 / HOME_WIN | 8.50 | .5 / .5 | .3823529411764705882352941176 | BLOCK |
| Burkina Faso–Benin, msg 131 | 1545815 / DRAW | 3.80 | .5 / .5 | .2368421052631578947368421053 | BLOCK |

- API-only: **3/3 singles, 3/3 combo legs**. Independent multi-family: **0**.
- Both explicit severe findings: **3/3 unique selections**, hence all combo legs.
- Proven percentage-parser impact: **0/3 published selections**. All six retained
  responses (two cycles, three unique fixture payloads) also have **zero** old/new
  comparison-field differences. These repeated responses are not independent data.
- Unavailable original prediction evidence: **0/3**. Original quote evidence for
  the incident is also retained. Frozen candidate-to-raw prediction hashes were
  absent in the old schema as explained above.
- Old software admitted all three singles and the combo. Corrected parsing alone
  changes none of these 1X2 decisions. New publication policy blocks all three
  singles and excludes all three legs from a newly prepared combo. Legacy previews
  also lack the new required normalization version; they need a new decision,
  not an in-place upgrade. These are counterfactual software checks, not bets,
  profit claims or retrospective changes to public records.

The replay fixture `tests/fixtures/lab_probability_incident_20260925.json` contains
explicitly identified projections of retained evidence, full candidate documents
and full-source hash references. It is not misrepresented as a newly fetched or
complete original provider response. Offline tests reproduce the old profile
probabilities/edges, the exact Morocco quote fingerprint and market consensus,
and the new severe-disagreement rejection even after warning fields are removed.

## Old and new publication behavior

Research/profile admission is unchanged: ordinary one-family experiments and
severe-disagreement candidates can still be observed and tracked. New policy
`LAB_SEVERE_DISAGREEMENT_PUBLICATION_V1` is applied at Lab V2 preparation and again
before a new Lab V2 delivery claim. Either existing severe finding prevents a new
single or combo leg. The existing comparisons are reused: edge above `.18`; for
the one-family profile, absolute predictive-versus-fair-market difference above
`.22`. Constants were extracted without changing values. The original ensemble
comparison is also replayed, preserving findings produced before the profile's
one-family override.

The boundary replays already profile-weighted signals and checks the selected
probability, source availability, complete API distribution/version, fixture/team
identity, quote fingerprint, final-review age and quote age. Missing or stale
inputs cannot bypass the restriction by deleting a warning list. Review results
retain exact reasons and policy version in publication-cycle evidence; eligible
previews freeze them too. The new policy does not call providers, alter discovery,
replace model probabilities with market prices, blend away an edge, cap odds,
change publication windows/destinations, or remove collection of high-odds data.
Existing economic claims, freshness checks and unknown-delivery reconciliation
remain in force. Settlement is outside the new-pick gate.

## Telegram failure handling

The original `17:30:19Z–17:34:23Z` service failure is consistent with the retained
health failure `TimedOut` and journal chain `initialize/getMe → httpx.ConnectTimeout
→ telegram.error.TimedOut`. There were 281 provider calls and retained analysis,
but no outer publication-cycle completion. Observation run
`cdac4694475b49149830c8c0ce2b365e` remains `completed=false`; it is not repaired.
The later cycle recorded four confirmed receipts. The underlying network cause
is not established; IPv4/IPv6, proxies and shared Official transport were untouched.

The Lab cycle now records analysis status separately from delivery status in
`goalvision-lab-v2-publication-cycle-v2`. Initialization failure yields typed
`LAB_TELEGRAM_INITIALIZATION_FAILED` with TIMEOUT/ERROR classification, FAILED
delivery, zero send attempts/claims, and completed analysis/observation. Exception
text, URLs and tokens are not persisted. The bot context closes request pools;
an idempotent local shutdown is attempted if lifecycle teardown fails, recording
cleanup failure explicitly if necessary. Client/repository cleanup remains active.

Shutdown failure after successful sends yields DEGRADED delivery and preserves
all confirmed receipts/counts. No batch, initialize or send retry is introduced;
cleanup does not send messages. Ambiguous sends retain durable claims and the
existing reconciliation-required outcome, and cannot automatically duplicate.
Health reports degraded delivery without relabelling completed analysis as failed.
The controlled-cycle CLI continues to return its structured report; a caller must
inspect `delivery_status` (the existing terminal-analysis-error exit convention is
preserved).

## Latest readable operations and resume decision

Separate state observation at **18:38:53Z**:

- Discovery's 18:30:01Z–18:34:56Z run succeeded with publication still disabled.
- Most recent observation END `978b9fa7a65d4af6914375d643442232` is completed,
  with 263 responses, 308 final evaluated candidates, 96 opportunities, one
  captured snapshot and 20 unavailable snapshot attempts. Availability limitations
  remain explicit; this is not evidence of an independent V2 prediction model.
- Settlement service completed successfully at 18:30:23Z. Ledger holds 50 single
  settlements and 7 combo settlements. Latest stored single settlement is LOST,
  `2026-09-24T20:40:19.213177Z`; latest combo is LOST,
  `2026-09-24T18:10:18.982468Z`. The three cohort singles are still unsettled at
  this read. Morocco–Gabon remains published and pending, and must settle normally,
  including LOST if supported by the eventual regulation result.

**Do not resume new picks on the installed commit.** Source integrity is sufficient
to reconstruct this incident and test the conservative rule; it does not establish
provider calibration. Resume requires a separately reviewed upgrade to this tested
code in an isolated release, preservation of the current disabled-publication
configuration, and operator verification of that release/configuration before an
explicit later re-enable. Old unclaimed previews cannot be silently relabelled;
new source normalization and a fresh final decision are required. The detailed
provider schema remains an external verification limitation; unsupported bare
formats fail closed. No model phase or calibration claim is a prerequisite invented
by this patch.

The old installer's `apply` must **not** be reused against existing drop-ins.
This task neither redesigns that installer nor authorizes overwriting the active
release. Continue existing discovery, V2 observation and settlement throughout the
later reviewed upgrade; preserve all claims, receipts and settlement history.

## Correction draft — not sent

Suggested reply to <https://t.me/c/3510920417/129>:

> Clarification for Morocco–Gabon DRAW at 9.00 (reference above): the displayed
> 50.0% came from API-Football's retained prediction, which gave Morocco 50%, draw
> 50% and Gabon 0%. Our percentage conversion for this selection was correct.
> The experimental policy allowed a severe disagreement with market prices to be
> published. We have prepared a stricter publication rule. The original selection
> remains in the record and will settle normally. This estimate was uncalibrated;
> it was not supported by multiple independent predictive families.

## Validation and changed files

Focused parser/policy/lifecycle/incident tests ran first. Final directly affected
regression command (no historical/ML/full-audit suites):

```text
python -m pytest -q --disable-warnings \
 tests/test_lab_probability_delivery_hardening.py tests/test_lab_v2_shadow.py \
 tests/test_lab_v2_global.py tests/test_lab_v2_hardening.py \
 tests/test_lab_v2_prematch.py tests/test_lab_v2_throughput.py \
 tests/test_lab_combo.py tests/test_lab_combo_integrity.py \
 tests/test_prematch_v2_enablement.py tests/test_prematch_production_integration.py \
 tests/test_prematch_football_context_readiness.py tests/test_prematch_registry_readiness.py
```

Results: **57 focused tests; 435 final directly affected regression tests passed**.
Tests use disposable stores and fake transports, including the real Telegram Bot
lifecycle with fake request pools that fail only on getMe. Existing tests cover
request/observation parity, economic deduplication, ambiguous sends, settlement and
labelled statistics, immutable evidence, and Official/LIVE/model isolation.
Synthetic tests that previously expected a goals-derived extra ready market were
updated to expect only the supported market; provider request counts remain tested.
`git diff --check` passed. No tests were run against writable production stores.

Changed application files: `app/lab_v2_shadow/api_prediction.py`, `runner.py`,
`ensemble.py`, `global_evaluation.py`, `publication_policy.py`, `publication.py`,
`cli.py`; the Lab V2 branch of `app/lab_combo/service.py`; delivery health reporting
in `app/adaptive_lab/health.py`. Tests: new hardening test and retained-evidence
projection fixture, updated `test_lab_v2_shadow.py` and `test_prematch_v2_enablement.py`.
This report is the only operations document added. No schema or shared Official
transport change, deployment, enablement or retrospective data mutation.
