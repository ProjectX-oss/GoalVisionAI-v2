# EARLY candidate lifecycle audit — 2026-09-17

Verdict: bugs found and fixed. The 21:00 disappearance was a query/schema
misinterpretation; the 21:30 loss of final-review eligibility was a real
lifecycle defect. Neither match should be assumed publication-ready.

## Bounded operational evidence

All operational SQL used `sqlite3 -readonly`. No operational repository was
constructed and no full rehearsal documents were loaded into Python. Queries
restricted evidence by kind and UTC cycle range; candidate-ID joins use the
existing primary key. The 2.64 GB shadow database was not copied or rewritten.

| Fixture | Provider fixture ID | Kickoff UTC | Kickoff Europe/Riga |
| --- | --- | --- | --- |
| Atletico-MG – Santos | 1631513 | 2026-09-16 22:00 | 2026-09-17 01:00 |
| Independ. Rivadavia – Atletico Tucuman | 1637267 | 2026-09-16 22:00 | 2026-09-17 01:00 |

The implemented review window is **75 minutes**, not exactly 60: it opened at
20:45 UTC / 23:45 Riga. Both 21:00 and 21:30 cycles were within it. Minimum
publication lead remains ten minutes.

| Cycle UTC, September 16 | Atletico-MG DRAW | Rivadavia DRAW |
| --- | --- | --- |
| 17:00:19.333865 through 19:00:04.073256 | EARLY, 3.70, edge 0.0651477668, MEDIUM | EARLY, 3.00, edge 0.0442348799, LOW |
| 20:19:47.706656 and 20:30:04.158483 | REJECTED: MATERIAL_SIGNAL_DISAGREEMENT | EARLY, 3.10, edge 0.0546945937, LOW |
| 21:00:29.312692 | 11 markets evaluated; DRAW REJECTED after exact refresh | 11 markets evaluated; DRAW FINAL_REVIEW_REQUIRED after exact refresh |
| 21:30:17.362168 | Discovered; FIXTURE_DISCOVERED_ODDS_STALE; zero markets | Discovered; FIXTURE_DISCOVERED_ODDS_STALE; zero markets |

The earlier EARLY records used `LAB_V2_BROAD_COVERAGE_ENSEMBLE_V3`; the
20:19 onward records used V4 from `43a8a8a`. In the Atletico-MG 21:00 DRAW
evidence, API prediction supports DRAW (0.45), market consensus selects
HOME_WIN (DRAW probability 0.2637887447), and goals/form CMI selects AWAY_WIN
(DRAW probability 0.2785103507). Two independent, sufficiently reliable
opposing votes correctly trigger MATERIAL_SIGNAL_DISAGREEMENT. Pi is
LOW_SAMPLE and also selects AWAY_WIN. Weighted agreement is 0.6892039258;
edge is 0.0684852002. The prior CMI vote incorrectly selected UNDER_3_5 for a
DRAW evaluation; the earlier commit corrected that family selection and
grouped correlated history signals. This task does not undo those fixes.

Atletico-MG's 21:00 candidate identity is
`lab-v2-candidate-bf96fa82bfbcd581c6e250df527c6d8edd72bec61422821d4e7a9ff4524d53b6`.
Rivadavia's is
`lab-v2-candidate-0f59412f2fc8715656eda27dc6f8d5619568d82a8234b6df8a6ad5fc513553fe`.

Exact `/fixtures?id=` evidence at 21:01:01.939263 for Atletico-MG and
21:01:00.430726 for Rivadavia reports **NS** and the unchanged 22:00 UTC
kickoff. Their exact odds were retrieved at 21:01:02.442775 and
21:01:00.947517 respectively. Both have provider update 18:00:16 UTC.
Both lineup responses were NOT_YET_PUBLISHED. Rivadavia's explicit blockers
were CONFIRMED_LINEUPS_REQUIRED_FOR_MARKET and TIER_C_READINESS_QUALITY_REQUIRED.
No READY outcome exists for either fixture in these cycles.

At 21:30, all 27 September 16 current-odds pages were visited. The stale
classification proves each fixture joined a broad odds response; outright
provider omission did **not** cause this incident. The raw 21:30 pages were
not retained, so their precise provider timestamp cannot be independently
recovered. The last retained exact timestamp, 18:00:16, reaches the existing
3h30 freshness limit at 21:30:16, just before that cycle. This is consistent
with, but not a substitute for, the recorded stale classification.

Indexed CMI snapshot lookups in `var/lab_combo/analysis.db` found neither
fixture. Relevant fixture/candidate/single-publication lookups in
`var/lab_combo/ledger.db` also found neither fixture. The V2 evidence is the
source of their lifecycle; no V1 identity or team-name join is implicated.

## Why the original query returned zero

Commit `43a8a8a` stopped duplicating full candidate payloads in rehearsal
documents. These cycles use
`candidate_payload_storage=INDIVIDUAL_APPEND_ONLY_DOCUMENTS_NOT_DUPLICATED_IN_CYCLE`.
The 21:00 cycle has 190 individual candidate references; 21:30 has zero.
`json_each(document_json,'$.candidate_markets')` therefore returns no rows
even when candidates exist. The current schema must be inspected by reference:

```sql
SELECT e.created_at_utc,
       json_extract(c.document_json,'$.fixture_id') AS fixture_id,
       json_extract(c.document_json,'$.market') AS market,
       json_extract(c.document_json,'$.stage') AS stage,
       json_extract(c.document_json,'$.rejection_reasons') AS rejection,
       json_extract(c.document_json,'$.readiness_reasons') AS readiness
FROM lab_v2_shadow_evidence e,
     json_each(e.document_json,'$.candidate_ids') ids
JOIN lab_v2_shadow_evidence c ON c.kind='candidate' AND c.identity=ids.value
WHERE e.kind='rehearsal'
  AND e.created_at_utc >= '2026-09-16T21:00'
  AND e.created_at_utc < '2026-09-16T22:00'
  AND json_extract(c.document_json,'$.fixture_id') IN (1631513,1637267);
```

For a cycle with no candidates, inspect its `fixture_coverage` array by
fixture ID. These queries do not reconstruct or rewrite old results.

## Cause and cache/budget findings

The runner built `odds_fixtures` only from fresh, normalized broad discovery
results. Histories, predictions, preliminary candidates and the exact-refresh
shortlist all depended on that set. There was no durable pending-review
identity across cycles. Thus stale, omitted, or uncovered broad quotes could
prevent exact current refresh altogether.

At 21:00 the cycle used 75 calls, including four exact odds calls, four lineup
calls and seven fixture calls, with a 36-call final-review reserve. At 21:30
it used 52 calls: status 1, date fixtures 3, date odds 48. There were **zero**
exact fixture/odds/lineup calls, and the recalculated final-review reserve was
**zero**, despite reserving 48 calls before broad odds discovery. Both cycles'
adaptive effective ceilings were 100 (`FULL_MAXIMUM_SAFE`); at 21:30 observed
daily remaining quota was 3,664 against the unchanged 1,500 safety reserve.
This was an eligibility/reserve-construction defect, not exhaustion
of the 100-call ceiling. Some later-date pages were budget-limited; the two
fixtures' UTC date was completely covered.

Date discovery uses UTC, and both queried the correct September 16 date.
Riga midnight did not contribute. Date-odds caching was already disabled by
43a8a8a (`ttl=None`, `use_cache=False`). The old 15-minute page cache could
not serve a 30-minute operational cycle. Cache identity is endpoint plus a
canonical query fingerprint; payload identity additionally includes retrieval
time and content fingerprint. Cache hits preserve the original retrieval
time, never relabel it. Exact fixture odds use `/odds` with `{fixture: ID}`
and bypass cache; their persisted five-minute cache cannot suppress a forced
refresh. The FootballClient methods call HTTP directly without another odds
cache. Provider update and retrieval are separate provenance timestamps.

## Implemented changes

- Add one Lab-only latest-state table keyed by fixture ID/market, backed by
  immutable `final_review_tracking` documents. Retain identity/context, never
  reuse EARLY quote values as new inputs. Recover upcoming pre-upgrade EARLY
  individual documents through a partial kickoff index (maximum seven-day
  horizon); do not read entire rehearsal history or alter historical results.
- Restore missing tracked fixtures from IDs/current capability metadata;
  retain tracked fixtures in evaluation and reserve planning even without
  broad fresh odds. Put due tracked fixtures first in the bounded five-fixture
  shortlist. Budget/shortlist deferral remains explicit and retryable.
- Force exact current fixture and odds refresh, supported lineups/injuries,
  current-season results and supported predictions within the existing quota.
  Use refreshed kickoff for readiness. Record status changes and expiry.
- Replace broad quotes with the exact response even if it is empty, stale,
  erroneous or lacks the tracked market. No fallback to old prices. Provider
  HTTP/timeout/quota failures leave explainable evidence and do not trigger
  extra retries in the runner; the client retains its bounded retry policy.
- Retain EARLY outside the window; near kickoff expose FINAL_REVIEW_REQUIRED,
  READY_TO_PUBLISH, REJECTED with reasons, CURRENT_ODDS_UNAVAILABLE, ODDS_STALE,
  FIXTURE_INVALID, or EXPIRED. Record exact retrieval/provider timestamps and
  tracked broad-page timestamp/date/page diagnostics. Terminal states remain
  inspectable after later empty discovery cycles.
- Resolve individual candidate references in `summary --fixture-id` and show
  concise market reasons alongside tracked state. Preserve exactly-once
  publication by the existing fixture/market key across changed quote hashes.

Ensemble edge/agreement/independence thresholds, Tier C quality, confidence,
odds policy, bankroll rules, Official and publication policy are unchanged.

## Validation and operational handoff

Deterministic synthetic multi-cycle replay covers T-6h EARLY followed by
missing/stale broad odds at T-60, exact success/unavailability/staleness/timeout,
Riga midnight, changed future/past kickoff, invalid statuses, refreshed value
rejection, quota deferral, expiry, missing fixture discovery, upgrade recovery,
unexpired exact-cache bypass, and READY publication replay with fake transport.
No historical bookmaker odds or predictive-performance claim is involved;
the prediction algorithm was not changed.

Final command:

```bash
.venv/bin/python -m pytest tests/test_lab_v2_shadow.py tests/test_lab_combo.py tests/test_lab_combo_integrity.py tests/test_lab_experimental_selection.py tests/test_current_match_intelligence.py tests/test_api_football_odds_freshness.py tests/test_official_prediction_selection.py tests/test_official_publication_quality_gate.py -q
```

Result: **206 passed, 34 subtests passed in 11.77s**. Targeted diff whitespace
validation also passed. These are unit, integration and deterministic lifecycle
replay regressions, including the real Lab send boundary with fake transport.

Real Telegram sends: NO. Operational DB writes by tests: NO. Historical
bookmaker odds: NO. Official changes: NO. `.env` changes: NO. Systemd state
changes: NO. The actual units `goalvision-lab-v2-discover.timer` and
`goalvision-lab-v2-discover.service` were inactive on initial and final inspection.

Shadow and analysis database sizes/mtimes were unchanged during final test
verification. The independent, already-enabled Lab Combo settlement timer
remained active: its 04:50:02.839987 UTC run appended a ledger record during
the audit (zero API calls, `lab_telegram_sent=false`), matching its 06:50 CEST
systemd activation. Thus the live ledger did change externally; it was not
written by these tests. No systemd unit was changed to prevent that activity.

No systemd reinstall, daemon reload or service restart is required: the
oneshot service loads repository code on its next authorized invocation.
Normal repository initialization will add the Lab tracker table and index
then; this audit did not migrate operational databases. Leave the discovery
timer **STOPPED** for operator review. No live rehearsal or deployment was run.
