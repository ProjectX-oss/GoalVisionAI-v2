# PREMATCH Football Context V2 readiness hardening

Date: 2026-09-24. Scope: prospective input-evidence plumbing only.

Accepted parent: `835ff60958599eb555f7e6d1914c482c0a3bdf2e`.
Branch: `codex/prematch-football-context-v2-readiness-hardening`, created directly
from that commit in the supplied worktree. The commit containing this report is
resolved by `git log -1 --format=%H -- docs/audits/PREMATCH_FOOTBALL_CONTEXT_V2_READINESS_HARDENING_REPORT.md`;
the handoff supplies the literal SHA.

## Findings

1. The five missing TARGET selections were **not lost exact refreshes**. They
   belonged to three later fixtures with no exact refresh in this run. The single
   already-observed exact response was captured and selected correctly. Reusing
   that response for the other fixtures would violate identity constraints.
2. Same-fixture market fan-out already works through Phase C/D immutable source
   receipts. The hardening removes an unnecessary scope-preparation dependency
   when an existing exact HTTP response arrives earlier than `prepare()`. It does
   not add any request, cache adapter, synthetic target, or retrospective repair.
3. No audited provider field or reviewed GoalVision competition-season contract
   proves regulation duration. All seven real features correctly remain null with
   `REGULATION_UNVERIFIED`.
4. The old report treated every failed run as an incomplete evidence window.
   The first real run has positive immutable zero-observation proof. Reporting now
   retains it as a historical preflight failure without poisoning the later window.
   Unknown, interrupted, or evidence-bearing failures remain blocking.

## Evidence handling and exact runtime trace

Only the supplied `var/readiness-test` root was inspected, using SQLite `mode=ro`
connections. No original event, source, snapshot, cache or database was modified.
A SHA-256 manifest was taken before inspection and compared after verification.
No database or raw provider payload is included in the commit.

The evidence contains these six new canonical opportunities. All use receipt
`006913d970b25ad86bec8f4df126b306d139679aa069ebae4af7d42d21f44451`,
ordering 5, cutoff **2026-09-24T12:25:25.516689Z**, competition 36, season **2027**,
profile `INTERNATIONAL_SENIOR`.

| Fixture | Market | Kickoff UTC | Exact review evidence | Deterministic TARGET classification |
| --- | --- | --- | --- | --- |
| 1545817 | AWAY_WIN | 16:00 | Empty final_review; no exact response | UNAVAILABLE: no durable exact same-fixture source before cutoff |
| 1545817 | DRAW | 16:00 | Same | Same |
| 1545820 | AWAY_WIN | 19:00 | Empty final_review; no exact response | UNAVAILABLE: no durable exact same-fixture source before cutoff |
| 1545820 | DRAW | 19:00 | Same | Same |
| 1545825 | DRAW | 16:00 | Empty final_review; no exact response | UNAVAILABLE: no durable exact same-fixture source before cutoff |
| 1545827 | AWAY_WIN | 13:00 | EXACT_FIXTURE_REFRESH_COMPLETE, NS | SELECTED; immutable snapshot reproduced |

This is established by joining the immutable opportunity/result events, the
retained candidate final-review documents, source receipts, and existing provider
cache query inventory. The run's allocation records two `/fixtures` requests:
one date discovery and one exact fixture request. Other “exact refresh” metrics
also count odds activity and must not be interpreted as exact TARGET responses
for every candidate. There are four durable sources: one TARGET and three CURRENT
histories (competitions 36/399 season 2027, and competition 5 season 2026).

The production-lineage PREMATCH path, unchanged here:

1. `_cycle` injects the optional observer into `FootballClient`, runner and
   coordinator only in the explicit readiness composition.
2. Existing discovery/restoration supplies classification scalars to `prepare()`.
   Discovery queries are not approved TARGET queries.
3. `LabV2ShadowRunner._exact_review` calls `_fetch('/fixtures', {'id': fixture_id},
   ..., use_cache=False, ttl=2 minutes)` only where the existing review policy calls
   for it. Farther-from-kickoff canonical opportunities do not guarantee a refresh.
4. `FootballClient.fixture` calls `_get('/fixtures', params={'id': fixture_id})`.
   `_get` samples completion after the entire body is received, before downstream
   parsing/mutation. Its synchronous observer persists sanitized Phase C material
   and the durable SOURCE receipt. Capture exceptions cannot trigger HTTP retries.
5. After collection, `begin()` captures the durable DECISION receipt immediately
   before final evaluation. `bind()` associates exact evaluated candidate IDs.
6. The coordinator's existing canonical freeze commits before `observe()` attempts
   the optional V2 snapshot. Existing canonical rows are never backfilled.
7. `available_pins` reads SOURCE receipts strictly ordered before that individual
   DECISION marker. `select_source` applies exact query, timing and freshness;
   assembly checks target fixture, competition, season, teams and NS status.
   Market keys can share a source without consuming it or making another request.

For Namibia–Congo, request identity is exactly `GET /fixtures` with integer
`id=1545827`. Echoed provider `parameters.id` is a string, but it is not the request
identity used by the observer. Durable source
`c8ce0d84028ef408e810e007d2823ef9adbd39fa9b95af2c6ff5ccd607122229` has:

- Response completion: `2026-09-24T12:25:07.736182Z`.
- Durable SOURCE receipt: ordering 1, `2026-09-24T12:25:07.743267Z`.
- Expiry: `2026-09-24T12:27:07.736182Z`.
- Decision cutoff: `2026-09-24T12:25:25.516689Z`, strictly inside that expiry.
- Review's `reviewed_at`: `2026-09-24T12:25:08.745888Z`, a later review/lineup
  timestamp, **not** substituted for exact-response completion.

Snapshot `fc-v2-18fdb920377db235bdff700eb9e389c54d468bbf226008279ef37dfb9ea691aa`
reproduces exactly. The four `CAPTURE_NOT_SCOPED` callbacks preceded the plan;
the inventory contains no missed exact target among them. The 32 unscoped
callbacks are not evidence of 32 missing TARGET requests. The accepted counter
format does not retain endpoint details for each rejected callback; no more
specific per-callback claim is made.

## Before/after capture semantics

| Concern | Accepted behavior | Hardened behavior |
| --- | --- | --- |
| Exact response before prepare | CAPTURE_NOT_SCOPED | Immediately persist under approved exact integer ID request and existing two-minute TTL |
| Exact response after prepare | Scoped Phase C capture | Same capture contract and immutable material |
| Same-fixture market fan-out | Already supported | Preserved, tested across separate cutoffs, prepare and repository reopen |
| History role | Explicit current/previous plan | Unchanged; ambiguity rejected, previous optional, no fallback calls |
| Cache hits | No HTTP observer callback | Unchanged; reuse only separately attested immutable source evidence |
| Late response/registration | Excluded from earlier decision | Unchanged, including equal wall-clock time without preceding durable order |
| Query matching | Exact request parameters | Exact positive integer TARGET ID only; no string/bool coercion or additional parameters |
| Missing source diagnostics | Overall selection verdict | Also persist Phase B candidate/rejection counts per source kind in new RESULT events |

The pre-prepare exact-query scope is constructed from the actual response callback
request, not a discovered fixture row or provider echo. Payload validation remains
in the accepted Phase B/C pipeline. A wrong payload fixture can be retained for
audit but cannot produce a valid snapshot. Source capture does not certify a
classification; assembly still requires the later explicit scope and identity.

A source can serve a later same-fixture decision only while both its stored expiry
and Phase B's strict 15-minute TARGET limit pass. The existing two-minute TTL is
not widened. A response after one cutoff may serve a later cutoff, but never
backfill the earlier decision. No attestation is manufactured for old cache rows.
No Phase A/B/C/D contract, schema, feature value calculation or hash changed.

These changes cannot turn the five real misses into snapshots. The historical
snapshot rate remains **1/6 = 0.166667**.

## Regulation audit

The exact raw TARGET row has NS status, null elapsed/period/fulltime fields,
identity, kickoff, venue and ordinary competition metadata. The current-history
response for competition 36/2027 has 11 FT rows, explicit fulltime score pairs,
`status.elapsed=90`, stoppage-time `extra`, and period timestamps. None is an
explicit reviewed assertion of the target competition-season's regulation format.
Elapsed values describe status telemetry; period timestamps cannot establish the
regulation contract. No duration is inferred from wall-clock differences.

Existing classification is `LAB_COMPETITION_CLASSIFIER_V5`, reason
`NAME_NATIONAL_TEAM_COMPETITION`, age `UNSPECIFIED`, with qualifier and capability
flags. It identifies a profile; it does not prove duration. The existing league
capability/registry metadata supplies no immutable reviewed format assertion.
The only runtime `FormatEvidence` construction in this composition is deliberately
empty for current and previous seasons. No existing reviewed format registry was
found to wire through.

Missing evidence is an explicit provider format field with reviewed semantics,
or a reviewed competition **36 / season 2027** format document, pinned proof
ID/hash and known-at timestamp before the decision. Any used previous-season
response would separately require its season's proof. This cannot be supplied
retrospectively for the already-frozen snapshot.

Therefore regulation behavior and all seven null values remain unchanged.
Synthetic tests alone exercise explicit reviewed 90-minute proof (`VERIFIED_90`),
80-minute proof (`UNSUPPORTED_REGULATION`), missing/unreviewed/late proof
(`REGULATION_UNVERIFIED`), and exact proof lineage during reproduction. AET/PEN
without explicit regulation fulltime scores remains excluded even with a verified
90-minute format; goals including extra time or penalties are not substituted.

## Failed runs and evidence windows

The ledger schema remains version 1, append-only and hash-verified. New RUN
content is `FC_READINESS_2`; reports use that version as well. No migration or
legacy-row rewrite occurs. New END records include counts of response callbacks,
scope preparations, decision boundaries, canonical callbacks and new attempts,
plus a fixed typed credential-failure flag. The manual CLI catches only the
existing `FootballCredentialError` for this flag and re-raises it; its failure
behavior and provider credential resolution are unchanged.

Classification rules:

- A completed END is a completed observation run; existing integrity and missing
  result checks still block independently.
- A failed V2 END is excludable preflight only with the typed credential failure,
  all explicit activity counters exactly integer zero, empty diagnostics, and no
  linked opportunity/result events. Any activity or storage failure blocks.
- A failed V1 END can supply legacy zero-observation proof only with the exact
  known version, an explicitly present **empty diagnostics object**, and no linked
  opportunity/result events. In the accepted implementation every capture
  callback and attempted observation contributes a nonzero diagnostic, including
  failure paths. This is positive terminal accounting, not absence of rows.
- V1 did not count successful `begin()` calls. Consequently any unassociated
  decision receipt conservatively prevents legacy preflight exclusion. All real
  receipt references here belong to the completed run's six opportunities.
- Missing END, omitted counters, unknown version, ledger failure, an observed
  response, or an evidence-bearing incomplete run is not excludable. General V2
  exceptions without credential proof remain blocking even with zero counters.

The legacy event itself does not record the exception class or prove zero HTTP
requests; the credential cause is the operator's supplied evidence. Its durable
END proves zero eligible observations under the audited V1 accounting contract.
This distinction is explicit in the report proof `LEGACY_ZERO_OBSERVATION_END`.
Nothing is inferred merely from a missing OPPORTUNITY row.

On the unchanged real store:

| Report field | Before | After |
| --- | --- | --- |
| runs | 2 | 2 |
| incomplete_runs (all historical unsuccessful runs) | 1 | 1 |
| historical_preflight_failures | Not distinguished | 1 |
| evidence_window_incomplete_runs | Not distinguished | 0 |
| completed_observation_runs | Not distinguished | 1 |
| denominator_completeness | UNPROVEN | VERIFIED_PERSISTED_RUNS |
| readiness | CAPTURE_BLOCKED | INSUFFICIENT_SAMPLE |
| attempts / successful snapshots | 6 / 1 | 6 / 1 |
| reproduction VERIFIED / FAILED | 1 / 0 | 1 / 0 |
| regulation VERIFIED_90 / UNVERIFIED / UNSUPPORTED | 0 / 1 / 0 | 0 / 1 / 0 |

The failed run remains visible with its original ID
`6702b4f760394e41a80e3828b5d6db5c`; completed run is
`76c615cadfde47fdac8c7a2a907fdc0b`. No failed event is deleted, changed, or replaced.
The coverage denominator and source selections are not reduced or rewritten.

## Exact changed files

- `app/prematch_football_context/readiness/composition.py`: self-scoped exact
  callback capture, bounded selection diagnostics, explicit terminal activity.
- `app/prematch_football_context/readiness/__main__.py`: typed credential-failure
  accounting on the already-explicit manual cycle only.
- `app/prematch_football_context/readiness/report.py`: conservative run
  classification, transparent historical/window counts and report version.
- `tests/test_prematch_football_context_readiness_hardening.py`: deterministic
  transport, fan-out, rejection, regulation-lineage and run-completeness tests.
- `docs/audits/PREMATCH_FOOTBALL_CONTEXT_V2_READINESS_HARDENING_REPORT.md`: this report.

## Request-count proof and tests

Tests use `/home/arvis/GoalVisionAI/.venv/bin/python`. All new tests block actual
socket connections and HTTPX network transport. Existing real-client parity tests
use `httpx.MockTransport`, synthetic credentials and disposable databases.

- `test_real_client_controlled_cycle_exact_parity` executes the actual client,
  CLI, runner and coordinator in two timing scenarios and nine modes each:
  observation off/on, capture/receipt/persistence failure, missing evidence or
  snapshot store, and locked evidence or snapshot store. It compares the exact
  ordered request sequence **and request_count**, complete cycle output, canonical
  opportunities, frozen V1 features and champion identity. All are identical to
  observation disabled. No fallback, retry or query expansion is added.
- `test_one_real_client_response_fans_out_without_requests` makes exactly **one**
  fake `GET /fixtures?id=9999`, then three market snapshots across separate
  decisions and a reopened repository. Total request count remains **one**;
  evidence reuse adds **zero** requests.
- Report, verify and diagnostics commands execute with provider `_get` forbidden,
  add **zero** requests, and leave database bytes identical. The typed missing
  credential path likewise performs **zero** requests.
- Rejection/failure cases never invoke a provider. Current history remains scoped,
  PREVIOUS remains optional without fallback, and no synthetic TARGET is created.
- Existing tests protect append-only UPDATE/DELETE/REPLACE guards, exact replay,
  old-canonical refusal, immutable fingerprints and model/publication isolation.

Executed results:

1. Baseline readiness + snapshot: **93 passed** in 28.91s.
2. Initial hardening tests: **27 passed** in 2.73s.
3. Combined hardening/readiness/A/B/C/D suite before the final conservative legacy
   receipt guard: **305 passed, 34 subtests passed** in 50.55s.
4. Final focused readiness + hardening rerun after the conservative legacy receipt
   guard and report-version change: **77 passed** in 37.13s (35 new hardening tests,
   42 accepted readiness tests).
5. Adjacent provider/PREMATCH regressions with real networking blocked:
   **159 passed, 8 subtests passed** in 73.16s.
6. `python3 -m compileall -q app/prematch_football_context/readiness
   tests/test_prematch_football_context_readiness_hardening.py`, `git diff --check`,
   and staged whitespace checks passed. Final SHA-256 comparison verified all
   **6 original evidence files** unchanged, including the five databases and
   retained capability file.

The combined command uses `-m pytest -q` followed by:

```text
tests/test_prematch_football_context_readiness_hardening.py
tests/test_prematch_football_context_readiness.py
tests/test_prematch_football_context_snapshot.py
tests/test_prematch_football_context_capture.py
tests/test_prematch_football_context_sources.py
tests/test_prematch_football_context.py
```

The adjacent regression run calls `pytest.main(['-q', ...])` after replacing
`socket.socket.connect`, `socket.create_connection`, and
`httpx.AsyncHTTPTransport.handle_async_request` with functions that raise
`AssertionError('REAL_NETWORK_FORBIDDEN')`. Its files are:

```text
tests/test_api_football_adaptive_discovery.py
tests/test_api_football_odds_freshness.py
tests/test_api_football_discovery_efficiency.py
tests/test_lab_v2_shadow.py
tests/test_lab_v2_prematch.py
tests/test_prematch_production_integration.py
```

No unrelated full-repository suite, refactor, training or historical backtest was
performed. Prediction algorithms did not change; validation is source/snapshot
reproduction and deterministic runtime parity.

## Remaining blockers and next observation

Only one snapshot, one competition and one UTC decision date exist. The exact
TARGET request is absent for the five other attempts; permitted plumbing cannot
invent it. The seven features remain unavailable until explicit prospective
regulation evidence exists, followed by the existing sample/support checks.
Legacy/unattested cache-only responses remain unavailable. Historical events that
lack terminal zero-observation proof remain blocking; no repair mechanism is added.

Another separately authorized controlled TEST readiness cycle is justified to
observe the hardened plumbing during naturally occurring exact review requests
and verify unchanged request counts. It is not expected to recover early-fixture
TARGETs or resolve regulation proof. No such cycle was executed here.

This work does not start or authorize Phase E and makes no predictive-improvement
claim. No real API-Football calls, historical bookmaker-odds work, Telegram sends,
Official/LIVE changes, probability/selection/strategy/publication changes,
bankroll/statistics mutation, model training, production activation, deployment,
push, systemd/timer/worker/startup changes or production mutation occurred.
