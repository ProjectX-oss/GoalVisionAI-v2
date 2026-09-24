# PREMATCH Football Context V2 — prospective readiness

## Lineage and scope

Starting commit: `b38ad57272f0b147adeef153997d704154dd4892`, accepted Phase D.
Branch: `codex/prematch-football-context-v2-readiness`.
Worktree: `/home/arvis/GoalVisionAI-prematch-context-v2-readiness`.
Created directly from the accepted commit. Other worktrees, including the dirty
shared checkout and A/B/C/D checkouts, were not modified. No cherry-pick, merge,
split-hardening integration, push or deployment occurred.

Read the project guides, RFC, A/B/C/D reports, complete context package and all
four phase test files. Runtime inspection was limited to the client, Lab cycle,
runner, coordinator, existing classification, nearby tests and startup/unit
boundaries. This implements prospective **input readiness only**, not RFC Phase E.
No real prospective coverage or predictive improvement is claimed.

Final commit: the local commit containing this report, resolved exactly with:

```sh
git log -1 --format=%H -- docs/audits/PREMATCH_FOOTBALL_CONTEXT_V2_READINESS_REPORT.md
```

The final handoff supplies its literal SHA. As in the accepted reports, embedding
a commit's own resulting SHA would change that SHA.

## Files changed

- `app/lab_v2_shadow/cli.py`: optional composition injection into the existing
  client, runner and coordinator; retain the client's bounded capture counter.
- `app/lab_v2_shadow/runner.py`: optional, exception-isolated scope preparation
  from already-discovered fixture/classification scalars before existing requests.
- `app/prematch_football_context/readiness/__init__.py`: inert package.
- `app/prematch_football_context/readiness/__main__.py`: explicit manual CLI.
- `app/prematch_football_context/readiness/composition.py`: one prospective
  composition helper around accepted C/D components.
- `app/prematch_football_context/readiness/ledger.py`: isolated append-only
  run/attempt/result diagnostic ledger, without feature values.
- `app/prematch_football_context/readiness/report.py`: read-only coverage and
  offline verification, with deterministic readiness classification.
- `tests/test_prematch_football_context_readiness.py`: synthetic verification.
- This report.

Phase A/B/C/D implementation, tests, schemas, seven names and fingerprints are
unchanged. No V1 schema, artifact, registry, resolver or learning code changes.

## Composition audit and exact enablement boundary

Existing `app.lab_v2_shadow.cli._cycle` owns construction of `FootballClient`,
`LearningCoordinator` (when an adaptive path is supplied), and
`LabV2ShadowRunner`. It calls the runner and later passes its existing APPROVED,
quoted, probability-bearing candidates to the coordinator. The coordinator's
existing quote/time/value gates determine canonical first opportunities. Those
filters and transactions are unchanged.

One explicit optional `football_context` dependency now flows through that
composition point. The dedicated readiness CLI constructs `ProspectiveObservation`
and calls this exact cycle. It binds Phase C `CaptureAdapter` to the existing
`FootballClient(response_observer=...)` and injects the same observation wrapper
into the runner and coordinator. The wrapper delegates final-boundary begin/bind
and snapshot observation to the accepted Phase D `SnapshotObserver`.

The original observer needs an explicit scope plan before requests. One small
runner hook supplies copied scalar fixture/competition/season/classification
metadata after existing discovery/restoration and before existing exact/history
calls. It neither returns inputs nor changes discovery, ordering or requests.
No dictionary of predictions, probabilities or adaptive inputs crosses this hook.
No broad runtime refactoring was necessary.

The existing Phase D receipt remains immediately before **final** evaluation,
after collection; the preliminary evaluation receives no receipt. Bindings use
that durable cutoff, never the earlier scope-preparation clock. Observation runs
after the existing canonical transaction and returns no prediction input.
Old canonical rows are counted separately, never reconstructed or snapshotted
using a later decision receipt. Within-run repeated hook notifications deduplicate.

Observation is OFF by default:

- `_cycle(..., football_context=None)` and existing runner/coordinator defaults
  remain inactive. The original Lab CLI has no implicit readiness flag.
- No environment variable enables readiness; imports construct no stores/client.
- Only the dedicated `cycle --environment TEST|LAB --observe` action enables it.
- `init` initializes stores but does not enable collection.
- `report`, `diagnostics`, and `verify` never import the runtime cycle or client.
- No main application, systemd file, timer, worker, startup or scheduler changed.

The dedicated command always passes `send=False`. It exposes no `--send` option.
The existing cycle's independent publication controls remain unchanged. Readiness
cannot grant publication authorization. Existing adaptive operation is compared
against the same explicitly configured Test/Lab databases, not against a different
champion or a cycle lacking its existing adaptive coordinator.

## Capture, TARGET, history and classification audit

Eligible transport requests are only `/fixtures` with exact queries present in
the existing discovered scope:

| Role | Exact query | Accepted capture TTL |
| --- | --- | --- |
| TARGET | `id=fixture_id` | 2 minutes |
| CURRENT | `league=C, season=S, status=FT, last=99` | 6 hours |
| PREVIOUS | `league=C, season=S-1, status=FT, last=99` | 24 hours |

The adapter performs the accepted translation to `/fixtures(results)` for history.
If one query has ambiguous CURRENT/PREVIOUS roles across discovered seasons, that
query is excluded with `AMBIGUOUS_QUERY_SCOPE`, rather than guessed. No query is
issued by the helper. Unrelated responses and date discovery never become sources.
Phase C owns completion timing, sanitization, registration and SOURCE/DECISION
ordering. No parallel sanitizer or inferred completion timestamp was introduced.

`_exact_review` naturally requests exact TARGET only for existing review paths.
Date discovery is not equivalent. A far-from-kickoff fake cycle makes **zero** exact
TARGET calls both OFF and ON; new canonical opportunities correctly record
`TARGET_SOURCE_UNAVAILABLE`, with no snapshots. A near-kickoff fake cycle naturally
produces exact TARGET and immutable snapshots. Absence is not repaired by fetching.
Phase B NS-only target status/identity and Phase D expected-team checks remain intact.

`_histories` still owns current fetching, previous-season conditional fetching,
query parameters, TTL/cache choice, quota and freshness. Capture observes HTTP
responses only. Cache hits cannot call the observer or create new attestations.
Legacy cache stays `ASOF_UNPROVEN`; no old row, `retrieved_at`, filesystem time or
provider update is certified. Already-retained genuine Phase C evidence can be
selected only through its accepted as-of/order/freshness verification.

No reviewed regulation evidence is present in the audited controlled runtime
metadata. Real composition therefore supplies empty `FormatEvidence` for both
seasons: `REGULATION_UNVERIFIED`. It never guesses 90 minutes, reads elapsed
minutes as proof, fetches formats or introduces a format registry. Tests inject
explicitly synthetic 90/80-minute reviewed proofs solely to exercise available
values and `UNSUPPORTED_REGULATION`; the CLI has no synthetic-format switch.

Classification copies the existing exact profile/version/reason/fingerprint,
flags and age category. Profile UNKNOWN remains UNKNOWN. Gender is explicit only
for senior-men/senior-women classifications or the existing women flag; otherwise
UNKNOWN. National/club entity categories are retained only where explicit profile
meaning supports them; other categories remain UNKNOWN. No name-based secondary
classifier or UNKNOWN-to-senior fallback exists. Invalid scope metadata is diagnosed
and cannot suppress the original prediction. No additional classification request.

## Persistence and failure isolation

Accepted source and snapshot repositories remain separate and unchanged:
`sources.db` and `snapshots.db`. New `attempts.db` owns one version-one table,
`fc_readiness_events(kind, identity, document, hash)`. It stores RUN,
OPPORTUNITY, RESULT and END events. It contains only scalar identities, receipt
references, profile labels, source verdicts, snapshot IDs and bounded counters.
No seven-feature duplication, training table, warehouse or outcome label.

An OPPORTUNITY event precedes the optional snapshot operation; RESULT follows it.
A missing RESULT or interrupted RUN blocks readiness and exposes incomplete
accounting. There is deliberately no cross-database atomicity claim or dependency
of V1 commits on optional V2 commits. Missing/locked stores and capture/receipt/
assembly/persistence exceptions are fail-open to existing PREMATCH behavior.
No retry invokes the provider. Errors retain fixed codes, never exception text.

The ledger is append-only with UPDATE/DELETE/REPLACE protection, content hashes,
exact retry/conflict detection, FULL synchronization, 100 ms lock waits and explicit
initialization. It refuses unrelated schemas; normal/report opens never create or
migrate stores. Read-only reporting verifies SQLite integrity/FKs, source evidence,
receipts, snapshot identity/linkage and complete offline reproduction.

If the diagnostic ledger itself cannot persist, bounded diagnostics remain on
stderr. A completely unrecorded failed run cannot be reconstructed from immutable
snapshots. Reports describe **persisted enabled runs**, and operators must retain
those failure diagnostics; no retrospective repair is provided. Missing stores,
invalid schema, corrupt data and report exceptions produce CAPTURE_BLOCKED, never
an invented empty-store success. Incomplete recorded runs block readiness.

## Denominators and report semantics

Canonical opportunities are unique existing PREMATCH `fixture_id:market` keys
seen at the coordinator hook while observation is enabled. Old canonical
notifications are counted separately and are never eligible new attempts.
An eligible observation attempt is every **new canonical opportunity seen by this
hook**, including scope, receipt, TARGET, history and persistence failures.
It is not every discovered fixture or final evaluated market. Existing no-quote,
nonpositive-value and other noncanonical candidates do not become canonical merely
for readiness. Final evaluated candidate count is separately reported. This
selection limitation is explicit, not evidence of coverage for all discovered
football fixtures or all markets.

- Snapshot rate = linked structurally valid immutable snapshots / eligible new
  V2 observation attempts, including failed attempts in the denominator.
- Primary feature availability = available values / successful immutable snapshots.
  Structurally valid snapshots whose reproduction fails remain explicitly blocked
  evidence, with reproduction failure counts; they cannot authorize research review.
- All-seven rate uses the same snapshot denominator. Histogram has every bucket
  0 through 7. Null and supported numeric zero remain distinct.
- Missing reasons count each applicable feature/reason once; multiple reasons can
  apply, so reasons need not sum to missing-feature count.
- Source availability uses eligible attempts, including no-snapshot attempts.
  SELECTED is the Phase B query/as-of/payload verdict, not proof of regulation,
  target NS eligibility, sufficient history or supported Pi state.
- Regulation/profile counts and competition/profile feature breakdown use snapshots;
  attempt profile counts are reported separately. Current target regulation counts
  once per snapshot. Groups show counts for all sizes, feature rates only at N>=10.
- Reproduction rate = verified snapshots / **all stored snapshot rows**, including
  corrupt rows as FAILED. No corruption is silently skipped as verified.
- Exact first/last cutoff uses durable receipts linked to new attempts, including
  no-snapshot attempts. Failed receipt attempts have no fabricated cutoff.
- Unique fixtures/competitions are reported for attempts and separately for snapshots.
  Market siblings are correlated; snapshot count is not an independent-fixture count.
- Every rate includes numerator, denominator, denominator name and decimal fraction.
  Zero denominators are `N/A`, never 0%.

Readiness precedence (no score, automatic action or Phase E authorization):

1. Integrity failure, inconsistent linkage or incomplete run: CAPTURE_BLOCKED.
2. No new prospective attempts: NO_PROSPECTIVE_EVIDENCE.
3. Attempts but zero snapshots: CAPTURE_BLOCKED.
4. Fewer than 100 successful immutable snapshots: INSUFFICIENT_SAMPLE.
5. At least 100 snapshots but fewer than five competitions or seven distinct UTC
   decision dates: PARTIAL_COVERAGE.
6. Otherwise: READY_FOR_V2_RESEARCH_REVIEW, requiring 100% stored-snapshot
   reproduction and no integrity failure. Seven distinct observed UTC dates is a
   conservative interpretation of spanning seven calendar days.

No minimum per-feature percentage is imposed. A genuine all-null cohort may be
ready for human **input-readiness review**, with its deficiencies fully visible.
`phase_e_authorized` is always false. Readiness never changes runtime/model state.

## Manual commands for later separately authorized use — NOT EXECUTED

Use a dedicated Test/Lab root, the accepted implementation's interpreter, and the
existing canonical API-Football credential resolution. This work did not read,
copy or configure credentials. The runtime root below owns isolated
`shadow.db`, `analysis.db`, `adaptive.db`, `lab-ledger.db` and `var/capabilities.json`;
no production path is selected implicitly. Existing Test/Lab champion preparation,
if desired, remains an independent operation; this CLI never bootstraps a champion.

```sh
cd /home/arvis/GoalVisionAI-prematch-context-v2-readiness

/home/arvis/GoalVisionAI/.venv/bin/python -m app.prematch_football_context.readiness \
  --root /home/arvis/GoalVisionAI-prematch-context-v2-readiness/var/readiness-test init

# Exactly one existing controlled Test PREMATCH cycle; no Telegram authorization.
/home/arvis/GoalVisionAI/.venv/bin/python -m app.prematch_football_context.readiness \
  --root /home/arvis/GoalVisionAI-prematch-context-v2-readiness/var/readiness-test \
  cycle --environment TEST --observe --max-calls 40 --horizon-days 1

/home/arvis/GoalVisionAI/.venv/bin/python -m app.prematch_football_context.readiness \
  --root /home/arvis/GoalVisionAI-prematch-context-v2-readiness/var/readiness-test diagnostics

/home/arvis/GoalVisionAI/.venv/bin/python -m app.prematch_football_context.readiness \
  --root /home/arvis/GoalVisionAI-prematch-context-v2-readiness/var/readiness-test report

/home/arvis/GoalVisionAI/.venv/bin/python -m app.prematch_football_context.readiness \
  --root /home/arvis/GoalVisionAI-prematch-context-v2-readiness/var/readiness-test verify
```

`cycle` preserves the existing report on stdout; V2 counters are separate stderr.
The last three commands are read-only and all verify stored snapshots offline.
Nighttime still follows the existing no-provider pause boundary. These are manual
commands only; no repeated real cycles, quota consumption or scheduling occurred.

## Verification and non-interference

Interpreter: `/home/arvis/GoalVisionAI/.venv/bin/python`.
Final combined targeted run: **575 passed, 42 subtests passed**, 92.99 seconds.
A subsequently added manual CLI-composition test passed separately: **1 passed**,
1.07 seconds. Total distinct passing tests: **576**, plus **42 subtests**.
The combined run included 41 readiness tests, 51 Phase D, 56 Phase C, 81 Phase B,
41 Phase A and 305 directly affected runtime regressions. No implementation changed
after that combined run began. All football/provider evidence is synthetic.

```sh
/home/arvis/GoalVisionAI/.venv/bin/python -m pytest -q \
  tests/test_prematch_football_context_readiness.py \
  tests/test_prematch_football_context_snapshot.py \
  tests/test_prematch_football_context_capture.py \
  tests/test_prematch_football_context_sources.py tests/test_prematch_football_context.py \
  tests/test_api_football_adaptive_discovery.py tests/test_api_football_odds_freshness.py \
  tests/test_api_football_discovery_efficiency.py \
  tests/test_lab_v2_shadow.py tests/test_lab_v2_prematch.py \
  tests/test_prematch_production_integration.py \
  tests/adaptive_lab/test_prematch_autonomy.py::test_baseline_exact_equivalence_and_registry_lane \
  tests/adaptive_lab/test_prematch_autonomy.py::test_baseline_context_required_and_artifact_tamper \
  tests/adaptive_lab/test_prematch_autonomy.py::test_existing_prematch_bootstrap_survives_light_safety_integration \
  tests/adaptive_lab/test_prematch_autonomy.py::test_registry_matches_golden_outputs_from_accepted_production_commit

/home/arvis/GoalVisionAI/.venv/bin/python -m compileall -q \
  app/prematch_football_context app/lab_v2_shadow/cli.py app/lab_v2_shadow/runner.py \
  tests/test_prematch_football_context_readiness.py
git diff --check
```

Compile/import smoke: PASS. Import audit blocks DB/network/filesystem writes.
Schema/integrity/FK checks and immutable guards: PASS on disposable stores.
Working/staged diff checks: PASS. The broad unrelated repository suite was not
needed; shared changes remain narrow observation/composition hooks.

| Required evidence | Tests/proof |
| --- | --- |
| A–I, C/D/E/F/G zero additional requests | Real FootballClient + HTTPX MockTransport through actual controlled CLI, runner and coordinator; near/far cases, OFF/ON and seven failures; exact full report, request sequence and count equality |
| J–P | Legacy ASOF_UNPROVEN; no exact TARGET fetch in far cycle; missing CURRENT/PREVIOUS; UNKNOWN, ambiguous scopes; unverified/unsupported formats |
| Q–S | Accepted A/B/C/D assembly and offline reproduction; exact seven values/masks/reasons, supported zeros and deterministic hashes |
| T–AA | Full canonical V1/input equality, nine legacy fields remain null/absent, existing baseline champion unchanged, no learning observations/LIVE publications, no Telegram construction, unchanged Official report |
| AB–AF | Missing/locked source and snapshot databases; capture exception; receipt/assembly/persistence failure; malformed current/target; no provider retry |
| AG–AS | N/A denominators, exact histograms 0–7, multireason aggregation, source/regulation/profile counts, exact windows/unique counts, explicit corrupt snapshot/source/ledger and reproduction failures |
| AT–AY | All five state boundaries; 100 actual synthetic immutable snapshots over five competitions/seven dates reproduce 100%, all-null coverage still explicitly reported; repeated read-only report leaves DB bytes unchanged |
| AZ–BE | Inert imports, default hooks off, explicit CLI/no send, no historical capture path, immutable retry/old-opportunity exclusion, deterministic report and unchanged A/B/C/D goldens |

The real-cycle comparison includes a synthetic existing PREMATCH baseline champion;
identity and exact adaptive inputs remain equal across all modes. It does not
train a model. The 100-snapshot fixture uses local synthetic responses, not 100
provider cycles. The all-mask aggregation test uses explicitly artificial
projections only as a unit test; it does not certify them as prospective evidence.

Development corrections were test-side restoration of schema guards after deliberate
corruption, plus defensive exception isolation for optional scope lookup. No
source semantics, prediction logic or fingerprint contract was relaxed.

Confirmed: **zero live API calls; zero Telegram sends; Official unchanged;
bankroll/statistics unchanged; LIVE unchanged; no historical bookmaker-odds work**.
No outcomes, W/L, ROI, performance comparison, backtest, training, calibration,
challenger, promotion, activation, rollback, production DB operation, environment
change, scheduler, deployment, push or merge was performed. Existing V1 feature
schema, artifacts, champion resolution and learning observations are unchanged.

## Limitations and evidence required before reconsidering Phase E

Real exact-TARGET coverage is unknown and may be low. Cache-only cycles cannot
supply new trustworthy capture. Real format coverage remains unverified, so many
or all seven values can legitimately be null. Canonical-only eligibility is a
selected cohort, not all discovered fixtures. Source scans and reproduction use
the conservative accepted repositories; no indexing/retention redesign was added.
Synchronous durable I/O adds physical latency; deterministic tests do not promise
zero elapsed overhead. Hashes prove consistency, not resistance to privileged
rewriting of every document/hash. Total ledger outage needs retained operator
stderr diagnostics; no historical repair is authorized.

Later explicitly authorized Test/Lab observation must accumulate real immutable
snapshots, precise missing-source/format/support reasons, competition/profile
coverage and complete offline reproduction. The conservative review target is
100 snapshots across five competitions and seven observed UTC dates, 100%
reproduction, complete accounting and no integrity failures. Review actual
per-feature coverage and unique-fixture diversity before deciding whether Phase E
is justified. No feature-benefit claim or automatic Phase E permission follows.
Split-hardening and every model/vector/registry/training task remain deferred.

Final commit SHA: resolve the report-containing local commit with the command at
the beginning of this report; literal SHA is supplied in the final handoff.

V2_READINESS_IMPLEMENTED_AND_VERIFIED
