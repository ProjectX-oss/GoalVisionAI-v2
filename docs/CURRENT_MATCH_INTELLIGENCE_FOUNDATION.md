# Current Match Intelligence Foundation

## Targeted API-Football inventory

| Signal | Status before this task | Current source and boundary |
|---|---|---|
| Confirmed lineups, starters, substitutes, formation | PARTIAL | Coverage flags and a generic availability domain existed; `/fixtures/lineups?fixture=` is now collected and normalized. API-Football responses are treated as confirmed only when actual lineup rows exist. No probable lineup claim is made. |
| Injuries and suspensions | PARTIAL | Availability persistence existed without a live adapter. `/injuries?fixture=` now records player/team identity, provider type, reason and objective unavailable status. Suspension is used only for explicit suspension/card wording. No importance is invented. |
| Goals and home/away performance | AVAILABLE | Existing fixture history and Feature Store fields are reused; the new layer requests up to ten current-season matches and `/teams/statistics`. |
| Shots, shots on target, possession, corners, cards | PARTIAL | Not present in fixture-list history. Optional `/fixtures/statistics?fixture=` requests cover up to three recent fixtures per team while budget remains. Missing statistics stay missing. |
| xG/xGA | PARTIAL | No xG is fabricated. It is populated only when an actual `expected_goals` statistic exists in a historical fixture-statistics response. |
| Venue and competition context | AVAILABLE | `/fixtures?id=` supplies fixture, league/season/round, teams, venue and referee when the provider has it. |
| Travel context | MISSING | No trustworthy team-base/route evidence is available in the existing integration. |
| Rest and schedule load | AVAILABLE | Derived only from completed prior fixture timestamps: rest days, matches in the previous 7/14 days, and explicitly named cup/European load. No fatigue claim is emitted. |
| Player appearances/minutes | MISSING | The existing integration has no complete recent player-minutes feed. This foundation does not infer it from season totals. |
| Starting-XI continuity and missing recent starters | PARTIAL | Derived when the current confirmed XI and prior lineup rows are available. “Expected” means started in at least two of up to three observed prior XIs, never subjective importance. |
| Referee | PARTIAL | Stored when `/fixtures?id=` supplies it. |
| Weather | MISSING | No trustworthy free/current source is already connected. |
| Current odds/bookmaker/timestamp | AVAILABLE | Existing `/odds?fixture=` normalization and freshness policy are reused. Movement requires multiple genuine immutable snapshots and is not claimed from one response. |

## Endpoints

Already usable before this foundation: `/status`, `/leagues`, `/fixtures`
(date/range/id/team history), `/standings`, `/fixtures/headtohead`, and
`/odds?fixture=`. Newly exposed through the intelligence adapter:
`/fixtures/lineups?fixture=`, `/injuries?fixture=`,
`/teams/statistics?team=&league=&season=`, and
`/fixtures/statistics?fixture=`.

## Data and freshness design

Every normalized field carries provider, endpoint, retrieval time, optional
provider timestamp, fixture identity, and optional team/player identity.
Fields are labelled `PRE_MATCH_STABLE`, `PRE_MATCH_DYNAMIC`, or
`LINEUP_SENSITIVE`. The append-only SQLite snapshot and raw-response cache both
reject updates/deletes and use canonical SHA-256 fingerprints.

Freshness is independent: fixture identity 24 hours, lineup responses 30
minutes, injuries 4 hours, team statistics 6
hours, team history 6 hours, immutable historical detail 30 days, and odds 15
minutes in the collector while the existing API-Football origin/retrieval
validation remains authoritative. There is no global freshness clock.

Required context is planned after the cheap discovery filter. Cross-run cache
hits cost zero calls. Optional detailed statistics/prior lineups run only for
one strongest fixture and stop at the existing absolute 40-call ceiling.

## Future feature contract

The separate v1 contract contains form strength, rest days, seven-day schedule
congestion, confirmed-starter counts, missing recent starters, lineup
continuity, injury/suspension counts, and recent home/away goal rates. Current
odds and implied probabilities are also ordered per supported market; bookmaker
and provider timestamps remain field-provenanced market context. The current
live-78 ordering and artifact are unchanged.

Real Match Lab receives this evidence through the read-only
`RealMatchLabIntelligenceBridge`, resolved by fixture and analysis cutoff. The
bridge exposes the snapshot/fingerprint, freshness, missing data, blockers and
future vector, and explicitly does not inject it into live-78 inference.
