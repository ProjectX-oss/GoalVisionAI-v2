# Lab V2 operational audit — 2026-09-16

## Verdict

**BUGS FOUND AND FIXED.** The audited path remains Lab-only and fail-closed.
No threshold, minimum-odds rule, provider limit, Official policy, systemd state,
credential or operational history was changed.

## Read-only production evidence

The latest persisted V2 cycle at audit start was
`2026-09-16T19:00:04.073256+00:00`: 1,008 provider fixture rows, 424 eligible
fixtures, 105 fixtures with usable current odds, 1,051 evaluated markets, 16
EARLY, zero FINAL and zero READY, using 92 calls. Allocation was `/status` 1,
date fixtures 3, paginated date odds 53, finished results 7 and predictions 28.
The old report labelled 148 fixtures no-odds, 159 stale and 12 unnormalizable,
but one odds page was unfetched; the 148 value therefore mixed confirmed
no-odds with unknown page coverage. This classification defect is fixed for
future cycles.

Current fixture responses contained 420, 177 and 411 rows with provider paging
`current=1,total=1`. A read-only cross-date check found 1,256 rows and 1,256
distinct fixture IDs, so no current provider-deduplication loss was evidenced.
Date-odds responses genuinely paginate (up to 27 pages in the inspected data).

## Defects and repairs

1. **Cross-market signal votes.** API prediction and CMI selected their global
   maximum across all eleven markets. A totals selection such as UNDER 3.5
   could therefore be stored as the vote beside a 1X2 probability and evade
   same-family disagreement handling. Votes and relation diagnostics now select
   only within 1X2, BTTS or the matching total-line family.
2. **False signal independence and repeated reliability.** Pi, goals/form CMI
   and the persisted CMI-derived model consume overlapping result-history/model
   context but were counted and weighted as independent adapters. Duplicate
   adapter names and selection-only signals could also inflate quorum. V4 groups
   correlated adapters into one evidence family, applies one family weight,
   rejects duplicate sources and counts only probability-bearing groups.
3. **Pi probability simplex residual.** Binary-float `erf` conversion left
   HOME/DRAW/AWAY totals slightly below or above one. AWAY is now the exact
   Decimal residual after HOME and DRAW.
4. **Odds pagination priority and classification.** Round-robin continuation
   fetched future-date pages while an earlier UTC date remained incomplete.
   Unjoined fixtures on incomplete days were then reported as no-odds, and the
   budget impact was guessed as ten fixtures per page. Page one is still sampled
   across dates, but continuations are now earliest-date-first. Each fixture is
   classified as current, no-odds, stale, unsupported market, unnormalizable or
   coverage-incomplete; unknown coverage is never called no-odds.
5. **Final-review reserve undercount.** Four logical endpoints were reserved as
   four calls although the HTTP client can make three bounded attempts for each.
   Optional history/prediction calls and date-odds pagination could consume the
   retry capacity. The pre-odds reserve now covers supported exact endpoints and
   all bounded attempts for up to five imminent fixtures; after odds coverage is
   known it is recalculated for the actual odds-covered shortlist.
6. **Provider errors marked refreshed.** An injury error payload became an empty
   absence list and `REFRESHED`, allowing a lineup-sensitive 1X2 readiness check
   to pass. Injury and lineup provider errors are now explicit fail-closed
   statuses and cannot satisfy readiness.
7. **Refreshed kickoff ignored.** Exact fixture refresh only returned a boolean;
   a postponed/rescheduled but still upcoming match retained its stale discovery
   kickoff for readiness and publication. The refreshed UTC kickoff now replaces
   the old value before the final window and minimum-lead checks.
8. **Edge mislabeled as expected value.** Probability edge (`p - 1/odds`) was
   copied into the publication leg's `expected_value`. Evidence now retains both
   probability edge and Decimal expected value (`p*odds - 1`) with unchanged
   edge thresholds and signs.
9. **Unclaimed replay conflicts.** Stable fixture/market combo identities were
   paired with changing preparation times and refreshed quotes. If configuration
   or bot identity blocked before a claim, the next cycle could conflict with the
   immutable ledger. Preparation timestamps are evidence-derived and IDs bind
   candidate and quote fingerprints. Claimed/unknown deliveries still consume
   the publication key and remain non-retryable.
10. **Combo ranking/report mismatch.** The V2 report returned the first lexical
    triples and could show overlapping combos, while publication used a separate
    path. Both now prefer the strongest weakest edge, then summed edge, require
    exactly three distinct fixtures and six distinct teams, and consume fixtures
    and teams across the batch. No combo is forced.
11. **Single settlement crash recovery.** Combo previews were repaired after a
    crash between settlement and preview persistence; single previews were not.
    The same idempotent recovery now exists for settled singles without refetching
    or overwriting a result.
12. **Unbounded evidence growth.** The 2.3 GiB shadow database contained about
    1.47 GiB of JSON from 2,511 expired `/odds(date)` cache rows. A 15-minute page
    cache cannot be reused by the 30-minute cycle. Rehearsals also duplicated
    about 196 MiB of candidates already stored individually. Future cycles no
    longer persist the unusable full-page cache and store candidate IDs in the
    cycle summary while retaining individual append-only candidates, normalized
    consensus, quote timestamps and provenance. Existing rows remain untouched.

## Discovery, odds and model findings

- There is no major-league allowlist. Capability classification is based on
  current league/season endpoint coverage; Tier A/B/C remains unchanged.
- UTC dates are derived from timezone-aware instants. Tests cover UTC,
  Europe/Riga, Europe/Berlin, midnight crossing and the spring DST boundary.
- Current quote construction requires provider update time, retrieval time,
  valid finite decimal odds, supported names, complete comparable bookmaker
  families and multiplicative no-vig normalization. Arithmetic mean consensus
  and dispersion remain transparent; no historical odds or fabricated prices
  are used.
- A discovered fixture without current actionable odds remains explicit evidence
  and cannot enter market evaluation, READY or publication.
- Pi orientation, API `/predictions` percentage/goal parsing, totals/BTTS Poisson
  derivation and current CMI market probabilities passed deterministic mapping
  regressions. Missing signals are absent rather than neutral probabilities.
- Odds refresh rebuilds the offered price, implied probability, edge and expected
  value. A material adverse move can turn an approved candidate into rejection.

## Draw diagnostic

The latest pre-fix operational cycle evaluated 105 HOME, 105 DRAW and 105 AWAY
markets. Approvals were HOME 1, DRAW 12 and AWAY 3. Mean ensemble / implied /
edge were HOME `0.3608 / 0.4353 / -0.0745`, DRAW
`0.3018 / 0.2608 / +0.0410`, and AWAY
`0.3374 / 0.3597 / -0.0223`. Median ensemble / implied / edge were HOME
`0.3441 / 0.4149 / -0.0718`, DRAW `0.3060 / 0.2740 / +0.0364`, and AWAY
`0.3327 / 0.3509 / -0.0226`.

This shows a real selection effect: DRAW alone had positive mean and median
market-relative edge. Pi's transparent normal-outcome mapping also has a high
balanced-match draw prior. No evidence justified suppressing draws or changing
calibration/thresholds in this bug audit. The cross-family vote and correlated
quorum bugs were fixed because they were implementation defects; V4 diagnostics
will show whether the remaining draw share persists on fresh data.

## Readiness, publication, combo and settlement proofs

- Tests prove EARLY to FINAL reconsideration, market-specific lineup behavior,
  NOT_SUPPORTED handling, Tier C gates, exact refresh freshness and a valid
  candidate reaching READY.
- Fake transport proves one READY single yields one durable claim, one send and
  one receipt; replay sends nothing. Timeout yields one claim plus delivery-
  unknown and no retry. The same ledger/service boundary applies to combos.
- Combo tests cover exactly three legs, no Lab minimum leg/combined odds,
  correlation rejection, disjoint batches, no forced combo and all 27
  WON/LOST/VOID leg combinations including partial void.
- Settlement uses terminal API-Football status and regulation-time fulltime
  score, persists one result, repairs previews idempotently and publishes result
  claims exactly once. All statistics remain in the Lab ledger; Official is not
  referenced or mutated.

## Operator view

`python -m app.lab_v2_shadow summary` opens the shadow database with SQLite
`mode=ro` and `query_only`, and reports the latest discovery/odds/stage counts,
top rejection/readiness reasons, API allocation, publication attempts/sends and
HOME/DRAW/AWAY distributions. `--fixture-id ID` returns its explicit lifecycle
or `FIXTURE_NOT_DISCOVERED` for the latest cycle. No schema migration is used.

## Safety evidence

At audit start the shadow, analysis and ledger SHA-256 values were respectively
`be81f766...d802e`, `62c4f8c...da6b3` and `633f1280...f7a7e`.
At the post-test check, shadow and analysis hashes and mtimes were unchanged.
The active, pre-existing settlement timer independently appended five zero-call
`run` documents to the Lab ledger by the final check, changing only its
hash/size and run count (494 to 499); claim, receipt, prediction and settlement
counts did not change.
Tests and audit code did not open operational databases for writing.

No real Telegram message was sent. Claim and receipt counts stayed at six.
Official was untouched. `goalvision-lab-v2-discover.timer` remained inactive
(and retained its pre-existing enabled setting). No systemd command that changes
state was executed.

## Verification

- Focused final set: `72 passed`.
- Relevant Lab/API/publication/settlement set: `355 passed, 66 subtests passed`.
- Full collection is blocked by the unrelated pre-existing import of missing
  `app.lab_combo.cli._analysis_input` in
  `tests/test_source_commit_provenance.py`.
- With only that collection-blocking file excluded: `1644 passed, 563 subtests
  passed, 1 failed`. The remaining unrelated failure expects
  `CALIBRATION_EVIDENCE_STALE` but current staging rehearsal evidence returns
  `CALIBRATION_REVIEW_MISSING` in
  `test_rolled_back_legacy_champion_is_stale_without_delivery`.

No provider call, live discovery, real Telegram transport, production database
mutation, Official mutation, timer start/restart/reinstall or `.env` change was
part of this audit.
