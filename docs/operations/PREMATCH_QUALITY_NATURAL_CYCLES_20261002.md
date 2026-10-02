# PREMATCH quality — natural-cycle verification, 2026-10-02

Scope: the three scheduled checks promised after the 2026-10-01 quality deployment. All displayed operational times are Europe/Riga.

## Result

- Deployment integrity: PASS — 805 Python modules and exact release environment verified again; all four PREMATCH environment routes and configured commands match; all four timers active.
- Discovery execution / no-odds-floor configuration: PASS. Publication in this cycle: BLOCKED by the existing 09:00–23:00 Lab kickoff window.
- Observer / full performance persistence: PASS.
- Dataset-readiness reporting and chronological replay: PASS. Training readiness: BLOCKED; forward training/publication evidence remains insufficient.
- Champion/holdout protection: PASS — generation and fingerprint unchanged, zero holdout results and no new training/cycle/activation records after deployment.

This does not establish predictive improvement or successful publication under the new policy.

## 22:30 discovery — 2026-10-01

Persisted cycle evidence starts at 22:30:03.361505 and completes at 22:32:17.141906.

135 fixtures discovered; 5 deeply considered/evaluated; 51 markets; 25 scheduled provider calls. These were natural production calls, not calls initiated by this verification. Two candidates reached upstream READY_TO_PUBLISH, but readiness is not final publication approval. Both were on the same fixture and had probability 0.45; they must not be described as passing the final accuracy-first 0.55 gate.

Publication attempts: 0; SINGLE sends: 0; COMBO sends: 0. Telegram transport was not constructed. Final health result is DEGRADED with no execution failure, due to publication blocking.

The five fixture kickoffs were:
- 23:00 — Talleres Córdoba Res. – Godoy Cruz Res.
- 23:00 — Sporting Cristal – ADT.
- 23:00 — US Virgin Islands – Saint Martin.
- 23:30 — Envigado – Orsomarso.
- 23:30 — Cumbayá – Santo Domingo.

All dates were 2026-10-01 in Riga. The same-day restriction was respected in this evaluated set. The existing publication_window policy accepts kickoff hours from 09:00 inclusive until 23:00 exclusive, so all 51 candidate publication checks reported FIXTURE_AFTER_LAB_CUTOFF.

The recorded policy is LAB_SINGLE_ACCURACY_FIRST_PER_FIXTURE_V2_NO_ODDS_FLOOR with minimum_published_decimal_odds=null. Four evaluated candidates had odds below 1.30. The probability threshold remains 0.55. Publication below 1.30 is not yet demonstrated because no ticket was sent in this cycle.

Operational observation: discovery spent 25 calls on five fixtures outside the publication kickoff window. This may be a useful later efficiency review; no discovery scope or publication time rule was changed during this audit.

## 22:38 observer — 2026-10-01

The observer started its persisted report at 22:38:02.077860; the complete structured journal output appeared at 22:38:23.947223 with exact invocation attribution.

PERFORMANCE status COMPLETE, version LAB_PERFORMANCE_SNAPSHOT_V1. Full SINGLE and COMBO financial/statistical evidence is persisted separately; 130 SINGLE and 106 COMBO segment rows are available. Dimensions include odds/probability bands, market, league, competition, lead time, odds age, confidence, model/market disagreement, probability kind, selection policy, signal basis and value cohort. Negative/non-positive EV cohorts are recorded separately.

20 natural observer snapshots were saved through 08:08 on October 2. Each inspected snapshot retained LIVE=DISABLED, heavy_training=false, api_calls=0 and telegram_sends=0.

Three MISSING_FROZEN_EVIDENCE single identities already appeared in the pre-deployment 22:08 observer and are unchanged. Financial history is included; missing probability evidence is counted explicitly, not fabricated.

Latest published-Lab snapshot (08:08 October 2, entire historical Lab cohort, hypothetical one-unit accounting):

| Type | Published | Settled | Won | Lost | Void | Pending | Flat P/L | ROI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SINGLE | 144 | 130 | 40 | 90 | 0 | 14 | -27.72u | -21.32% |
| COMBO | 32 | 21 | 2 | 19 | 0 | 11 | -4.588824u | -21.85% |

These totals include earlier strategies/cohorts and are not the performance of the newly deployed policy. They are also distinct from the 1,926 resolved research observations and from the separately frozen public V2 cohort.

## 05:12 research — 2026-10-02

The natural attempt used as_of=05:12:01.546744 and emitted final output at 05:12:02.033549.

The outer status was RESEARCH_ELIGIBLE, but research_due=false, cycle_due=false, automatic_eligible=false and reason=CYCLE_COOLDOWN. Therefore no challenger training was due. Independently, the newly required dataset-readiness projection reported RESEARCH_DATASET_NOT_READY:

| Partition | Actual | Required minimum |
|---|---:|---:|
| TRAIN | 626 | 1 plus training contract |
| VALIDATION | 3 | 30 |
| SEALED_HOLDOUT | 313 | 100 fresh |
| PURGED | 984 | — |

Blocking reason: VALIDATION_SAMPLE_INSUFFICIENT.

A read-only replay of the pure dataset constructor at the exact saved timestamp reproduced the whole readiness document and dataset fingerprint:
341b842716d2dbbd3a848d4908070dfcf9f241ebba1000740b23c0631387436c

Chronology checks passed:
- Fixture groups are disjoint across all partitions.
- All labels were available at the historical attempt time.
- TRAIN and VALIDATION prediction/settlement availability precede the next partition boundary by the required 24-hour embargo.
- SEALED_HOLDOUT observations were unconsumed.
- Only SINGLE/SHADOW learning sources occur; no COMBO learning observations.
- TRAIN: 176 fixtures; VALIDATION: 3 fixtures; HOLDOUT: 127 fixtures; PURGED: 328 fixtures.

Because this attempt was also under cooldown, it does not alone prove the training-due branch was reached and stopped specifically by readiness. That branch remains covered by the previously completed code tests; a naturally due attempt is still forward evidence to collect. No minimum, embargo or split threshold was relaxed.

## Champion and protected state

Champion generation:
generation-aa7e535b86267741aabc967e8044de2ab94a4334b1520a829414dd55ebc7371a

Champion fingerprint:
56498b2c53657b8ad66a016c91a91a51b6dd640a5d364d2f615171775188fe11

Total learning cycles remain 3; total holdout results remain 0. Since the quality deployment there are zero new learning_cycles, learning_datasets, training_runs, validation_results, champion_generations, activation_events or promotion_gates.

Weekly configuration remains unchanged. ADMIN was separately and explicitly updated this morning to admin-monitor-compat-a28f2a6; Codex Auto-Repair remains disabled. This later authorized ADMIN change is distinct from the unchanged ADMIN routes at the original quality deployment.

## Work performed

Read-only production inspection and pure in-memory dataset replay. No code fix was required for the three scheduled checks. No manual discovery/research/observer/settlement cycle, provider/model call, test Telegram send, deployment or production-state mutation was performed by this verification.

Changed repository files are this report and its summarized evidence only. Existing quality implementation tests are not rerun because no runtime code changed.

Next: collect more resolved forward observations until readiness passes, observe a normally scheduled publication-eligible discovery cycle, and retain the manual promotion requirement.
