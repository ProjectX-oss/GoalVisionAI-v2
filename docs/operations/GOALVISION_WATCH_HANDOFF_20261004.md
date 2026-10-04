# GoalVision AI — konsolidētais Watch handoff, 2026-10-04

Authoritative learning/performance cutoff: **2026-10-04T13:46:24.308796+03:00 (Europe/Riga)**; UTC `2026-10-04T10:46:24.308796+00:00`. Auditā izmantoti VPS read-only dati, immutable release faili, Git objekti un operatora sanitizētais ADMIN eksports. Vēlākās naturālās darbības nav pieskaitītas šim snapshotam. Testi un smokes darbojas ar bloķētu tīkla savienošanu, normālu prioritāti/nice=10.

## 1. CURRENT_REPOSITORY_STATE

**NO_CHANGE.** PREMATCH faktiskā instalācija ir `/opt/goalvision-prematch-combo-market-parallel-abddde7-20261004`, forward research — `/opt/goalvision-dixon-coles-forward-ebd0924-20261004`. Monitoram saglabāta operatora health-projection instalācija. Aktīvās politikas: SINGLE ≥1.50; katra COMBO kāja ≥1.30; papildu combined floor nav. DC agreement un market parallel Lab līnijas, Riga today-only, early COMBO loss, remaining-leg tracking un result replies saglabāti.

**NO_CHANGE.** `/home/arvis/GoalVisionAI` HEAD ir `fadd59d7d9492133f84d9d80c9a72dad14c57c67`, branch `codex/lab-v2-global-overhaul-2026-09-17`, ar **220 iepriekš pastāvējušām izmainītām/neizsekotām takām**. Šis checkout nav production source-of-truth; servisi izmanto immutable releases. Tas netika tīrīts, labots vai pushots. Pārskatītais sākumpunkts ir `d1b6147f4dbc475796fe45f4a05d25f2a4ba7abb`; darbs veikts atsevišķā `audit/watch-reconciliation-20261004` worktree. Kvotas pakotnei ir atsevišķs tīrs branch `fix/settlement-status-reserve-20261004`, balstīts tieši uz d1b6147, bez jaunā research moduļa ievietošanas PREMATCH release.

Evidence: `docs/evidence/watch_reconciliation_20261004/repository_state.json`.

## 2. DIXON_COLES_FORWARD_REPAIR

**NO_CHANGE — PASS.** Watch sākotnējais blockers vairs nav aktuāls. Repair ir **`ebd09247ad34a578b330b79a02a17e87fb2b8628`**, un tas jau bija operatora deployots pirms šī uzdevuma. Trūkstošais `app/lab_v2_shadow/reviewed_competitions.json` release ir klāt. Visi **843** instalētie Python/JSON faili sakrīt ar package manifestu; `845` package checksum ieraksti iztur SHA256 pārbaudi. Kārtots deterministisks manifests; `SHA256SUMS` SHA256: `29d64d8c883af66021eccb25582370f0b02dcc80e8926a43ea19ddca8b632090`.

Izolēts `-I -B` import smoke no faktiskā immutable `application/` ielādēja **513 app moduļus**, nepieļaujot source-checkout fallback. Papildu smoke atvēra visus piecus runtime JSON resursus: competition registry, calendar plan, research plan, forward plan un constrained protocol; pēdējais pārbaudīja arī baseline model source hash. Citu trūkstošu failu šajā worker import/resource ceļā nav atrasts. Research avotu DB un cycle/latest faili ir apzināti ārēji runtime ceļi, nevis release assets.

Faktiskajā forward DB tagad ir **47 forecast families**, **15 pending neatkarīgas spēles**, **0 resolved**, **10 dabisko ciklu metrics ieraksti**. Pēdējais pārbaudītais cikls `2026-10-04T10:42:55.209524+00:00` ir COMPLETED. FileNotFoundError ir vecajos žurnālos, nevis šī labotā cikla rezultātā.

Repair commit mainītie faili:

- `TASKS.md`
- `docs/evidence/forward_package_repair_20261004/verification.json`
- `docs/operations/ADMIN_FORWARD_PACKAGE_REPAIR_20261004.md`
- `operations/admin-diagnostics/inspect_recent.py`
- `operations/dixon-coles-forward/build.py`
- `operations/dixon-coles-forward/update.py`
- `tests/test_dixon_coles_forward_install.py`
- `tests/test_forward_package_repair.py`

`git diff ebd0924^ ebd0924 -- app` ir tukšs: šis repair nemaina prediction logic. Focused regression: 154 PASS (repair/forward/calendar/probability/performance). Provider calls=0; Telegram sends=0.

**OPERATOR_ACTION_REQUIRED tikai turpmākas drift situācijas gadījumā.** Atkārtots deployment tagad nav vajadzīgs. Read-only pārbaude:

```bash
cd /home/arvis/goalvision-operations/dixon-coles-forward-ebd0924-20261004
sha256sum --check --quiet SHA256SUMS
systemctl show goalvision-dixon-coles-forward.service -p Result -p ExecMainStatus -p WorkingDirectory
```

Veco forward-r2 apply komandu nevajag atkārtot pāri jaunākai PREMATCH konfigurācijai: sākotnējās pakotnes route preconditions var būt novecojušas. Nekāds worker/cycle netika manuāli startēts.

## 3. GITHUB_SYNC_STATUS

**SMALL_GITHUB_FIX — PASS.** Sākumā GitHub bija 42 remote branchi un trūka 109 reviewed commit no atlasītās research/operations ķēdes. Pārbaudīti 1,471 jauni Git objekti, tostarp 627 blobs / 18,506,936 bytes. Aizliegtas .env/DB/runtime takas un atpazīstami token/private-key/provider-key formāti netika atrasti. Publiskojami ir reviewed code, testi un sanitizēta evidence; runtime datubāzes, credentials un pagaidu logi netiek pushoti. Šiem branchiem nav GitHub Actions workflow failu.

Sekmīgi atomic pushoti šādi reviewed branchi (pilni SHA ir `github_preflight.json`):

| Branch | Pārskatītais HEAD |
| --- | --- |
| research/forward-ai-ml-20261001 | `938402ae7e2279f2e36a5abd8cb8124e793d7495` |
| research/calibration-calendar-20261002 | `8c1dd20539179d91f47eb1643be817b940f932d4` |
| research/prematch-devig-shadow-20261002 | `666307b4b276a2c498fa9546f8e6114b6a5e42c7` |
| research/calibration-observer-20261003 | `45d51a4a38364f8ae9f3e2cdb78d8d37911c64c3` |
| feat/dixon-coles-research-20261003 | `a8df4252eafe79ab8345e8e1e86cc532e873c4db` |
| feat/dixon-coles-automation-20261003 | `1ace0df2f2d0d93875b2344f698df2ddb2e81c76` |
| feat/dixon-coles-constrained-20261003 | `801ff47d2837da469b3894a570b8cad8ea9eadea` |
| feat/dixon-coles-forward-combo-20261003 | `711f6da67cf5cdfaa72be6d1fed4ce4b51c7fabb` |
| fix/forward-package-repair-20261004 | `7e77b6411de16534023a5b803e87ad33ac158f78` |
| fix/admin-health-projection-20261004 | `5ae11b7be6b582760cbbec7596dec2b718ee9b7c` |
| feat/combo-conservative-publication-20261004 | `0fdd6eb2e40b79a1c9c6ffa46894363bebb556ad` |
| feat/combo-market-parallel-20261004 | `d1b6147f4dbc475796fe45f4a05d25f2a4ba7abb` |

Papildus šī audita code/evidence tiek publicēti `audit/watch-reconciliation-20261004`; atsevišķā kvotas release ķēde — `fix/settlement-status-reserve-20261004`. `clean`, `goalvision/current-production` un production deployment branchi netiek pārrakstīti/mergeoti; force push nav izmantots. Gala remote readback ir `github_sync_final.json`.

## 4. PREMATCH_CHAMPION_STATE

**NO_CHANGE.** Champion ir tas pats bootstrap, LAB_ONLY/PREMATCH:

- Generation: `generation-aa7e535b86267741aabc967e8044de2ab94a4334b1520a829414dd55ebc7371a`.
- Artifact ID: `bootstrap-artifact-694ab4cc98179ddb0bb2e62d9d77a01c0fee5f3e6d3eff28f9e240e34f929f8d`.
- Model family: `EXISTING_PREMATCH_BASELINE_V1`.
- Registry/schema: `LAB_MODEL_REGISTRY_V1`; feature schema `LAB_FROZEN_FEATURES_V1`; ensemble `LAB_V2_BROAD_COVERAGE_ENSEMBLE_V4`.
- Aktivācija: `2026-09-18T19:53:42.075830+00:00` (2026-09-18 22:53:42 Riga), reason `BOOTSTRAP`, previous generation nav.
- Activation events=1 (bootstrap); jaunas promotions=0, rollbacks=0.

Generation un aizsargāto governance tabulu skaiti pirms/pēc darba sakrīt. Esošā champion publicēšanas loģika nav aizvietota ar research modeli.

## 5. LEARNING_AND_PARTITIONS

**BLOCKED_NEEDS_MORE_EVIDENCE.** Aktuāli 2658 total observations; **2646 resolved eligible**, **940 neatkarīgas resolved fixtures**. Sources: {'COMBO_LEG': 12, 'SHADOW': 2373, 'SINGLE': 273}. 12 legacy COMBO_LEG ieraksti saglabāti vēsturē un izslēgti no neatkarīgās learning/calibration atlases.

Stage `CHALLENGER_RESEARCH`, status `RESEARCH_ELIGIBLE`; `CYCLE_COOLDOWN`, research_due=false, automatic_eligible=false. Aptvertas 15 dienas; 90 dienu automatic-readiness prasība nav sasniegta. Šajā darbā training netika veikts vai ieslēgts.

| Partition | Observations | Independent fixtures |
| --- | --- | --- |
| TRAIN | 1804 | 560 |
| CALIBRATION_FIT | 73 | 73 |
| VALIDATION_EVALUATION | 0 | 0 |
| SEALED_HOLDOUT | 0 | 0 |
| PURGED | 759 | 297 |
| EXCLUDED | 22 | 20 |

Dataset fingerprint: `137bcaf9c17f133508d78d0928ab388cf0a39ae48a8406cbf112827bf92addd9`. Cross-partition fixtures tiek kontrolētas esošajā frozen calendar contract; sample nav mākslīgi palielināts ar viena fixture tirgiem.

## 6. CALIBRATION_STATE

**BLOCKED_NEEDS_MORE_EVIDENCE.** CALIBRATION_FIT = **73/300** observations un neatkarīgas fixtures; logs vēl nav aizvērts. Tas ir faktiskais atjauninātais skaits, nevis iepriekšējais 71. Frozen logi UTC:

| Partition | Sākums (ieskaitot) | Beigas (neieskaitot) |
| --- | --- | --- |
| CALIBRATION_FIT | 2026-10-03T00:00:00+00:00 | 2026-10-10T00:00:00+00:00 |
| SEALED_HOLDOUT | 2026-10-19T00:00:00+00:00 | 2026-10-26T00:00:00+00:00 |
| TRAIN | 2026-09-18T00:00:00+00:00 | 2026-10-02T00:00:00+00:00 |
| VALIDATION_EVALUATION | 2026-10-11T00:00:00+00:00 | 2026-10-18T00:00:00+00:00 |

Fit vērtēšana iespējama ne agrāk par **2026-10-10 03:00 Riga**, un tikai ja sasniegti 300 piemēri. Validation sākas 2026-10-11 03:00 Riga, holdout 2026-10-19 03:00 Riga. Datums pats par sevi negarantē readiness.

Post-hoc calibration artifacts pie registry modeļiem=0. Astoņi vēsturiskie `CALIBRATED_ENSEMBLE` family modeļi nav šī jaunā calendar fit immutable calibrators. Identity/raw, sigmoid/Platt, temperature scaling un pietiekama sample gadījumā isotonic salīdzinājums paliek aiz esošā gate. Jāsaglabā Brier/log loss/ECE/MCE, reliability bins/extremes un pieejamie slope/intercept, dataset/partition provenance, generation un timestamps. VALIDATION/HOLDOUT fit veikšanai netiek izmantoti. Jauns calibration fit netika palaists.

## 7. CHALLENGER_VALIDATION_HOLDOUT_SHADOW

**NO_CHANGE / BLOCKED_NEEDS_MORE_EVIDENCE.** Esošie PREMATCH governance skaiti:

| Tabula/artefakts | Skaits |
| --- | --- |
| activation_events | 1 |
| candidate_comparisons | 0 |
| holdout_results | 0 |
| learning_cycles | 3 |
| model_artifacts | 59 |
| promotion_gates | 0 |
| rollback_events | 0 |
| shadow_predictions | 0 |
| shadow_runs | 0 |
| shadow_settlements | 0 |
| training_runs | 133 |
| validation_results | 0 |
| post-hoc calibration artifacts | 0 |

Training status: {'REJECTED': 74, 'REVIEWED_BOOTSTRAP': 1, 'TRAINED': 58}. Artifact families: {'CALIBRATED_ENSEMBLE': 8, 'EXISTING_PREMATCH_BASELINE_V1': 1, 'LOGISTIC': 26, 'REGULARIZED_LOGISTIC': 16, 'STUMP_ENSEMBLE': 8}. Tie ir iepriekš uzkrāti ieraksti, nevis šajā uzdevumā veikts training. `promotion_gates=0`, `candidate_comparisons=0`, latest observer promotions=[]: jauna promotion recommendation nav. Research forward 47 forecasts atrodas atsevišķā research DB; tās nedrīkst pārdēvēt par pabeigtām governance shadow runs.

## 8. PERFORMANCE_SINGLE

**NO_CHANGE.** Authoritative ledger, tikai apstiprinātas SENT receipts; viens hipotētisks units uz likmi. Odds vidējais/mediāna ir visām publicētajām likmēm; ROI denominator — visas settled, ieskaitot VOID. Hit rate — WON/(WON+LOST). Probability metrics tikai resolved binary SINGLE ar derīgu frozen p; 3 vecajām likmēm p trūkst, tādēļ metrics n=273. Bias ir mean(p−y), pozitīvs nozīmē pārvērtējumu.

| Metrika | Visa saglabātā vēsture | Pašreizējais SINGLE ≥1.50 cohorts |
| --- | --- | --- |
| Published | 304 | 55 |
| Settled | 276 | 30 |
| WON | 139 | 15 |
| LOST | 137 | 15 |
| VOID | 0 | 0 |
| Pending | 28 | 25 |
| Hit rate | 50.36% | 50.00% |
| Average odds | 2.555625 | 1.552545454545454545454545455 |
| Median odds | 1.525 | 1.53 |
| Flat P/L (1 unit) | -37.67 | -6.32 |
| Flat ROI | -13.65% | -21.07% |
| Brier | 0.222380 | 0.266600 |
| Log loss | 0.635200 | 0.729545 |
| ECE | 0.110828 | 0.171446 |
| Calibration bias (p−y) | 0.102121 | 0.138171 |

Visa vēsture sajauc vairākas politikas; aktuālais 1.50 tests ir vērtējams atsevišķi un ir mazs/nepabeigts. Negatīvais ROI neizraisa threshold tuning.

Segmenti ar vismaz 30 settled tickets zemāk ir tikai aprakstoši, nevis statistiskas nozīmības apgalvojums. Pilni visi pieprasītie segmenti un probability metrics ir `performance.json`.

| Dimension | Band/value | Settled | P/L | ROI | Brier |
| --- | --- | --- | --- | --- | --- |
| lead_time_bucket | [25,45) | 58 | -7.33 | -12.64% | 0.2265 |
| lead_time_bucket | [45,90) | 85 | -19.03 | -22.39% | 0.2593 |
| lead_time_bucket | [90,inf) | 108 | -5.61 | -5.19% | 0.1902 |
| league | 5 | 38 | 5.61 | 14.76% | 0.2211 |
| market | DRAW | 44 | -0.04 | -0.09% | 0.2207 |
| market | OVER_1_5 | 52 | -3.23 | -6.21% | 0.1794 |
| market | OVER_2_5 | 35 | -7.25 | -20.71% | 0.2560 |
| market | UNDER_3_5 | 51 | -3.44 | -6.75% | 0.2121 |
| model_market_disagreement_bucket | [0,0.05) | 135 | -14.35 | -10.63% | 0.2121 |
| model_market_disagreement_bucket | [0.05,0.1) | 34 | 7.48 | 22.00% | 0.2086 |
| model_market_disagreement_bucket | [0.1,0.2) | 82 | -13.50 | -16.46% | 0.2126 |
| odds_age_bucket | [3600,14400) | 241 | -22.70 | -9.42% | 0.2221 |
| odds_band | [0,1.5) | 114 | -3.88 | -3.40% | 0.1922 |
| odds_band | [1.5,2) | 68 | -11.71 | -17.22% | 0.2655 |
| odds_band | [3,5) | 50 | -0.70 | -1.40% | 0.2356 |
| probability_band | [0,0.4) | 38 | 3.90 | 10.26% | 0.1848 |
| probability_band | [0.6,0.7) | 94 | -17.08 | -18.17% | 0.2524 |
| probability_band | [0.7,0.8) | 59 | 3.06 | 5.19% | 0.1930 |
| value_cohort | NEGATIVE_EV | 145 | -12.26 | -8.46% | 0.2074 |
| value_cohort | POSITIVE_EV | 128 | -22.41 | -17.51% | 0.2393 |

Frozen data-quality grupas:

| State | Published | Settled | ROI | Brier |
| --- | --- | --- | --- | --- |
| FROZEN_ACCURACY_REVIEW_ELIGIBLE | 187 | 159 | -7.45% | 0.2120 |
| FROZEN_ACCURACY_REVIEW_UNAVAILABLE | 117 | 117 | -22.08% | 0.2369 |

League grupām, kuras nesasniedz 30 settled, salīdzinošs secinājums netiek dots. Frozen probability ir publicētā ensemble p, nevis pierādījums, ka bootstrap jau būtu kalibrēts.

## 9. PERFORMANCE_COMBO

**NO_CHANGE / BLOCKED_NEEDS_MORE_EVIDENCE jaunajiem cohortiem.**

| Metrika | Visa saglabātā vēsture |
| --- | --- |
| total_published | 142 |
| total_settled | 122 |
| WON | 47 |
| LOST | 75 |
| VOID | 0 |
| PARTIAL_VOID | 0 |
| pending | 20 |
| average_combined_odds | 11.72493019014084507042253521 |
| median_odds | 2.578440 |
| flat_unit_pnl | -10.540259 |
| flat ROI | -8.64% |

| Policy/statistics cohort | Published | Settled | WON | LOST | Pending | P/L | ROI |
| --- | --- | --- | --- | --- | --- | --- | --- |
| COMBO_AGREEMENT_20261004_V1 | 1 | 0 | 0 | 0 | 1 | 0 | N/A |
| COMBO_MARKET_20261004_V1 | 1 | 0 | 0 | 0 | 1 | 0 | N/A |
| LAB_COMBO_ACCURACY_FROM_SINGLES_V1 | 68 | 66 | 32 | 34 | 2 | -6.243887 | -9.46% |
| LAB_COMBO_ACCURACY_FROM_SINGLES_V2_LEG_MIN_ODDS_130 | 53 | 37 | 14 | 23 | 16 | 1.276552 | 3.45% |
| LEGACY_COMBO | 19 | 19 | 1 | 18 | 0 | -5.572924 | -29.33% |

DC agreement un Tirgus tests katrs jau ir dabīgi publicējis vienu likmi; abas pending. Tātad pašreiz nav pierādījuma, kura atlase ir labāka. Kopējo odds vidējo ļoti ietekmē vecais legacy cohorts; to nedrīkst attiecināt uz jaunajiem 3-leg testiem. Early loss nozīmē, ka zaudējumi var nobriest pirms uzvarām. COMBO nav neatkarīgi calibration/learning piemēri.

## 10. INVALID_PROBABILITY_ROOT_CAUSE

**NO_CHANGE — cēlonis apstiprināts; clamp nav veikts.** Pēdējos 12 completed rehearsal ciklos `2026-10-03T19:00:02.666684+00:00`–`2026-10-04T10:30:03.435286+00:00` pārbaudīti **13444 kandidāti / 315 unikālas fixtures**. **31** INVALID_MODEL_PROBABILITY gadījums **7** fixtures: 30 AWAY_WIN, 1 HOME_WIN. Fixture IDs: 1528940, 1528943, 1616105, 1637964, 1637965, 1639984, 1639985.

Visos 31 raw provider probability ir `0%`; producer un independence group `API_FOOTBALL_PREDICTION`. Transformācija: percent units → Decimal zero (`0E+1`) → vienīgās predictive family svērtais ensemble zero. `CURRENT_MARKET_CONSENSUS` ir pieejams kā tirgus konteksts, bet netiek izmantots, lai maskētu nederīgu predictive endpoint. HOME/AWAY šajā ceļā nav complement calculation. JSON saglabā Decimal tekstu; serialization nav nulles cēlonis. Normalization `available=true`; trūkstošie expected-goals inputs netiek pārvērsti šajās nullēs. Calibration status `UNCALIBRATED_LAB_ENSEMBLE`, artifact nav; guard noraida kandidātu pirms tālāka modeļa/publication ceļa.

Source fingerprint, pirms-normalizācijas raw value, normalized probability, ensemble un producer provenance saglabāti `candidates.json`. Esošais regression `test_provider_zero_is_not_a_decimal_or_complement_bug` PASS. Nav pierādīts jauns lokāls arithmetic bugs; piegādātāja nulles semantika/rounding nav nosakāma bez papildu piegādātāja evidence. Ārējie calls diagnostikai netika veikti.

## 11. THROUGHPUT_AND_NO_PICK_REASONS

**NO_CHANGE.** Pēdējo 24h persisted discovery health: 28 cikli; fixtures-discovered ierakstu summa 31297 (atkārtoti sweepi, **ne unikālas spēles**), markets evaluated 31941, klasiskie READY 124, confirmed cycle publication counters 119. Pēdējā ciklā 817 discovered / 598 considered / 126 evaluated fixtures, 1208 markets, classic READY=0, esošo Lab experiment politiku publications=4 (3 SINGLE + 1 COMBO). Classic readiness skaitītājs un atsevišķā Lab publication policy nav viens un tas pats denominator.

Pēdējo 12 candidate ciklu galvenie skaiti:

| Reason | Candidate rows |
| --- | --- |
| INVALID_MODEL_PROBABILITY | 31 |
| MARKET_REVIEW_TERMINAL | 10 |
| NON_POSITIVE_VALUE | 9372 |
| MATERIAL_SIGNAL_DISAGREEMENT | 3962 |
| SEVERE_MODEL_MARKET_CONTRADICTION | 479 |
| ENSEMBLE_MARKET_DIVERGENCE_TOO_LARGE | 281 |
| NO_INDEPENDENT_NON_MARKET_EVIDENCE | 5067 |

Pēdējā cikla publication blockers (kandidātu iemesli; ne unique fixtures):

| COMBO / SINGLE | Reason | Count |
| --- | --- | --- |
| COMBO | LAB_COMBO_LEG_ODDS_BELOW_1_30 | 71 |
| COMBO | FIXTURE_AFTER_LAB_CUTOFF | 138 |
| SINGLE | LAB_PUBLICATION_PROBABILITY_BELOW_0_55 | 763 |
| SINGLE | LAB_SINGLE_ODDS_BELOW_1_50 | 117 |
| SINGLE | FIXTURE_AFTER_LAB_CUTOFF | 138 |
| SINGLE | LAB_ACCURACY_PUBLICATION_POLICY_REJECTED | 8 |

Pēdējā saglabātā blocker map nav duplicate/exposure iemeslu; tas nav apgalvojums, ka tie nav notikuši visā vēsturē. Turpmākam pilna 24h exposure auditam vajag atsevišķi apkopot lane diagnostics, nezaudējot cohort robežas. Volume mākslīgi nav palielināts.

## 12. QUOTA_DATA_QUALITY_RUNTIME

**NO_CHANGE.** 180 s settlement pre-discovery guard joprojām ir efektīvais ExecStart `/opt/goalvision-settlement-guard-v1/runtime_guard.py`. Pieejamajā 24h journal ir 13 `SETTLEMENT_DEFERRED_DISCOVERY_ACTIVE` atlikšanas; nav atrasts `database is locked` vai quota-contention retry/exhausted. Tas ir bounded observed evidence, nevis matemātiska garantija, ka procesi nekad nepārklājas. Pārbaudes neuztur garas production SQLite write transactions.

**SMALL_GITHUB_FIX + OPERATOR_ACTION_REQUIRED.** Read-only settlement run ledger rāda **131 runs, 119 bez terminal error, 12 FootballQuotaError** 2026-10-04 01:05–02:55 Riga; katrā api_calls_consumed=0, Telegram send=false. Root cause: lokālie 7,414/7,500 claims atstāja 86 slots; STATUS prasa 100 reserve, lai gan SETTLEMENT drīkst to patērēt. Tas nav atjaunojies SQLite lock bugs. Pēc UTC dienas reset settlement atkopās.

Labojums divos app failos saglabā esošo HTTP pieprasījumu skaitu un limits, bet sākotnējo settlement status request uzskaita SETTLEMENT kategorijā. Discovery reserve, nulles kvotas atteikums, observed provider header limits un contention bounds saglabāti. Fake-HTTP regression pārbauda atļautu 86-slot robežu, exhausted/local/provider daily/minute robežas un atteikumu discovery. Sagatavota, ne-deployota immutable operator package: `{q['package']}`. Manifest overlays ir tikai `app/adaptive_lab/quota.py` un `app/lab_combo/cli.py`. 847-file baseline un 544-module assembled smoke PASS; default preflight current_mode=BASE, ADMIN Codex disabled.

**BLOCKED_NEEDS_MORE_EVIDENCE / LARGER_CODEX_TASK.** Datu coverage ierobežojumi nav atrisināti, mīkstinot atlasi. Pēdējā cikla fixture skaiti:

| Reason | Fixtures |
| --- | --- |
| CURRENT_ODDS_AVAILABLE | 6 |
| NEEDS_NEAR_KICKOFF_REFRESH | 121 |
| NON_POSITIVE_VALUE | 5 |
| NO_CURRENT_ODDS | 5 |
| ODDS_BOOKMAKER_FILTER_REMOVED_ALL | 5 |
| ODDS_INSUFFICIENT_COMPARABLE_BOOKMAKERS | 1 |
| ODDS_PAGINATION_CHANGED_DURING_SWEEP | 324 |
| ODDS_STALE | 131 |
| PREMATCH_PUBLICATION_CLOSED | 219 |

Provider partial-page skaits nav droši atvasināms no šiem summary; `ODDS_PAGINATION_CHANGED_DURING_SWEEP` ietekmēja 324 fixtures. Tas ir konkrēts nākamais coverage audita kandidāts, saglabājot kvotu. Trūkstošs/stale context ne vienmēr ir provider kļūda: candidate snapshot ir 13422 trūkstoši lineup, 7047 recent_form un 616 competition_state; missing injuries/advanced_stats/standings ir 13444 katrs. Precīzs atsevišķs stale-context kopskaits šajā saglabātajā auditā nav pieejams; tas netiek izdomāts kā nulle.

UTC dienas local claims snapshotā: **3077**. Pēdējā discovery provider remaining=4580, cycle max=244 no requested 400; `REDUCED_TO_PRESERVE_QUOTA`. 28 health cikli DEGRADED šīs kvotas saglabāšanas dēļ, nevis 28 crash. Pieejamais journal viens pats neatspoguļo visus systemd failure notikumus; to salīdzināju ar operatora ADMIN eksportu un settlement run ledger.

## 13. DIXON_COLES_INCREMENTAL_INFORMATION

**SMALL_GITHUB_FIX — implementācija/testi PASS; BLOCKED_NEEDS_MORE_EVIDENCE — kvalitātes secinājums.** Jauns izolēts SHADOW-ONLY comparator ar immutable prospective protocol. Declaration commit `e345e3f6b6f1df8c1625243db502a5d661a24e93`, sākotnējā implementācija `58fdedd557bf0765679bb5adfd1def79ff938ec0`, hardening `1e580922acdde160347179f4cba820391bc89b7c`.

Ir champion/market/DC un champion+DC / market+DC logarithmic pools, 1X2 RPS, multiclass Brier, log loss, ECE/MCE, draw/favourite/longshot calibration, DC-baseline un champion-market disagreement. Champion drīkst piedalīties tikai ar pareiziem frozen generation/artifact IDs un coherent pilnu 1X2 vektoru. Market šeit ir iepriekš frozen forward protokola first-complete-book multiplicative de-vig; tas nav pārdēvēts par market-parallel multi-book publication score.

Weight grid 0.0…1.0, solis 0.1; fit tikai slēgtā CALIBRATION_FIT ar 300 neatkarīgām fixtures. Ties izvēlas 0. Immutable pool artifact satur dataset fingerprint, source references, generation un laikus. Read-only report **neizsauc fit**. VALIDATION izmanto pirms tās fiksētu svaru, atsevišķas fixtures, slēgtu logu, 100 fixtures/7 kickoff dates, deterministic date-cluster bootstrap un abas hronoloģiskās puses. Near-zero (≤0.1), nestabils vai inconclusive ieguldījums nevirzās tālāk; stabils pozitīvs rezultāts var ieteikt tikai nākamā holdout research plānošanu.

Šī snapshotā: 2 qualifying pilni 1X2 forecasti, 0 resolved paired fixtures; 39 pirms declaration excluded. **Optimālais forward weight=N/A**, nevis 0. Pašlaik nevar apgalvot, ka DC dod vai nedod papildu informāciju.

**OPERATOR_ACTION_REQUIRED pirms holdout posma.** Esošais forward plāns beidzas tieši holdout sākumā 2026-10-19T00:00Z. Jauna prospective holdout capture governance jāizskata atsevišķi; pašreizējais comparator holdout nelasa un nevar dot promotion eligibility. Publication imports/timers nav mainīti. Kā palaist tikai read-only report, dokumentēts `docs/operations/DIXON_COLES_INCREMENTAL_INFORMATION_20261004.md`.

## 14. PROMOTION_ELIGIBILITY

**BLOCKED_NEEDS_MORE_EVIDENCE.** Champion saglabāts. Calibration 73/300 un logs atvērts; validation un holdout=0; governance shadow=0; incremental paired results=0. Nav pamata activation/promotion/rollback. 1.50 SINGLE negatīvs aprakstošais ROI un agrīnie COMBO rezultāti nav threshold tuning trigger. Automatic training/promotion netika ieslēgti.

## 15. ACTION_ITEMS

1. **OPERATOR_ACTION_REQUIRED:** pēc savas pārskatīšanas uzlikt sagatavoto settlement preflight reserve fix. Tas ir vienīgais šajā auditā sagatavotais production operator apply; aģents to nav izpildījis.

```bash
python3 ~/goalvision-operations/settlement-quota-reserve.py
sudo python3 ~/goalvision-operations/settlement-quota-reserve.py --apply
```

Wrapper ir piesaistīts `9d7389458866100468f36fc542af02255cfaf203` package hashes; tas atsaka neatbilstošus source/route/config stāvokļus. Sagaidāmais rezultāts: `PREMATCH_SETTLEMENT_QUOTA_RESERVE_DEPLOYED`. Neveikt manual cycle vai test send. Pēc operatora darbības jāpārbauda nākamie dabiskie settlement cikli. Atkārtoti lietot vecos PREMATCH/DC installerus nevajag.

2. **NO_CHANGE:** ļaut esošajiem taimeriem krāt forward, SINGLE 1.50 un abu COMBO cohort rezultātus. Neizdarīt uzvarētāja izvēli no viena pending COMBO.
3. **BLOCKED_NEEDS_MORE_EVIDENCE:** atkārtot calendar readiness pēc fit loga slēgšanās/300 neatkarīgiem piemēriem; neapmācīt tagad tikai apjoma dēļ.
4. **LARGER_CODEX_TASK:** bounded provider pagination/context/exposure audit, saglabājot pašreizējās kvotas un publication gates. Šajā auditā konstatēts coverage ierobežojums, nevis dots pamats mākslīgi palielināt pick volume.
5. **OPERATOR_ACTION_REQUIRED:** ja DC incremental posms vēlāk iztur validation, pirms 19. oktobra atsevišķi pārskatīt prospective holdout collection plānu. Nekādas automātiskas aktivācijas.

Veiktā darba commiti:

| Darbs | Commit |
| --- | --- |
| Prospective declaration | e345e3f6b6f1df8c1625243db502a5d661a24e93 |
| Quota fix audita ķēdē | 2c758427843621c10cfb92cd8fb8ae628c5b4a53 |
| Quota operator package source | 9d7389458866100468f36fc542af02255cfaf203 |
| Incremental comparator | 58fdedd557bf0765679bb5adfd1def79ff938ec0 |
| Incremental protocol/CLI hardening | 1e580922acdde160347179f4cba820391bc89b7c |

Gala evidence/standalone snapshot tests commit ir šī handoff branch HEAD (precīzs SHA gala operatora atbildē). Pārskatīto branchu/commit pilns saraksts ir `github_preflight.json`; gala push readback — `github_sync_final.json`.

Testu rezultāti (suite skaiti daļēji pārklājas; tos nesummēt):

| Scope | Rezultāts |
| --- | --- |
| forward repair + original forward + calendar/probability/performance regression | 154 PASS / 8.4 s |
| quota/preflight/forward incremental/autonomy/early combo regression | 303 PASS / 45.57 s |
| operator installer + incremental + settlement preflight | 39 PASS / 2.45 s |
| final incremental adapter/protocol guards + snapshot/standalone CLI regression | 22 PASS / 2.91 s |

Papildus: installed forward checksum/import/resource smoke PASS; assembled quota package/import/preflight PASS; read-only as-of snapshot PASS; reālo immutable forward forecastu adaptera reproducibility/forgery regressions PASS. Nekādi testi nav izmantoti kā model quality pierādījums.

Noslēguma invarianti: agent deployment=0; manual service cycles=0; agent football-provider calls=0; agent Telegram sends=0; champion training/activation/promotion/rollback=0. LIVE paliek DISABLED, ADMIN Codex inactive/disabled, Official pilnīgi neskarts. Esošie dabiskie servisi turpināja savus jau autorizētos provider calls/publications; to skaiti ir atsevišķi no aģenta darbībām. Historical bookmaker odds nav iegūti. Publication/selection thresholds nav mainīti.

Audita un kvotas worktree pēc gala commit jābūt tīriem; vecais `/home/arvis/GoalVisionAI` checkout paliek iepriekšējā netīrajā stāvoklī (220 takas), neaiztikts. Nav izmantots `git add .`, force push vai production branch vēstures pārrakstīšana. Evidence publicēta tikai pēc satura/secret un forbidden-file pārbaudes.
