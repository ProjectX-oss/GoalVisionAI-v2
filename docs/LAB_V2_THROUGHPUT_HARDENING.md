# Lab V2 throughput hardening

This Lab-only continuation starts at e710c303e60c93d3299941597d949f43f5a7f18b.
It does not enable timers, transport, publication, Official state, or models.

## Reviewed competition identity

`competition_registry.py` loads immutable versioned facts from
`reviewed_competitions.json`, keyed by `(API_FOOTBALL, league_id)` with a country
consistency guard. Names document identities; they are not lookup keys. The
classifier fingerprint includes the registry version and entire registry digest.
Each entry records profile, gender, age, competition type, tier, review reason,
and source. Extend this file through reviewed changes and bump its version.
The previous reviewed IDs were migrated with their captured country identity.

Identity evidence is the captured provider catalogue and fixture metadata from
2026-09-17, plus the explicitly reviewed competition examples in the task.
[API-Football documents its league ID catalogue](https://www.api-football.com/news/post/leagues-teams-ids).
[UEFA distinguishes domestic women's competitions](https://www.uefa.com/nationalassociations/women/),
[J.League identifies its professional competition](https://www.jleague.co/news/),
and [CBF records the Brazilian Serie A competition](https://www.cbf.com.br/futebol-brasileiro/times/campeonato-brasileiro/serie-a/2026/37743).

The existing `SENIOR_*_PRO` names are policy cohorts, not claims that every
player has a professional contract. Employment status remains explicitly
UNSPECIFIED. Elitettan retains a women-specific profile and SECOND tier.
Unreviewed ambiguous competitions remain UNKNOWN. No league quality scores exist.

Captured replay: UNKNOWN 612 -> 67, across 20 remaining league IDs; 237 convert
to senior men, 285 to lower division, 23 to senior women. A reviewed league's
competition profile takes precedence over incidental reserve-team names.

## Quota and pagination

`LAB_ADAPTIVE_QUOTA_V2` allows an operator ceiling up to 400, replacing the old
mandatory 100 maximum. Smaller explicit ceilings remain authoritative. The
runner protects the daily 1,500 reserve plus 100 settlement calls. Default
adaptive cycles use no more than a quarter of safely spendable daily headroom.
Provider minute remaining and per-request retry guards always bound actual work.
Unknown quota stops discovery after status. There is no automatic quota refill
assumption, waiting loop, or scheduler.

Due exact reviews run first (at most five fixtures); tracked due fixtures have
priority. Approaching tracked demand retains six calls per protected fixture.
Broad pages then complete dates chronologically, before optional enrichment.
The adaptive plan incorporates advertised remaining pages and discovery days.
The optional enrichment allowance cannot consume final-review reserve.

Each requested page appends a coverage checkpoint with maximum advertised total,
requested/valid/failed/unrequested pages, completion and explicit canonical
reason. Cursor recovery visits previously unrequested pages and fills gaps;
previously valid pages are not reused as current quotes. High-water totals
survive restart. Drift, malformed pages, timeout, provider/rate errors and budget
limits cannot be reported as a completed no-record sweep. Legacy detail codes
remain for existing consumers; `coverage_status` is the canonical code.

## Evidence and readiness

Experimental requires at least one genuine non-market predictive family.
Correlated result-history adapters remain one family. Current bookmaker consensus
is never a predictive family. A single-family Experimental probability is computed
only from its model family; current quotes validate market availability and
contradiction, and supply the offered price. Duplicate source names remain errors.

Standard requires two non-market families plus current consensus, existing
agreement and uncertainty-adjusted thresholds. Strong additionally requires at
least three non-market families and HIGH ensemble confidence. UNKNOWN and
FRIENDLY are Experimental-only. Optional missing inputs incur explicit penalties.
Youth and reserves have larger uncertainty and prefer goal markets; U21/U23
strength decays somewhat more slowly than younger youth. Lower divisions and
women have more uncertainty than established senior men. Women use their own
competition's venue results, never men's home-advantage constants. No fitting
against September 17 outcomes or optimization was performed.

All lanes require EV > 0, correct market mapping and fresh quotes. Arithmetic:
`fair_odds=1/p`, `edge=p-1/odds`, `EV=p*odds-1`.
The compatibility stage remains `READY_TO_PUBLISH`; `readiness_lane` explicitly
records EXPERIMENTAL_READY, STANDARD_READY or STRONG_READY. Experimental is not
required to become Standard. Exact status/odds requests bypass cache. Their
responses replace broad quotes even on failure. Readiness checks the actual
end-of-evaluation clock and five-minute review freshness.

Earlier stale/no-record/incomplete sweeps retain explicit retriable odds states
and refresh times. Exact failures/unavailable markets are distinguished in audit
records; subsequent manual review can recover transient failures. A rejected
final market retains its terminal projection, independently of other markets.
Forward capture freezes the entire ready candidate, including quote/bookmaker,
side, timestamps, uncertainty, families, classifier/policy, provenance and value.
Append-only fingerprints and first-selection deduplication remain enforced.

## Verification and bounded operation

Offline tests cover registry identity/collisions, independent-family gates, value,
quota, restart, exact refresh, readiness and 250-fixture accounting. Existing
Lab, adjacent and full suites remain required. Schema/import/startup checks use
disposable databases. Captured replay uses the original capture clock and current
quotes as captured then; it does not fetch historical bookmaker odds.

The manual runner supports `near_only=True`: restore tracked/discovered fixtures,
filter to the current 10–75-minute window, perform exact reviews, and skip broad
date fixture/odds scans. Zero due fixtures reports NO_FIXTURES_CURRENTLY_DUE.
Production CLI wiring and timer units are unchanged. The one-off current-data
verification uses an isolated Lab evidence database and explicitly passes the
existing credential file for reading only. No Telegram transport is constructed.

Baseline reconciliation: the parentless review snapshot contains two tested fixes
absent from e710c30: current-odds test fixtures with mandatory provider timestamps,
and read-only model-activation audit handling for a valid bootstrap with no
activation/rollback activity. Those exact patches are restored onto the normal
implementation ancestry so the reported clean baseline can be reproduced. No
activation, rollback or Official execution service is changed.

## Recorded no-send verification

Final suite: 1,821 passed, 563 subtests passed; focused/adjacent: 315 passed,
8 subtests passed. Fresh/upgrade schema checks and append-only guards passed.
The captured replay evaluates 952 markets and produces 34 early Experimental
observations. The results-only chronological diagnostic scores 548 fixtures from
1,446 available results, with no bookmaker prices or parameter fitting.

The due-only live review evaluated two fixtures and 18 markets; two single-family
candidates reached EXPERIMENTAL_READY after exact refresh. A local harness cache
path error stopped the initial status/leagues setup before any exact review;
the corrected resume reduced its ceiling by six calls to preserve the original
60-call worst-case bound. The completed review used 12 calls.

One live discovery used 134 calls, evaluated 1,978 valid upcoming fixtures from
2,177 provider rows, and completed all 83 advertised odds pages (14/28/41).
Current-odds fixtures: 185; stale: 491; complete no-record: 1,294; incomplete: 0.
It evaluated 1,733 markets: 108 Experimental, 1,625 rejected, zero Standard/Strong,
and two Experimental-ready observations. No output was sent. Protected Official
tables, credentials and timer state were verified unchanged.

The existing provider-origin freshness allowance remains 3h30m; the live exact
responses had an 18:00:18 UTC provider snapshot and approximately 19:50 UTC
retrieval. Exact retrieval is not evidence of a newly updated bookmaker price.
Daily remaining headers varied across endpoints (4,420 during pagination and
4,481 on the final response); actual request counts are recorded separately.
See `/home/arvis/goalvision_lab_v2_throughput_review.txt` for the complete review.
