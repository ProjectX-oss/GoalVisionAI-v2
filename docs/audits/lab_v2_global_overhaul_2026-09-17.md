# Global Lab V2 audit — 17 September 2026

Starting commit: `aa6c234cf7aedefbad38b033d13dd4fbfe4ad974`.
The working tree already contained extensive unrelated changes. This task's
commit contains only the Lab V2 extension, its new tests and documentation.
No existing user changes were reverted or bundled into it.

## What was wrong

The runner's name exclusion explicitly removed youth, academy, reserve and
friendly fixtures. Missing current capability metadata or an unsupported
capability tier also prevented discovery. The latest persisted baseline at
16:30 UTC contained 2,177 provider rows, 1,267 discovered fixtures, 910
pre-odds exclusions, 191 fixtures with odds, 1,835 evaluated markets and zero
ready candidates. Every evaluated market failed the three-family quorum;
1,825 also failed the global .04 edge threshold. Reasons overlap.

The baseline JSON includes a source-level trace through discovery, markets,
quotes, history, model inference, calibration, value, tracking, quality,
selection and publication eligibility. Old persistence does not contain every
requested per-stage count; unavailable historical measurements are not invented.

## What changed

The existing runner now admits all legitimate upcoming provider fixtures and
persists initial discovery immediately, including before enrichment can fail.
Capability metadata no longer excludes a competition. Thirteen deterministic,
versioned profiles drive signal priorities, uncertainty margins, history decay,
market preference and refresh plans. Explicit metadata/known provider IDs precede
narrow fallback patterns; ambiguous competitions stay UNKNOWN.

Profile evaluation keeps probability, current-price, disagreement and correlated
source safeguards. Optional data affects uncertainty. Two distinct evidence
families can support a clearly marked EXPERIMENTAL observation; three remain
necessary for STANDARD. Same-history Pi/CMI/model adapters still count as one
family. This is a deliberate Lab quorum change, not an unchanged quorum claim.
Uncalibrated probabilities are labelled. No market-only or nonpositive-value
selection is admitted, and no minimum-odds floor or daily bet target is added.

Global states, market gate evidence, stage counts and profile/league/country/
market throughput are persisted. Fair enrichment service counts and odds-page
continuation cursors survive restart. Exact failed odds refresh cannot fall
back to old prices. Global discovery recovery and the existing market tracking
queue retain deferred work. First-ready current-price observations and explicit
results support joint profile/league/market/lane statistics without tuning.

The architecture and policy detail are in
[the global policy guide](../LAB_V2_GLOBAL_COMPETITION_POLICY.md).

## Exactly one real no-send rehearsal

The run started at **17:10:14 UTC**, used the configured credential and requested
17–19 September UTC. It used an isolated `var/global_lab_audit/rehearsal.db`;
existing analysis snapshots were read-only. All three fixture dates succeeded.

| Observation | Count |
|---|---:|
| Provider fixture rows | 2,177 |
| Valid current/upcoming fixtures persisted | 2,016 |
| Invalid/non-upcoming rows accounted for separately | 161 |
| Fixtures with current usable odds / evaluated | 190 / 190 |
| Markets evaluated | 1,818 |
| STRONG / STANDARD / EXPERIMENTAL | 0 / 0 / 10 |
| Rejected market candidates | 1,808 |
| READY / EXPERIMENTAL_READY | 0 / 0 |
| TRACKING fixtures | 1,485 |
| UNAVAILABLE fixtures, retryable | 375 |
| REJECTED fixtures in that cycle | 156 |
| Real Telegram sends / Official mutations | 0 / 0 |
| API calls / reported daily remaining | 88 / 4,689 |
| Protected daily reserve | 1,500 |
| `PRAGMA foreign_key_check` violations | 0 |

The 10 experimental candidates were EARLY, outside the final-review window.
They are not publications, bets or proven profitable selections. The 1,860
retryable tracking/unavailable fixtures include incomplete odds coverage.
API allocation: 49 current date-odds pages, 27 completed-result history calls,
6 fixture calls (3 date discovery + 3 exact review), 3 exact current-odds calls,
1 league catalogue, 1 bookmaker catalogue and 1 status call. No historical
bookmaker odds endpoint was used. No second real run was executed.

## Correction from reviewing real evidence

A name-pattern bug incorrectly interpreted a league's letter B as a reserve
team suffix (for example Primera B Metropolitana). Classifier V2 restricts
that suffix to team names. Explicit reserve competition names still classify
normally. Three new regressions cover this distinction.

The original run's immutable V1 evidence remains intact. An **offline** replay
of the same captured fixtures, current quotes and completed results at the
original clock applied V2; it made **zero API calls**. Two evaluations produced
identical fingerprints. The replay still had 1,818 market evaluations and
10 early experimental candidates, but individual candidates can change when
classification changes history weighting. It is not a second live observation.

Corrected counts from that offline classification of the real fixture universe:

| Profile | Fixtures |
|---|---:|
| Senior men | 48 |
| Senior women | 63 |
| U17/U18 | 15 |
| U19/U20 | 110 |
| U21/U23 | 43 |
| Reserve/B teams | 145 |
| Lower division/semi-pro | 152 |
| Domestic cup | 122 |
| International club | 10 |
| International senior | 0 |
| International youth | 2 |
| Friendly | 2 |
| UNKNOWN | 1,304 |
| **Total** | **2,016** |

UNKNOWN is intentionally large: unfamiliar leagues are retained, not silently
labelled senior professionals. International senior fixtures were absent from
this observed window, while their inclusion is covered by deterministic tests.
The original V1 distribution is retained in the machine-readable report.

## Remaining bottlenecks and evidence limits

The raw rehearsal recorded 1,441 fixtures with budget-incomplete odds coverage,
203 with no current odds, 165 with stale odds, 10 with unnormalizable markets,
and 7 with unsupported markets. At the market level, 1,506 lacked independent
non-market evidence, 1,588 had nonpositive value and 1,782 fell below the
profile uncertainty/value margin. These overlapping counts must not be added.
The legacy three-family shortfall remains an auditable soft finding, including
on two-family experimental candidates; it is not by itself a global hard veto.

This demonstrates global inclusion and usable experimental paths, not complete
odds/enrichment coverage in one bounded cycle. Some profiles had no valid price
or sufficient evidence to produce an experimental candidate. Persistent cursors
and fair scheduling need repeated *future* authorized cycles to cover the
remaining work. No quota or safety control was bypassed to inflate throughput.

A frozen chronological **results-only** backtest used 1,848 captured completed
results. Only 493 targets had sufficient prior venue history; 1,355 were
explicitly unscorable. It used no odds, no ROI and no later-than-target results.
For the scored targets, profile decay versus previous linear recency yielded
Brier scores: HOME_WIN .242653 vs .242351; BTTS_YES .235526 vs .235310;
OVER_2_5 .237229 vs .239598. This mixed, sparse result is not evidence for
production promotion. No thresholds were tuned against these outcomes.

Forward result capture is an explicit service API; automatic integration with
the existing settlement worker is not installed. No live outcomes, calibration
improvement, ROI or profitability are claimed. Future manual policy review
requires 200 resolved observations over 90 days per joint bucket.

## Verification

Final adjacent verification: **142 passed**, including **37 new global tests**.
Whole-suite execution: **1,697 passed**, **563 passing subtests**, **1 failed**
and **1 collection error**. The final identity-conflict regression is included
in the adjacent run. Full details are in the companion JSON. Targeted tests cover the 225-fixture synthetic
universe, category retention, neutral/second-leg metadata, optional data,
positive experimental value, invalid probabilities/value, exact refresh failure,
tracking transitions, replay/restart, fairness, quota reserve, duplicate delivery,
current-price freezing and append-only guards.

No relational schema changes were necessary: new Lab document kinds reuse the
existing immutable store. Fresh main schema and schema-41 upgrade both reached
42 and passed foreign-key checks. Lab fresh/legacy-store upgrade and mutation
triggers passed. Compile and controlled import smoke passed with socket connects
blocked. The real Lab store passed `foreign_key_check`.

Protected `bankroll_accounts`, `bankroll_transactions`, `predictions`,
`published_predictions` and `result_publications` in `data/goalvision.db` had
identical before/after row counts and content hashes. Environment-file hashes
were unchanged. The Lab V2 timer remains disabled and inactive. Test delivery
checks use fake transports; no real Telegram sends occurred.

The whole-suite collection error imports nonexistent `_analysis_input` from
unchanged `app.lab_combo.cli`. The staging test separately expects
`CALIBRATION_EVIDENCE_STALE` but receives `CALIBRATION_REVIEW_MISSING` in the
existing calibration chain. Neither unrelated failure is hidden or fixed by
changing the user's existing work.

Next exact operational step: inspect `summary --human` for this rehearsal,
then authorize a separate manual no-send near-kickoff cycle using the persisted
Lab discovery/tracking store. Keep sending and timers disabled while collecting
forward evidence. Resolve the two repository-wide test issues before considering
any deployment.

## Files in the task commit

- `app/lab_v2_shadow/cli.py`
- `app/lab_v2_shadow/diagnostics.py`
- `app/lab_v2_shadow/ensemble.py`
- `app/lab_v2_shadow/forward_evidence.py`
- `app/lab_v2_shadow/global_evaluation.py`
- `app/lab_v2_shadow/profiles.py`
- `app/lab_v2_shadow/publication.py`
- `app/lab_v2_shadow/repository.py`
- `app/lab_v2_shadow/runner.py`
- `app/lab_v2_shadow/scheduling.py`
- `app/lab_v2_shadow/segmentation.py`
- `app/lab_v2_shadow/summary.py`
- `app/lab_v2_shadow/tracking.py`
- `app/lab_v2_shadow/README.md`
- `tests/test_lab_v2_global.py`
- `docs/LAB_V2_GLOBAL_COMPETITION_POLICY.md`
- `docs/audits/lab_v2_global_baseline_2026-09-17.json`
- `docs/audits/lab_v2_global_overhaul_2026-09-17.md`
- `docs/audits/lab_v2_global_overhaul_2026-09-17.json`
