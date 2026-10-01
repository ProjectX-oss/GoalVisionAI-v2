# GoalVision AI — apvienotā darbu plāna izpilde, 2026-10-01

Iziets cauri visiem plāna punktiem. Koda labojumi un research pamats ir sagatavoti atsevišķos Git zaros. Daļai punktu vēl vajag reālu nākamā cikla vai spēļu rezultātu evidence; tie nav marķēti kā production PASS.

**Operators uzlicis tikai divu failu discovery CPU labojumu `1a18dc0`; tā hashes un route pārbaudīti. Pārējais AI/ML darbu komplekts vēl nav deployots. Official, LIVE un champion nav mainīti. Historical bookmaker odds, manuāli provider pieprasījumi un Telegram testa sūtījumi nav izmantoti.**

## Statuss pa posmiem

| Posms | Izpildītais darbs / atradums | Secinājums |
|---|---|---|
| SQLite observer | Ilgo avota read transakciju aizstāj ierobežots konsekvents atmiņas snapshot; avota savienojums aizveras pirms aprēķiniem. | PASS testos; deploy/runtime pārbaude vēl vajadzīga. |
| ADMIN startup | Worker vairs nepieprasa setgid bitu, kas konfliktē ar systemd ierobežojumu; saglabājas vecākdirektorija pārvaldītā grupa. | PASS testos; sākotnējā runtime syscall atribūcija NEEDS_MORE_EVIDENCE. |
| 1. INVALID_MODEL_PROBABILITY | Izpētīti 63 incidenti 20 fixtures: visiem avots ir provider raw 0%, kas pārvēršas 0E+1. Tas nav Decimal serialization bugs. Guard un provenance regression testi saglabā rejection. | PASS izpētītajiem incidentiem. Nav clamp. |
| 2. Dataset readiness | Katrā PREMATCH mēģinājumā redzami sadalījumu counts arī cooldown laikā; COMBO/COMBO_LEG izslēgti no learning. | BLOCKED datu dēļ: TRAIN 581, VALIDATION 28, HOLDOUT 327, PURGED 807. Vajag vismaz 30 VALIDATION. |
| 3. Performance snapshot | Vienots SINGLE/COMBO W/L/VOID/partial void/pending/P&L/ROI/odds audits un negatīva EV atsevišķi segmenti. | PASS implementācijā un read-only snapshot. |
| 4. Accuracy policy | Noņemts neatbilstošais 1.30 Lab floor; netiek atjaunots 1.70/2.00. Saglabāta veco frozen ierakstu saderība. Bloķēti atkārtoti fixture SINGLE un neatbilstoši/duplikāti signāli. | PASS regression testos; policy forward kvalitātei NEEDS_MORE_EVIDENCE. |
| 5. Lead-time / odds-age | Iesaldēti atlases laiki un bucket; performance un no-pick/invalid/stale segmenti. | PASS; publication laika sliekšņi nav mainīti. |
| 6. De-vig | Multiplicative, Shin, Power un OO-EPC no tām pašām current quotes; provenance un forward metrics. | PASS research implementācijā; salīdzinājuma kvalitātei NEEDS_MORE_EVIDENCE. |
| 7. Kalibrācija | TRAIN raw modelis → atsevišķs calibration fit → vēlāks VALIDATION evaluation → untouched holdout; Platt, temperature, isotonic ar pietiekamu sample. | PASS sintētiskajā pilnajā ķēdē; reāli dati BLOCKED. |
| 8. xG shadow | Īsta venue xG/pretinieka xG provenance, Poisson 1X2/totals/BTTS, forward metrics. | Kods PASS; reālie ievaddati BLOCKED — svaiga īsta xG nav. |
| 9. Dynamic strength | Glicko-2 rating/RD/volatility, home advantage, recency/uncertainty, atsevišķs eksperimentāls draw link. | Kods PASS; 562 reālas current-context forward prognozes, kvalitātei NEEDS_MORE_EVIDENCE. |
| 10. Promotion ķēde | Automātiskais promotion izsaukums aizstāts ar read-only rekomendāciju; vajadzīga pilna evidence un manuāla, konkrētai rekomendācijai piesaistīta atļauja. | PASS testos; nekāda faktiskā promotion nav veikta. |

## Būtiskākie pierādījumi

- 2026-10-01 14:19 UTC dataset projekcija: 581 TRAIN / 28 VALIDATION / 327 svaigs SEALED_HOLDOUT / 807 PURGED. Neviens holdout un research cycle šajā darbā netika patērēts.
- Kalibrācijas papildu projekcija: 0 CALIBRATION_FIT / 6 VALIDATION_EVALUATION / 22 CALIBRATION_PURGED. Datus nedrīkst aizņemties no TRAIN vai holdout.
- 2026-10-01 14:15 UTC Lab SINGLE: 117 settled, 32 WON, 85 LOST, 0 VOID, 9 pending; flat P/L −25.83, ROI −22.08%.
- COMBO: 19 settled, 1 WON, 18 LOST; flat P/L −5.572924, ROI −29.33%. Tie ir agrāko, jau noslēgto politiku rezultāti, ne jaunās accuracy-combo politikas efektivitātes pierādījums.
- Deviņu šodienas publicēto SINGLE audits: astoņi negative-EV, astoņi market-only, visi deviņi UNCALIBRATED. Esošā totals/BTTS market-only atkāpe nav paplašināta. Ar šo sample nevar pierādīt accuracy-first kvalitāti; atlases 0.55 slieksnis nav mainīts.
- Current-results shadow probe: 1650 upcoming fixtures, 562 prognozes, 768 insufficient-team-history, 320 current-cache-unavailable. Pilnie ievaddati/fingerprints saglabāti saspiestā JSON; visi 562 artefakti atkārtoti validēti.
- xG avotā 423 CMI snapshots; jaunākais 2026-09-15, jaunākajos 25 nav xG lauku. Īsta svaiga xG vietā nav izmantoti provider goal bounds vai izdomāti dati.

## Discovery CPU aizture — cēlonis atrasts un labojums sagatavots

14:00 UTC discovery process pēc pēdējās provider atbildes 14:04:53 turpināja intensīvi izmantot CPU. Novērotā 17 minūšu intervāla lifetime CPU bija 87.3%; tas pats par sevi nepierāda SQLite lock.

Precīzo 2106 kandidātu no-send publication replay ar tukšu atmiņas ledger un bez optional context observer aizņēma 3.869 profiled sekundes un sagatavoja trīs COMBO no 118 eligible fixtures. Šis replay neaizstāj dzīvo ledger/adaptive/context stāvokli un nenosaka live aiztures cēloni.

Operators saglabāja live stack diagnostiku 15:27:44–15:27:55 UTC. Abi veiksmīgie paraugi rāda pilnu visu avotu validāciju available_pins ceļā pirms publication. 5594 avoti (91.6 MB) tika atkārtoti pārbaudīti katrai iespējai. Sagatavots viena cutoff avotu indekss ar datu/schema izmaiņu invalidāciju un pilnu sākotnējo validāciju. Reālo datu kopijā atkārtota meklēšana: 7.5567 s → mediāna 0.000093 s; auksta pārbaude joprojām 8.184 s. Trīs saglabāti snapshoti pilnīgi sakrīt pēc atkārtotas izveides. Tas vēl nav end-to-end production ātruma pierādījums. Operators 19:12 pēc Latvijas laika uzlika divu failu discovery pakotni; kontrolsummas un aktīvais route ir PASS. Nākamais dabiskais cikls paredzēts 19:30; tā runtime pierādījumi vēl jāsaņem. Runbook: docs/operations/CONTEXT_SCOPE_CPU_FIX_20261001.md.

Pilns jaunās COMBO politikas publication → receipt → settlement cikls vēl nav pierādīts. Pirmajā pēc-deploy ciklā kandidātu nebija; CPU cēlonis un offline labojums pierādīti, dabīga pēc-deploy cikla pārbaude vēl vajadzīga.

## Testi

- Pēc CPU labojuma: **1498 PASS + 34 subtests PASS**, 195.03 s; atsevišķi **6 installer PASS**, 0.30 s. Mērķētais context kopums **200 PASS**, 30.53 s (pārklājas).

- Kopējais PREMATCH/adaptive/Lab V2/COMBO/football-context tests: **1481 PASS + 34 subtests PASS**, 178.55 s.
- Pēc fāžu diagnostikas labojuma mērķētais kopums: **117 PASS**, 10.07 s; daļa pārklājas ar kopējo testu.
- ADMIN atsevišķajā zarā: **104 PASS**.
- Pilns sintētiskais PREMATCH governance tests izmanto 2500 resolved observations, reālu logistic training, kalibrāciju, validation, holdout, 140 vēlākus shadow iznākumus, manuālu promotion un integrity rollback.
- Trūkstoša, novecojusi vai citai rekomendācijai dota atļauja nemaina champion.
- Git diff whitespace pārbaude ir veikta. Testi nav production forward performance pierādījums.

## Git zari un komiti

Galvenais worktree:
`/home/arvis/goalvision-worktrees/forward-ai-ml-20261001`
Zars: `research/forward-ai-ml-20261001`

ADMIN worktree:
`/home/arvis/goalvision-worktrees/admin-worker-startup-20261001`
Zars: `fix/admin-worker-startup-20261001`

| Commit | Saturs |
|---|---|
| df13f2c | Avota ledger lock atbrīvošana pirms observer aprēķiniem. |
| 644d2ad | Provider zero root-cause evidence un regression tests. |
| 7914a04 | COMBO learning izolācija un katra research attempt preflight. |
| ee16392 | Vienots performance un timing audits. |
| 7a70f48 | Lab no-odds-floor politika, signālu un fixture exposure aizsardzība. |
| 2b1319e | Current-odds de-vig research. |
| 9cddccb | Kalibrācijas ķēde un obligāts manuāls promotion approval. |
| 88acedb | xG un dynamic-strength shadow pamats un current-data evidence. |
| fb52837 | Research provenance, health kļūdas ceļš un nepabeigtu fāžu diagnostika. |
| 994bdf8 | ADMIN startup permission labojums atsevišķajā zarā. |

Komiti ir VPS worktrees; push un merge nav veikts. Operators uzlicis tikai CPU labojumu `1a18dc0`; pārējie sagatavotie labojumi nav deployoti.

## Nākamie nepieciešamie pierādījumi

1. CPU labojuma operatora deploy un read-only verifikācija ir PASS. Vajag dabīgā pēc-deploy cikla ātrdarbības un delivery pierādījumus.
2. Atsevišķi apstiprināts izvēlēto labojumu deploy; sagatavotais kods vēl nav runtime.
3. Nākamā dabiskā research attempt pārbaude. Taimera nākamais izsaukums ir 2026-10-02 02:12 UTC, bet cooldown var vēl neļaut research cycle.
4. Turpināt resolved observations vākšanu līdz validation un calibration readiness PASS. Neapiet embargo vai minimumus.
5. Jaunās COMBO politikas pilns dabīgs delivery/settlement cikls un atsevišķa negative-EV forward analīze.
6. Svaigi īsta xG avoti un pietiekami paired forward iznākumi jauno comparatoru kvalitātes izvērtēšanai.
7. Tikai pēc pilnas evidence ķēdes — explicit promotion recommendation un atsevišķs manuāls approval.

## Mainītie faili pa commit

Tālāk saraksts ģenerēts no Git commit metadatiem.

### df13f2c

- app/adaptive_lab/observations.py
- docs/operations/FORWARD_STABILITY_20261001.md
- tests/adaptive_lab/test_source_snapshot.py

### 644d2ad

- docs/evidence/forward_ai_ml_20261001/invalid_probability.json
- docs/operations/INVALID_PROBABILITY_ROOT_CAUSE_20261001.md
- tests/adaptive_lab/test_provider_zero_trace.py

### 7914a04

- app/adaptive_lab/automl.py
- app/adaptive_lab/contracts.py
- app/adaptive_lab/datasets.py
- app/adaptive_lab/metrics.py
- app/adaptive_lab/models.py
- app/adaptive_lab/observations.py
- app/adaptive_lab/policy.py
- docs/evidence/forward_ai_ml_20261001/dataset_readiness_projection.json
- docs/operations/DATASET_READINESS_20261001.md
- tests/adaptive_lab/test_forward_metrics.py
- tests/adaptive_lab/test_no_combo_learning.py

### ee16392

- app/adaptive_lab/health.py
- app/adaptive_lab/metrics.py
- app/adaptive_lab/observer.py
- app/adaptive_lab/performance.py
- app/adaptive_lab/prematch.py
- app/lab_v2_shadow/audit.py
- app/lab_v2_shadow/cli.py
- app/lab_v2_shadow/publication.py
- docs/evidence/forward_ai_ml_20261001/performance_snapshot.json
- docs/operations/PERFORMANCE_TIMING_20261001.md
- tests/adaptive_lab/test_lab_product_schedule.py
- tests/adaptive_lab/test_performance_snapshot.py
- tests/adaptive_lab/test_v2_audit_snapshot.py

### 7a70f48

- app/lab_combo/service.py
- app/lab_v2_shadow/accuracy_combo.py
- app/lab_v2_shadow/public_presentation.py
- app/lab_v2_shadow/publication.py
- app/lab_v2_shadow/publication_policy.py
- docs/evidence/forward_ai_ml_20261001/accuracy_policy_audit.json
- docs/operations/ACCURACY_POLICY_AUDIT_20261001.md
- tests/test_lab_accuracy_delivery.py
- tests/test_lab_accuracy_policy_audit.py
- tests/test_lab_v2_public_presentation.py
- tests/test_lab_v2_shadow.py

### 2b1319e

- app/adaptive_lab/devig_research.py
- app/lab_v2_shadow/runner.py
- docs/operations/DEVIG_RESEARCH_20261001.md
- tests/adaptive_lab/test_devig_research.py

### 9cddccb

- app/adaptive_lab/automl.py
- app/adaptive_lab/calibration_research.py
- app/adaptive_lab/coordinator.py
- app/adaptive_lab/governance.py
- app/adaptive_lab/models.py
- docs/evidence/forward_ai_ml_20261001/calibration_readiness_projection.json
- docs/operations/CALIBRATION_AND_MANUAL_PROMOTION_20261001.md
- tests/adaptive_lab/test_calibration_research.py
- tests/adaptive_lab/test_dataset_readiness.py
- tests/adaptive_lab/test_governance_rehearsal.py
- tests/adaptive_lab/test_prematch_autonomy.py

### 88acedb

- app/adaptive_lab/dynamic_strength.py
- app/adaptive_lab/shadow_cli.py
- app/adaptive_lab/shadow_inputs.py
- app/adaptive_lab/shadow_research.py
- docs/evidence/forward_ai_ml_20261001/dynamic_strength_current_probe.json
- docs/evidence/forward_ai_ml_20261001/dynamic_strength_forward_captures.json.gz
- docs/evidence/forward_ai_ml_20261001/xg_input_readiness.json
- docs/operations/CONTEXT_SHADOW_RESEARCH_20261001.md
- tests/adaptive_lab/test_context_shadow_research.py

### fb52837

- app/adaptive_lab/devig_research.py
- app/lab_v2_shadow/cli.py
- docs/evidence/forward_ai_ml_20261001/discovery_cpu_diagnostic.json
- docs/evidence/forward_ai_ml_20261001/performance_snapshot.json
- docs/evidence/forward_ai_ml_20261001/test_summary.json
- docs/operations/FORWARD_STABILITY_20261001.md
- tests/adaptive_lab/test_cycle_phase_diagnostics.py
- tests/adaptive_lab/test_devig_research.py

### 994bdf8 — ADMIN

- app/admin_autorepair/worker.py
- docs/operations/ADMIN_STARTUP_20261001.md
- tests/admin_autorepair/test_worker.py
