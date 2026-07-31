# Reviewed Real Historical Data Foundation

## Outcome

The first real-data pilot uses seven immutable operator-acquired OpenLigaDB
Bundesliga season snapshots (2018/19 through 2024/25). OpenLigaDB documents its
API data under the Open Database License. The review approves controlled internal
derived-data use with attribution; raw snapshots remain outside Git. Commercial or
production use still requires a separate legal review.

The pilot imported 2,142 genuine completed matches. The canonical live projection
produced 2,085 examples after honestly excluding 57 early matches for insufficient
team history. No example was excluded for invalid provenance. The dedicated audit
checked all 2,085 examples and passed with no future, target, or equal-kickoff source
references.

## Source and identity controls

Every source decision records ownership, URL/API identity, access and authentication,
terms, robots/public-access considerations, redistribution and commercial boundaries,
rate-limit knowledge, fields, coverage, cadence, reliability, storage and evidence
permissions, review time, operator note, and a typed approval state. Only the two
approved statuses permit manifest construction.

Manifests bind source ID and version to ordered filenames, SHA-256 hashes, byte/row
counts, match count, field coverage, competition/season scope, dates, provenance,
parser and normalization versions. Reusing a source ID/version for different content
is rejected. Team resolution supports only reviewed exact source IDs or unambiguous
exact normalized aliases; fuzzy similarity never merges teams.

## Live-78 derivation and missingness

The single schema authority remains `goalvision_model_input_v1` / `v1`, fingerprint
`048405d961c2752d492819479788274942cd65c3397f9c9120c83c1a93e5be8a`.
All 78 features are reported in canonical order. The pilot has 43 fully supported,
6 partially supported, and 29 optional-missing-acceptable features. No required
feature is blocking.

Recent form, venue form, season-to-date aggregates, goals, clean sheets, BTTS,
totals, points, rest, congestion, and available H2H are calculated only from matches
strictly before kickoff. Lineups, injuries, suspensions, player availability,
post-match statistics, and genuine pre-kickoff odds are not supplied and remain
explicitly missing. Values are not invented. Equal kickoffs are indivisible in the
split and cannot see one another during projection.

## Split, candidates, calibration, and TEST

The chronological split contains 1,459 TRAIN, 313 VALIDATION, and 313 TEST examples.
Two deterministic compatible logistic candidates were trained with regularization
`0.001` and `0.01`. Preprocessing is fitted only on TRAIN; calibration is fitted only
on VALIDATION; TEST is loaded only for final predictive evaluation.

Both calibration-quality reviews are `CALIBRATION_QUALITY_INELIGIBLE`: calibrated
maximum calibration error exceeds policy for `AWAY_WIN` and `OVER_2_5` in both
candidates. The persisted target-level reports retain support, method, ECE/MCE,
scoring degradation, clamp/extreme frequency, and adjustment diagnostics. This
outcome is not weakened. On TEST, the baseline mean Brier/log loss are approximately
0.214997/0.619939 and the regularized candidate values are approximately
0.214817/0.619445. These are historical descriptive measurements, not evidence of
future quality or profitability.

No genuine immutable pre-kickoff odds were present. Betting, ROI, CLV, bankroll,
drawdown, and risk evidence are therefore unavailable rather than fabricated.
Comparison is `INSUFFICIENT_REAL_EVIDENCE`; shadow evidence is insufficient; the
independent staging audit is blocked; no activation or Real Match Lab rehearsal ran.

## Evidence tiers and safety

`CONTROLLED_SYNTHETIC`, `REVIEWED_REAL_HISTORICAL`, and `PRODUCTION_AUTHORIZED` are
explicit immutable tiers. Reviewed-real evidence may support internal review but is
not automatically publication eligible. Production authorization is a separate
future decision and must carry an explicit authorization reference.

The canonical evidence is
`docs/rehearsals/live_78_reviewed_real_historical_foundation_2026-07-31.json`.
It records zero Telegram calls/sends, zero delivery records, zero Official
publications, zero Official bankroll/statistics changes, zero production activation,
and disabled scheduling. The protected `data/goalvision.db` SHA-256 was
`61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0`
before and after.

## Refresh and next gate

An operator must re-review source terms, acquire versioned snapshots outside Git,
record acquisition time, validate fingerprints, and run against a new isolated
database. Runtime never downloads historical data.

Before any genuine Lab publication can be considered, acquire lawful immutable
pre-kickoff odds with event/timestamp/bookmaker provenance, rerun TEST betting and
risk evidence, obtain acceptable per-target calibration quality, complete settled
shadow evidence, pass the independent audit, and receive separate explicit
publication authorization. Production activation is outside this task.
