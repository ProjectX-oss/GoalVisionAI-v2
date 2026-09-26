# Lab V2 PREMATCH

This isolated Lab path analyzes valid upcoming fixtures first, scores quality
and risk, then ranks selected opportunities for publication. Official policy,
bankroll, statistics, activation and rollback are separate. LIVE is disabled.
No historical bookmaker odds are used. Importing this package never schedules
work or sends Telegram.

## Discovery window and quota

Europe/Riga is authoritative, including DST. Discovery runs every 30 minutes
from **09:00 through 22:30**. At 23:00–08:59 both CLI entry points and the runner
return `NIGHT_DISCOVERY_PAUSED` before provider access. The CLI does not even
construct the provider at night. The live CLI also supplies a runtime clock to
stop new provider operations if a daytime cycle crosses 23:00. Existing in-flight
provider requests may finish. The repository timer has `Persistent=false` to
avoid catch-up discovery outside the window. Result processing and local learning
are independent of this discovery guard.

After `/status`, provider-reported remaining daily and minute quotas control:

```
usable = max(0, daily_remaining - 100)
cycles = remaining half-hour daytime slots, including the current slot
additional_calls = min(usable // cycles, minute_remaining,
                       configured_cycle_maximum - calls_already_used)
```

At 09:00 there are 28 slots; at 22:30 there is one. The maximum is 400 calls,
including bootstrap and retries. Work only consumes calls when needed. The
provider client enforces the paced ceiling for retries too; unknown quota stops
provider work after status. The explicit 100-call reserve is for settlement and
results, not a fixed 1,500-call discovery buffer. `--daily-reserve` is a deprecated
alias for `--settlement-reserve`; 1500 is rejected, not silently retained.

## Coverage and analysis

Priority uses the existing competition classifier: senior men's professional,
international club, international senior, and full provider-coverage tier A
fixtures. There are no new league-ID admission lists. A reserved priority phase
finishes each fixture's exact-odds retry, league history and supported provider
prediction before ordinary fixture enrichment consumes the remainder. Broad date
pages remain shared discovery. All other profiles retain global discovery and
fair enrichment ordering when quota permits. Priority means first access to
analysis resources, never a required bet or a promise of provider availability.

`ODDS_COMPLETE_SWEEP_NO_FIXTURE_RECORD` means no matching fixture ID occurred
on any valid page of a completed date sweep. It is assigned before bookmaker
filtering can matter. The implementation retains this diagnostic. Up to 20
priority fixtures per cycle can get one exact current-odds request when broad
coverage is missing/stale, subject to the cycle quota; bounded provider retries
remain inside the same cap. Persisted least-served ordering rotates bounded
retries across cycles and restarts. A same-cycle exact response is reused by final
review, avoiding a duplicate odds request. Ordinary misses wait for a later
cycle. Existing bookmaker matching, timestamp and normalization rules remain.

Every legitimate upcoming fixture reaches local context/model evaluation,
including missing and stale prices. Append-only `model_analysis` documents
retain available history, Pi, API and persisted-model probabilities without
inventing a price or EV. No-price fixtures remain `TRACKING` with
`WAITING_FOR_REFRESH` analysis evidence. New quotes trigger a fresh assessment.

A started fixture is valid result/audit/learning evidence. Global state becomes
`RESULT_TRACKING`, and its publication review becomes `PUBLICATION_CLOSED`.
Discovery does not enrich it as a new PREMATCH selection. Existing captured
observations remain settleable. Cancellation/postponement also closes new
publication without corrupting the fixture identity.

## Light safety and publication

Lab V2 has no 1.60 odds floor for singles or combo legs. Decimal prices must be
finite and greater than 1. Positive EV at 1.40 is allowed. Official's 1.60 rule
is untouched.

The profile policy retains these as visible soft findings rather than vetoes:

- `ENSEMBLE_EDGE_BELOW_0_04`, `VALUE_BELOW_PROFILE_THRESHOLD`
- `INSUFFICIENT_INDEPENDENT_SIGNALS`, `NO_INDEPENDENT_NON_MARKET_EVIDENCE`
- `MATERIAL_SIGNAL_DISAGREEMENT`, `WEIGHTED_AGREEMENT_BELOW_0_65`
- `ENSEMBLE_MARKET_DIVERGENCE_TOO_LARGE`, `SEVERE_MODEL_MARKET_CONTRADICTION`
- The existing provider-context equivalent
  `SEVERE_CURRENT_MATCH_INTELLIGENCE_CONTRADICTION`, and unavailable consensus.

Existing profile uncertainty, feature weights, probability calculations and
independence grouping are reused. No new numeric confidence penalty is added.
Quality findings cap confidence at LOW and the lane at EXPERIMENTAL. A positive
edge below the existing experimental edge-plus-uncertainty margin, or inadequate
independent evidence, keeps the market in TRACKING. The field
`experimental_lane_edge` describes a lane threshold, not a rejection threshold.
Stronger evidence can reach STANDARD or STRONG using the existing thresholds.
The internal ensemble still emits its original diagnostics; `evaluate_profile`
is the authoritative Lab PREMATCH decision boundary.

Hard non-actionable outcomes are non-positive EV and invalid/corrupt contracts,
identities, prices, probabilities, duplicate signal sources or unsupported market
mappings. Missing data is deferred, not represented as trusted EV. A previously
negative-EV tracked selection can be reconsidered with new current evidence.

Only ranked READY candidates can enter the separate publication handoff.
TRACKING never becomes READY. Exact fixture/quote review, kickoff restrictions,
immutable captured quotes, distinct combo fixtures/teams, destination isolation,
and delivery claims remain enforced. The handoff rechecks current quote age,
positive EV and kickoff at preparation time. Ranking prefers lanes, then edge
and stable tie-breaks. There is no minimum publication count. A claimed or
indeterminate delivery cannot be resent under a refreshed quote identity.

## Canonical shadow learning

The existing append-only `forward_selection` / `forward_result` path now freezes
the first fresh, pre-kickoff, positive-EV observation per fixture/market even if
it is EARLY or TRACKING and never sent. It records identity, competition,
kickoff, selection, probability, odds, implied probability, edge, EV,
confidence/lane, evidence quality, model/policy generation, capture/retrieval
and provider timestamps, and quote provenance. Refreshed quotes and subsequent
cycles cannot replace or multiply the observation.

Production adaptive observer, research/AutoML, champion registry, governance,
health and weekly schedules remain in place. With the existing adaptive database
configured, the coordinator freezes one canonical fresh positive-EV observation
per fixture/market. The existing settlement worker resolves pending canonical
samples within its current call limit; the observer imports them into the same
adaptive learning evidence. Published copies are deduplicated. No separate
shadow worker or Telegram destination is introduced. Public SINGLE/COMBO statistics
and bankroll are unaffected. Audit schema 5 adds append-only canonical tables.

## Commands and status

```bash
.venv/bin/python -m app.lab_v2_shadow summary --human
.venv/bin/python -m app.lab_v2_shadow summary --fixture-id 123456
.venv/bin/python -m app.lab_v2_shadow rehearse --max-calls 400 --settlement-reserve 100
```

`rehearse` never constructs Telegram transport. The explicitly armed
`controlled-cycle --send` command uses the existing Lab ledger. The repository
service template preserves that existing arming; updating a template does not
deploy it.

Status distinguishes discovery, model-analysis attempts, fixtures with model
probabilities, current-odds market scoring, waiting refresh, priority discovered
and analyzed, soft confidence findings, actual hard rejections, new shadow
observations, READY, sends, provider calls and remaining quota. A current
nighttime pause is intentional and has no DEGRADED warning. Last-cycle counters
remain visible separately from the current discovery clock state.

No schema migration is needed. Historical rows and losing results are unchanged.
See [implementation and validation report](../../docs/LAB_V2_PREMATCH_SIMPLIFICATION.md).

## Compact controlled-cycle stdout

`controlled-cycle` and `rehearse` emit one JSON line with schema
`goalvision-lab-v2-operator-cycle-v1`. It contains the evaluation timestamp,
`cycle_id` (the existing `rehearsal` evidence identity), analysis/delivery status,
mode, publication flags, discovery/candidate/API counts, cycle-persistence result,
and a bounded controlled-publication summary. `summary` keeps its existing format.

Every service delivery invocation retains kind, prediction ID, stage, claim and
transport facts, transport failure kind, acknowledgement chat/message IDs, receipt
status, reconciliation requirement, unknown-marker persistence, persistence failure
and status. Successful deliveries before a later failure remain visible. There is
no delivery-list truncation, including when publication-cycle persistence fails.
Size depends on delivery invocations, never discovered fixtures or candidates.

Only bounded scalar fields are projected. No candidate arrays, fixture lists,
provider responses, message bodies, tokens or raw exception text are printed.
A truthy terminal error becomes `{"code":"CYCLE_TERMINAL_ERROR"}`; the original
report still determines the process exit code. Night pauses have zero attempts,
`analysis_status=SKIPPED`, and `publication_cycle_persistence.persisted=null`
because that path only stores the existing night rehearsal record.

Persistence is unchanged: inspect the complete cycle with
`ShadowEvidenceRepository.get("rehearsal", cycle_id)`, then resolve its
`candidate_ids` through `get("candidate", candidate_id)`. Publication-boundary
records remain under `publication_cycle`; delivery claims and receipts remain in
the existing ledger. The formatter neither writes nor modifies these records.
For emergency delivery reconciliation, retain the protected stdout line even if
the evidence store failed. Never retry a send based on stdout alone.
