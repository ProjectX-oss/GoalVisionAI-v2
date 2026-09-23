# PREMATCH Football Context V2 — Phase C report

## Pre-edit runtime boundary review

Starting commit: `bf437a91b207fb7f0f6484f9d9946eb10bbd3aea` (accepted Phase B).
Branch: `codex/prematch-football-context-v2-phase-c`.
Worktree: `/home/arvis/GoalVisionAI-prematch-context-v2-phase-c`.
Before editing, recorded the branch, HEAD, empty status, and complete worktree list
of the supplied Phase B checkout. Created this isolated sibling directly from
Phase B. Phase A/B worktrees remain untouched; no split-hardening cherry-pick.

Read AGENTS.md, PRODUCT_RULES.md, ROADMAP.md, TASKS.md, the complete RFC, both
accepted reports, the complete Phase A/B package and their tests before editing.

Only existing runtime file modified (boundary reviewed before editing): `app/football/client.py`.
Its `_get` is the precise transport boundary: `_pace_request` applies existing
quota authorization, pacing and request counting; `await self._client.get(...)`
returns the complete non-streaming response; quota headers are inspected;
`_safe_json` parses a separate payload; legacy response metadata is populated;
`raise_for_status` preserves existing HTTP failure/retry behavior; the response
returns to the caller. `finished_matches` unwraps the JSON response list;
`fixture` returns the JSON envelope.

The PREMATCH consumer is `LabV2ShadowRunner`: `_histories` calls `_fetch` with
`/fixtures(results)`, league, season, FT, last=99; its existing optional previous
season branch uses the same query with season-1. `_exact_review` calls `_fetch`
with `/fixtures?id=fixture_id` and a two-minute cache TTL, bypassing cache.
`_fetch` returns cache hits without transport, otherwise awaits the operation,
reads legacy `_metadata_time` (with runner-clock fallback), appends the existing
cache, and returns. `ShadowEvidenceRepository.append_cache` commits the raw
cache entry without registration proof. `_histories` parses/filters history and
replays the existing Pi adapter; `_evaluate` consumes that history. None of those
files or calculations changed. Date-discovery fixture lists are not exact
target evidence under the accepted Phase B query contract.

Safety proof before modifying the client:

1. Only the transport return exposes completion before parsing/normalization;
   later runner/cache clocks cannot attest it.
2. An optional injected observer defaults to absent. Completion clock and capture
   failures are isolated from provider exception handling; HTTP failures still
   raise/retry exactly as before. Legacy metadata timing stays unchanged.
3. The observer receives the already parsed separate payload and copied query;
   it returns no prediction inputs. No V1/V2 features or model calls are added.
4. The observer has no provider reference, network method, scheduler or fetching
   fallback. Only explicitly scoped existing exact queries are captured.
5. Fake-transport tests cover completion, retries/failure isolation, query
   and response parity, request-count equality, and unchanged PREMATCH calculation.
   Existing client/quota/freshness and directly affected PREMATCH/cache regression
   suites were run. No live transport or Telegram operation is authorized.


## Final scope and files

Phase C is **capture/persistence only**, following the narrower task specification
where it differs from the RFC's original phase outline. Phase A/B contracts,
calculations, fingerprints, selectors and tests are unchanged.

| Exact changed file | Purpose |
| --- | --- |
| `app/football/client.py` | Optional response observer and injected completion clock; 39 added lines, one replaced constructor line |
| `app/prematch_football_context/capture/__init__.py` | Inert persistence subpackage, separate from pure A/B APIs |
| `app/prematch_football_context/capture/adapter.py` | Exact scoped request adapter, Phase B sanitizer reuse, fixed capture statuses/counters |
| `app/prematch_football_context/capture/repository.py` | Immutable source units, post-commit registration, ordered cutoff receipts and verified exact offline loading |
| `app/prematch_football_context/capture/schema.py` | Explicit dedicated-store additive bootstrap, integrity/immutability guards |
| `tests/test_prematch_football_context_capture.py` | Fake-transport/disposable-store capture, replay, failure and runtime parity tests |
| `docs/audits/PREMATCH_FOOTBALL_CONTEXT_V2_PHASE_C_REPORT.md` | This report, including the pre-edit shared-runtime safety review |

No other runtime file changed. The nested persistence subpackage keeps the
accepted pure package's top-level no-database/no-clock contract intact; new
submodule imports have their own side-effect-blocking test. No package initializer
imports persistence or constructs a connection.

## Exact completion and registration semantics

`retrieval_completed_at` is the local UTC timestamp captured immediately after
the complete successful provider HTTP response has been received by GoalVision.
The opt-in observer's clock is sampled on the next statement after the awaited
non-streaming transport returns, before quota parsing or JSON parsing. The
installed HTTPX 0.28.1 source was inspected: `AsyncClient.get` delegates to
`request`/`send`; non-streaming `send` awaits `response.aread()` before returning.
The test also supplies a multi-chunk asynchronous response body and proves that
body completion precedes the clock and parsing follows it.

The client has no trustworthy transport-provided completion timestamp, so an
injected clock is used, defaulting to UTC now only when the observer is present.
Naive/invalid/raising clocks produce no evidence and cannot retry or fail a
successful provider response. Failed HTTP/transport attempts create no successful
source evidence. HTTP-200 provider errors remain provider errors and are not
registered. Malformed/oversized/incomplete successful payloads retain Phase B's
sanitized rejection representation and cannot become valid football inputs.

The old `retrieved_at_utc` metadata remains at its original post-parsing location,
with its original semantics. It is **not** used for the new completion proof.
No request-start, kickoff, provider update, cache timestamp, or analysis clock is
substituted. Request start is not persisted by this minimal boundary; Phase B's
optional `request_started_at` remains null. The streamed fake transport test
independently establishes start < completion. Fixture responses in this audited
path do not supply a trustworthy update timestamp, so provider update remains
null/UNKNOWN. The supplied-data adapter can bind one only when explicitly supplied
and no later than completion.

`registered_at` is the UTC observation associated with the **successful durable
commit of the complete source unit**. It is sampled after that commit returns,
under the acknowledgement append lock. Thus it is a conservative upper bound on
source-commit completion, never a pre-commit wall clock labelled as a commit time.
`known_at = registered_at`. A value earlier than completion or the preceding
receipt clock is rejected, never clamped or fabricated.

SQLite does not provide a trustworthy post-commit timestamp inside the transaction
being committed. The implementation therefore uses a deliberately explicit
source-commit/acknowledgement protocol:

1. Under `BEGIN IMMEDIATE`, atomically insert the canonical source identity,
   logical capture key, and entire sanitized material document; commit with
   `synchronous=FULL` and a durable journal mode.
2. Acquire the append lock, sample the injected clock **after step 1 succeeds**,
   and atomically append the source registration acknowledgement. Return a
   registration only after this second commit succeeds.
3. Every reader requires and verifies both records. A complete source without an
   acknowledgement is unavailable. Read-only loading never repairs it.

The acknowledgement timestamp attests the source commit in step 1; it is **not**
claimed to be a timestamp taken after the acknowledgement's own commit. Equal-time
ordering additionally requires that acknowledgement to have committed before the
cutoff marker. This distinction avoids the endless attempt to persist the exact
post-commit time inside the same commit.

If the source transaction fails, neither facts nor identity exist. If acknowledgement
fails, only a complete, unregistered orphan may remain; no valid registered source
or receipt is returned. An explicit exact retry can acknowledge that new-path
orphan at a fresh later time. It cannot certify it at the earlier attempt's cutoff.
A process interrupted after the acknowledgement actually committed recovers the
original identity/time/order on exact retry. This is a successful durable commit
with lost return, distinct from a failed commit. No cleanup UPDATE/DELETE exists.

## Persistence, identity and order

Dedicated version-one schema:

- `fc_sources(source_id, capture_key, material_json)`: one atomic, immutable source.
  Unique logical capture key; source ID is a canonical content hash.
- `fc_receipts(ordering, event, source_id, observed_at, receipt_hash)`: SOURCE
  acknowledgements and minimal DECISION cutoff markers in one append sequence.
  SOURCE references an existing source with a foreign key and is unique per source;
  DECISION has no source foreign key. No feature snapshot/vector tables exist.

Both tables reject UPDATE and DELETE. Additional INSERT guards reject REPLACE,
including SQLite's implicit-delete behavior. The store has no mutable latest row,
auto-increment semantic identity, deletion, or production database default.
Connections explicitly enable foreign keys and full synchronous durability;
unsupported journal modes and incomplete/wrong schemas fail closed. Writer lock
wait is bounded to 100 ms. Each repository connection is used by its owning thread;
concurrency tests use separate connections, with serialization by SQLite.

The complete material binds `FC_DURABLE_CAPTURE_V1`, `FC_DURABLE_SOURCE_V1`,
API_FOOTBALL, parser version, exact canonical endpoint/query, source role,
completion, expiry, nullable provider update and sanitized content/hash. IDs are
computed through the accepted Phase A canonical serializer and Phase B `digest`;
no new fingerprint algorithm or sanitizer is introduced.

Logical capture identity binds provider, namespace/version/parser, exact query,
role and completion. Exact replay returns the same source and original receipt.
Different content, expiry or provider-time metadata under that logical identity
raises `ImmutableConflict`. A genuinely later completion, including a corrected
score response, creates a new immutable source version; old pins remain replayable.
Equal-precision completions with conflicting material are rejected conservatively,
not ordered using UUIDs or silently overwritten.

Under the same `BEGIN IMMEDIATE` lock, order = last committed order + 1. Cutoff T
is sampled locally under that lock after prior registrations committed; callers
cannot supply a backdated T to `capture_cutoff`. The marker must commit before its
receipt is returned. It records only ordering, not prediction context or features.
`load_cutoff` recovers an exact verified marker after restart without a clock.

`load(source_id, decision=marker)` verifies the durable source/registration and
exact persisted marker, and supplies Phase B `CaptureOrder` only when the source
receipt order is strictly smaller and registration is no later than T. The proof
hash binds both receipt hashes and integer positions; each receipt binds its
source or cutoff. Without a marker, or for a source acknowledged after an equal-time
marker, equality stays ASOF_UNPROVEN. Phase B's equality rules are unchanged.

The ordinary `< T` timestamp proof uses the acknowledged post-source-commit time.
Proof hashes detect accidental/inconsistent evidence changes; they are not a
cryptographic attestation against an administrator rewriting the database and
recomputing every hash. The injected clocks and underlying fsync-capable storage
remain trusted collection boundaries.

## Integration, diagnostics and zero additional calls

The only integration is `FootballClient(response_observer=..., completion_clock=...)`.
The default is absent; no configuration flag, CLI, startup, scheduler or production
composition enables it. The observer receives only the already parsed separate
payload, copied query, endpoint and trustworthy completion timestamp. It receives
no HTTP client, authorization headers or credentials. It cannot change the returned
HTTP response, query strategy, retry/pacing policy, or prediction inputs.

`CaptureAdapter(repository, tuple_of_scopes)` explicitly identifies accepted
queries and CURRENT/PREVIOUS/TARGET roles. No season is guessed from wall time.
History TTLs are six/24 hours; the audited exact-target collector's two-minute TTL
can be supplied (and is used in tests), bounded by Phase B's 15-minute maximum.
Only matching `/fixtures` transport calls are translated into the existing
`/fixtures(results)` history namespace or exact target query. Missing, cache-only,
unscoped and broader date-discovery evidence never triggers another request.

The adapter returns CAPTURED, REPLAY, UNAVAILABLE_CONFLICT,
UNAVAILABLE_CAPTURE_FAILURE, UNAVAILABLE_PROVIDER_ERROR or
UNAVAILABLE_UNSCOPED_QUERY. Fixed status counters are inspectable and retain no
exception text. Unexpected observer/clock failures also increment the client's
`evidence_capture_failures` and emit only `FC_EVIDENCE_CAPTURE_UNAVAILABLE`.
Successful evidence counts/identity/timing/order are available read-only through
`inspect`; `load` exposes source kind, content hash, expiry and proof bindings for
Phase B's as-of verdict. No dashboard or coverage/performance analysis was added.

Failure counters are process-local, not promised durable when the evidence store
itself is failing. Returned failure status and the absence of a valid registered
unit are explicit. Successful captures and receipts survive process restart.
No unnecessary raw API response, provider headers, authorization, player data,
credentials, or raw error text is persisted. No extra raw payload was necessary.

## Verification of unchanged PREMATCH behavior

The integration test uses the real `FootballClient`, fake HTTP transport, real
`LabV2ShadowRunner._fetch`, `_histories`, Pi/history calculations and `_evaluate`.
No prediction calculation is patched. It runs with capture disabled, enabled and
with injected source-commit failure. It compares exact canonical prediction bytes,
analysis evidence, target response, full legacy response metadata, request sequence
and request count: **identical in all three modes, exactly two provider attempts**
(one exact target and one history response). A second history lookup hits the
existing cache and causes zero additional calls/captures. Legacy V1 context input
injection is absent, and the entire old prediction output remains identical.

HTTP failure tests preserve three existing retry attempts; the transient-success
test preserves two attempts and captures only the successful one. Observer,
completion-clock and persistence failures after a successful response never cause
an extra provider attempt. Quota parsing, retry count, discovery, freshness,
request ceilings, exact refresh, cached reuse and PREMATCH behavior are protected
by the directly affected existing regression suites below.

This establishes deterministic response/calculation parity, not a promise of zero
wall-clock overhead. Opt-in SQLite commits add synchronous local I/O; locks have a
bounded wait, while physical filesystem latency is an operational limitation.
There is no background worker or automatic production enablement in this phase.

## Offline replay and format/status boundaries

Synthetic capture → source commit/receipt → close/reopen read-only store → exact
retained candidate → unchanged bounded Phase B selector → `retain_evidence` →
`EvidenceBundle` → `replay_evidence` → Phase A `ContextInput` and `ContextResult`
is tested with provider access configured to raise. All three source kinds are
exercised, including optional prior season, later corrections, unknown format,
verified **synthetic** format and restart recovery at equal precision.

The reconstructed input recalculates to the identical Phase A result and exact
result fingerprint. Repeated retained bundle generation reproduces the exact
bundle/evidence hash. Later corrections cannot change original pins. Corrupted
content, hash, query, capture key, receipt timestamp or receipt hash fail closed.
No provider call can repair missing/corrupt evidence.

No format registry is populated. With no separately reviewed format assertion,
Phase B returns REGULATION_UNVERIFIED and all dependent values remain missing.
Tests supplying reviewed-looking 90-minute assertions are explicitly synthetic;
they make no real coverage claim. The accepted NS-only eligibility mapping is
unchanged: observed TBD/started/finished/postponed/cancelled/unknown statuses are
retained but rejected by Phase B replay for PREMATCH eligibility.

Legacy `legacy_cache_candidate` still leaves completion/registration null and
returns ASOF_UNPROVEN. The store has no legacy reader or migration/backfill path.
No old `retrieved_at`, rowid, file time, provider update or cache order is certified.

## Schema verification

This is a new isolated database, using the adjacent isolated repository's explicit
SQLite schema-creation approach. There is **no shared production migration** and
no modification to `app/database/migrations.py`. The local schema bootstrap is
versioned: empty version 0 → version 1, atomically; reopening version 1 verifies
rather than rewrites evidence. It refuses unrelated or incomplete databases.

Disposable tests verify fresh creation, pre-existing empty-store upgrade,
repeat initialization with retained data, exact replay, UPDATE/DELETE/REPLACE
guards, FK insertion rejection, `foreign_key_check` empty, `integrity_check=ok`,
full synchronous mode, read-only no-create/no-migration behavior, interrupted
source and acknowledgement commits, insert-trigger rollback and concurrent exact
replay. Only pytest temporary databases were opened for this work.

## Exact executed tests and checks

All commands below ran from this isolated worktree. Python test interpreter:
`/home/arvis/GoalVisionAI/.venv/bin/python`.

```sh
/home/arvis/GoalVisionAI/.venv/bin/python -m pytest -q \
  tests/test_prematch_football_context_capture.py \
  tests/test_prematch_football_context_sources.py \
  tests/test_prematch_football_context.py \
  tests/test_api_football_adaptive_discovery.py \
  tests/test_api_football_odds_freshness.py \
  tests/test_api_football_discovery_efficiency.py \
  tests/test_lab_v2_shadow.py tests/test_lab_v2_prematch.py \
  tests/test_prematch_production_integration.py \
  tests/test_current_match_intelligence.py::CurrentMatchIntelligenceTests::test_cache_reuse_consumes_no_new_api_calls \
  tests/test_current_match_intelligence.py::CurrentMatchIntelligenceTests::test_network_retrieval_after_run_start_sets_snapshot_cutoff \
  tests/test_current_odds_forward_test.py::ForwardTestFoundationTests::test_api_football_client_is_network_inert_until_explicit_call

python3 -m compileall -q app/prematch_football_context app/football/client.py \
  tests/test_prematch_football_context_capture.py
/home/arvis/GoalVisionAI/.venv/bin/python -B -c \
  'import app.football.client, app.prematch_football_context.capture.adapter, app.prematch_football_context.capture.repository, app.prematch_football_context.capture.schema'
git diff --check
git diff --cached --check
```

Final combined result: **340 passed, 42 subtests passed**: 56 Phase C, 81 Phase B,
41 Phase A, 161 affected regressions and one client-inertness test. Compile/import
and working/staged whitespace checks passed, exit 0. This is the targeted suite,
not the broad full repository suite. Only one shared runtime file changed, and
focused provider plus PREMATCH regressions resolved the affected behavior.

Earlier incremental runs passed 46 and 55 Phase C cases, the
combined A/B/C development set (174 tests, 34 subtests), affected regressions
(161 tests, 8 subtests), and client startup (one test). The final combined command
above supersedes those development counts. It was rerun after adding a client
failure-isolation guard: even a broken logging handler must not fail or retry a
successful provider response. Its test injects both a sidecar TransportError and
a failing diagnostic handler, and still receives the unchanged successful response
with exactly one attempt.

Development corrections: the parity test initially passed integer dictionary keys
to Phase A's string-key-only canonical serializer; it now serializes the exact
fixture's analysis document. One manually selected startup test initially used the
wrong unittest class name and collected no tests; the corrected selection passed.
Neither issue required changing existing prediction behavior or Phase A/B code.

| Required cases | Executed evidence |
| --- | --- |
| A–D | Streamed fake body, injected clock, request-start ordering, failed HTTP/transport/application responses |
| E–I | Sanitized persistence, post-commit observation, backwards-clock rejection, commit/insert failures, unavailable orphans and explicit retry |
| J–Q | Exact/concurrent replay, conflicts/corrections, UPDATE/DELETE/REPLACE rejection, fresh/empty-upgrade/reopen/FK/integrity tests |
| R–T | Secret exclusion, no network dependency, identical real PREMATCH request sequence/count with capture off/on/failing |
| U–AA | Reopened read-only exact loading, bounded selection, retained bundle, exact Phase A replay/hash, corruption, proven/unproven equality and rolled-back markers |
| AB–AF | Unmodified legacy ASOF_UNPROVEN adapter, full existing-output parity, no V1 injection, retained status/NS-only admission and unknown regulation |
| AG–AL | Fake-only transport and blocked real sockets; isolated dependency/table checks; unchanged product paths and affected PREMATCH regressions |
| AM–AN | Imports audited with DB/network/writes blocked, default observer absent, no automatic clock/store/capture at startup |

## Confirmations and deferred work

- **Zero live API requests**. New tests use HTTPX MockTransport and block actual
  HTTP transport/socket connects; existing targeted suites use fakes.
- **Zero Telegram sends**. No sender/transport was added or invoked.
- **Official unchanged; bankroll/statistics unchanged; settlement unchanged.**
- **LIVE unchanged**; no enablement or runtime composition change.
- No historical bookmaker-odds code/path or acquisition/backtest work.
- No legacy backfill, V1 field population, feature vector, training/calibration,
  research, challenger/champion changes, model activation or predictive-benefit claim.
- No `.env`, credentials, production DB, systemd unit/timer, service, quota policy,
  publication/staking/odds/confidence threshold or source query strategy changes.
- No push, merge, deploy or production collection enablement. Phase A/B worktrees
  were rechecked and remain clean and untouched.

Limitations: capture requires explicit Test-only composition with a trusted UTC
clock and exact scope/expiry plan. No automatic discovery of scopes or runtime
cutoff wiring is added. Cache-only/absent exact target requests remain unavailable.
Real format coverage is still unmeasured/unverified. Failure counters are local to
the current process. Complete unacknowledged orphans remain retained and unavailable;
there is no cleanup worker. Hashes prove consistent retained representation, not
resistance to privileged database rewriting. Source capture adds opt-in disk latency.

Exactly deferred to Phase D: frozen V2 feature projection; prediction-input/context
snapshot orchestration and persisted links to first canonical opportunities;
using the same future frozen snapshot for inference/observation; explicit V1/V2
vector dispatch and frozen learning evidence. No part of those is implemented.
Registry/model integration, real coverage collection/research, challenger work and
production enablement require their separately authorized later phases.

Final commit SHA: the commit containing this report, resolved exactly by:

```sh
git log -1 --format=%H -- docs/audits/PREMATCH_FOOTBALL_CONTEXT_V2_PHASE_C_REPORT.md
```

The final handoff supplies its literal SHA. As in the accepted Phase A/B reports,
a commit cannot embed its own resulting SHA without changing that SHA. This report
and all implementation/test files are committed together on the branch above.

PHASE_C_IMPLEMENTED_AND_VERIFIED
