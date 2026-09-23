# PREMATCH Football Context V2 — Phase B report

Date: 2026-09-23. Scope: bounded source evidence and offline replay only.

## Lineage and isolation

- Starting/accepted Phase A commit: `c711070fc8565388b6e1062fc00e96a0b85d2a57`.
- Branch: `codex/prematch-football-context-v2-phase-b`.
- Worktree: `/home/arvis/GoalVisionAI-prematch-context-v2-phase-b`.
- Initial shared checkout: `codex/lab-v2-global-overhaul-2026-09-17`,
  HEAD `fadd59d7d9492133f84d9d80c9a72dad14c57c67`, with numerous existing
  tracked modifications and untracked files. Recorded branch, HEAD, status and
  worktree list before editing. Left that checkout untouched.
- Created a sibling worktree directly from the accepted Phase A branch. Its
  existing worktree remains clean and untouched. No reset, clean or cherry-pick.
  Split hardening `25f536199fd893bd681a82ae586e62b545e28d23` was not imported.
- Read the project guides, complete RFC, Phase A report/package/tests before
  code changes; inspected only adjacent source/cache/status handling needed here.
- Final commit SHA: the commit containing this report, resolved exactly by
  `git log -1 --format=%H -- docs/audits/PREMATCH_FOOTBALL_CONTEXT_V2_PHASE_B_REPORT.md`.
  The final handoff supplies the literal SHA. As in the accepted Phase A report,
  embedding a commit's own resulting SHA would change that SHA.

## Files added

| File | Responsibility |
| --- | --- |
| `app/prematch_football_context/sources.py` | Frozen query/timing/source contracts; pure bounded selector; sanitized-content validation; small deterministic diagnostics |
| `app/prematch_football_context/source_adapter.py` | Allowlisted API-Football facts; conservative legacy adaptation; status mapping; explicit format evidence |
| `app/prematch_football_context/evidence.py` | Retained typed bundle, Phase A reconstruction and verified offline replay |
| `tests/test_prematch_football_context_sources.py` | Synthetic source, replay, integrity and inertness tests |
| This report | Audit findings, verification and limitations |

No existing file changed. In particular, Phase A calculations, contracts,
manifest, canonical serialization, feature order and golden fingerprints are frozen.
No shared runtime/cache code changed; no production caller imports these modules.

## Timestamp and source audit

Findings are from the accepted implementation base, not another working tree or
an inspection of production records.

| Source path | Actual semantics and proof limits |
| --- | --- |
| `app/football/client.py:_get` | Awaits HTTP response, reads quota and calls `_safe_json`, then assigns UTC `retrieved_at_utc`. On this concrete path it is **after response completion**, not request start. `_pace_request` tracks a monotonic request-start value, not a retained UTC request-start timestamp. |
| `FootballClient.finished_matches` | Calls existing `/fixtures` with league, season, `status=FT`, last; returns the unwrapped response list. No new endpoint is needed. |
| `lab_v2_shadow/runner.py:_histories` | Current exact last-99 query; conditional already-existing previous-season query. Cache namespace `/fixtures(results)`; TTLs 6h/24h. Normalization discards source timing/identity. |
| `runner.py:_fetch`, `_metadata_time` | Uses client metadata if parseable, otherwise falls back to the earlier supplied runner clock. Cache rows do not preserve which timing path was used. A fallback clock is not completion proof. |
| `lab_v2_shadow/repository.py:append_cache` | Stores endpoint, query JSON/hash, supplied retrieval timestamp, expiry derived from that timestamp, payload JSON/hash and deterministic cache ID. The insert commits, but **no durable registration/commit timestamp or capture-order receipt is retained**. |
| `repository.py:cached` | Latest retrieval timestamp; expiry comparison permits equality; no retrieval/registration cutoff bound. Unchanged by Phase B. |
| `current_match_intelligence/{provider,service,repository}.py` | Adjacent cache has similar metadata/fallback and no registration timestamp. Provider timestamp is extracted only for odds, not result/fixture context. It is not an alternative history source for Phase B. |
| `lab_v2_shadow/pi_ratings.py:parse_api_fixture_results` | FT/AET/PEN result normalization; explicit fulltime for AET/PEN, FT goals fallback, conflict filtering. Loses retained raw/source bindings, so it cannot supply Phase B replay evidence alone. |

**Proven in code:** real-client metadata is recorded after response completion;
query/payload identities and TTL derivation are explicit. **Unproven for existing
cache rows:** completion-path provenance, durable registration time, capture
transaction ordering, provider update time and regulation format. No historical
row is admitted based solely on its retrieval-named field or TTL.

`legacy_cache_candidate` preserves the ambiguous old timestamp separately as
`legacy_retrieved_at`, leaves completion/registration/known-at null and produces
`ASOF_UNPROVEN`. It reads a supplied record only, never a database. No convenient
request-start, completion or registration meaning is retrofitted onto old rows.

## Selection and validation

`select_source(tuple_of_candidates, exact_query_identity, cutoff=T, source_kind)`
performs no I/O. Exact endpoint/query/kind, proven completion/registration/known-at
at or before T, and `T < expiry` are required. Collection age must be strictly less
than 6h CURRENT, 24h PREVIOUS or 15m TARGET. Boundary equality is stale/expired.
Any local time equal to T requires a supplied durable ordering receipt bound to
T, source identity and retained-content hash. Provider update stays null/UNKNOWN
when absent; when present it cannot exceed completion or rescue late retrieval.
Registration cannot precede completion; known-at cannot precede registration.

Order: latest completion, latest registration, ascending retained-content hash,
then stable source ID (namespace breaks any remaining cross-namespace tie).
Only the chosen version is parsed/validated. Invalid timing, parser, malformed,
wrong-scope, oversized or failed responses never trigger older-response fallback.
Conflicting immutable source identities fail closed, including across bundle
source kinds. Metadata decisions for all supplied candidates are retained; only
the chosen candidate's sanitized content is retained. Exact duplicate candidates
collapse in diagnostics.

## Status and regulation evidence

Mapping version: `FC_API_FOOTBALL_STATUS_V1`.

| Provider status | Canonical state |
| --- | --- |
| NS | NOT_STARTED; sole admitted PREMATCH state |
| 1H, 2H | STARTED |
| FT, AET, PEN | FINISHED |
| PST, CANC | POSTPONED_OR_CANCELLED |
| All others, including TBD | UNKNOWN; rejected |

Evidence: runner `_refreshed_fixture_kickoff`/fixture admission uses NS/TBD;
LIVE policy explicitly identifies 1H/2H; result parser identifies FT/AET/PEN;
existing fixture-status policy identifies PST/CANC. The legacy runner's broader
TBD acceptance is not propagated into Phase A. Other statuses are conservatively
unclassified, not guessed. No external provider-status request was made.

`FC_REGULATION_EVIDENCE_V1` binds competition, season, reviewed minutes, proof
ID/hash and known-at. No reviewed duration field exists in the inspected fixture
path or competition registry. Absent/incomplete/future review evidence remains
REGULATION_UNVERIFIED; proven 90 gives VERIFIED_90; explicit non-90 gives
UNSUPPORTED_REGULATION. Format review equality at T is conservatively unverified
because this minimal format contract supplies no transaction-order receipt.
Previous-season format is independently bound. No registry was populated and
elapsed fixture minutes are never treated as regulation-format proof.

## Retention, fingerprints and replay

The immutable bundle contains expected scope/classification, cutoff, format
assertions, selected source headers, selection decisions, sanitized football
content, validation/normalized-facts hashes, target status mapping version,
Phase A exclusions, and expected input/result/semantic/evidence hashes.
Sanitized content preserves IDs, designated teams, UTC kickoff, status, fulltime
and goals pairs, explicit neutral indication and bounded round designation.
Provider ordering is canonicalized; duplicate multiplicity is retained for the
99-entry bound. Invalid fields retain fixed INVALID markers; arbitrary error text,
credentials, headers, player data, Telegram data, paths and unrelated fields are
not copied. Oversized responses retain count/rejection only, never truncated facts.
Malformed selected sources remain explicit unavailable inputs. Conflicting
football facts and exclusions are retained and deterministically reproduced.

All hashes reuse Phase A canonical JSON/SHA-256 and existing domains.
`FC_SOURCE_BUNDLE_V1` covers source/header/facts/bundle material; Phase A's unchanged
`FC_SNAPSHOT_V1` result fingerprint verifies exact calculations. Query, source
version, relevant timing, format, status and exclusion changes affect evidence
identity. No operational log receipt fields enter the contract. The semantic
manifest remains `f6b27feb0a0352f02390f392cfeea9e200039ad163dad7f764567cc4efe8276a`.

`replay_evidence(bundle)` verifies contract versions, selection decisions,
retained schema/content hashes, exclusions and derived input/result hashes,
then returns the reconstructed Phase A input and result. Missing/corrupt evidence
raises `EvidenceUnavailable` with EVIDENCE_UNAVAILABLE; it cannot contact a provider,
consult latest cache or repair facts. Tests demonstrate cache removal, corrections,
exact replay idempotency and append-only/conflict behavior using a tiny test-only
in-memory ledger. No persistence repository or database schema was introduced.

## Executed verification

```sh
/home/arvis/GoalVisionAI/.venv/bin/python -m pytest -q \
  tests/test_prematch_football_context_sources.py \
  tests/test_prematch_football_context.py \
  tests/test_current_match_intelligence.py::CurrentMatchIntelligenceTests::test_cache_reuse_consumes_no_new_api_calls \
  tests/test_current_match_intelligence.py::CurrentMatchIntelligenceTests::test_network_retrieval_after_run_start_sets_snapshot_cutoff \
  tests/test_lab_v2_shadow.py::test_pi_result_parser_ignores_odds_and_rejects_cross_league
python3 -m compileall -q app/prematch_football_context \
  tests/test_prematch_football_context_sources.py tests/test_prematch_football_context.py
python3 -B -c 'import app.prematch_football_context.sources, app.prematch_football_context.source_adapter, app.prematch_football_context.evidence'
git diff --cached --check
```

Final focused result: **125 passed, 34 subtests passed** (81 new Phase B cases,
41 Phase A cases and three directly relevant existing source/cache cases).
Compile/import: **PASS**, exit 0. Staged diff check: **PASS**, exit 0.
The subprocess audit blocks socket/SQLite access and filesystem writes during
source imports, selection and replay. AST checks prohibit runtime/provider,
Telegram, database and historical-odds dependencies. Existing cache tests use
fakes and temporary test databases only. No broad unrelated suite was run.
An initial test-fixture identity collision was corrected; the selector correctly
rejected two different headers using the same immutable ID.

Coverage includes user cases A–AL and source-side RFC T06/T07/T08/T09/T13/T14/T16/
T19/T20/T32: local-time/expiry/freshness boundaries, exact deterministic choice,
no invalid-latest fallback, legacy unproven metadata, source/season isolation,
status/format rejection, duplicate/conflict/correction retention, regulation-only
scores, complete retained replay, tampering, version/hash sensitivity and inertness.
No predictive-performance or betting-outcome evaluation was performed.

## Limitations and deferred work

- Real cache rows remain ASOF_UNPROVEN; real format coverage is unmeasured.
  Synthetic assertions demonstrate the contract, not production availability.
- Completion, durable timestamps, ordering receipts and reviewed classification/
  format assertions are trusted boundary inputs. Phase B verifies their consistency
  and bindings; it does not manufacture receipts or independently attest storage.
- Typed bundles are retained in memory. Durable serialization/loading, atomic
  append-only production source/snapshot storage, transactions, migrations and
  crash/concurrency behavior belong to Phase C, not this implementation.
- Phase C must expose trustworthy existing-collection completion/registration
  evidence and capture ordering without extra provider traffic, copy facts into
  durable evidence, and implement separately reviewed decision-time orchestration.
- Runtime integration, V2 observations/vectors, coverage infrastructure and all
  research/training/activation remain deferred to their authorized later phases.
  No feature-benefit or production-coverage claim is made.

Confirmed: **zero live provider calls; zero Telegram sends; no Official changes;
no bankroll/statistics changes; LIVE unchanged; no production DB read, migration
or write; no historical bookmaker-odds work; no deployment, merge or push.**
No `.env`, systemd, champion, settlement, odds/staking/publication threshold,
Lab V2 prediction behavior or V1 semantics changed. Stop after the local commit.

PHASE_B_IMPLEMENTED_AND_VERIFIED
