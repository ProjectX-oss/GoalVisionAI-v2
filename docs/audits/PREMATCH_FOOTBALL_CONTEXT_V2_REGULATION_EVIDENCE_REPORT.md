# PREMATCH Football Context V2 regulation evidence audit

## Executive verdict

**NO_ACCEPTABLE_EXISTING_PROOF**

Base: `7359876` (Harden prematch V2 target evidence capture and readiness run
accounting). Branch: `codex/prematch-football-context-v2-regulation-evidence`.

No explicit real `VERIFIED_90` source was found in the inspected runtime/evidence
chain. No resolver, registry entries, persistence, provider requests or runtime
behavior were added. The change contains only tests and this report. Phase E
remains unauthorized (`phase_e_authorized = false`).

The current chain can retain an assertion about format; it cannot establish its
truth from the already available fields. A completed immutable fixture response
proves which fixture facts were observed, not the competition's regulation rules.
The correct runtime result remains `REGULATION_UNVERIFIED`, with all seven V2
features null when that reason applies. TARGET availability is a separate issue
and was not changed.

## Scope and evidence examined

Inspected the accepted code, source contracts and Phase A/B/C/D reports, RFC,
readiness composition, provider client, candidate metadata, classifier/review
registry, capability parser and cache paths. Read the local JSON metadata caches
`/home/arvis/GoalVisionAI/var/lab_v2/capabilities.json` (1,239 records) and
`/home/arvis/GoalVisionAI/var/api_football_capabilities.json` (1,238 records) for
field inventory only. Neither contains a regulation/duration/minutes field.
Their existence today is not evidence of availability at a historical cutoff.

No production database or real readiness database was opened. No public internet,
real API-Football traffic, Telegram, historical bookmaker odds, deployment,
workers or scheduling were used. The original workspace was dirty; all writes
were confined to an isolated worktree and disposable test stores. Real snapshot
counts below are operator-supplied evidence, not a new measurement or independent
reproduction of those stores.

## Source-by-source audit

In this table, “prospective” means the path can observe facts during a new run;
it does not establish that a particular old decision had those facts. “Bind”
means immutable offline evidence under the existing V2 chain, not merely a JSON
hash. Every row requires zero additional requests to inspect already held data.

| Source and exact provenance | Exact candidate fields | Prospective / before cutoff | Explicit duration / inference only | Competition-season stability | Immutable binding | Additional requests | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Existing fixture responses: `app/football/client.py`, `_get`, `fixtures_by_date`, `fixtures_between` | `response[].fixture.{id,date,status.short,status.elapsed,periods.first,periods.second}`, `league.{id,season,name,type,round}`, `score.{fulltime,extratime,penalty}`, `goals` | Prospective HTTP completion hook exists; discovery response alone is not admitted TARGET ordering proof | No explicit duration rule. Status/elapsed/period starts/scores describe a fixture; names and round labels only suggest context | IDs bind a fixture to a season; match timing does not establish a season-wide format | Phase C does not turn date/range discovery into exact TARGET evidence; its sanitizer retains only allowlisted facts | 0 | INSUFFICIENT |
| Exact TARGET: `FootballClient.fixture`, readiness `capture`, `CaptureAdapter` | Same fixture fields, exact `/fixtures?id=<fixture_id>`; completion, registration, durable cutoff receipt | Yes, only if complete acknowledged source precedes decision marker and satisfies as-of/TTL | No duration field with attested semantics. NS proves only accepted pre-match state | Exact fixture/league/season binding, no format rule | Yes for sanitized fixture facts and exact query; no format proof to bind | 0 | INSUFFICIENT |
| CURRENT finished history: `FootballClient.finished_matches`, runner `_histories` | `/fixtures` league/season/status=FT/last=99; `score.fulltime.{home,away}`, `goals.{home,away}`, `fixture.status.short` | Yes for newly captured exact response with Phase C receipt; legacy cache path alone unproven | FT is not “90 minutes”. Neither scores nor elapsed=90 prove competition regulation | Correct competition-season fixture scope only | Yes for sanitized facts, independent of missing format | 0 | INSUFFICIENT |
| PREVIOUS history already obtained by existing runner | Same fields and query with explicit previous season | Only if already captured and ordered before cutoff; no new history request authorized | Same missing duration semantics as CURRENT | Current proof must not be copied into previous season | Separate exact source and separate `previous_format` required | 0 | INSUFFICIENT |
| Candidate metadata: runner `_fixture_rows_with_evidence`, tracking | `provider_metadata.{league,fixture,teams}`; `competition_profile`, `classification_version`, `classification_reason`, `classification_fingerprint`, `age_category`, `flags`, country | Constructed prospectively; candidate existence/hash alone does not supply durable format observation/review time | No attested rule; professional/senior/women/youth/name/category cannot prove duration | Classification scope is not a reviewed season format | Classification is copied into V2 Binding; raw metadata is not a format evidence channel | 0 | INSUFFICIENT |
| Reviewed competition registry: `competition_registry.py`, `reviewed_competitions.json` | `provider`, `league_id`, `country`, `name`, `profile`, `gender`, `age_group`, `professional_status`, `competition_type`, `tier`, `review_reason`, `review_source`, `registry_version` | Static reviewed classification; no per-format observation/review timestamp or historical cutoff attestation | No duration. Review sources concern classifier migration/provider catalogue, not competition regulations | Key is provider+league with country guard, not competition+season validity | Registry/classification fingerprints exist; reinterpreting them as duration evidence would change their meaning | 0 | INSUFFICIENT |
| Name-only local list: `app/core/leagues.py:TOP_LEAGUES`; classifier `profiles.py` patterns/fallback | Names, profile patterns, fallback capability flags | Static policy, not observed season rule | Name/profile inference only | No season-bound format | No regulation review provenance | 0 | UNSAFE if used as proof |
| Capability cache: `lab_v2_shadow/capability.py`, local Lab JSON | `league_id`, `season`, country, competition name/type, season start/end, fixtures/standings/lineups/statistics/injuries/predictions/odds flags, tier/reasons; retrieval/expiry/content fingerprint | Prospective metadata possible; JSON timestamps alone do not prove Phase C ordering for historical decisions | Coverage describes provider services. Season dates are not match duration | Season keyed coverage, not format validity | Fingerprinted replaceable JSON; no durable format review receipt/payload | 0 | INSUFFICIENT |
| Already-fetched league/season catalogue: runner `_capabilities`; `current_odds_forward_test/provider.py` and local API capability JSON | `/leagues?current=true`: `league.{id,name,type}`, `country.name`, `seasons[].{year,current,start,end,coverage}`; legacy cache also has source provenance | Existing catalogue may be consumed offline; no claim its current copy predates old cutoff | No explicit regulation-duration semantics in inspected parser/retained catalogue | Current-year filter cannot prove previous season; coverage interval is not rule validity | Not an admitted Phase C query; no format payload/receipt | 0 to inspect; a refresh would add traffic and is forbidden | INSUFFICIENT |
| Legacy raw runtime cache: `lab_v2_shadow/repository.py`, `_fetch`; adjacent current-match-intelligence cache | endpoint, query JSON/hash, retrieved timestamp, expiry, payload JSON/hash | Old retrieval timestamp has ambiguous collector provenance and no durable predecision registration receipt | A plausible arbitrary duration key would remain unattested; no approved schema/source semantics | Query scope alone insufficient | `legacy_cache_candidate` leaves completion/registration/known-at null: `ASOF_UNPROVEN` | 0 | UNSAFE if promoted to proof |
| Phase B `source_adapter.py:FormatEvidence`, Phase D retained binding | `competition_id`, `season`, `minutes`, `proof_id`, `proof_hash`, `known_at`, `version` | Supports explicit trusted supplied assertions, strictly before cutoff | Can represent reviewed duration; does not discover, authenticate or review a source | Binding checks exact current and previous season independently | Assertion retained in bundle/snapshot and fingerprinted; referenced source document not stored by this type | 0 | NOT_AVAILABLE as a real populated proof source |
| Current readiness `scope_binding` | `FormatEvidence(league, season)` and `FormatEvidence(league, season-1)` | Constructed for new decision | Explicitly unverified; no guessed minutes/proof/time | Correct season scope without claimed duration | Immutable missingness in snapshot | 0 | INSUFFICIENT |

No claim is made about every possible undocumented provider field or uninspected
raw production payload. Such material is not qualifying proof merely because it
might exist. The accepted retained schema and audited runtime supply no attested
competition-season regulation field; no external provider schema was consulted.

## Minimum acceptable proof and existing contract limits

There is **no newly accepted real proof contract/source** in this change. The
following is the minimum admission requirement for a separately reviewed future
source, not an implemented resolver or permission to populate a registry:

- Provider namespace and exact `competition_id` and `season`.
- An explicit positive integer `regulation_minutes`, with source semantics that
  identify regulation duration, separately from extra time and match elapsed time.
- Source type (response-derived or reviewed static document), immutable source
  identity, content fingerprint, and retained canonical payload/document excerpt
  sufficient to reproduce the actual duration claim offline. A hash of an absent
  document is not independently reproducible evidence of its meaning.
- Observation/retrieval completion and durable registration before the decision
  cutoff; do not substitute kickoff, publication date, cache TTL or request start.
  Equal-time review cannot pass the existing `FormatEvidence` contract.
- For static evidence: reliable source document identity/version, exact supporting
  statement, explicit reviewer identity/review time and effective competition-season
  validity. No implicit cross-season validity. Review time cannot be backdated to
  the source document's publication time.
- Deterministic evidence fingerprint over scope, duration, source type/identity,
  retained content commitment, timestamps, review and validity metadata. Bind the
  proof into the immutable decision evidence with exact replay/conflict detection.
- Missing, late, wrong-scope, unauthenticated or conflicting valid evidence must
  fail closed. Proven non-90 is `UNSUPPORTED_REGULATION`; explicit valid 90 is
  `VERIFIED_90`; no qualifying proof is `REGULATION_UNVERIFIED`.

The existing `FC_REGULATION_EVIDENCE_V1` is a **trusted supplied assertion**:
`proof_hash` pins a claimed reviewed document; `known_at < cutoff` is required;
`Binding` enforces exact competition and season. `FormatEvidence.verdict()` alone
does not validate target scope. `digest(format)` becomes the regulation evidence
fingerprint, and the assertion is included in retained bundle and snapshot hashes.
It has no source-type, reviewer, validity-interval or retained review-document
fields and no multi-source reconciliation. Tests using `SYNTHETIC90`/synthetic
hashes prove plumbing only. They are not real proof and must never populate a
runtime registry. Do not bypass the admission requirements by manually fabricating
these assertion fields. No changes to this accepted contract were justified here.

An earlier supplied immutable assertion can be reused for later decisions within
its same scope under existing no-expiry assertion semantics. That test does not
authorize indefinite reuse of a future reviewed registry entry: its explicit
validity contract would also have to pass. Current and previous seasons remain
separate. No format resolver or conflict-selection policy was implemented because
there is no admissible real source to resolve.

## Rejected inference paths

FT/NS/AET/PEN identifies status, not competition duration. Elapsed=90 describes a
clock observation; period start timestamps do not prove two regulation halves or
their lengths. Fulltime scores describe a result, not a rule. Missing extra-time
scores do not prove 90 minutes. Senior/professional/NPFL/league/category/name,
gender, roster class and provider capability tier do not prove duration. A season's
calendar start/end does not describe match length. A checksum proves consistency,
not truth, source authority, predecision existence or applicability to other
seasons. Later learning cannot upgrade a historical snapshot.

## AET/PEN safety

Format and score evidence remain independent. With synthetic verified 90-minute
format, AET/PEN rows lacking explicit `score.fulltime` remain excluded with
`INVALID_REGULATION_SCORE_PAIR`, even when final `goals` are 4–3. With explicit
regulation fulltime 1–1, the calculation uses 1–1, not 4–3. The existing FT-only
fallback in `calculations._pair` is unchanged. No score is fabricated by format
verification. New tests exercise both statuses with and without fulltime pairs;
existing Phase A and readiness-hardening tests cover the same boundary.

## Persistence, reproduction and historical preservation

No new storage or migration is necessary for an audit with no acceptable proof.
Existing Phase C sources/receipts and Phase D snapshots remain explicitly
initialized, isolated, append-only and offline-reproducible. Exact replay is
idempotent; changed format assertions for the same immutable opportunity conflict.
Bundle tampering invalidates its hash. Existing tests cover update/delete/replace,
missing evidence, locked stores and corruption. No new runtime default path exists.
A future review would need to decide how to retain the actual format source and
its review provenance; the fixture sanitizer must not be silently repurposed.

**Existing real readiness evidence was not mutated, rewritten, backfilled or
repaired.** No real evidence DB was opened and no cycle/report was run against it.
The new historical-preservation test uses a disposable synthetic snapshot: after
later 90/80 assertions and failed replacements, original bytes, null projection
and offline reproduction remain unchanged. This tests the mechanism and does not
claim a fresh verification of the operator's real snapshot.

Operator-supplied accepted readiness remains: `INSUFFICIENT_SAMPLE`; 1 completed
run; 0 incomplete evidence-window runs; `VERIFIED_PERSISTED_RUNS` denominator;
`integrity_failures = {}`; 8 eligible attempts; CURRENT 8/8 SELECTED; TARGET 1/8
SELECTED; 1 immutable snapshot; reproduction 1/1 VERIFIED; all seven values null
with `REGULATION_UNVERIFIED`; `VERIFIED_90 = 0`; Phase E unauthorized. Those counts
are not replaced by synthetic test results or older report counts.

## Provider traffic and behavior isolation

The new fake-transport test runs the real `FootballClient` with observation off
and on. Both sequences are exactly:

1. `/fixtures?id=9999`
2. `/fixtures?last=99&league=10&season=2026&status=FT`

**2 requests off, 2 requests on; additional requests = 0.** Repeated format checks,
selection, snapshot assembly, offline reproduction and read-only coverage add zero
requests. There is no new resolver. No `/leagues`, fallback, retry or broader
query was added. Existing full runner/coordinator parity tests additionally compare
request sequences/counts, full reports, canonical opportunities, V1 feature inputs
and champions across observation and failure modes. Production and LIVE hooks,
probabilities, selection, publication, learning and the nine legacy V1 fields
remain unchanged. All `app/` files are identical to the accepted base.

## Tests and acceptance coverage

New module: `tests/test_prematch_football_context_regulation_evidence.py`.
Standalone execution: **37 passed** in 1.00s. Combined focused and adjacent
suite: **502 passed, 42 subtests passed** in 57.86s, with no failures or skips.
The 37 new tests are included in the 502; the standalone run is not additional
unique coverage. `compileall` for the new test module and `git diff --check`
also passed.
All data are synthetic, transports mocked, stores disposable. The combined runner
blocks `socket.socket.connect`, `socket.create_connection`, and
`httpx.AsyncHTTPTransport.handle_async_request` before invoking pytest. No real
network access is permitted. No prediction logic changed, so no new backtest or
historical-odds acquisition was necessary.

| Requested cases | Deterministic coverage / honest limitation |
| --- | --- |
| 1–3: valid 90, non-90, absent | Existing `test_format_proof_lineage_survives_exact_snapshot_reproduction` and Phase B explicit-format cases: supplied synthetic reviewed assertions only |
| 4–5: category/name/FT | New all-profile and fixture-hint tests; FT rows with no format proof keep seven nulls |
| 6–8: current/previous and wrong scope | New current-does-not-upgrade-previous and four scope mismatch cases |
| 9: cutoff | New before/equal/after cutoff and later same-scope reuse; existing durable source ordering tests |
| 10: conflict | New same-opportunity 90/80 assertion replacements rejected; existing immutable source conflict tests. Independent format-proof aggregation is NOT implemented/tested; no acceptable sources exist |
| 11–13: replay, tamper, offline | New exact append replay, four altered format fields, original snapshot reproduction; existing Phase B/C/D corruption/restart tests |
| 14–16: AET/PEN separation | New four format-versus-score cases and existing hardening/Phase A tests |
| 17–18: request parity/zero resolution traffic | New exact two-request off/on test; existing complete cycle parity; no resolver added |
| 19: historical snapshot | New synthetic immutable-preservation regression; actual evidence untouched, not newly reproduced |
| 20–21: no V1/model/selection/publication effects | Existing `test_real_client_controlled_cycle_exact_parity` and Phase D full-runner parity, unchanged runtime diff |
| 22: read-only report | New byte comparison before/after coverage; existing read-only report/verify/diagnostics tests |
| 23: missing/locked store | Existing readiness mode parity and Phase C/D missing/lock failure tests |
| 24: unchanged fingerprints | Existing literal canonical/semantic/result goldens and exact A/B/C/D replay; all runtime/contract/schema files unchanged |

Executed combined command: the Python interpreter
`/home/arvis/GoalVisionAI/.venv/bin/python`, with the three network guards above,
then `pytest.main(['-q', ...])` with these exact paths:

```text
tests/test_prematch_football_context_regulation_evidence.py
tests/test_prematch_football_context_readiness_hardening.py
tests/test_prematch_football_context_readiness.py
tests/test_prematch_football_context_snapshot.py
tests/test_prematch_football_context_capture.py
tests/test_prematch_football_context_sources.py
tests/test_prematch_football_context.py
tests/test_api_football_adaptive_discovery.py
tests/test_api_football_odds_freshness.py
tests/test_api_football_discovery_efficiency.py
tests/test_lab_v2_shadow.py
tests/test_lab_v2_prematch.py
tests/test_prematch_production_integration.py
```

## Changed files and next step

- `docs/audits/PREMATCH_FOOTBALL_CONTEXT_V2_REGULATION_EVIDENCE_REPORT.md`: audit,
  proof requirements, limitations, coverage and next-step record.
- `tests/test_prematch_football_context_regulation_evidence.py`: 37 focused offline
  regressions; no application changes.

Keep regulation unverified and preserve the existing real snapshot. The exact next
step is a separately authorized **source review**: obtain an authoritative explicit
competition-season regulation statement with retained content, observation/review
time, reviewer provenance and effective validity. If no such evidence can be
supplied, stop. If it can, review a prospective immutable proof contract and its
storage/conflict semantics before implementing a resolver. Do not populate a static
registry from football conventions, reinterpret classifier assertions, add provider
traffic, or retroactively upgrade old decisions. Public-internet research requires
separate authorization. Phase E remains unauthorized. No merge, push or deployment.
