# PREMATCH Football Context V2 — incorporated-law evidence

Base: `f297435e643d9e2c8fd273e483b7cf5d940347ca`.
Branch: `codex/prematch-football-context-v2-incorporated-law`.

## Outcome and truthful attribution

The dormant reviewed registry can now resolve an explicit competition-regulation
incorporation of a retained reviewed IFAB base law. Direct organizer-duration
reviews assert duration in the competition source itself. Incorporated-law reviews
instead assert that the competition adopts a specific base law; duration comes
from that independently retained law. An incorporation-only competition review
has `regulation_minutes=null`. It must never claim that an incorporation article
itself states 90 minutes.

No real evidence was imported. All added fixtures are explicitly SYNTHETIC and
use competition 10, not UCL's task-supplied identity. UCL 2026/27
(`API_FOOTBALL`, competition 2, season 2026) does **not** currently resolve
`VERIFIED_90` from supplied repository evidence. The task's descriptions are not
complete operator-reviewed registry records. No web claim was researched,
hard-coded as a rule, scraped or automatically trusted.

## Contract and provenance

`IncorporatedCompetitionRegulation` is a narrow versioned extension of the
accepted record (`FC_V2_INCORPORATED_REGULATION_V1`). Its mandatory composed
`Incorporation` contains:

- Relationship `INCORPORATES`.
- Owning competition review ID.
- Target base-law review ID and exact target evidence fingerprint.
- Explicit reviewed incorporation statement.
- Domain-separated SHA-256 relationship fingerprint (`FC_V2_INCORPORATION_V1`).

The relationship is embedded in, and owned by, the immutable competition review.
It has no independently mutable lifecycle: its identity is the owner's review ID
plus relationship type, and its review time/effective interval are the owner's.
Changing a link under an existing owner conflicts. A new reviewed relationship
requires a new review identity. One link per competition review is supported;
multiple applicable reviews are all evaluated.

Both records retain the accepted authority-domain checks, document identity,
edition, section, bounded excerpt, applicability statement, provider mapping
review, source-content hash, reviewer, review timestamp, effective interval and
full evidence fingerprint. The law remains scope-reviewed under the accepted
provider/competition/season contract; it is not a globally reusable assertion.
The accepted explicitly declared season intervals remain supported on both sides;
there is no implicit cross-season or cross-competition reuse.

The extension uses a dataclass subtype solely to preserve the old record's exact
serialized fields and hashes while sharing its full validation. The relationship
itself is composed. Existing V1 direct-duration and IFAB records still require a
positive explicit duration and retain their original evidence version.

## Resolution, conflicts and as-of behavior

Resolution first verifies the entire isolated registry's schema, canonical rows,
source integrity and record fingerprints. It selects independently applicable
records for the exact decision scope and cutoff, then evaluates all applicable
competition authorities. An incorporated target must be present, have base-law
source type, match the pinned fingerprint, and establish duration.

`reviewed_at < cutoff` is strict for each record, including the relationship's
owner. Equality and later reviews fail. Effective intervals are half-open:
`effective_from <= cutoff < effective_until`. Both records must pass their season
scope constraints independently. Late reviews cannot upgrade a historical
resolution; persisted readiness snapshots are never updated.

All explicit competition durations and valid incorporated durations participate
in conflict detection. Different durations produce
`CONFLICTING_REGULATION_EVIDENCE`; this includes an explicit 80-minute competition
rule incorporating a 90-minute law, or two competition authorities adopting
incompatible laws. An incomplete applicable relationship prevents verification
even if another direct proof exists. Missing, expired, late or mismatched targets
fail closed. Store tampering produces `REGULATION_UNVERIFIED`.

An unlinked IFAB record never establishes competition duration and cannot override
a direct organizer rule. IFAB alone remains `REGULATION_UNVERIFIED`. No inference
uses competition name, organizer identity, classification, FT status or general
football knowledge.

## Fingerprints, persistence and bridge

The relationship hash commits to its owner, target ID/hash, type and statement.
The competition evidence hash commits to the complete relationship and review.
The existing resolution SHA-256 commits to scope, cutoff, verdict, reason and all
retained applicable records, including both chain records and the embedded link.
Canonical CLI resolution JSON exports this complete provenance. Decoding the
exported reviews and hashing the complete exported resolution reproduces it
offline; reversed import order gives the same result.

The existing SQLite schema and repository are unchanged. Embedded links inherit
UPDATE, DELETE and REPLACE blocking, canonical row verification, exact replay
idempotency and changed replay conflicts. Normal resolution remains read-only;
only the explicit writable operator import path appends. No automatic migrations,
repair, initialization or production database operations were added.

The FormatEvidence bridge revalidates and reevaluates every supplied review and
relationship at the exact resolution cutoff. A complete consistent 90-minute
chain yields `minutes=90`; missing, invalid or conflicting chains yield unverified
format evidence. Both `proof_id` and `proof_hash` commit to the complete resolution.
Changing the competition provenance, link or base provenance changes that proof.
The full resolution must be retained alongside FormatEvidence. A new cutoff
requires a new resolution; FormatEvidence alone does not encode expiry.

Phase B score semantics remain unchanged: duration proof does not establish a
regulation-time score. AET/PEN fixtures still need their explicit regulation score
pair and never substitute the final extra-time/penalty score.

## Verification

Commands use the existing `/home/arvis/GoalVisionAI/.venv/bin/python`; the system
Python has no pytest. No dependency installation or network access was needed.

- PREMATCH suite: `-m pytest tests/test_prematch_football_context*.py -q`:
  **449 passed, 34 subtests passed** before six final additional guard tests.
- Final focused registry and incorporated-law suites: **112 passed** (56 accepted
  registry tests and 56 incorporated-law tests), including those six guards.
- Official, bankroll, feature migration/store and adaptive LIVE regressions:
  `-m pytest tests/test_official*.py tests/test_persistent_official_bankroll.py
  tests/test_feature_migration.py tests/test_feature_store.py
  tests/adaptive_lab/test_live.py -q`: **316 passed, 191 subtests passed**.
- `git diff --check`: passed.

The chain tests block socket connections and HTTPX network transport, and cover
missing/incorrect links, IFAB alone, independent scope and chronology, expiry,
conflicts, tampered imports and stored rows, replay, immutability, deterministic
hashing, read-only reproduction, CLI import/export and complete-chain bridge
hashes. Accepted integration regressions are rerun with chain-backed evidence for
seven-feature output equality, AET/PEN, provider parity and frozen snapshots.
Readiness regressions also verify the nine legacy context fields stay absent,
no LIVE champion/publications, no learning observations, zero Official mutations,
zero Telegram sends and `phase_e_authorized=false`.

Provider request parity is unchanged: both observation modes make the same two
mock fixture requests (exact fixture and FT history); repeated registry resolution
adds **zero** requests. Real API-Football calls, HTTP calls, scraping and automatic
source discovery performed by this task: **zero**.

This is evidence-resolution testing and historical fixture/snapshot replay, not a
new prediction algorithm or predictive-profitability backtest. No model was
trained. The full repository suite was not run; validation covers the affected
PREMATCH boundary and adjacent product/feature regressions above.

## Changed files and isolation

- `app/prematch_football_context/regulation_registry/contracts.py`: versioned
  relationship and incorporated-review contracts; strict decoding.
- `app/prematch_football_context/regulation_registry/service.py`: shared offline
  chain evaluator and full-chain bridge revalidation.
- `app/prematch_football_context/regulation_registry/__init__.py`: public exports.
- `tests/test_prematch_football_context_incorporated_law.py`: synthetic regressions.
- `TASKS.md`: completed isolated milestone.
- This audit report.

No prediction/readiness runtime wiring changed. No V1 field population, seven V2
formula changes, model-vector changes, Official policy/state changes, LIVE
activation, Telegram, production DB mutation, deployment, merge, push, scheduling,
systemd/startup changes or training. Phase E remains **unauthorized**.

## Limitations and exact next step

These are reviewed operator assertions, not automatic legal interpretation.
Hashes detect content inconsistency, not source authenticity or an authorized
reviewer's factual mistake. Host admission alone does not prove applicability.
Source excerpts and mapping statements must be genuinely reviewed. The existing
trusted operator boundary and retained-evidence requirements remain essential.
The bridge cannot prove that a caller has omitted an entire separate conflict
record; callers must use the complete registry resolution, as before.

Next: an operator should supply and review retained official API-Football mapping
material for competition 2 / starting-year season 2026, the exact UEFA 2026/27
incorporation article with edition/enforcement/applicability provenance, and the
applicable IFAB Law 7 section with its edition/effective interval. Create two
complete reviewed records with genuine review times, pin the base review ID/hash
in the competition relationship, validate and import through the existing offline
CLI into a new isolated Test registry, then resolve/export at a cutoff strictly
after both reviews and within both effective intervals. Review that complete
chain before considering any separately authorized runtime work. Do not backdate
reviews or upgrade old readiness snapshots. No deployment or Phase E is authorized.
