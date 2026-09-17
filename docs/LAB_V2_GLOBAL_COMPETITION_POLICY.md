# Competition-aware global Lab V2

This is a Lab-only, manually invokable extension of `app.lab_v2_shadow`. No
Official policy, bankroll, statistics, activation or timer configuration changes.
Discovery/evaluation construct no Telegram transport. Historical bookmaker odds
are never queried. Existing `controlled-cycle --send` remains an explicitly
separate boundary; this change does not authorize or execute it.

## Discovery and classification

The date fixture endpoint defines the universe for the configured 1–7 UTC dates.
Every valid upcoming fixture survives discovery, including youth, women,
reserves/B teams, lower divisions, internationals, qualifiers and friendlies.
League capability metadata describes optional endpoint usefulness; it no longer
controls admission. Missing metadata gets a conservative capability record.
Malformed identity/date records and invalid statuses retain rejection evidence.
No major-league admission list exists.

`profiles.py` defines thirteen profiles and classifier/policy versions. Reviewed
provider IDs are classification hints only; they were checked against the local
provider capability catalogue. Explicit metadata and narrow name patterns are
fallbacks. Unknown or unspecified-age academy competitions remain UNKNOWN with
an auditable reason. Senior professional status is not inferred merely from an
unfamiliar league name. Flags preserve explicit neutral venues, second legs,
qualifiers, playoffs and provider capabilities. No derby is guessed.

The append-only discovery record includes original fixture/league/team metadata,
classifier version, reason and fingerprint. Each cycle appends one current state
per fixture: DISCOVERED, TRACKING, READY, EXPERIMENTAL_READY, REJECTED,
UNAVAILABLE or EXPIRED. These states are separate from the legacy runner stages,
which remain readable for old evidence and delivery compatibility.

## Evidence, markets and gates

The existing market normalizer and ensemble still evaluate 1X2, BTTS and totals
1.5/2.5/3.5 independently. A failing winner market does not suppress a totals
market. Current quote provenance, freshness and final exact refresh remain
mandatory. Failed exact refresh supersedes broad/older quotes, including missing
markets. Market-only estimates cannot create selections.

Hard gates cover invalid identity/status, invalid probability or model contract,
invalid/missing/stale current odds, nonpositive value, duplicate sources,
material disagreement and correlation/independence integrity. Missing lineups,
injuries, advanced statistics, standings or shallow form become explicit
profile-weighted uncertainty margins. Missing optional data never invents a
feature or substitutes senior-team strength for youth-team strength.

The existing independent-family aggregation is retained: Pi, result-based CMI
and the persisted CMI model share one family. Three families remain necessary
for STANDARD evidence. EXPERIMENTAL permits two genuinely separate families,
including the current market, with positive edge exceeding both its policy
threshold and uncertainty margin. This is an explicit Lab quorum change, not an
assertion that correlated adapters are independent. Existing material
spread/agreement vetoes remain in force.

The profile priorities HIGH/MEDIUM/LOW/IGNORE map to 1/.65/.25/0 signal relevance
and missing-feature penalties. Youth history uses a 120-day window and 30-day
half-life; reserve/friendly history uses 180/60; established profiles use 365/120.
Only completed pre-evaluation results with the exact provider team IDs enter
form. Neutral venues suppress venue-specific Pi and use both venues in goal
rates. Women's estimates use their own league/team results, without an imported
male home-advantage constant. Unavailable knockout state adds uncertainty;
aggregate-score and rotation models are not fabricated.

These are versioned initial experimental settings based on the requested
feature priorities, not validated fitted competition parameters. Probabilities
are explicitly `UNCALIBRATED_LAB_ENSEMBLE`. Uncertainty changes required edge,
not probability semantics. No model is activated or recalibrated.

STRONG/ STANDARD/ EXPERIMENTAL express evidence quality. Readiness additionally
requires valid exact fixture and current-odds refresh inside the existing
T-75 to T-10 review window. UNKNOWN and FRIENDLY stay experimental. No minimum
single or combo decimal-odds floor, daily bet target or profit guarantee exists.

## Quota and refresh

Global discovery stays cheap. Current odds are joined by date; per-day
continuation cursors survive restart so bounded cycles do not repeatedly stop
at the same page. Incomplete coverage is reported as incomplete, never as
confirmed absence of odds.

History, prediction and review queues use persisted least-served profile counts
and equal-weight round robin, then least-recently-serviced fixture and kickoff.
Only serviced work advances a category. All active categories have positive
weight; league prestige is not a scheduling input. A fixture can be discovered
without an enrichment allocation. API client ceilings, retries, pacing and the
1,500 daily reserve remain unchanged. Exact final-review calls retain their
reserved budget. Unavailable data and quota deferrals remain inspectable.

Central profile refresh windows identify the next useful reevaluation time.
The existing manual/cycle runner can recover pending global fixture metadata
and market tracking after restart. Recovery never reloads old quote values into
new evaluations. No timer is installed, enabled or started here.

## Forward evidence and reports

The first ready fixture/market observation freezes its current captured odds in
`forward_selection`. A refresh cannot overwrite that price. Explicit final
result capture appends `forward_result`; conflicting results fail closed.
`forward_evidence.performance` reports joint league/profile/market/lane counts,
wins/losses/voids/pending, probability and implied probability, edge, Brier score,
Wilson hit-rate interval and hypothetical flat-one-unit ROI from captured odds.
Voids and pending observations are excluded from binary metrics. This is
statistical observation, not actual wagering or Official accounting.

Manual policy review needs at least 200 resolved observations spanning 90 days
in the joint bucket. No automatic tuning, promotion or threshold rewrite exists.
New evidence uses the existing immutable document store; no relational schema
change or main database migration is needed. UPDATE/DELETE guards and replay
conflicts apply to new document kinds. SQLite foreign keys are explicitly enabled
on the Lab connection. New document references are validated by service APIs.

Commands (from the repository using the configured Python environment):

```sh
.venv/bin/python -m app.lab_v2_shadow summary --shadow-database var/global_lab_audit/rehearsal.db
.venv/bin/python -m app.lab_v2_shadow summary --shadow-database var/global_lab_audit/rehearsal.db --human
.venv/bin/python -m app.lab_v2_shadow summary --shadow-database var/global_lab_audit/rehearsal.db --fixture-id 123
```

Machine-readable cycle evidence contains `gate_evidence`, `rejection_funnel`,
`global_fixture_states`, profile/state counts, throughput, dominant bottleneck,
API usage and remaining daily quota. Gate rows retain competition, country, age,
market, missing fields, HARD/SOFT and retryability. Fixture counts and market gate
counts are separate: several markets or gates may fail on one fixture.
`ZERO_READY_WITH_HIGH_FIXTURE_VOLUME` is diagnostic only and never forces bets.

## Limits requiring forward validation

Provider coverage can still have no current markets. Bounded runs cannot fetch
all odds pages or enrich all fixtures immediately. UNKNOWN classification is
intentional when reliable metadata is absent. The default profiles need
prospective validation; synthetic tests establish invariants, not profitability.
No automatic final-result provider job is added; the explicit forward-result
service is ready for audited integration with the existing Lab settlement path.
