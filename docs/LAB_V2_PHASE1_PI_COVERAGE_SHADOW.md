# GoalVision AI — LAB V2 Phase 1

Status: implemented as `LAB_V2_SHADOW`; it is not a publisher and has no
Telegram transport or send option.

## Safety boundary

V2 reads current/upcoming fixtures, completed match results/goals, current
API-Football predictions, current match information and current bookmaker
quotes captured at evaluation time. It does not read, request, download,
backfill, train on or research historical bookmaker odds. Official prediction,
bankroll and statistics paths are unchanged. No timer is installed, enabled or
started by this package.

## Persisted V1 bottleneck audit

The most recent complete 24-hour evidence window in the Lab ledger is
2026-09-14 14:30:41 UTC through 2026-09-15 14:30:41 UTC. Its 27 discovery
cycles recorded the following cycle observations (the same fixture can occur
in multiple cycles):

| Measure | Count |
|---|---:|
| Fixture rows discovered | 22,749 |
| Excluded before odds | 9,795 |
| Fresh-current-odds fixtures | 190 |
| Fixtures enriched with sufficient data | 141 |
| Candidate markets evaluated | 1,551 |
| Approved market observations | 130 |
| EARLY | 128 |
| FINAL_REVIEW | 0 |
| READY_TO_PUBLISH | 2 |
| Runs at the 40-call/quota ceiling | 12 |
| Fresh-odds fixtures left unenriched in those runs | 33 |

The reconstructable request allocation is 519 current-odds calls, 145 lineup
calls, 81 date-fixture calls, 58 exact-fixture calls, 58 team-statistics calls,
38 injury calls, 12 historical fixture-statistics calls, and 36 status or
otherwise unattributed failed calls: 947 calls total.

V1's largest market rejection groups were low confidence (1,237), insufficient
market-context agreement (1,152), odds below 1.70 (445), excessive
model/market divergence (123), odds above the experimental safety limit (152),
and unavailable/extreme model signals (58 combined). The fundamental volume
loss is not a shortage of fixtures. It is the combination of sequential
per-fixture odds probing, mandatory advanced enrichment for every league and
market, every market being lineup-sensitive, repeated near-kickoff lineup
calls, and the 40-call ceiling.

V1 has no hard `major_leagues_only` rejection: it eventually falls back to all
supported senior competitions. It does, however, evaluate a fixed major/known
competition priority list first. Under the call ceiling that ordering is an
effective coverage bias. Only nine deeply evaluated league IDs are
reconstructable in the 24-hour evidence. V1 persisted aggregate fixture-row
counts rather than every encountered fixture's league identity, so the exact
number of all leagues encountered cannot honestly be reconstructed.

## Capability tiers

`LeagueCapabilityCache` parses the current league/season coverage object and
caches it for seven days beneath `var/`. Classification depends only on
capability, never league name, country, prestige or a European-major list.

- `TIER_A_FULL`: fixtures/current odds plus lineups, injuries, fixture and
  player statistics.
- `TIER_B_GOOD`: fixtures/current odds plus standings or fixture statistics;
  missing advanced sources are recorded as optional limitations.
- `TIER_C_BASIC`: fixtures/results and current odds, sufficient for
  league-local Pi/current-market work; advanced endpoints are not required.
- `UNSUPPORTED`: fixtures or current odds are missing.

Market evaluation still fails closed if the evidence required by that market
is untrustworthy. A Tier C league is not rejected merely because lineup or
injury coverage is absent.

## Pi ratings

The adapter is an independent Decimal implementation of the published Pi
update equations, isolated in `app.lab_v2_shadow.pi_ratings`. The full
`penaltyblog` package was not installed because its broad NumPy/SciPy/pandas,
compiled-model, scraping, visualization and event-data dependency footprint is
disproportionate for this service. Penaltyblog is MIT-licensed; attribution and
license details are recorded in `docs/third_party/PENALTYBLOG_PI_ATTRIBUTION.md`.

Inputs are only completed fixture ID/time, league/season, home/away team IDs
and full-time goals. Replays are ordered by UTC kickoff then provider fixture
ID and namespaced to one provider league. Outputs include both teams' average,
home and away Pi ratings, the venue-specific rating difference, relative
strength, 1X2 support probabilities, observation totals and venue observation
totals. Cross-league updates are rejected.

Sufficiency is explicit: fewer than four observations for either team is
`INSUFFICIENT`; four to seven observations or fewer than three observations at
the relevant venue is `LOW_SAMPLE`; at least eight per team and three at the
relevant venue is `AVAILABLE`; no observations is `UNAVAILABLE`. Only
`AVAILABLE` receives full ensemble reliability.

## Current supporting signals

The API-Football prediction adapter normalizes a currently fetched predicted
winner, 1X2 percentages, under/over indication, expected home/away goals and
provider comparison indicators. It checks league coverage, caches successful
responses for one hour, and can never satisfy the ensemble quorum by itself.

Current-market consensus reads every comparable bookmaker returned in the
current `/odds?fixture=` response. It rejects provider snapshots older than the
existing 3.5-hour policy, requires at least two bookmakers with a complete
outcome set, removes margin independently per bookmaker using multiplicative
normalization, averages fair probabilities, and records dispersion. Raw
current payload, GoalVision retrieval time, provider update time, bookmaker,
market, price and a provenance fingerprint are stored append-only. Quotes from
different market definitions are never combined.

Opponent-adjusted form compares each recent result with a deterministic
expectation derived from the same-league Pi baseline and applies a small capped
goal-margin adjustment. Each component retains opponent, venue, score,
expected result and adjusted performance.

Availability impact uses objective starts, minutes, recent starting frequency,
position and goal contributions when those provider fields exist. Missing
usage produces a conservative count-only fallback. It never creates a
subjective `key player` label.

## Ensemble and result evidence

The market-specific policy accepts available signals from the GoalVision
experimental model, Pi, API-Football prediction, current bookmaker consensus
and Current Match Intelligence. Each signal has an explicit reliability.
Current consensus and at least three usable independent signals are required;
weighted agreement must be at least 0.65, ensemble edge at least 0.04, and a
trustworthy probability spread above 0.22 or two strong opposing votes rejects
the candidate. Missing signals reduce the denominator rather than being
invented. Single odds remain at least 1.70 and three-leg Lab combos remain at
least 2.00 with distinct fixtures and teams.

Future settlements can be segmented separately for singles and combos by
market, league, capability tier, odds band, confidence, lineup state, Pi state,
API-prediction relation and current-consensus relation. No thresholds are
automatically optimized.

## Existing loss post-mortems

No retrospective provider prediction or bookmaker quote was fetched.
Consensus below uses only immutable raw current quotes already captured before
the corresponding V1 evaluation.

1. Stade Brestois 29 0–1 Paris Saint Germain, `BTTS_YES` at 1.75. V1 used
   0.7140 versus one-book implied 0.5714 (edge 0.1426), high confidence, with
   lineup not yet published. Seven-book current consensus was 0.5358, below
   the offered implied probability. Pi reconstruction had only 3/3 team
   observations (`INSUFFICIENT`). Brest had four recorded injuries, evaluated
   with count fallback (0.100 impact); PSG had none. V2 rejects for no
   independent-signal quorum and consensus not supporting value; unavailable
   lineup would additionally downgrade where supported.
2. Getafe 1–1 Deportivo La Coruna, `OVER_2_5` at 2.84. V1 used 0.4594 versus
   implied 0.3521 (edge 0.1073), medium confidence, with lineup not published.
   Seven-book consensus was 0.3281, again below implied. Reconstructed Pi was
   `LOW_SAMPLE` (4/4 observations, venue difference -0.2013) and is not a
   direct totals signal. Getafe had five injuries and one suspension (0.150
   count impact); Deportivo had one injury (0.025). V2 rejects for quorum and
   current-consensus value failures and downgrades incomplete lineup context.
3. Torino 0–2 AS Roma, `OVER_2_5` at 1.80. V1 used 0.7024 versus implied
   0.5556 (edge 0.1468), high confidence, with confirmed lineups. Eight-book
   consensus was 0.5494, slightly below implied. Pi had only 3/3 observations
   and is not a direct totals signal. Torino's five absences included three
   with persisted recent-start evidence, producing a conservative
   usage-weighted 0.2795 impact; Roma's one injury used the 0.025 fallback. V2
   rejects for quorum and current-consensus value failures.

## One real no-send rehearsal

Executed once at 2026-09-15 15:55:44 UTC for current/upcoming fixtures through
2026-09-17:

| Measure | Result |
|---|---:|
| Eligible fixtures discovered | 474 |
| Leagues represented | 126 |
| Tier A / B / C | 40 / 339 / 95 |
| Excluded before odds | 369 |
| Exact current-odds probes | 16 |
| Fixtures with fresh current odds | 7 |
| Candidate markets evaluated | 77 |
| Pi `AVAILABLE` fixtures | 0 |
| API prediction available fixtures | 5 |
| Current comparable consensus fixtures | 7 |
| V1 candidates | 3 |
| V2 candidates | 0 |
| Overlap / additional V2 | 0 / 0 |
| V1 candidates removed by V2 | 3 |
| API calls | 32 of 40 |
| Telegram sends | 0 |

The three removed V1 candidates were Alaves–Valencia `OVER_2_5`, Deportivo La
Coruna–Sevilla `OVER_3_5`, and Rayo Vallecano–Espanyol `OVER_2_5`; each failed
V2's independent-signal quorum. Seven odds fixtures spanned La Liga and the
Championship, versus persisted current V1 model evidence in La Liga only, a
one-league evaluated-coverage increase. The broader capability pass covered
126 leagues without a major-league restriction.

The call allocation was status 1, capability metadata 1, date fixtures 3,
current odds 16, result-history requests 4, current predictions 5 and injuries
2. The provider returned empty rows to the rehearsal's four `last=100`
finished-match requests, so Pi was honestly `UNAVAILABLE`. Validation identified
the provider's two-digit `last` bound; the adapter now requests `last=99`.
Per the one-rehearsal instruction this was not followed by a second real run.
The focused deterministic Pi tests remain passing. The run left eight calls
unused and 458 eligible fixtures unprobed; even spending all eight on odds would
leave at least 450 unprobed, proving that the 40-call ceiling still constrains
broad same-cycle coverage. No limit increase is recommended yet.

Runtime evidence is append-only in `var/lab_v2/shadow.db`; capability metadata
is in `var/lab_v2/capabilities.json`. These runtime files are not committed.
