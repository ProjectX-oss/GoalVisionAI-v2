# PREMATCH Football Context V2 — Phase D report

## Pre-edit decision-boundary review

Base: `65204a7f7d4879052f12c12219ea2e6e51fb9a23`.
Branch: `codex/prematch-football-context-v2-phase-d`.
Worktree: `/home/arvis/GoalVisionAI-prematch-context-v2-phase-d`.
The shared checkout was dirty at `fadd59d7d9492133f84d9d80c9a72dad14c57c67`
on `codex/lab-v2-global-overhaul-2026-09-17`. Status and worktree list were
recorded before creating this clean sibling directly from accepted Phase C.
No other worktree is edited, no split-hardening cherry-pick is made.

The runner has two evaluation moments: preliminary shortlisting, then final
candidate evaluation after existing collection/final review. Neither discovery
start nor quote retrieval nor publication is the final input boundary. T must
be a Phase C `capture_cutoff()` immediately before the final `_evaluate` call.
The existing `evaluation_clock` continues to govern V1 unchanged; it is not
promoted to durable availability proof. The preliminary pass gets no V2 receipt.

`LearningCoordinator.shadow` freezes the first eligible PREMATCH fixture/market
under `canonical_opportunities`, key `str(fixture_id) + ':' + market`. Its
`prepared_at_utc` is a later freeze time, not proof of input capture. The snapshot
must bind this existing key AND the exact existing candidate ID, without creating
a competing fixture identity or modifying the existing observation hash. The
forward-selection ledger has a different APPROVED admission gate; it cannot be
silently substituted for the adaptive canonical opportunity.

Proposed narrow observation-only integration, documented before runtime edits:

1. Opt-in observer records a durable receipt before final evaluation, retaining
   the receipt outside V1 inputs. After evaluation it associates candidate IDs
   with that receipt. No preliminary candidate can acquire that receipt.
2. When the coordinator has frozen its canonical opportunity, the same explicitly
   injected observer attempts the snapshot for that exact candidate. A missing
   association fails closed; it never captures a fresh cutoff for an old candidate.
3. Observer return values never enter probabilities, selection, confidence,
   ranking, odds, stake or publication. Copies/minimal immutable identities cross
   the observer boundary; V1 candidate and observation documents remain unchanged.
4. Observer has only local source/snapshot repositories and explicit scope facts;
   no provider/Telegram/client reference. It cannot add or retry API requests.
5. Every optional invocation is exception-isolated. Diagnostic text is a fixed
   code. Missing sources or format proof, locked stores and failed persistence
   leave V1 behavior unchanged. No schema/bootstrap occurs on import/startup.
6. A crash before snapshot persistence may lose the optional observation. Missing
   original decision linkage is unavailable, never repaired with today's cutoff.
   This phase does not make V1 canonical writes depend on V2 transactions.

## Implemented scope and exact files

The user task's Phase D scope governs where the original RFC phase outline differs.
Phase A/B/C code, tests, schema, semantic manifest and fingerprints are unchanged.

| File | Change |
| --- | --- |
| `app/prematch_football_context/snapshot/__init__.py` | Inert subpackage |
| `app/prematch_football_context/snapshot/contracts.py` | One immutable snapshot, existing opportunity identity binding, seven-value projection |
| `app/prematch_football_context/snapshot/service.py` | Durable ordering validation, Phase B selection/evidence, Phase A calculation, exact reproduction |
| `app/prematch_football_context/snapshot/repository.py` | Explicit isolated append-only store, canonical decoding and read-only inspection |
| `app/prematch_football_context/snapshot/observer.py` | Optional final-evaluation to canonical-freeze association and bounded failure diagnostics |
| `app/lab_v2_shadow/runner.py` | Optional constructor dependency; receipt before final evaluation; immutable identity association afterward |
| `app/adaptive_lab/coordinator.py` | Optional constructor dependency; observe exact canonical row after its transaction commits |
| `tests/test_prematch_football_context_snapshot.py` | Phase D synthetic/disposable integration, persistence, reproduction and isolation tests |
| `docs/audits/PREMATCH_FOOTBALL_CONTEXT_V2_PHASE_D_REPORT.md` | This report |

The only shared runtime edits are 16 added runner lines and 11 added/two replaced
coordinator lines. No calculation, gate, source query, source request, candidate
material, observation document, model artifact or product policy is changed.

## DecisionReceipt placement and canonical identity

The implementation follows the pre-edit audit above. The real-runner test spies
on the existing evaluator without replacing any calculations: receipt count is
zero at preliminary evaluation and one at final evaluation. All candidates from
that final immutable input batch share its receipt; each snapshot binds its own
fixture/market and exact `lab-v2-candidate-<existing hash>` identity. These are
separate opportunities, not a collapsed preliminary/final decision.

The canonical first-opportunity key remains exactly `fixture_id:market`, within
PREMATCH. `LearningCoordinator.shadow()` remains its authority. The later
`opportunity()`/observation digest also includes candidate identity, quote and
probability; those semantics are untouched. V2 uses the canonical store key plus
the candidate identity that already binds candidate material; it does not add a
second fixture ID system or substitute the forward-selection ledger's narrower
gate. No Official identity changes.

The coordinator tells the observer whether the canonical row was newly created.
An existing canonical row with no V2 snapshot MUST NOT acquire a new snapshot
from a later evaluation, even if that later candidate has identical content/hash.
A regression explicitly covers this subtle case. An existing snapshot is verified
and returned as a replay using its original receipt/pins. A materially different
candidate under the same canonical key conflicts. The current product permits
only the first decision per fixture/market; later decisions for another market
can coexist, but a second same-market decision cannot overwrite the first.

`prepared_at_utc`, discovery clock, quote timestamps, filesystem times, UUIDs,
rowids and legacy `retrieved_at` are never used as Phase D ordering evidence.
The existing evaluation clock is not replaced. V2 returns no model input.

## Source selection and format truth

Assembly requires an exact `EvidenceRepository.load_cutoff()` verification.
Source enumeration uses persisted SOURCE receipts strictly before the DECISION
ordering, followed by Phase C `load(source_id, decision=receipt)` verification.
Every admitted candidate must carry the Phase C-generated `before_capture` proof,
including candidates whose timestamps are strictly less than T. Phase D never
constructs `CaptureOrder` itself. Equal timestamps are valid only with strict
SOURCE-before-DECISION order. A test rewrites a disposable later receipt with
older, internally rehashed timestamps: that source is still rejected by order.

Only exact TARGET fixture, CURRENT competition/season/FT/last-99 and optional
PREVIOUS same competition/season-minus-one queries enter the Phase B selector.
No provider, cache fallback, latest-provider read, additional request, current
clock reconstruction, query expansion or freshness relaxation exists here.
Phase B retains its existing ordering, malformed-latest rejection, TTL/expiry,
status and wrong-scope behavior. Selected-but-invalid optional source IDs remain
pinned as evidence of why values were unavailable; they do not supply values.
TARGET unavailable/wrong scope/non-NS fails closed without a snapshot. Missing
CURRENT preserves all required nulls; missing PREVIOUS remains optional.

All candidate IDs considered for the three roles and exact selected IDs are
retained, with compact source selection verdicts. This permits independent
reconstruction of Phase B's decisions without persisting arbitrary runtime trees.
An expired source is `EXPIRED` in the source decisions; the accepted Phase B/A
mapping yields `SOURCE_UNAVAILABLE`, not a newly invented missing reason.

Bindings require explicit classification and format assertions. No classification
or competition-format registry is populated. Unreviewed duration, including a
bare supplied `90` without proof, stays `REGULATION_UNVERIFIED`. No elapsed-time
or 90-minute default exists. Verified-looking format proofs in tests are synthetic.

## Snapshot and seven-feature projection

Contract: `PREMATCH_FOOTBALL_CONTEXT_V2_SNAPSHOT_1`, stream `PREMATCH`.
Projection: `PREMATCH_FOOTBALL_CONTEXT_V2_PROJECTION_1`.
This projection is seven football inputs only, not the RFC's later fourteen-field
learning vector, model coordinates, prediction, bet, training row or label.

Canonical ordered names are imported unchanged from Phase A:

1. `home_team_observed_weighted_scoring_rate`
2. `home_team_observed_weighted_conceding_rate`
3. `away_team_observed_weighted_scoring_rate`
4. `away_team_observed_weighted_conceding_rate`
5. `home_team_current_pi_adjusted_form`
6. `away_team_current_pi_adjusted_form`
7. `pi_designated_side_rating_difference`

Values are copied as Phase A six-place Decimal strings or JSON null. No float
conversion, second rounding, default zero, imputation, aliases or transformation.
Supported zero remains `0.000000`; missing has mask 1 and ordered Phase A reasons.
Projection shape/order/contract, numeric canonical form, mask and reasons validate.

The frozen snapshot binds: existing opportunity key/candidate identity; fixture,
competition, season, designated teams; exact cutoff and receipt hash/order;
classification and current/previous format assertions; complete exact candidate
manifest and selected source IDs; EvidenceBundle, semantic, ContextInput and
ContextResult fingerprints; projection values/mask/reasons and fingerprint;
source validation/selection and exclusion summaries; snapshot fingerprint.
Binding contains only small explicit replay contracts. Full football facts remain
in the dedicated Phase C evidence store. No raw candidate/prediction/model/label
object is copied into the snapshot.

Hashes reuse accepted canonical JSON and domain-separated SHA-256. The projection
uses `LAB_VECTOR_V2` with its explicit projection contract; the snapshot uses
`FC_SNAPSHOT_V1` with its explicit snapshot contract. Its self hash is excluded;
`snapshot_id = 'fc-v2-' + snapshot_hash`. No operational wall-clock creation time
or database surrogate is added to semantic material. Receipt provenance is included
because it proves availability, not merely because it is a write timestamp.

## Persistence, idempotency and offline reproduction

Phase C's schema verifier deliberately owns exactly its two source tables. Phase D
therefore uses a separate explicitly initialized database, preserving Phase C's
source semantics and schema byte-for-byte. No unrelated production table or
migration is added. Snapshot schema version 1 has one table:

`fc_v2_snapshots(snapshot_id PRIMARY KEY, opportunity_key UNIQUE, document)`.

One canonical document contains the whole immutable snapshot atomically. UPDATE,
DELETE, REPLACE and conflicting UPSERT are rejected by database guards. Inserts
use `BEGIN IMMEDIATE`, FULL synchronization and a 100 ms lock timeout. Exact
replay is idempotent; same-key different immutable content raises
`ImmutableConflict`. Failed insert/commit rolls back without a partial snapshot;
a commit that succeeds but loses its return is recoverable by exact replay.
Concurrent exact appends yield one row. No cross-database FK is claimed; Phase C
bindings are verified by the service. Disposable `integrity_check` is `ok` and
`foreign_key_check` is empty. Source-store FK tests remain passing.

Repository open is read-only by default and never creates or migrates schema.
`initialize(path)` is the only explicit bootstrap and refuses unrelated stores,
including Phase C databases. Imports/startup never call it. Read-only reopening,
no-create/no-schema-write, repeat initialization and empty-store creation pass.

`reproduce(evidence_repository, snapshot)` loads only the persisted receipt and
exact candidate manifest, redoes Phase B selection and retained EvidenceBundle,
replays Phase A inputs/result, and rebuilds the projection and snapshot. Full
snapshot equality proves identical selected pins, EvidenceBundle fingerprint,
ContextInput fingerprint, ContextResult fingerprint, seven values, missingness,
projection fingerprint and snapshot fingerprint. Later source corrections are
excluded from the original manifest; they cannot rewrite an earlier snapshot.
Missing/corrupt sources, receipts or snapshots fail closed. Rehashed inner-field
corruption is tested, as well as ordinary hash mismatches. No provider or clock
is available to reproduction.

Minimal read-only inspection is `SnapshotRepository(path).inspect(key, evidence)`
with `EvidenceRepository(source_path)` opened read-only. It returns snapshot and
candidate identities, opportunity key, cutoff/receipt, selected sources, all seven
named values, missing fields/reasons, source/exclusion summaries, fingerprints and
`reproduction='VERIFIED'`. Missing/corrupt evidence raises `EvidenceUnavailable`;
it is never falsely reported as verified. No dashboard, Telegram view or metrics.

## Runtime isolation and unchanged behavior evidence

Explicit Test composition injects the same `SnapshotObserver` into runner and
coordinator, plus explicitly opened repositories and reviewed scope bindings.
There is no flag, environment variable, CLI wiring, automatic startup change,
worker or collection enablement. Default constructors remain inactive.

The observer sees immutable scalar identities, not mutable candidate structures.
It never returns values to prediction logic. It has no provider, Telegram client,
model resolver, outcome loader or bankroll dependency. Every optional hook has an
outer exception guard; the observer itself handles receipt/assembly/storage errors
with fixed bounded counters. No exception text, secrets, paths or payloads enter
diagnostics. A failing receipt does not cause another API request or backdated
receipt. Snapshot failure does not roll back or modify the V1 canonical row.

The end-to-end parity test runs the real runner, real history/Pi/ensemble/profile
calculations, real final review and real LearningCoordinator canonical freezing.
Only the provider is fake. It compares exact serialized full reports, V1 canonical
rows, existing captured features, provider request sequence and request counts for
five modes: disabled, enabled, snapshot commit failure, decision receipt failure,
and throwing hooks. All are identical. The enabled mode also verifies every
persisted canonical snapshot and retries the original rows after discarding
transient associations. Preliminary/final marker placement is asserted directly.
Phase C's real HTTP client/fake transport parity test also remains passing.

V1 fields `home_goal_rate`, `away_goal_rate`, `recent_form`, `goals_scored`,
`goals_conceded`, `home_form`, `away_form`, `strength`, `rest_days` are untouched.
No seven-value append to V1 vectors occurs. Existing V1 feature code, observations,
artifact registry/transformer, champion resolution, thresholds, odds, confidence,
publication and stake policies are unchanged. Selected existing baseline/registry
regressions pass. No snapshot is joined to an outcome or used for a performance
label, metric, training job or model comparison.

## Tests and executed checks

Interpreter: `/home/arvis/GoalVisionAI/.venv/bin/python`. All data and databases
are synthetic/disposable; all provider transports are fake. No real API access.

Combined verification command:

```sh
/home/arvis/GoalVisionAI/.venv/bin/python -m pytest -q \
  tests/test_prematch_football_context_snapshot.py \
  tests/test_prematch_football_context_capture.py \
  tests/test_prematch_football_context_sources.py \
  tests/test_prematch_football_context.py \
  tests/test_api_football_adaptive_discovery.py \
  tests/test_api_football_odds_freshness.py \
  tests/test_api_football_discovery_efficiency.py \
  tests/test_lab_v2_shadow.py tests/test_lab_v2_prematch.py \
  tests/test_prematch_production_integration.py \
  tests/adaptive_lab/test_prematch_autonomy.py::test_baseline_exact_equivalence_and_registry_lane \
  tests/adaptive_lab/test_prematch_autonomy.py::test_baseline_context_required_and_artifact_tamper \
  tests/adaptive_lab/test_prematch_autonomy.py::test_existing_prematch_bootstrap_survives_light_safety_integration \
  tests/adaptive_lab/test_prematch_autonomy.py::test_registry_matches_golden_outputs_from_accepted_production_commit \
  tests/test_current_match_intelligence.py::CurrentMatchIntelligenceTests::test_cache_reuse_consumes_no_new_api_calls \
  tests/test_current_match_intelligence.py::CurrentMatchIntelligenceTests::test_network_retrieval_after_run_start_sets_snapshot_cutoff \
  tests/test_current_odds_forward_test.py::ForwardTestFoundationTests::test_api_football_client_is_network_inert_until_explicit_call
```

Result: **535 passed, 42 subtests passed**, 37.21 seconds. This included 49 Phase D,
56 Phase C, 81 Phase B, 41 Phase A and 308 directly relevant regressions.
Afterward two additional adversarial ordering/concurrent lost-return tests were
added; the final complete Phase D suite passed **51 tests**, 4.71 seconds. No
implementation changed after the combined passing run. Total distinct passing
tests across these final runs: **537**, plus **42 subtests**; not 586 tests.

```sh
python3 -m compileall -q app/prematch_football_context \
  app/lab_v2_shadow/runner.py app/adaptive_lab/coordinator.py \
  tests/test_prematch_football_context_snapshot.py
/home/arvis/GoalVisionAI/.venv/bin/python -B -c \
  'import app.prematch_football_context.snapshot.contracts, app.prematch_football_context.snapshot.service, app.prematch_football_context.snapshot.repository, app.prematch_football_context.snapshot.observer, app.lab_v2_shadow.runner, app.adaptive_lab.coordinator'
git diff --check
git diff --cached --check
```

Compile/import and working/staged whitespace checks: PASS. Import subprocess
blocks DB/network/filesystem-write activity. No additional dependency installed.
Disposable schema fresh/empty/reopen/idempotency/rollback/immutability/lock/FK/
integrity checks pass. Full unrelated repository suite was not run: runtime edits
remain narrow observation hooks and the targeted tests resolve affected behavior.
No algorithm changed, and no predictive backtest or training was performed.

Development corrections were test-only expectations: capability-cache fixtures
must use the existing `var/` path; expired CURRENT evidence maps to source missing
under the accepted Phase B rules. Neither prompted a relaxation of existing code.

| Requested cases | Verification |
| --- | --- |
| A–H | Durable exact pins; equal-time strict proof; missing/fake/later receipt rejection; adversarial older timestamps; no provider replay; legacy IDs rejected |
| I–P | Wrong target/history competition/season/fixture/team; NS-only status; CURRENT/PREVIOUS missingness; absent or bare-90 format stays unverified |
| Q–W | Exact seven names/order; canonical Decimal strings; hostile Decimal context; mask/reasons/null/zero distinction; V1 separation; deterministic hashes |
| X–Z | Exact append/reopen/replay; immutable same-key conflicts; later distinct market coexists; original correction replay unchanged |
| AA–AE | UPDATE/DELETE/REPLACE/UPSERT guards; commit/insert rollback; locking; read-only schema immutability |
| AF–AI | Corrupt snapshot/source, missing source, altered/missing/wrong receipt fail closed |
| AJ–AP | Full independently rebuilt snapshot equality and inspection prove all requested hashes, values and missingness; network prohibited |
| AQ–AT | Five-mode real-runner/coordinator full-output and request-sequence/count parity; Phase C real-client fake-transport parity retained |
| AU–AZ | No sender, no Official/bankroll/statistics changes, LIVE hook exclusion, no historical-odds dependency; inert imports |
| BA | Defaults absent; no production/CLI/startup composition added |

## Limitations and exact deferred work

- This is Test-ready observation-only code, not authorized prospective production
  collection. Scope/format/classification evidence and Phase C source capture need
  explicit composition. Cache-only or absent exact TARGET remains unavailable.
- No real regulation-format coverage is asserted. Seven nulls are valid truthful
  snapshots; coverage is not optimized or presented as predictive value.
- A failed snapshot after V1 canonical commit can leave no V2 snapshot. Automatic
  retries of an old canonical opportunity never invent a later association. This
  intentional loss of optional evidence preserves V1 independence and truth.
- Pending candidate associations last only for the latest final evaluation batch;
  restart/lost association fails closed. There is no worker, recovery scheduler,
  historical reconstruction or legacy backfill.
- Enumeration currently verifies preceding registered sources and filters exact
  queries. It is conservative on corruption and may scan old evidence. Optimized
  source indexing/retention is not a reason to weaken ordering or Phase B rules.
- SQLite lock waiting is bounded, but opt-in durable I/O has physical latency.
  Tests prove equality for identical inputs/clocks, not zero wall-clock overhead.
  Actual later publication still applies its existing clock-based gates.
- As in Phase C, hashes prove consistency, not resistance to an administrator
  rewriting all evidence and recomputing every hash. Trusted clocks/storage and
  reviewed assertions remain boundary assumptions.
- Phase E: V2 fourteen-input learning vector/dispatch, registry, transformer,
  model/dataset compatibility and split-hardening integration remain deferred.
- Phase F: prospective Test/Lab composition, real capture/format readiness,
  coverage collection and coverage reporting remain deferred.
- Phase G: permitted outcome-linked research, ablations, training, evaluation,
  calibration, challenger/model comparison and any promotion remain deferred.
  No Phase E/F/G code or workflow was implemented or executed.

Confirmed for this task: **zero live API requests; zero Telegram sends; Official
unchanged; bankroll/statistics unchanged; LIVE unchanged; no historical bookmaker-
odds work; no production database reads/writes/migrations; no deployment, merge,
push, training, activation or production configuration change.** All durable
writes during verification were to disposable test stores. Other worktrees and
unrelated user changes remain untouched.

Final commit SHA: the commit containing this report, resolved exactly by:

```sh
git log -1 --format=%H -- docs/audits/PREMATCH_FOOTBALL_CONTEXT_V2_PHASE_D_REPORT.md
```

The final handoff supplies the literal SHA. As with the accepted Phase A/B/C
reports, embedding a commit's own resulting SHA changes that SHA. This report,
implementation and tests are committed together; stop after the local commit.

PHASE_D_IMPLEMENTED_AND_VERIFIED
