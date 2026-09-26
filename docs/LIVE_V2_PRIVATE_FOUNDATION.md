# GoalVision V2 LIVE private foundation

Status: **LIVE_V2_PRIVATE_FOUNDATION_BLOCKED**

Base: `23e57e9c48f321b8ee5f67bd536fbb2b264f6cb0`
Branch: `codex/live-v2-private-foundation`
Scope: dormant, isolated application and review package. No deployment, sudo,
unit installation, Telegram calls, push or merge occurred.

## Decision and blockers

The offline foundation is implemented and tested. The single bounded real
rehearsal stopped before its first request: `QUOTA_RESERVED_FOR_PREMATCH`.
The captured safe LIVE budget is **zero**. No genuine fixture, market catalogue,
bookmaker coverage or candidate qualification was observed.

Three blockers prevent production approval:

1. Retained PREMATCH evidence cannot prove fresh provider quota or exclusive
   per-minute headroom across shared-token producers. Current remaining daily
   capacity also falls below the protected requirement.
2. `/odds/live/bets` has not been captured under a safe permit. No LIVE bet IDs
   are guessed or approved. The actual feed must provide independently identified
   bookmakers, complete comparable markets and current origin timestamps before
   market consensus can qualify.
3. Fixed private configuration, the user's `/start`, bot identity, competition
   coverage and a real no-send evidence rehearsal still require operator review.

**Exact next step:** review the frozen quota report and agree how fresh exact
provider headers and a real shared-token permit can be exposed to LIVE without
changing PREMATCH in this task. A service-inactive check alone cannot prove that
another worker will not consume quota between the check and LIVE's request.
Do not enable the proposed timer or sending to work around this blocker.
A future separately authorized infrastructure change may be needed. No boolean
configuration flag can grant a production shared-token permit here.

## Architecture and isolation

All new runtime code is in `app/live_v2/`:

| Module | Responsibility |
| --- | --- |
| `contracts.py` | Canonical finite JSON, hashes and UTC/freshness primitives |
| `schedule.py` | Eight Riga slots, DST and protected PREMATCH slots |
| `quota.py` | Read-only audit adapter, installed-contract check, LIVE reservations |
| `provider.py` | One current API request per invocation, bounded timeout, no retries |
| `state.py` | Fixture identity, cheap shortlist, actual shots/cards and missing fields |
| `markets.py`, `markets.json` | Reviewed LIVE catalogue contract, normalization, consensus |
| `policy.py` | Versioned deterministic market-value gates |
| `runner.py` | One discovery, one shortlisted fixture, minimum useful details |
| `store.py` | Dedicated LIVE append-only SQLite schema v1 |
| `delivery.py`, `presentation.py` | Frozen Latvian preview, private claims/receipts/reconciliation |
| `settlement.py` | Regulation result, 1u accounting, LIVE-only segments |
| `__main__.py` | No-send operator entry point |

No PREMATCH/Lab service, repository, prediction engine or delivery module is
imported. The only shared application primitives are the pure provider-header
normalizer and the lazy secret-safe Football credential resolver. LIVE never
binds PREMATCH's `SharedQuota`, changes its accounting or uses its LIVE allocation.
The existing `app/live_lab` independent-model implementation is not treated as
an independently validated Phase 1 probability engine.

The supplied task's direct-private product specification supersedes the older
channel-oriented LIVE descriptions in project rules. Official/PREMATCH policies,
thresholds, bankrolls and publication remain unchanged.

## Measured PREMATCH evidence

Frozen at **2026-09-26 19:46:41 UTC / 22:46:41 Europe/Riga**.
Source: read-only `var/adaptive_lab/audit.db` of the installed application.
Full sanitized calculation and fingerprint:
[`rehearsals/live_v2_private_foundation_2026-09-26.json`](rehearsals/live_v2_private_foundation_2026-09-26.json).

| Retained window | Cycle reports | Sum | Min | Median | p95 | Max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Latest 24h, all reports | 28 | 6,099 | 0 | 253 | 272 | 275 |
| Latest 24h, calls >1 | 24 | 6,099 | 225 | 255 | 272 | 275 |
| Latest 7d, all available reports | 167 | 17,968 | 0 | 1 | 281 | 299 |
| Latest 7d, calls >1 | 82 | 17,959 | 2 | 256 | 293 | 299 |

Zero-call reports and one-call reports are retained, not hidden. The second/fourth
rows merely show how pauses/status-only reports affect the distribution.
Seven-day evidence starts at 2026-09-19 20:00 UTC within the requested window.
These reports alone undercount total shared-token consumption:

| Measure | Latest 24h | Latest 7d |
| --- | ---: | ---: |
| Durable shared-token claims | 6,925 | 35,241 |
| Settlement category claims | 665 | 2,463 |
| Status category claims | 172 | — |

The earlier inspection at 19:26 UTC found 7,223 claims / 666 settlement calls in
the then-current 24h window. Rolling windows changed as older activity aged out;
the committed report above is the rehearsal's authoritative cutoff.

Last retained claim: 19:40:22 UTC, daily remaining **719 before** that attempt,
minute remaining **293 before** that attempt. Conservatively subtracting its
attempt gives **718 / 292**. These are historical upper limits on spendable
capacity, despite the initial frozen capture's `*_lower_bound` field names (the final adapter uses `*_upper_bound`): later
unobserved traffic can only reduce them. They are **not fresh exact response
headers**, and never authorize a production LIVE call.

At the rehearsal cutoff there were **zero future scheduled PREMATCH starts**
before midnight. The governor conservatively still protected one current
22:30–23:00 Riga slot, even though its latest completion record was available.
There were no future LIVE opportunities that Riga day either.

## Quota governor

Provider plan: 7,500/day, 300/minute. LIVE ceiling: 40 attempted calls per day,
5 per opportunity. Failed attempts count. No retries or status bootstrap bypass.
Both UTC and Riga day boundaries are conservatively covered by the daily count.

Before each request, inside a LIVE-only transaction:

1. Read recent cycle/claim evidence using SQLite `mode=ro`, `query_only=ON`.
2. Read active systemd `ExecStart` and `TimersCalendar`. Require the reviewed
   09:00–22:30 Riga PREMATCH half-hour cadence and a parseable configured ceiling.
   Drift/unavailable configuration fails closed; nothing is modified.
3. Require at least eight retained reports in 24h and a completed report at most
   one hour old with positive observed maximum. Missing evidence fallback is zero.
4. Protect each remaining/current PREMATCH slot by
   `max(installed cycle ceiling, ceil(1.20 × recent 24h maximum))`.
5. Protect results by
   `ceil(1.20 × max(100, last-24h settlement claims, max retained UTC-day settlements))`.
   Add 375 calls (5% of daily plan) as an independent safety margin.
6. Require verified provider headers at most 60 seconds old and an independently
   enforced shared-token exclusive permit lasting through the request. The retained
   adapter intentionally supplies neither because they are not present.
7. Deduct LIVE claims not yet reflected by the observation. A subsequent provider
   response can only reduce headroom. Bad headers/request failure block follow-up.
8. Limit by remaining daily/slot/minute capacity; persist decision, inputs and
   reservation **before** transport. Serialize opportunities with a LIVE-only lock.

The synthetic tests inject a permit; this is never a runtime override exposed
through the CLI or environment. The production adapter remains blocked until a
reviewed source of concurrency proof exists.

At the frozen cutoff:

- Per PREMATCH slot protected: `max(400, ceil(275 × 1.20)) = 400`.
- Settlement reserve: `ceil(max(100, 665, 547) × 1.20) = 798`.
- Protected remaining requirement: `1 × 400 + 798 + 375 = 1,573`.
- Full-day protected projection: `28 × 400 + 798 + 375 = 12,373`.
- Median-based full-day projection with reserves: `28 × 253 + 798 + 375 = 8,257`.
- Observed retained capacity after the last claim: at most 718.
- Safe LIVE budget: **0**.

The full-day projections describe demand, not permission to exceed 7,500.
PREMATCH already paces its own calls. LIVE cannot assume that it will continue
using only 237–253 calls, or take capacity that PREMATCH might later require.
Even the median projection exceeds the plan at this cutoff. A larger data set or
new plan could change the assessment; no such change is made here.

## Discovery schedule and coverage

Exactly 08:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00 and 22:00 Europe/Riga.
No 23:00 run. Starts are accepted only during the first five minutes of a slot.
Timer `Persistent=false` prevents catch-up requests. Local clock conversion
preserves eight slots on both DST transition days.

Two-hour polling bounds API spend and respects PREMATCH priority. It deliberately
misses matches and short-lived price opportunities; it cannot support continuous
in-play coverage, pressure trends between snapshots or trading execution.

One `/fixtures?live=all` request per accepted opportunity. Empty response stops
at one request. Immutable global response includes retrieval time, fingerprint,
provider evidence link, fixture/competition/season/team orientation/kickoff/status/
minute/score. Duplicate conflicting fixture IDs stop shortlisting.

Local filtering accepts only reviewed configured competitions and regulation
`1H`/`2H` states. It rejects finished, suspended, postponed, abandoned, halftime,
extra-time and invalid/missing scores. Ranking uses available local coverage and
PREMATCH context, proximity to minute 60, score difference and fixture ID tie-break.
Only one fixture receives details. No production competition allowlist is guessed.

Detail order: current fixture odds, statistics, then events if not embedded in the
global response. An unreviewed catalogue capture uses one detail slot. Without
three usable books, statistics/events cannot create a candidate, so those calls
are skipped. Lineups are not useful to the current conservative gates and are not
requested merely to fill a five-call allowance. The current-only transport supports
that endpoint for a future reviewed need; captured responses use the same immutable
store. There is no historical odds endpoint or automatic sportsbook execution.

The runner accepts optional locally supplied context for ranking and vetoes.
The operator CLI does not scrape an unreviewed PREMATCH context format: context is
explicitly absent until a reviewed read-only export adapter is supplied.

## State and probability policy

Version: `LIVE_V2_PRIVATE_POLICY_V1`; minute version: `LIVE_MINUTE_10_82_V1`.
These are conservative engineering gates, not calibrated winning probabilities.

| Gate | Explicit Phase 1 rule |
| --- | --- |
| Minute | 10–82 inclusive; first half <=45, second half >=46 |
| Kickoff plausibility | elapsed clock between minute−3 and minute+35 minutes |
| Score | integer 0–20 for each oriented team |
| State/quote age | <=30 seconds, no future timestamps |
| Bookmakers | >=3 distinct IDs and names with a full outcome set |
| Overround | sum of implied probabilities between 1.00 and 1.20 |
| Peer disagreement | maximum peer fair-probability difference <=8 percentage points |
| Price advantage | >=2 percentage points above reciprocal best price |
| Price validity | finite decimal >1 and <=1,000; no 1.60 floor |
| Completeness | both teams' SOT and total shots plus known red-card state: 5/5 |
| Red cards | any confirmed dismissal or unknown/disagreeing count blocks |
| Contradictions | none; VAR/ambiguous goal events require review |
| Duplicate | one publication claim per fixture/family/line/side/regulation semantics |

Within each bookmaker: `fair_i = (1 / odds_i) / Σ(1 / odds)`.
For each side, choose the best price among complete current books. Exclude that
book from the probability estimate and take the equal-weight mean from at least
two peers. This is **current market-value evidence**, not an independently
calibrated GoalVision model. PREMATCH probabilities are retained context only;
they never enter that formula. A critical PREMATCH context contradiction can veto.

Minute/score/player disadvantage dominate state gating. SOT and total shots are
mandatory pressure evidence. Box shots and saves are retained when provided.
Corners, possession, passes/accuracy, yellows and substitutions remain secondary.
Missing data stays `null`; no xG, post-shot xG, dangerous attacks, field tilt or
expected threat is derived or fabricated. Goal-event totals must agree with score;
second-yellow/red records for the same player are deduplicated.

Market agreement:

- Over: unresolved total, >=4 combined SOT, >=10 total shots.
- Under: unresolved total, minute >=30, <=4 combined SOT, <=12 total shots.
- BTTS Yes: not already resolved, both sides >=2 SOT and >=10 total shots.
- BTTS No: not already resolved, minute >=30, one side <=1 SOT, <=12 total shots.
- 1/2: selected side not trailing, SOT advantage >=2 and no total-shot deficit.
- X: tied score, minute >=30, SOT difference <=1 and <=12 total shots.

Possession/corners never create a candidate. Already resolved totals/BTTS reject.
There is no unsupported blending or independent LIVE probability fallback.
These boundaries require real availability review and forward evidence before any
production send; the current rehearsal supplies no evidence to loosen them.

## Provider markets and current odds

Research used the [official API-Football guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide)
and [LIVE endpoint documentation](https://www.api-football.com/documentation-v3#tag/Odds-(In-Play)).
The provider separates LIVE and PREMATCH bet catalogues. Current LIVE responses
have suspension/state flags; GoalVision must capture its own snapshots because
this endpoint supplies no historical archive.

`markets.json` is versioned with an empty mapping and an explicit unverified
status. `review_catalogue()` requires an actual `/odds/live/bets` payload plus
reviewed ID/name/family/full-match semantics and a review reference. A capture
never automatically approves an ID. Fictional test IDs 901–903 are test data only.

Supported mapping contracts: regulation 1X2, BTTS and main half-goal totals
1.5/2.5/3.5. No next-goal, team totals, quarter lines, Asian lines or Correct Score.
Normalize only matching fixture, oriented team IDs, score and minute. Retain
bookmaker ID/name, LIVE bet ID, market/side/line, decimal price, blocked/stopped/
suspended state, provider origin when supplied, retrieval time, state/catalogue/
source fingerprints. Missing bookmaker/origin stays in raw evidence and cannot
qualify as consensus. Do not relabel an unattributed aggregate as several books.
No stale snapshot is used after a current-request failure.

Actual mapping and bookmaker coverage are **unavailable**, not zero coverage.
A future safe capture may show that this feed cannot satisfy the multi-bookmaker
contract. If so, Phase 1 remains no-pick; never manufacture a bookmaker or model.

## Storage, delivery and private configuration

Schema v1 initializes only a dedicated LIVE SQLite file: `live_schema` and
`live_documents`. No PREMATCH migration is added. Kind/id primary keys, optional
parent foreign keys, content SHA-256, update/delete rejection and verified reads
protect replay. Changed bytes at an existing identity fail. Whole opportunities
have a process lock; reservations and delivery claims use SQLite transactions.
A crashed opportunity is not automatically retried.

Document kinds cover opportunities/skips, quota decisions, API claims/responses/
failures, global snapshots, shortlist, catalogue, normalized odds, state/features,
all candidate decisions/reasons, previews, claims, receipts/unknown delivery,
settlements and statistics. Statistics/events/optional lineups are retained in
their endpoint-tagged API response documents. No runtime databases or logs are
committed; `var/live_v2/` is ignored. Rehearsal evidence is locally retained there.

Private contract:

- `LIVE_BOT_TOKEN`: existing separate LIVE bot; never printed.
- `LIVE_PRIVATE_CHAT_ID`: positive fixed numeric user chat, never a group/channel.
- `LIVE_EXPECTED_BOT_USERNAME` and `LIVE_EXPECTED_BOT_ID`: explicit identity.
- `LIVE_DESTINATION_CONTRACT=PRIVATE`.
- `LIVE_USER_STARTED_BOT=true`: operator verifies that the user sent `/start`.
- `LIVE_SEND_ENABLED=false` by default.

`telegram-config-check` validates configuration without networking. No environment
file is loaded implicitly by the CLI. This task neither reads the private bot's
secret nor checks it online. Actual private identity/start evidence remains unverified.

`preview()` freezes exact Latvian plain-text bytes and configured destination.
`deliver()` requires enablement and `SEND_LIVE_TO_FIXED_PRIVATE_CHAT`, verifies
bot identity, validates freshness again after identity verification, then persists
a claim before transport. Acknowledgements must match private chat, bot identity,
message ID and exact text before a durable receipt is recorded. The real adapter
uses the documented [Telegram Bot API](https://core.telegram.org/bots/api#sendmessage)
contract. No adapter was invoked against Telegram during development.

Unknown/timeout/bad acknowledgement/receipt-persistence failure leaves a durable
claim. Automatic resend is forbidden even if the unknown record itself cannot be
persisted. Manual reconciliation accepts an externally verified acknowledgement
and operator reference, never releases the claim or sends again. Exactly-once
*confirmed accounting* and at-most-once transport attempts are achievable here;
Telegram cannot provide atomic commit with our database after network ambiguity.

There is no shadow channel, arbitrary candidate destination, operator send
command, automatic getMe or automatic result send. Both prediction and result
previews use professional Latvian labels and no raw IDs/enums. User-visible
probability is labelled `LIVE tirgus novērtējums`.

## Settlement and statistics

No post-selection odds are required. `settle()` starts from a confirmed LIVE
receipt and its immutable candidate. It validates fixture/team/league/season,
chronology, final regulation score and captured market semantics/price. FT and
explicit regulation results from AET/PEN can settle; overtime scores are ignored.
Suspended/abandoned/postponed states stay pending. Cancellation requires an explicit
void review reference. Invalid/Correct Score markets cannot settle even as VOID.

Fixed hypothetical 1u: WON = odds−1, LOST = −1, VOID = 0. Accuracy excludes voids;
ROI divides total P/L by all fixed stakes including voids. Separate LIVE segments:
overall, family, odds (<1.60 / 1.60–2.49 / 2.50+), minute (10–30 / 31–60 / 61–82),
and completeness. No PREMATCH statistics are read or updated. A statistics snapshot
is frozen with each settlement and feeds the private result preview.

The service accepts verified result evidence by dependency injection. A scheduled
result-fetch/send composition is deliberately not installed or enabled; any future
provider request must consume the same LIVE limits and governor. The inspection
CLI reports existing settlements; it never silently fetches or settles matches.

## Operator commands

Use the repository's Python environment:

```sh
python -m app.live_v2 status
python -m app.live_v2 quota --prematch-audit /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db
python -m app.live_v2 discover
python -m app.live_v2 fixtures
python -m app.live_v2 markets
python -m app.live_v2 candidates
python -m app.live_v2 settlements
python -m app.live_v2 statistics
python -m app.live_v2 telegram-config-check
```

Inspection is read-only and does not create a store. `discover` without
`--real-api` is offline. Explicit real discovery also needs retained PREMATCH
path, reviewed `--competitions`, and all governor proofs. `--rehearsal` permits
one out-of-schedule rehearsal, charges the nearest scheduled slot, and cannot
bypass the 40/day cap or replay itself in the same store. Do not create another
store to evade opportunity/claim history.

## Deployment review package

Prepared only in `app/live_v2/deployment/`:

- `goalvision-live-v2-private.service`: oneshot, own release/environment/state,
  PREMATCH audit read-only, no-send CLI.
- `goalvision-live-v2-private.timer`: exactly eight Riga opportunities, no catch-up.
- `private.env.example`: names/placeholders only; send disabled.
- `disable-live-v2`: stops/disables only the LIVE timer, preserving in-flight evidence.
- `REVIEW.md`: isolated release/config/unit review and installation checklist.

The package is **blocked**, not approved for installation. There is no executable
installer that can replace a PREMATCH release, and no PREMATCH stop/restart action.
Future direct-private sending needs a separately reviewed composition, safe quota
proof, mapping/coverage evidence and explicit operator authorization.

## Validation and rehearsal

Focused LIVE tests: **92 passed**. Related regressions: **151 passed**:
`test_api_football_odds_freshness.py`, `test_lab_delivery_accounting.py`,
`test_lab_probability_delivery_hardening.py`, `test_lab_v2_public_presentation.py`,
`test_lab_v2_prematch.py`. No unrelated historical/ML suite ran.

Coverage includes DST/eight slots, hard call limits, concurrent reservations,
PREMATCH priority/config drift, zero-call unsafe runs, one-call empty discovery,
one shortlisted fixture, state/cards/shots/missingness, mapping/consensus/overround/
best price/staleness/suspension, PREMATCH-prior independence, economic duplicates,
regulation settlement/voids, replay/immutability, private destination/acknowledgement,
ambiguous delivery/reconciliation/disk failure, default no transport, secret
redaction and separate storage. `systemd-analyze calendar` confirms the eight
proposed times. Compilation and whitespace checks pass.

The historical replay is explicitly fictional unit/integration evidence for
contracts and settlement determinism. There is **no real LIVE predictive backtest
or calibrated profitability claim**. A genuine chronological forward corpus must
precede any independent LIVE model or send-policy promotion.

Real rehearsal (after offline tests passed): **0 API calls**, **0 Telegram calls**,
`QUOTA_RESERVED_FOR_PREMATCH`. Live fixtures, shortlist, statistics, bookmakers,
verified bet IDs and whether a real candidate would qualify are **not observed**.
The stored attempted request was `/fixtures?live=all`; the governor rejected it
before transport or credential resolution. No candidate was manufactured.

## Future independent LIVE model

Retain genuine current snapshots, missed/missing states, rejections, exact prices,
minute/score/cards, publication receipts and regulation outcomes. Create temporal
splits with fixture-level separation, evaluate calibration and compare against
this frozen market-consensus baseline. Keep PREMATCH signals as explicit priors
or features only in a separately versioned, validated model. Promote no model
without independent backtesting, forward evidence and reviewed delivery policy.
