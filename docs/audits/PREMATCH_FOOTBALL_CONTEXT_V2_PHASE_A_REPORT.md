# PREMATCH Football Context V2 — Phase A implementation report

Date: 2026-09-23. Decision: **PHASE_A_IMPLEMENTED_AND_VERIFIED**.
Authority: [reviewed RFC](../design/PREMATCH_FOOTBALL_CONTEXT_V2_RFC.md),
`READY_FOR_PHASE_A_IMPLEMENTATION`. Phase A only; no runtime integration.

## Lineage and isolation

- Starting commit: `f23b0c5c4a8968d2196484d1730420a2ec1b0f57`.
- Starting branch: `codex/prematch-context-v2-rfc`.
- Starting worktree: `/home/arvis/GoalVisionAI-prematch-context-v2-rfc`;
  `git status --short` was empty: no dirty or untracked files.
- Implementation branch: `codex/prematch-football-context-v2-phase-a`.
- Isolated worktree: `/home/arvis/GoalVisionAI-prematch-context-v2-phase-a`.
- Created a new sibling worktree directly from the RFC commit. No merge,
  cherry-pick, reset, push, or change to another checkout.
- Production design baseline remains `89477a139746657e33dbcb4ac12a67438b151677`.
  Split hardening `25f536199fd893bd681a82ae586e62b545e28d23` is **not integrated**;
  later integration must preserve it before RFC phases E/F/G.
- Final commit SHA: the commit containing this report, obtainable with
  `git log -1 --format=%H -- docs/audits/PREMATCH_FOOTBALL_CONTEXT_V2_PHASE_A_REPORT.md`.
  Its exact SHA is supplied in the final handoff. A committed report cannot
  embed its own resulting commit hash without changing that hash.

## Changed files and public boundary

Only these seven files are added:

| File | Responsibility |
| --- | --- |
| `app/prematch_football_context/__init__.py` | Inert public calculation/manifest exports |
| `app/prematch_football_context/contracts.py` | Frozen typed supplied facts, results and diagnostics |
| `app/prematch_football_context/policy.py` | Pinned profiles, identities, arithmetic and semantic manifest |
| `app/prematch_football_context/calculations.py` | Pure eligibility, selection, rates, Pi replay and form |
| `app/prematch_football_context/fingerprint.py` | Canonical JSON, decimal serialization and domain-separated SHA-256 |
| `tests/test_prematch_football_context.py` | Synthetic goldens, integration of pure primitives and invariants |
| This report | Implementation evidence and limitations |

`calculate_context(ContextInput) -> ContextResult` is the complete pure entry
point. Construct `Target`, `Classification`, `Regulation`, `SourceRef`, and
current/optional previous `History` with immutable fixture tuples. Input types
reject unknown constructor keys, malformed identities/timestamps/hashes and
noninteger score types. Typed but ineligible rows (including missing/out-of-range
scores) remain exclusions. Source/target/as-of violations raise `ValueError`;
normal unavailability produces `MISSING`, explicit nulls and ordered reasons.

`SourceRef` supplies a stable evidence identity/hash and asserted completed-fact
known-at time; equality at T requires an explicit before-capture assertion.
`History` supplies a collection-freshness verdict and per-season verified format.
Phase A checks these supplied assertions; **it does not establish their truth**,
verify retained provider bytes, discover classifications/formats, read freshness
from a cache, or supply the richer future source provenance. Phase B remains
responsible for proving retrieval completion, durable registration, query identity,
TTL/expiry/provider timestamps and retained payload hashes. The pure result is
not a persisted Phase C snapshot or a runtime-ready V2 evidence envelope.

Lower-level calculation functions expose deterministic samples and replay states
for offline goldens. `calculate_context` always reconstructs Pi from zero; it does
not accept an injected/warm-start state. The form goldens use explicitly synthetic
supported states to isolate the approved formula. Real use must obtain its state
from the same bound pool/cutoff via `replay_pi`.

## Contracts and calculations

Identities implemented:
`PREMATCH_FOOTBALL_CONTEXT_V1`,
`PREMATCH_FOOTBALL_CONTEXT_V2_SEMANTICS_1`,
`FC_OBSERVED_HISTORY_POLICY_V1`,
`GV_PI_RATIONAL_REPLAY_V1`,
`FC_DECIMAL28_HALF_EVEN_V1`, and `FC_CANONICAL_JSON_V1`.

Exactly seven ordered features:

1. `home_team_observed_weighted_scoring_rate`
2. `home_team_observed_weighted_conceding_rate`
3. `away_team_observed_weighted_scoring_rate`
4. `away_team_observed_weighted_conceding_rate`
5. `home_team_current_pi_adjusted_form`
6. `away_team_current_pi_adjusted_form`
7. `pi_designated_side_rating_difference`

- History: exact competition/provider/entity category, current and optional
  previous season, verified regulation, FT/AET/PEN only, `[T-H,T)`, no target
  result, both venues, quarantine conflicting duplicates. Each supplied response
  is bounded to 99 rows; replay is bounded to 198. UTC kickoff/numeric fixture ID
  orders selection descending and replay ascending. No inferred complete history.
- Rates: latest 3–8 observed score pairs, `w=exp(exponent*ln(2))` where
  `exponent=-exact_days(latest_selected,kickoff)/L`; `sum(w*GF or GA)/sum(w)`.
  Diagnostics retain selected IDs/fact hashes, oriented scores, kickoffs, weights,
  H/L/N, effective N, oldest/latest times and exclusions.
- Pi: zero-seeded old-state simultaneous rational-error updates with coefficients
  `0.75`, `0.15`, `0.10`; no reset, decay, outside state or league transfer.
  Difference requires totals >=8, appropriate designations >=3 and both target
  recency guards; validated range `[-79.2,79.2]`, without clipping.
- Form: decision-time `x`, rational expectation `0.5+x/(2*(1+abs(x)))`, regulation
  W/D/L actual, clamped `0.025` goal margin, clamped performance and latest-first
  rank weights `N..1`. Every selected team/opponent needs >=4 total and >=1 used
  dimension update. Unsupported opponents invalidate the whole side; no replacement.
- Decimal: fresh explicit precision-28/ROUND_HALF_EVEN contexts, explicit traps,
  integer-microsecond days, no intermediate quantization. Only final features
  round to six places; negative zero normalizes; nonfinite/range failures reject.

**Semantic deviations from the Phase A RFC: none identified.** No parameter was
chosen from outcomes or tuned. Later-phase manifest entries are declarations,
not implemented source/vector/transformer/registry functionality.

Reviewed the directly relevant runtime rate/form/Pi/profile implementations and
immutable dataclass/canonical JSON patterns. Kept small primitives isolated:
reusing current code would inherit float-time/venue behavior, mutable Pi state,
missing support guards or runtime dependencies. No existing helper was extracted,
refactored, imported, or behaviorally changed. Consequently no adjacent helper
regression suite was required or run.

## Fingerprints and machine-readable manifest

`semantic_manifest()` returns a fresh machine-readable document;
`canonical_bytes(semantic_manifest())` gives its deterministic JSON bytes.
It pins seven-feature meanings/units/ranges, profile table, formulas/coefficients,
supports, normalization/exclusions, source rules, missingness, Decimal policy,
serialization, and the RFC's future ordered vector/transformer declarations.
It is not registered anywhere at runtime.

Canonicalization follows the repository's compact sorted JSON + SHA-256 pattern,
with RFC-required NFC, UTC microseconds, no floats, exact plain intermediate
Decimal strings and domain + newline separation. Ordered arrays stay ordered.
Input evidence sets collapse equivalent duplicates independently of input order;
source identity/hash, excluded facts, target/cutoff, normalized pool, selected
samples, support state, diagnostics, values and missingness remain fingerprinted.
No operational receipts, temporary database IDs or ambient process state enter
these contracts. Supplied immutable source IDs are deliberately significant.

Generated literal semantic golden:

`f6b27feb0a0352f02390f392cfeea9e200039ad163dad7f764567cc4efe8276a`

Unicode/time/null/zero canonical JSON golden:

`d6cd07468eb48663d4218ab0a407ec433f553137629e796ec6ec676ce73efecb`

Eight synthetic 1–0 fixtures (`request(tuple(fixture(i) for i in range(1,9)))`)
result replay fingerprint under both `PYTHONHASHSEED=1` and `777`:

`14c1fd761e2a91fa8ca9fac4afd1b8e3575395d9353673673808616ca70f0037`

## Executed verification

Run from the isolated implementation worktree:

```sh
/home/arvis/GoalVisionAI/.venv/bin/python -m pytest -q tests/test_prematch_football_context.py
python3 -m compileall -q app/prematch_football_context tests/test_prematch_football_context.py
git diff --check
```

Final focused result: **41 passed, 34 subtests passed**. Compile: exit 0.
Import smoke of all five modules with `python3 -B`: **PASS**. Diff check: **PASS**.
Two separate-process fingerprint replays with hash seeds 1 and 777: **identical**.
The focused subprocess test also blocks socket/SQLite/environment lookup and
filesystem-write attempts during imports/calculation, and verifies no runtime
Lab/adaptive/LIVE/Telegram imports. No new dependencies were installed.

Earlier development runs used `python3 -m unittest tests.test_prematch_football_context -q`
(up to 39 tests before the final two cases were added). Only final focused pytest
counts above describe the completed suite. Development literal-hash placeholders
were replaced with generated, independently canonical-byte-checked goldens.

| RFC acceptance coverage | Executed Phase A assertions |
| --- | --- |
| T01–T06 | Exact rates/form/Pi, support/zero boundaries, all profiles, horizons, recency and seasons |
| T10–T11 | Conflicts, duplicate/permutation/order invariance, literal hashes, Unicode/UTC/precision, sensitivity |
| T15–T16 | Independent side/form missingness, no borrowed identity/state, previous-season carry and youth horizon |
| T17–T20 | No rest feature/completeness claim; neutral designation; category/competition/format isolation; regulation-only scores/statuses |
| T32 | Inert imports/calculations, no runtime dependencies, blocked I/O side effects |

Also exercised 198-game replay, source unavailable versus empty, ordered multiple
reasons, cutoff equality proof, state binding, hostile ambient Decimal context,
strict typed contracts and deterministic range/sample-size invariants.

Full repository suite: **not run**. The unchanged baseline documents about
12 minutes for its broad suite; it includes unrelated database and model-training
workflows. It was not necessary to exercise those workflows for this isolated,
no-database/no-training task. No broad Official/bankroll/Telegram/LIVE suites were
run; no existing runtime file was changed. No pre-existing full-suite failure is
claimed or inferred. Historical baseline test counts are not this task's results.

## Limitations and non-interference

1. Predictive benefit has **not** been established; Phase A makes no quality claim.
2. Rate samples of 3–8 games can be noisy; N and effective N are diagnostics only.
3. Current-Pi-adjusted form uses decision-time state, including recent results;
   it is not historical pre-match opponent strength or historical surprise.
4. Pi is reconstructed from a bounded observed same-competition pool, not an
   exhaustive team history or globally calibrated strength model.
5. Sparse competitions and early season may have limited Pi/form availability.
6. Existing V2-compatible prospective coverage is not established. Supplied
   synthetic format/source assertions do not prove runtime provenance readiness.
7. `rest_days` is intentionally excluded. Neutral games keep provider designation,
   which is not a physical home-advantage claim.
8. No research/backtest, source adapter, persistence, vector projection, training
   registry or split integration was implemented. Those require separate phases.

Confirmed for this task: **no network/provider calls; no database reads,
migrations or persistence; no model training; no model activation/promotion;
no Telegram messages; no production deployment.** Tests use in-memory synthetic
football facts and do not create a test database or train a model. Python compile
and Git operations only create normal local development artifacts.

Official behavior, bankroll/statistics, settlement, publication/odds policy,
current Lab V2 behavior and all existing V1 frozen observations are unchanged.
LIVE was not enabled or modified. No `.env`, runtime database, timer, service,
champion state or production configuration was changed. No later phase started.
The next step is independent review of this local Phase A commit.
