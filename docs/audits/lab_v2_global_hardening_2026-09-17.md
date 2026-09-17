# Lab V2 global hardening — 2026-09-17

Status: one bounded current-data no-send rehearsal; no production activation or timer authorization. This report records coverage and limitations, not a profitability claim.

Starting commit: `902e96b7bc3b3b4ec33ecd987aaa5df642ae9bec`. The task commit is the commit containing this report.

## Changes and repository-wide failures

The `_analysis_input` collection failure came from an obsolete import through the Lab Combo CLI. The test now targets the still-active current-odds workflow helper. That re-export was removed before the global overhaul. The staging expectation was also obsolete: missing reviewed artifact provenance correctly rejects before stale calibration is checked. The test now asserts the provenance rejection and independently confirms the same calibration evidence is stale and non-actionable. Production safety guards were preserved.

Classifier V3 recognizes explicit lower-tier names and multilingual women’s metadata, requires terminal B/II team suffixes, and stops treating a club named Junior as an age group. Unknown metadata remains included. Current-date odds sweeps retain the largest advertised total, flag changing totals, and persist precise coverage causes. Today is prioritized, followed by uncovered fixtures per remaining page. Only demonstrably unused review reserve can expand the discovery allocation; the 100-call ceiling and 1,500 daily reserve remain unchanged.

Mandatory independent probability evidence is distinguished from soft optional context. Each market records offered implied probability, fair odds, edge, EV, probability kind, calibration state and signal requirements. Read-only summaries expose both fixture and overlapping market/gate reasons. No automatic tuning was introduced.

## Verification

Phase 1 full suite: **1,704 passed; 563 subtests passed; zero failures/errors**. Final full suite: **1782 passed; 563 subtests passed; zero failures/errors**. New hardening tests: 78; focused global/shadow/hardening: 178; adjacent Lab/current-odds checks: 267. Counts overlap and must not be added.

Compileall, controlled imports, inert CLI startup, fresh schema 42, schema 41→42 upgrade, migration replay, foreign keys, integrity, append-only update/delete guards, and deterministic captured-input replay passed. No schema change was required: cycle evidence extends existing immutable JSON records. The 225-fixture mixed-profile discovery regression and 225-fixture provider-timeout accounting regression pass. Existing exact-refresh failure, freshness, quota reserve, duplicate, restart and fair-scheduling regressions remain green.

## Baseline bottlenecks

All **1,441** originally incomplete cases belonged to September 19: page 11 of 40 was the last requested page, with 55 cycle calls consumed and 45 reserved for final review. There were 29 unrequested pages, not merely one missing frontier page. Odds existence for those fixtures was unobserved. On September 18 the advertised total oscillated between 28 and 23, and the old sweep stopped at page 24. Another **193** missing-record conclusions therefore lacked a stable complete sweep. The corrected unresolved baseline is **1,634**. Raw old bookmaker pages were not retained, so more specific retrospective filtering claims would be invented.

On identical captured inputs, UNKNOWN falls **1,304 → 619**. Conversions out of UNKNOWN: lower/semi-pro 666, women 18, reserve/B 1, international club 1. One formerly inferred reserve fixture becomes UNKNOWN after the stricter terminal-suffix rule. All 619 remaining cases lack deterministic category metadata. The replay retains all 2,016 fixtures and is deterministic; early experimental candidates change from 10 to 12, with no publication-ready selections.

The baseline value audit checked 1,818 markets: zero arithmetic mismatches, zero quote/market mapping mismatches, zero bookmaker normalization mismatches. Nonpositive EV affects 1,588 markets; missing independent probability affects 1,506; 1,390 overlap. These are not mutually exclusive rejection totals. Positive value and independent probability requirements remain intact.

## One real no-send rehearsal

Captured: `2026-09-17T18:08:24.995394+00:00`. Search dates: 2026-09-17, 2026-09-18, 2026-09-19. Provider rows: 2177; non-upcoming/invalid rows explicitly excluded: 180. Every legitimate discovered fixture has exactly one persisted current state.

| Metric | Before | After |
|---|---:|---:|
| Discovered | 2016 | 1997 |
| UNKNOWN | 1304 | 612 |
| Fixtures with markets examined | 190 | 94 |
| Fixtures with independent probability | 46 | 32 |
| Eligible early/final Lab candidates | 10 | 6 |
| Incomplete odds coverage (recorded baseline) | 1,441 | 329 |
| Complete odds coverage (recorded baseline) | 575 | 1668 |

Live snapshots differ in time and provider state. The separate captured-input classifier replay isolates code effects. “Complete coverage” means the fixture record was observed or its date sweep completed stably; it does not mean usable current odds existed. Markets examined using bookmaker evidence alone are not independently predicted.

Throughput: `{"experimental_candidates": 6, "fixtures_discovered": 1997, "fixtures_scored": 94, "fixtures_tracking": 1925, "fixtures_with_current_odds": 94, "fixtures_with_independent_probability": 32, "published_candidates": 0, "rejected_candidates": 946, "standard_candidates": 0, "strong_candidates": 0}`.
Fixture states: `{"REJECTED": 72, "TRACKING": 356, "UNAVAILABLE": 1569}`.
Candidate lanes: `{"EXPERIMENTAL": 6, "REJECTED": 946}`. Ready to publish: **0**.

| Profile | Valid upcoming | Usable odds / examined | Provider records | September 17 upcoming |
|---|---:|---:|---:|---:|
| SENIOR_MEN_PRO | 48 | 5 | 49 | 1 |
| SENIOR_WOMEN_PRO | 81 | 0 | 90 | 0 |
| YOUTH_U17_U18 | 15 | 0 | 15 | 0 |
| YOUTH_U19_U20 | 108 | 0 | 114 | 0 |
| YOUTH_U21_U23 | 43 | 1 | 44 | 0 |
| RESERVE_OR_B_TEAM | 138 | 3 | 147 | 2 |
| LOWER_DIVISION_OR_SEMIPRO | 815 | 32 | 852 | 9 |
| DOMESTIC_CUP | 121 | 0 | 132 | 3 |
| INTERNATIONAL_CLUB | 12 | 0 | 21 | 9 |
| INTERNATIONAL_SENIOR | 0 | 0 | 0 | 0 |
| INTERNATIONAL_YOUTH | 2 | 0 | 6 | 0 |
| FRIENDLY | 2 | 0 | 4 | 0 |
| UNKNOWN | 612 | 53 | 703 | 3 |

No legitimate fixture was filtered because of competition category. Zero categories are explained explicitly in the JSON report; non-upcoming provider rows are distinguished from zero provider returns.

### Odds coverage causes

| Cause | Fixtures |
|---|---:|
| CURRENT_ODDS_AVAILABLE | 94 |
| ODDS_BOOKMAKER_FILTER_REMOVED_ALL | 7 |
| ODDS_COMPLETE_SWEEP_NO_FIXTURE_RECORD | 1159 |
| ODDS_DISCOVERY_BUDGET_LIMITED_PAGINATION | 329 |
| ODDS_INSUFFICIENT_COMPARABLE_BOOKMAKERS | 5 |
| ODDS_STALE | 403 |

### Market rejection reasons

Percentages use all evaluated markets as denominator. Reasons overlap.

| Reason | Markets | Percent |
|---|---:|---:|
| INSUFFICIENT_INDEPENDENT_SIGNALS | 935 | 98.214% |
| VALUE_BELOW_PROFILE_THRESHOLD | 922 | 96.849% |
| ENSEMBLE_EDGE_BELOW_0_04 | 916 | 96.218% |
| NON_POSITIVE_VALUE | 820 | 86.134% |
| NO_INDEPENDENT_NON_MARKET_EVIDENCE | 696 | 73.109% |
| MATERIAL_SIGNAL_DISAGREEMENT | 133 | 13.971% |
| WEIGHTED_AGREEMENT_BELOW_0_65 | 38 | 3.992% |

API calls: **93**; cycle allocation remaining: **7**; observed daily quota remaining: **4519**. Daily reserve: 1,500. Awaiting near-kickoff review: **1925**.

Provider-origin quote age distribution: `{"60_TO_210_MINUTES": 106, "OVER_210_MINUTES_STALE": 403}`. The existing provider-origin limit remains 12,600 seconds; exact review freshness remains separately enforced.

Rehearsal `PRAGMA foreign_key_check`: `[]`; `PRAGMA integrity_check`: `ok`.

## Safety and limitations

The live run does not demonstrate improved candidate throughput: independently supported fixtures fell 46→32 and eligible early candidates fell 10→6 as the current-odds snapshot changed. Women and U17–U20 fixtures remain visible, but had no usable current odds and therefore did not reach live scoring in this cycle. Their profile-specific odds reasons are included in the JSON. Near-kickoff exact refresh remains covered by deterministic tests; this snapshot generated only early candidates and no exact-refresh call.

Zero Telegram transports/sends or Official publications by this task. Protected prediction, publication, bankroll and result-publication table hashes match the starting snapshot. Zero Official bankroll/statistics changes, zero `.env` changes, zero timer enablements, and zero production activation. Lab discovery remains disabled/inactive. The already-enabled settlement timer was untouched. Historical bookmaker odds were never requested.

- UNKNOWN remains for ambiguous league metadata; no professional/gender/age status is fabricated.
- A finite cycle can leave date odds sweeps incomplete; current quotes cannot prove absence across changing pagination.
- No independent probability can be manufactured from market consensus or missing optional context.
- Ensemble remains uncalibrated Lab evidence; no Official promotion or activation.
- No timer re-enable is authorized by this report.
- Women and U17-U20 fixtures survived discovery but had no usable current odds in this live snapshot; their real end-to-end scoring is not demonstrated.
- This live snapshot produced only early candidates and did not exercise exact near-kickoff odds refresh; deterministic tests cover that contract.

Full persisted local evidence: `var/global_lab_hardening/rehearsal.db`, `rehearsal.json`, `classification_audit.json`, `baseline_odds_audit.json`, `value_audit.json`, `offline_replay.json`, and test logs. Database files, secrets and logs are not committed. Aggregate machine-readable evidence and remaining UNKNOWN league metadata are in the adjacent JSON report.

Next exact step: inspect the no-send summary below and review the remaining UNKNOWN league metadata and incomplete date sweeps before authorizing any later bounded cycle. Keep the Lab discovery timer disabled.

```bash
.venv/bin/python -m app.lab_v2_shadow.cli summary \
  --shadow-database var/global_lab_hardening/rehearsal.db --human
```

## Files changed

- `app/lab_v2_shadow/diagnostics.py`
- `app/lab_v2_shadow/market_consensus.py`
- `app/lab_v2_shadow/odds_coverage.py`
- `app/lab_v2_shadow/profiles.py`
- `app/lab_v2_shadow/quota.py`
- `app/lab_v2_shadow/runner.py`
- `app/lab_v2_shadow/signal_evidence.py`
- `app/lab_v2_shadow/summary.py`
- `docs/LAB_V2_GLOBAL_COMPETITION_POLICY.md`
- `docs/audits/lab_v2_global_hardening_2026-09-17.json`
- `docs/audits/lab_v2_global_hardening_2026-09-17.md`
- `tests/test_lab_v2_hardening.py`
- `tests/test_source_commit_provenance.py`
- `tests/test_staging_model_operations_rehearsal.py`
