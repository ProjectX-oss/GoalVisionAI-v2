# GoalVision AI — V2 broad-coverage Lab launch

## Safety boundary

V2 is Lab-only and the only configured destination is `-1003510920417`.
Official publication, Official bankroll/statistics, the production champion,
startup and timers are untouched. `rehearse` is always no-send. An explicit
`controlled-cycle --send` may hand off only `READY_TO_PUBLISH` candidates to
the existing append-only Lab ledger, exactly-once claim and settlement path.

V2 persists two explicit boundaries. The immutable rehearsal document uses
`analysis_mode = LAB_V2_NO_SEND` because analysis and candidate generation
never construct Telegram transport; `publication_requested` and
`publication_enabled` retain the controlling CLI intent. The immutable
`publication_cycle` document then records whether transport was constructed,
the READY count, publication-attempt count and successful send count. Thus a
send-enabled cycle with no READY candidates correctly records requested and
enabled publication alongside zero transport, attempts and sends. Any durable
claim, including an indeterminate delivery, consumes that fixture/market key
for V2 replay safety.

Historical bookmaker odds are prohibited. V2 has no historical-odds adapter,
query, import, archive, training or backfill path. Pi and form accept only
completed football fixture identities, home/away teams and goals. Current
bookmaker quotes are recorded with actual provider name, provider update time,
GoalVision retrieval time, raw implied probability, multiplicative vig-removal
evidence and consensus probability.

## Broad discovery and capabilities

There is no major-league allowlist. UTC date fixture pages are joined to
current `/odds?date=...&page=...` pages before enrichment. This replaces the
old one-odds-call-per-fixture bottleneck. League/season coverage from
`/leagues?current=true` is cached for seven days and deterministically maps to:

- `TIER_A_FULL`: fixtures/current odds plus lineups, injuries, fixture and
  player statistics.
- `TIER_B_GOOD`: fixtures/current odds plus standings or fixture statistics;
  unavailable advanced endpoints remain optional.
- `TIER_C_BASIC`: results history plus current odds. It can become READY only
  with at least three usable signals, medium/high confidence, agreement of at
  least 0.75, and a fresh exact fixture/odds final review.

Unsupported endpoints are not called. Injuries and lineups are requested only
when their league coverage flag is true and only for a five-fixture shortlist;
lineups are never requested outside the near-kickoff review.

## Bookmaker relevance

`/odds/bookmakers` is cached for seven days. Exact normalized catalogue matches
for Optibet, OlyBet, Betsafe and TonyBet are tagged as reviewed Latvian-facing
brand matches. Bet365, Betfair, Betano, Pinnacle, William Hill, Unibet and
BetVictor are reviewed current-consensus sources. Unreviewed catalogue names
are not included in consensus. A brand tag never claims account-level Latvian
availability, and a public/internal quote is always attributed to the actual
provider returned by API-Football.

## Signals and ensemble

Pi is league-local, deterministic and match-result-only. Current-season
history uses the provider-valid `last=99`; a cached prior season is requested
only when current observations are insufficient and budget remains. The
opponent-adjusted form calculation retains expected result, actual result,
venue and capped goal-margin adjustment. Goals-based CMI uses recent venue
scoring/conceding rates, opponent-adjusted form and conservative availability
impact. API-Football prediction percentages, goal estimates and comparisons
are normalized as one supporting expert; goal estimates deterministically
produce totals/BTTS support.

The ensemble applies market-specific weights: Pi has increased relevance for
1X2; current goals/form context has increased relevance for totals/BTTS.
Current multi-book consensus and three usable signals are mandatory. Material
signal disagreement, low agreement, insufficient edge, extreme model-market
divergence or a severe current availability contradiction rejects the market.
Missing evidence is never fabricated.

## Quota and cadence

The hard per-cycle maximum is 100 and the daily safety reserve is 1,500.
`/status` is called first, then the effective budget is reduced from exact
daily/minute quota headers. Missing or ambiguous quota stops network expansion
after status. Current odds are date-batched and paginated; capability,
bookmaker, league history and prediction responses use endpoint-appropriate
caches. Identical league history is fetched once per cycle and reused across
fixtures and markets.

At a 30-minute cadence, the absolute discovery ceiling is `100 × 48 = 4,800`
calls/day. Adding the full 1,500-call operational reserve gives a conservative
6,300 calls/day, below the 7,500 daily plan. The cap is not a target; cache hits
and adaptive budgeting should keep actual use materially lower.

## 2026-09-15 no-send launch rehearsal

The one authorized real no-send run discovered 441 eligible upcoming fixtures
in 119 leagues from 843 provider rows: 37 Tier A, 313 Tier B and 91 Tier C. It
consumed 53 calls (`/status`: 1, `/odds/bookmakers`: 1, date fixtures: 3,
paginated current odds: 48), ended with 6,761 daily calls remaining and did not
skip an odds page for budget. No Telegram transport was constructed and no
Official state or timer was touched.

The run also exposed a launch-blocking clock bug: provider retrieval timestamps
several seconds after the cycle-start clock were incorrectly classified as
future. Consequently, the recorded zero current-odds fixtures and all downstream
zero coverage/candidate counts from this run are invalid as selection evidence.
The implementation now evaluates freshness at the later of cycle time and
retrieval time, while still aging cached quotes against the later cycle time.
An offline replay of the immutable current payload made no provider calls and
found 282 fixture joins, including 135 fixtures with usable fresh consensus and
597 available market families across Bet365, BetVictor, Betano, Betfair,
Pinnacle and William Hill. That replay validates the narrow freshness fix, but
it does not replace a complete real rehearsal because the blocked run never
requested result history, Pi, predictions or deep CMI.

For that reason the controlled send was deliberately not run: zero singles and
zero combos were sent. Continuous operation remains blocked pending one fresh
no-send cycle that exercises the full downstream pipeline. This is a small
operational-validation fix, not an architecture failure.

## Operator activation

Do not run this while the validation blocker above remains. After a clean
no-send cycle and controlled-cycle review, the command intentionally disables
the old V1 discovery timer, installs a separate V2 unit and starts only V2:

```bash
sudo systemctl disable --now goalvision-lab-combo-discover.timer && sudo install -m 0644 app/lab_v2_shadow/systemd/goalvision-lab-v2-discover.service app/lab_v2_shadow/systemd/goalvision-lab-v2-discover.timer /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now goalvision-lab-v2-discover.timer
```

This repository task does not execute that command.
