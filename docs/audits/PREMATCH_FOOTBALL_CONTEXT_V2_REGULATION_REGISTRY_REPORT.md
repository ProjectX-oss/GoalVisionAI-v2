# PREMATCH Football Context V2: reviewed regulation registry foundation

Starting point: `df9df0ee3e0de81d0ea35610552990d7996dc12c`.
Branch: `codex/prematch-football-context-v2-regulation-registry`.

The accepted audit conclusion remains **NO_ACCEPTABLE_EXISTING_PROOF**. Existing
runtime/API-Football metadata still does not prove competition-season duration.
This change provides a dormant, operator-controlled evidence store and an offline
bridge. It does not wire the registry into prediction or readiness observation.

**Phase E remains unauthorized.** No real regulation records were added. No real
competition currently resolves `VERIFIED_90` from evidence delivered by this task.
All positive examples exist only in synthetic tests, using explicitly fictional
text, mappings, reviewers and document paths. They are not seed evidence.

## Architecture and authority

The new `app/prematch_football_context/regulation_registry` package contains frozen
contracts, isolated persistence, resolution/bridge services and a manual CLI.
It depends on the accepted canonical serialization and `FormatEvidence` contract.
There are no imports of this package in existing application runtime modules.

The authority hierarchy is explicit:

1. `ORGANIZER_REGULATIONS`: manually reviewed competition-specific regulations.
2. `IFAB_BASE_LAW`: retained supporting provenance only, never sufficient to
   verify a competition or to override competition-specific duration.

An official URL alone is insufficient. Import requires all retained evidence,
reviewer, timing, scope, mapping and integrity fields. A deliberately small,
code-reviewed organizer/host admission policy currently contains UEFA/uefa.com,
FIFA/fifa.com, IFAB/theifab.com, THE_FA/thefa.com and DFB/dfb.de. This list is an
admission constraint, **not evidence that any document establishes 90 minutes**.
HTTPS document paths on those hosts or their subdomains are required; credentials,
query strings, fragments, third-party hosts and lookalike host suffixes are
rejected. Adding another organizer requires a reviewed policy/code change.
IFAB cannot be relabeled as organizer regulations, or vice versa.

The operator remains responsible for examining the authoritative document,
confirming category/edition applicability, mapping the exact provider competition
ID, and recording the actual duration claim. No automatic trust decision,
website fetch, source discovery or scraping is implemented. The validator checks
structure, policy and integrity; it cannot authenticate a human review or prove
that arbitrary natural-language statements are true.

## Evidence contract and bounded retained content

`ReviewedCompetitionRegulation`, version `FC_V2_REVIEWED_REGULATION_V1`, requires:

| Fields | Meaning |
| --- | --- |
| `review_id` | Stable immutable review identity, independent of its content hash |
| `provider`, `competition_id`, `season` | Exact provider competition and season; currently API_FOOTBALL only |
| `regulation_minutes` | Explicit positive integer duration claim reviewed by the operator |
| `organizer`, `competition_name` | Reviewed organizer identity and human-readable competition identity |
| `source_type`, `source_title`, `source_url`, `source_edition` | Authority category and exact document provenance |
| `source_effective_from`, `source_effective_until` | UTC decision applicability interval, inclusive start/exclusive end |
| `reviewed_statement` | Explicit reviewed regulation-duration claim, including relevant qualifications |
| `retained_source_content` | Frozen document identity, article/section, short extract, applicability statement and retained provider-mapping evidence summary |
| `source_content_sha256` | Hash of the full retained source object |
| `reviewer`, `reviewed_at` | Accountable operator identity and actual timezone-aware review time |
| `validity_start`, `validity_end` | Inclusive provider season labels, both null for exact-season-only evidence |
| `evidence_version`, `evidence_fingerprint` | Version and complete canonical record fingerprint |

Every field is required in JSON, including explicit null season interval fields.
No unavailable-source checksum substitutes for retained content. The mapping
summary must identify the supplied mapping material and explain how it proves the
provider ID; a name resemblance is insufficient. The applicability summary must
explain the reviewed competition/category/edition and any declared multi-season
coverage. The reviewed statement must identify regulation duration, excluding
extra time and penalties.

Text is bounded to 1,000 characters per field. The retained source extract is
additionally capped at 25 whitespace-separated words. Total import size is capped
at 32 KiB. Operators must still respect cumulative quotation limits and applicable
reuse permissions; this numeric guard does not grant copyright permission.
Whole websites, downloaded arbitrary payloads and URL-only records are excluded.
The CLI neither downloads nor automatically computes a trust declaration.

## Persistence and fingerprints

Initialization requires an explicit new file path. Exclusive creation rejects
*every existing file*, including an empty or already initialized file. There is
no default production path, startup initialization or migration of an existing
store. Normal repository access uses SQLite `mode=ro`; manual import explicitly
uses `mode=rw`. Connections use a bounded 0.1-second lock wait.

The isolated schema contains one `fc_v2_reviewed_regulations` table. Review ID is
the primary key, fingerprint is unique, and the full canonical document is
retained in the same row. There are no external references requiring foreign
keys. Foreign-key enforcement/checks are enabled nevertheless. Exact schema SQL,
schema version, SQLite integrity, indexed identity, canonical document and all
hashes are checked before evidence is resolved.

UPDATE and DELETE triggers reject mutation. A BEFORE INSERT duplicate guard
blocks REPLACE and INSERT OR REPLACE even when SQLite recursive triggers are off.
Service imports use one immediate transaction: exact replay returns the same
record; changed content under the same review ID raises an immutable conflict.
A separate review ID preserves a distinct review rather than overwriting history.

All fingerprints use `SHA256(ASCII(domain) + newline + canonical_UTF8_JSON)`:

- Source domain: `FC_V2_REGULATION_SOURCE_V1`, covering all retained source fields.
- Record domain: `FC_V2_REVIEWED_REGULATION_V1`, covering all record fields except
  `evidence_fingerprint`, including the source hash and all review metadata.
- Resolution domain: `FC_V2_REGULATION_RESOLUTION_V1`, covering exact query,
  cutoff, outcome, reason and full ordered applicable records.

Canonical JSON reuses the accepted sorted-key, compact, NFC serializer with UTC
microsecond timestamps. Non-NFC review text is rejected rather than silently
changing retained wording. Duplicate JSON keys and malformed/incomplete imports
are rejected. Schema guards are a database application boundary, not protection
against a privileged actor replacing a database and recomputing every hash.
Hashes are integrity identifiers, not signatures or authenticated timestamps.

## Resolution, conflict and as-of semantics

Only records matching provider and competition ID can apply. Default scope is
exactly the declared season. Both explicit interval endpoints are required to
cover other seasons; the anchor season must lie inside that interval. Neither a
name, professional/senior profile, FT status nor IFAB baseline establishes scope
or duration. No cross-competition or implicit cross-season propagation exists.

`reviewed_at` must be **strictly earlier** than the decision cutoff. Equal-time
reviews are excluded. The cutoff must also be inside the source effective
interval. Future/expired/wrong-scope evidence is excluded before conflict checks.
The resolver has no clock dependency; the caller supplies the decision cutoff.

| Applicable competition authority records | Controlled outcome |
| --- | --- |
| All explicitly declare 90 | `VERIFIED_90` |
| All declare one equal non-90 duration | `UNSUPPORTED_REGULATION` |
| None, including IFAB-only evidence | `REGULATION_UNVERIFIED` |
| Distinct simultaneously valid durations | `CONFLICTING_REGULATION_EVIDENCE` |

All applicable records are retained in deterministic review-ID order. Equivalent
reviews are not discarded. There is no newest-source, preferred-organizer or
convenient-source conflict override. Supporting IFAB evidence cannot override a
reviewed organizer's non-90 duration. Missing, locked, corrupt or schema-invalid
stores produce `REGULATION_UNVERIFIED` with an unavailable/invalid reason; runtime
does not create, repair or fetch anything.

T1 before review T2 remains unverified; T3 after T2 can use it. Existing readiness
snapshots are never reopened or modified by the registry. Their immutable
append/reproduction contracts remain intact, including rejection of replacement
attempts. Import relies on honest actual review timestamps: backdated operator
attestations cannot be authenticated by this offline foundation. Historical
snapshots remain authoritative regardless of later imported declarations.

## Phase B bridge and AET/PEN

`format_evidence(resolution, cutoff=...)` accepts only the exact resolved cutoff.
A verified resolution produces the existing `FormatEvidence` with minutes 90;
a reviewed non-90 resolution uses its existing unsupported path. Missing and
conflicting results produce an unverified `FormatEvidence`. Successful proof ID
and proof hash pin the complete resolution fingerprint; `known_at` is the latest
qualifying organizer review timestamp. The bridge rechecks scope, duration
agreement and review timing rather than accepting an asserted verdict alone.

Retain the resolution export alongside the resulting Phase B bundle and preserve
the registry file. The export includes the full records/content needed to
reproduce the proof hash offline. The existing `FormatEvidence` contract has no
expiry or registry-conflict field: it is a decision-bound projection, not a
reusable cache for new decisions. Resolve again for each different cutoff; never
reuse a prior bridge to bypass expiry or a newly visible conflict.

No seven-feature formula, nine-field V1 projection or model vector changed.
Format evidence proves duration only. AET/PEN still require explicit regulation
full-time scores; post-extra-time/penalty `goals` cannot be used as those scores.
Tests exercise both absent and supplied regulation score pairs through the bridge.

## Manual operator CLI

Use a Python environment with the project dependencies. Every command is offline:

```bash
python -m app.prematch_football_context.regulation_registry init --db /isolated/new-regulations.db
python -m app.prematch_football_context.regulation_registry validate reviewed-record.json
python -m app.prematch_football_context.regulation_registry import --db /isolated/new-regulations.db reviewed-record.json
python -m app.prematch_football_context.regulation_registry inspect --db /isolated/new-regulations.db --review-id REVIEW_ID
python -m app.prematch_football_context.regulation_registry resolve --db /isolated/new-regulations.db --provider API_FOOTBALL --competition-id 2 --season 2026 --cutoff 2026-09-25T12:00:00Z
python -m app.prematch_football_context.regulation_registry verify --db /isolated/new-regulations.db
```

The example competition ID is CLI syntax only, not a verified mapping or entry.
Prepare the complete reviewed JSON manually using the contract above. Compute
`source_content_sha256` with `contracts.digest` and its source domain, then compute
`evidence_fingerprint` with the record version domain over every other field.
Validation never silently repairs missing hashes or incomplete reviews. Inspect
prints the full canonical record; resolve prints the full scoped resolution.
Validation/import/inspection/integrity failures return exit status 1. Resolve
returns its controlled verdict as JSON, including unverified failures; consumers
must check that verdict rather than treating exit status 0 as verified evidence.

## Verification and safety

Synthetic tests cover all requested evidence boundaries. Existing accepted audit
regressions continue covering professional/senior profiles, FT/name hints and
unproven legacy metadata. The focused readiness/PREMATCH regression suite checks
nine V1 fields remain unavailable, immutable snapshot reproduction, unchanged
champion/candidate behavior, zero Official mutations and no LIVE champion or
publication activation. This task adds no predictive algorithm; no operational model training
or performance backtest is appropriate. Historical replay is tested
with deterministic synthetic facts only.

The explicit provider-parity test constructs the real FootballClient with a mock
transport: observation disabled/enabled each issue exactly the same two fixture
requests (one fixture and one finished-history query). Repeated populated-registry
resolution and bridging add **zero provider requests and zero HTTP calls**.
Network transports and sockets are forbidden in the new test module.

Validation results:

- New registry tests: **56 passed**, including complete CLI workflow and standalone
  JSON export/source reproduction, with socket/HTTP transport blockers.
- Initial focused regression selection: **668 passed, 42 subtests passed**.
- The initial selection inadvertently included two pre-existing synthetic training
  tests: `test_scheduled_ticks_complete_prematch_autonomy_without_live` and
  `test_training_does_not_hold_database_write_lock`. These executed training only
  in disposable pytest stores; no repository/production model or registry was
  changed. This was a test-selection deviation from the requested no-training
  boundary. It is disclosed here rather than reported as zero training execution.
- Final focused run: **666 passed, 2 deselected, 42 subtests passed** in
  58.27 seconds, explicitly excluding both training tests (command below).
- CLI help smoke check and `git diff --check` passed.

```bash
/home/arvis/GoalVisionAI/.venv/bin/python -m pytest -q \
  tests/test_prematch_football_context*.py \
  tests/test_api_football_adaptive_discovery.py \
  tests/test_api_football_discovery_efficiency.py \
  tests/test_api_football_odds_freshness.py \
  tests/test_lab_v2_prematch.py tests/test_prematch_production_integration.py \
  tests/adaptive_lab/test_prematch_autonomy.py \
  -k 'not scheduled_ticks_complete_prematch_autonomy_without_live and not training_does_not_hold_database_write_lock'
```

Changed files:

- `app/prematch_football_context/regulation_registry/__init__.py`
- `app/prematch_football_context/regulation_registry/__main__.py`
- `app/prematch_football_context/regulation_registry/contracts.py`
- `app/prematch_football_context/regulation_registry/repository.py`
- `app/prematch_football_context/regulation_registry/service.py`
- `tests/test_prematch_football_context_regulation_registry.py`
- `docs/audits/PREMATCH_FOOTBALL_CONTEXT_V2_REGULATION_REGISTRY_REPORT.md`
- `TASKS.md`

All existing application modules, feature formulas, provider implementations,
readiness contracts and prior audit reports remain unchanged.

## Limitations and exact next step

No source authenticity automation, review signature, revocation/supersession
workflow, new-organizer onboarding UI, runtime wiring or production store exists.
Conflicting reviews fail closed until a separately reviewed remediation design is
authorized; existing evidence must not be edited or deleted to clear a conflict.
The small-registry implementation verifies all rows for each lookup; it is not a
large-registry indexing or performance project.

The next step is an operator-controlled review of **one genuine organizer document
for one exact provider competition-season**, retaining a bounded duration extract,
category/season applicability and independently substantiated provider-ID mapping.
Prepare and validate the complete record, import into a newly initialized isolated
Test registry, inspect it, verify integrity and resolve at a future decision cutoff.
Then review future-only observation wiring as a separate task. Do not reinterpret
old snapshots, populate real entries from synthetic tests, or infer applicability
from IFAB alone. **Phase E remains unauthorized.**

No merge, push, deployment, Telegram action, Official change, LIVE activation,
production DB mutation, real API-Football traffic, historical bookmaker odds,
scheduling/systemd/startup change, probability change or operational model training occurred.
The synthetic regression-training exception is disclosed above.
