# PREMATCH daytime throughput and light-safety refactor

Implemented against starting commit `5076b4707f9f4161af9ec4e6000be188b1e92de7`.
The workspace already contained extensive unrelated modifications; these are
excluded from the task commit. This document and the package README are the
current task documentation; older audit reports remain immutable historical
records, not the active PREMATCH policy.

## Behavioral changes

The [package guide](../app/lab_v2_shadow/README.md) documents exact policy,
entry points and commands. The implementation changes only Lab V2 code, its
repository templates and focused tests.

- No Lab V2 minimum odds requirement. Existing Lab V2 price validation already
  accepted prices above 1; the new 1.40 positive-EV test protects that behavior.
  No Official odds or confidence policy was edited.
- Both CLI and runner pause at night before provider access. Daytime is 09:00
  inclusive–23:00 exclusive Europe/Riga, at 30-minute intervals. The template
  uses an explicit timezone and no persistent catch-up trigger.
- Provider quota, 28-to-1 remaining daytime slots, the minute balance and a
  400-call ceiling replace the fixed 1,500-call buffer. The result reserve is
  100 calls. Quota is a ceiling, never a spending target. The pre-existing
  repository template used 100 calls (the task's production example used 400);
  both runner support and template now use the requested 400 maximum.
- Priority classification and tier A reserve odds/history/prediction analysis
  before ordinary enrichment. Shared broad pagination is bounded. Final-review
  reservation is limited to one quarter of available cycle calls, so a large
  imminent fixture set cannot prevent useful analysis. The original T-75/T-10
  publication window and refresh checks remain intact.
- Missing/stale odds no longer decide admission to context/model analysis.
  Probabilities may be retained without quoting a current price or trusted EV.
- Broad-sweep fixture misses retain their original diagnostic and receive up to
  20 exact priority retries per cycle. This does not weaken provider-ID,
  bookmaker, current-price or timestamp checks. One exact response per priority
  fixture is reused within its current cycle.
- The requested edge, evidence and disagreement vetoes become LOW-confidence
  EXPERIMENTAL or TRACKING decisions. Existing uncertainty/weights determine
  lane thresholds; no new numeric penalty or replacement rejection stack.
- EV <= 0, invalid inputs and unsupported markets remain non-actionable.
  Duplicate claims, immutable odds, Lab destination and publication checks remain.
- Started matches retain valid result/audit evidence and cannot become new
  PREMATCH recommendations. Neither LIVE nor a live model is enabled.
- Fresh positive-EV unpublished observations use canonical `forward_selection`
  evidence, idempotent per fixture/market. `settle-shadow` uses the existing Lab
  regulation-time result rules and writes only shadow evidence. It also recovers
  interrupted source/outcome capture without changing the frozen source.

## Changed files

All paths are relative to the repository root:

- `app/lab_v2_shadow/runner.py`, `global_evaluation.py`, `profiles.py`
- `app/lab_v2_shadow/quota.py`, `scheduling.py`, `tracking.py`
- `app/lab_v2_shadow/forward_evidence.py`, `publication.py`, `repository.py`
- `app/lab_v2_shadow/cli.py`, `summary.py`, `diagnostics.py`
- `app/lab_v2_shadow/systemd/goalvision-lab-v2-discover.service`
- `app/lab_v2_shadow/systemd/goalvision-lab-v2-discover.timer`
- `app/lab_v2_shadow/README.md`
- `tests/test_lab_v2_prematch.py`, `tests/test_lab_v2_global.py`
- `tests/test_lab_v2_shadow.py`, `tests/test_lab_no_minimum_odds_policy.py`
- `docs/LAB_V2_PREMATCH_SIMPLIFICATION.md`

The low-odds combo test fixture now calculates probability from its quoted price
plus the stated edge. Its previous fixed probability of 0.86 at odds 1.10/1.15
was negative EV, contrary to that test's intended positive-value scenario.

## Evidence and scope limits

The exact `ODDS_COMPLETE_SWEEP_NO_FIXTURE_RECORD` path is `_date_odds` in
`runner.py`: the set of discovered fixture IDs is compared with IDs joined from
all valid pages. For this reason the reported 769 misses cannot be explained
by early bookmaker filtering in this implementation. Bookmaker filtering and
normalization have separate reasons. We did not perform production requests to
assert which provider fixtures actually recover; exact retry results are visible
per fixture alongside the broad reason.

The existing local Pi/history/CMI calculation and provider probabilities are
unchanged. The policy replay is synthetic and deterministic, not a claim of
historical ROI improvement or of a fitted confidence model. The production
counts supplied in the task are context, not reproduced observations.

This checkout contains no adaptive observer/research scheduler implementation or
its tests, and no weekly SINGLE/COMBO scheduler module. Existing Lab SINGLE/COMBO
settlement/statistics, forward-test weekly reporting, champion registry and
rollback modules were left unchanged and are included in suite validation.
It would be inaccurate to claim testing absent production-only components.
The smallest deployment follow-up for shadow results is to invoke the new
result-only `settle-shadow` command from the existing operational result schedule.
When the separate adaptive observer source is available, consume these canonical
observations/outcomes by their stable selection key; do not create another ML
store or add them to public betting statistics.

## Deterministic throughput replay

`test_representative_300_fixture_old_new_throughput` supplies 300 legitimate
fixtures: 100 fresh-odds fixtures, 100 stale-odds fixtures and 100 broad-sweep
misses, including two priority fixtures with recoverable exact odds. It injects
one fixed model probability vector to isolate admission policy from model skill.
Old admission counts reproduce the starting revision's fresh-odds-or-tracked
filter. New counts execute the runner, normalization, profile evaluation,
append-only evidence and no-send boundary.

| Counter | Old admission | New runner |
| --- | ---: | ---: |
| Discovered fixtures | 300 | 300 |
| Considered for model analysis | 100 | 300 |
| Fixtures with model probabilities | 100 | 300 |
| Current-odds coverage | 100 | 102 |
| Fixtures waiting for current odds | — | 198 |
| Fixtures tracking, including early review | — | 300 |
| EXPERIMENTAL markets | — | 102 |
| STANDARD / STRONG markets | — | 0 / 0 |
| REJECTED / actual hard-blocked markets | — | 408 / 408 |
| Markets with soft confidence penalties | — | 510 |
| READY / published | — | 0 / 0 |

Fixture and market counts have different denominators. Soft findings can coexist
with negative EV, so soft and hard counts overlap. No old lane totals are invented
for markets the old admission path never evaluated. A separate 300-market replay
uses probabilities 0.505–0.514 at odds 2.00: all 300 old decisions reject, while
all 300 new decisions retain identical probabilities in TRACKING. No publication
count or profitability target is asserted.

## Validation

Final validation completed on 2026-09-20:

- Targeted: **366 passed, 42 subtests passed** (25.57 seconds). Includes all Lab
  V2 tests, low-odds policy, Lab combo/integrity/experimental settlement, adaptive
  discovery, odds freshness, Official selection and Official publication quality.
- Complete suite: **1,818 passed, 563 subtests passed** (462.59 seconds), zero
  failures. Includes existing registry/rollback, shadow, result/statistics and
  forward-test weekly reporting checks. The earlier full run exposed the invalid
  negative-EV test fixture described above; the final complete rerun passed.
- `python -m compileall -q app tests`: passed.
- Import smoke: **23 Lab V2 library modules**, passed with socket connections
  blocked. Executable `__main__` is exercised through CLI help, not imported as a
  library. CLI help passed without provider or Telegram construction.
- `systemd-analyze verify` on both repository discovery units: passed.
- `systemd-analyze calendar` accepted the Riga expression and showed that a base
  time after 22:30 Riga advances directly to 09:00 the next day.
- Staged whitespace/diff checks: passed; exactly 20 task files, no secrets or
  database files, no unrelated pre-existing changes included.

All tests use synthetic providers and fake Telegram transports. External socket
connections were blocked in the full-suite pytest process; localhost remained
available for local console checks and existing subprocess smoke fixtures stayed
offline. No production data migration or API-heavy rehearsal was performed.

No database migration was introduced. Existing append-only tables store the
additional document kinds. Foreign-key and immutability/replay tests exercise
this path. Systemd calendar parsing and unit verification pass using local
`systemd-analyze`; only repository-controlled templates were read and changed.
No `/etc/systemd/system` file was modified, no service restarted, no production
deployment performed, and no real Telegram message sent.

## EXPECTED PRODUCTION IMPACT

On a day resembling 1,451 discovered / 260 evaluated, the old fresh-price admission
filter no longer prevents hundreds of stale/missing-price fixtures from receiving
available context/model analysis. Top competitions receive enrichment before
ordinary fixtures use that capacity, and recoverable priority date-sweep misses
get bounded exact odds requests. The removed edge/evidence vetoes retain usable
positive EV as EXPERIMENTAL or TRACKING instead of discarding the market.
Daytime pacing saves overnight discovery quota and releases available headroom
more readily near 23:00, while preserving 100 result calls.

Actual gains depend on provider coverage, available history, quota and real
probabilities. More analysis can coexist with zero READY selections. Missing
current odds, non-positive EV, final review and kickoff constraints still prevent
publication; neither bet counts nor profit are guaranteed.
