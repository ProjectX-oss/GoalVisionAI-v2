# GoalVision AI — PREMATCH/Lab quality handoff, 2026-10-07

Snapshot: **2026-10-07T17:47:33.519387+00:00 = 20:47:33 Europe/Riga**.
Read-only audits un coupon diagnostika pabeigti; research eligibility joprojām bloķēta ar datu apjomu.
**LIVE prasības neatbilstība paliek atvērta:** faktiskā sistēma ir ENABLED pēc operatora iepriekšējā deploy.
Šis darbs LIVE neieslēdza un neizslēdza. Production konfigurācija nav mainīta.

Source commit: **6e7ae9f64792c0152d7a90cc7b1da3f2467cf917**.
Branch: **work/prematch-quality-evidence-20261007**.
Sanitizēti pierādījumi: docs/evidence/prematch_quality_20261007/.

## CURRENT_STATE

**NO_CHANGE.** Champion, publication/selection sliekšņi, bankroll/staking, atlase,
rezultātu Replies un agrīna COMBO loss uzskaite saglabāti. Snapshot izmanto tikai
jau uzkrātus forward ierakstus un sākotnējo publikāciju koeficientus.
Historical bookmaker odds iegūšana vai izpēte nav atsākta.

**OPERATOR_ACTION_REQUIRED.** Pēdējā operatora autorizētā release jau ieslēdza LIVE Lab.
Norāde “LIVE paliek DISABLED” neatbilst faktiskajam timerim. Nevar apliecināt LIVE OFF.
Ja jaunā prasība nozīmē LIVE apturēšanu, tā ir atsevišķi saskaņojama operatora darbība;
šajā PREMATCH auditā netika apturēti arī LIVE rezultātu pārbaudes ceļi.

## REPOSITORY_AND_RELEASE

**NO_CHANGE.** Sākuma HEAD un GitHub darba branch: 0162759dd4bffe35b8ab9d7ed326818ddcd30fd6.
Jaunais audita branch izveidots no šī pārbaudītā HEAD. Production branch vēsture nav pārrakstīta.
Darba koks: /home/arvis/goalvision-worktrees/prematch-evidence-20261006.
Oriģinālajā /home/arvis/GoalVisionAI saglabātas **220 iepriekš esošas dirty paths**;
tās nav labotas, tīrītas vai commitotas.

Faktiskā production release: /opt/goalvision-live-evening-4f547cf-20261007.
Pinned-wrapper read-only pārbaude: current_mode=ENABLED, **857 application failu hashi PASS**,
ADMIN_CODEX_SYSTEMD_DISABLED PASS; konfigurācijas un četri PREMATCH import routes pārbaudīti.
Jaunie šī audita moduļi production release nav ievietoti.

PREMATCH discovery: 10:00–18:00 Riga, nākamais dabiskais starts 2026-10-08 10:00.
Rezultātu timeris: visu diennakti. LIVE discovery: 18:00–23:00 Riga.
24 odds ciklu analīzes logs: **2026-10-06 22:30 līdz 2026-10-07 20:00 Riga**.
Tās ir pabeigtas atlases pirms jaunā vakara grafika aktivizācijas.
Jaunā PREMATCH dienas budžeta uzvedība vēl jāvēro nākamajos dabiskajos ciklos.

## CHAMPION_AND_LEARNING

**NO_CHANGE.** Aktīvais PREMATCH:
generation-aa7e535b86267741aabc967e8044de2ab94a4334b1520a829414dd55ebc7371a.
Family EXISTING_PREMATCH_BASELINE_V1; registry LAB_MODEL_REGISTRY_V1;
feature schema LAB_FROZEN_FEATURES_V1; probability contract FINITE_OPEN_UNIT_INTERVAL.
Bootstrap ieraksts: **2026-09-18T19:53:42.075830+00:00**, iepriekšējas generation nav.
Tas pats bootstrap joprojām ir champion pointer.

Stage **CHALLENGER_RESEARCH**. Total learning rows **2832**;
resolved eligible **2819**, neatkarīgas resolved fixtures **1113**.
Source products: SINGLE 447, SHADOW 2373, legacy COMBO_LEG 12.
12 vēsturiskie COMBO_LEG ieraksti ir no 18.–30. septembra; tie nav eligible
learning/calibration source un netika dzēsti. Jaunā coupon exporta katra rinda
marķēta source_product=COMBO; model_learning_observations=0.
Esošais learning_source to noraida.

| Partition | Observations | Independent fixtures |
| --- | --- | --- |
| TRAIN | 1804 | 560 |
| CALIBRATION_FIT | 246 | 246 |
| VALIDATION_EVALUATION | 0 | 0 |
| SEALED_HOLDOUT | 0 | 0 |
| PURGED | 760 | 298 |
| EXCLUDED | 22 | 20 |

## CALIBRATION_READINESS

**BLOCKED_NEEDS_MORE_EVIDENCE.** CALIBRATION_FIT **246/300**; trūkst vismaz **54 neatkarīgas fixtures**.
Fit logs atvērts līdz **2026-10-10 00:00 UTC / 03:00 Riga**.
Apjoma minimums pats par sevi neatceļ frozen calendar robežu.
Dataset fingerprint: 01eed440e3359080990ed55f910c97919da8dfaa5160b5796c3050ccc7ddb15a.
Plan fingerprint: 9b154abc5b1ca4f18187150c2ca0a8d4d37b93b9c3893e97b2e61457329ca439.

Calibrator nav trenēts, calibration artifact nav izveidots, VALIDATION/HOLDOUT fit nav izmantoti.
Nākamā atļautā darbība: dabiskā datu vākšana; pēc visu readiness nosacījumu izpildes
research-only identity/Platt/temperature salīdzinājums, isotonic tikai ar pietiekamu sample.
Minimumi nav mīkstināti.

## ODDS_COVERAGE_AND_REFRESH_YIELD

**DATA_QUALITY_LIMITATION.** Lietotāja 193-fixture piemērs reproducēts
**2026-10-07 09:00 Riga** ciklā: 24 fresh, 106 complete-sweep no-record,
61 stale, 2 bookmaker-filtered. Izmantoti 252/252 cycle calls,
bet pēc cikla palika **7100 dienas calls**. Tas nebija dienas quota exhaustion.

24 ciklos: **3069 fixture-cycle novērojumi / 199 unikālas fixtures**.
Fresh 746 (**24,31%**), no-record 1426 (**46,46%**), stale 629 (**20,50%**),
pagination changed 233, insufficient bookmakers 21, bookmaker-filtered 14.
Tie ir atkārtoti exposure, ne 3069 neatkarīgas spēles.

Pēdējā 20:00 Riga ciklā broad scope 55: fresh 5, stale 24, no-record 26.
Pēc exact-review overrides current_odds_fixtures=2. Broad un final skaitļiem ir
atšķirīga pārbaudes stadija; tos nedrīkst savstarpēji saskaitīt.

| Exact grupa | Novēroti attempts | Fresh | Yield |
| --- | --- | --- | --- |
| FINAL_REVIEW | 124 | 76 | 61.29% |
| PRIORITY_EXACT | 20 | 1 | 5.00% |
| TRACKED_EXACT | 121 | 85 | 70.25% |

Kopā **305 exact HTTP calls**, **162 zināmi fresh fixture refreshes**:
**1,88 calls uz zināmu fresh fixture**, ne uz market quote.
Untracked final-outcome trūkuma dēļ tā ir izmaksu augšējā robeža.
Date sweep atsevišķi izmantoja **302 calls**.
Detalizētajā eksportā ir 265 exact outcome ieraksti.
55 WAITING/failed ierakstos precīzs failure veids nav saglabāts;
attiecīgajām grupām stale/no-record likmes atstātas null, ne pieņemtas par nulli.

Pēc iepriekšējā neveiksmīgā fixture refresh bija 65 nākamie attempts;
48 atkal bez rezultāta (**73,85%**), jeb **18,11%** no visiem 265 attempts.
Previous-history logs ir ierobežots ar šī audita 24 cikliem.

| Competition profile | Attempts | Fresh | Yield |
| --- | --- | --- | --- |
| DOMESTIC_CUP | 58 | 42 | 72.41% |
| FRIENDLY | 2 | 0 | 0.00% |
| INTERNATIONAL_SENIOR | 2 | 2 | 100.00% |
| LOWER_DIVISION_OR_SEMIPRO | 18 | 10 | 55.56% |
| RESERVE_OR_B_TEAM | 8 | 3 | 37.50% |
| SENIOR_MEN_PRO | 151 | 92 | 60.93% |
| UNKNOWN | 23 | 13 | 56.52% |
| YOUTH_U19_U20 | 3 | 0 | 0.00% |

Labākie piemēri ar vismaz 5 novērojumiem: Finland Veikkausliiga **18/19**,
Italy Coppa Italia Serie D **18/21**, Nigeria NPFL **14/18**.
Sliktākie: Angola Girabola **0/17**, China League One **1/6**, Argentina Reserve League **1/5**.
Tie nav neatkarīgi līgu kvalitātes vērtējumi: Angola ir **viena fixture 1627266**.

**NO_CHANGE — ODDS_REFRESH_YIELD_PRIORITY_V1 nav ieviests.**
Discretionary priority-exact posmā ir 20 mēģinājumi uz divām fixtures:
vienā ciklā tikai 1–2 kandidāti pret esošo **20** retry vietu limitu.
Pārkārtošana neizmainītu apstrādāto kandidātu kopu.
Tracked/final-review kvotu atņemt nav pieļaujams, bet viena Angola fixture
nepamato competition blacklist/cooldown. Domestic cups yield ir laba.
Tādēļ nav pierādīta reordering priekšrocība, kuru varētu droši ieviest.

**SMALL_GITHUB_FIX.** Ieviests read-only yield audits ar country, competition,
league, fixture status, lead-time, phase un iepriekšējo attempt rezultātu.
Provider HTTP status/calls-per-quote katram attempt nav vēsturiski saglabāts;
tie norādīti kā unavailable. Papildu API calls vai ceiling palielinājumu nav.

## SINGLE_PERFORMANCE

**NO_CHANGE.** Autoritāte: confirmed sākotnējās publikācijas receipt plus immutable settlement
līdz cutoff. Publiskā un privātā ledger statistika ir atsevišķa.
ROI denominator ir visi settled tickets, arī VOID; odds average/median — visi published.
Binary scoring izmanto derīgos W/L probabilities; pending nav zaudējums.

| Rādītājs | Publiskais Lab all-time | Aktīvais SINGLE 1.50 V4 | Privātais SINGLE 1.70 |
| --- | --- | --- | --- |
| Published | 471 | 222 | 3 |
| Settled | 450 | 202 | 3 |
| WON | 249 | 123 | 1 |
| LOST | 200 | 78 | 2 |
| VOID | 1 | 1 | 0 |
| Pending | 21 | 20 | 0 |
| Hit rate | 55.46% | 61.19% | 33.33% |
| Average odds | 2.2146 | 1.5836 | 1.7500 |
| Median odds | 1.5600 | 1.5700 | 1.7500 |
| Flat P/L (u) | -36.9000 | -6.2600 | -1.3000 |
| Flat ROI | -8.20% | -3.10% | -43.33% |
| Brier | 0.2248 | 0.2356 | 0.3761 |
| Log loss | 0.6405 | 0.6637 | 0.9689 |
| ECE | 0.0600 | 0.0147 | 0.3887 |
| Bias: predicted-observed | 0.0534 | 0.0035 | 0.3887 |

| SINGLE cohort | Published | Settled | W/L/VOID | P/L u | ROI |
| --- | --- | --- | --- | --- | --- |
| LAB_EXPERIMENTAL_SELECTION_V1 | 3 | 3 | 0/3/0 | -3.0000 | -100.00% |
| LAB_SINGLE_ACCURACY_FIRST_PER_FIXTURE_V1 | 27 | 27 | 20/7/0 | 0.5000 | 1.85% |
| LAB_SINGLE_ACCURACY_FIRST_PER_FIXTURE_V2_NO_ODDS_FLOOR | 18 | 18 | 16/2/0 | 0.0400 | 0.22% |
| LAB_SINGLE_ACCURACY_FIRST_PER_FIXTURE_V3_MIN_ODDS_130 | 87 | 86 | 58/28/0 | -5.3500 | -6.22% |
| LAB_SINGLE_ACCURACY_FIRST_PER_FIXTURE_V4_MIN_ODDS_150 | 222 | 202 | 123/78/1 | -6.2600 | -3.10% |
| LAB_SINGLE_PROBABILITY_FIRST_PER_FIXTURE_V1 | 5 | 5 | 1/4/0 | -1.2500 | -25.00% |
| LAB_V2_BROAD_COVERAGE_ENSEMBLE_V4 | 109 | 109 | 31/78/0 | -21.5800 | -19.80% |

All-time scoring sample **446** pret 449 W/L: 3 legacy publikācijām trūkst p.
V4 scoring sample 201, privātajā tikai 3; V4 ir arī 20 pending.
Mazs ECE nepierāda neatkarīgu calibration kvalitāti vai profitability.
Pilni market/league/odds/probability/lead-time/odds-age/disagreement/EV/data-quality
segmenti: performance.json un private_performance.json.

## COMBO_PERFORMANCE

**NO_CHANGE.** Published **190**, settled **181**: **66 W / 115 L / 0 VOID / 0 partial VOID**,
pending **9**. Average combined odds **9,4844**, median **2,6144**;
flat P/L **−16,403013u**, ROI **−9,0624%**.

| Cohort | Published | Settled | W/L | Pending | P/L u | ROI | Brier | Log loss | ECE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| COMBO_AGREEMENT_20261004_V1 | 11 | 6 | 2/4 | 5 | 0.9556 | 15.93% | 0.2564 | 0.7261 | 0.2662 |
| COMBO_DOUBLE_20261006_V1 | 0 | 0 | 0/0 | 0 | 0.0000 | n/a | n/a | n/a | n/a |
| COMBO_MARKET_20261004_V1 | 39 | 39 | 10/29 | 0 | -10.5250 | -26.99% | 0.1971 | 0.5835 | 0.1174 |
| LAB_COMBO_ACCURACY_FROM_SINGLES_V1 | 68 | 66 | 32/34 | 2 | -6.2439 | -9.46% | 0.2318 | 0.6547 | 0.1082 |
| LAB_COMBO_ACCURACY_FROM_SINGLES_V2_LEG_MIN_ODDS_130 | 53 | 51 | 21/30 | 2 | 4.9831 | 9.77% | 0.2563 | 0.7094 | 0.1157 |
| LEGACY_COMBO | 19 | 19 | 1/18 | 0 | -5.5729 | -29.33% | 0.0538 | 0.2165 | 0.0620 |

DC agreement ir iepriekš operatora aktivizēta COMBO cohort, ne jauna DC/champion promotion.
Tirgus jaunas publikācijas jau ir izslēgtas; vēsturiskie zaudējumi paliek.
Double nav apstiprinātu kuponu. V2 pozitīvais ROI un DC sešu settled kuponu
rezultāts nav pierādījums pārākumam; sliekšņi nav mainīti.

## COMBO_CALIBRATION

**SMALL_GITHUB_FIX.** Jauns izolēts app/adaptive_lab/combo_evidence.py.
Eksportē 190 coupon ierakstus: cohort/policy, kāju skaits, katras kājas frozen p
un probability-kind, bookmaker odds/ID, combined odds, naive joint p,
deklarētā joint p, publication/kickoff/settlement, P/L, lead-time/odds buckets,
source un report fingerprints.

| Cohort | Scored coupons | Mean naive joint p | Observed hit rate |
| --- | --- | --- | --- |
| COMBO_AGREEMENT_20261004_V1 | 6 | 27.12% | 33.33% |
| COMBO_DOUBLE_20261006_V1 | 0 | n/a | n/a |
| COMBO_MARKET_20261004_V1 | 39 | 29.01% | 25.64% |
| LAB_COMBO_ACCURACY_FROM_SINGLES_V1 | 66 | 44.98% | 48.48% |
| LAB_COMBO_ACCURACY_FROM_SINGLES_V2_LEG_MIN_ODDS_130 | 51 | 31.80% | 41.18% |
| LEGACY_COMBO | 19 | 11.46% | 5.26% |

Naive joint p ir frozen kāju p reizinājums saglabātajā secībā;
19 legacy kuponiem tas auditā atvasināts un attiecīgi marķēts.
Reāls correlation-adjusted joint modelis šajos ierakstos neeksistē:
adjusted p ir null. Correlation screen nav nosaukts par kalibrācijas modeli.
335 kājām p ir market-inclusive, 235 independent-single-model.

Kopējie coupon diagnostics: Brier **0,213362**, log loss **0,611132**,
ECE **0,054909**, bias **−0,027496**. Tie nav model-training novērojumi.
VOID/partial VOID izslēgti no binary scores; agrīns loss skaitās viens zaudēts kupons.
Frozen probability/combined-odds mismatch **0**.
Probability netiek clampota; float extremes, kurus nevar korekti score,
paliek saglabāti un atsevišķi norādīti kā neskaitāmi.

## DIXON_COLES_FORWARD

**BLOCKED_NEEDS_MORE_EVIDENCE.** 53 eligible pilnas 1X2 forecasts,
**14 resolved paired fixtures / 4 kickoff datumi**.
Visas sešas metodes izmanto vienu un to pašu 14-fixture sample.

| Metode | Fixtures | Brier | RPS | Log loss | ECE |
| --- | --- | --- | --- | --- | --- |
| CHAMPION | 14 | 0.5593 | 0.1602 | 0.9360 | 0.1715 |
| DIXON_COLES | 14 | 0.6181 | 0.1706 | 1.0159 | 0.1363 |
| MARKET | 14 | 0.6311 | 0.1826 | 1.0296 | 0.1558 |
| OO_EPC | 14 | 0.6356 | 0.1833 | 1.0282 | 0.1640 |
| POWER | 14 | 0.6357 | 0.1832 | 1.0312 | 0.1637 |
| SHIN | 14 | 0.6334 | 0.1829 | 1.0288 | 0.1621 |

DC pret champion: paired Brier delta **+0,058830**, log loss **+0,079921**,
RPS **+0,010434**, ECE **−0,035234**.
Pret multiplicative market: Brier **−0,013040**, log loss **−0,013696**,
RPS **−0,011958**. Šajā mazajā izlasē DC zaudē champion pēc trim proper scores,
bet nedaudz pārspēj market; stabils incremental contribution nav pierādīts.

CI nav: frozen minimums **30 fixtures un 7 datumi**.
Optimal DC pool weight null; fit minimums 300 un logs vēl atvērts.
Draw/favourite/longshot reliability, league/competition/lead-time/date-window
segments un deltas saglabāti dixon_coles.json.
Holdout nav lasīts; nav algoritma, capture, publication vai champion maiņu.

## MODEL_MARKET_DISAGREEMENT

**BLOCKED_NEEDS_MORE_EVIDENCE.** Pēdējos 12 ciklos **2398 candidate-market rows /
63 fixtures**. Severe contradiction **145 (6,05%)**, material disagreement
**762 (31,78%)**, ensemble divergence **112 (4,67%)**.
Vidējā absolute ensemble-market divergence **0,05930**.

Severe: HOME_WIN 53/278; UNKNOWN 50/311; YOUTH_U19_U20 42/238;
DOMESTIC_CUP 40/774. League 895 (Egypt League Cup) **49/220**, league 617 **42/238**.
Quote+API prediction grupā severe **96/2178 (4,41%)**;
quote bez API prediction **49/220 (22,27%)**, bet tikai četras fixtures.

Visiem scored rows ir price un nav stale failure marķiera: šie rows jau
izgājuši price admission. 2200/2398 saglabāto quote ages ir 1–4 h
esošās PREMATCH freshness politikas ietvaros, un tur ir 142/145 severe gadījumi.
Tas nav cēloņsakarības pierādījums: stale/no-quote fixtures bieži vispār
nenonāk scored candidate sample. Nevar no šī vien nošķirt modeļa kļūdu no provider kļūdas.
Pilna segmentācija un ierobežojumi: disagreement.json.

**NO_CHANGE.** PROVIDER_ZERO_PROBABILITY **17** candidate rejections.
Nulles nav clampotas, disagreement thresholdi nav mainīti.

## FINAL_REVIEW_QUEUE

**NO_CHANGE — PASS.** Reproducēti **12 dabiskie cikli / 103 attempts**.
Due maksimums **34**, attempted maksimums **10**.
Visos 12 sakrīt deadline/least-recent ordering un pirmās batch secība.
Same-cycle repeats **0**, invalid kickoff-window attempts **0**, batch limits PASS.
Visos šajos 12 provider calls zem cycle ceiling.

15:00 Riga cikla 24 pending bija due arī 15:30; divus no tiem pārbaudīja.
Nākamajā ciklā tie vairs nebija due. 17:30 cikla divus pending pārbaudīja 18:00.
Expiry netiek sajaukts ar rindas pazušanu.
Jaunu duplicate publications šajā logā nav. All-time 10 SINGLE fixture repeats
ir 21. septembra–1. oktobra vēsture; exact COMBO duplicates 0.
Rindas implementācija nav mainīta.

## RUNTIME_AND_QUOTA

**NO_CHANGE.** Pēdējo 24 h pieejamajos discovery/settlement/observer/DC journals:
DB locked 0, quota contention retry/exhausted 0, protected reserve errors 0,
FileNotFoundError 0, failed-result/timeout markers 0.
Tas ir pieejamo journal/ledger pārklājums, ne privātā ADMIN DB pilnas redzamības solījums.

Health evidence: 27 DEGRADED cikli, 2598 provider calls, 7184 tirgu novērtējumi,
798 fixture evaluations, 141 READY rows. Tie ir atkārtotu novērojumu skaiti;
DEGRADED ir data quality, ne 27 crashes.
Līdz cutoff dienas durable quota claims **3610**; atlikums **3890/7500**,
PREMATCH rezultātu rezerve **798**; 300/min limits nemainīts.

Publication cycles pēdējās 24 h: **55 SENT / 55 persisted receipts**,
rejected-before-transport 0, reconciliation-required 0, transport failures 0.
Pašreiz nav claims bez receipts ne public, ne private ledger.
Vēsturiskais delivery_unknown marķieris 1 ir saglabāts pēc reconcile un nav
atvērts missing receipt. Jauns COMBO Decimal mismatch nav atrasts.

**DATA_QUALITY_LIMITATION.** Pieci tickets vecāki par 6 h gaida pārceltās spēles.
20:45 Riga natural settlement diagnostika visām to unresolved kājām rāda
**PST / POSTPONED**. Mapping: overdue_results.json. Nav izdomātu VOID vai manual settlement.

**SMALL_GITHUB_FIX — FOLLOW-UP.** Observer/health avotā LIVE='DISABLED' ir hardcoded,
health CLI skatās veco goalvision-live-lab.timer. Reālais vakara timeris ir
goalvision-lab-live-evening.timer un ir ENABLED.
Šis handoff/runtime_state.json izmanto actual systemd/release autoritāti.
Runtime health lauka un ADMIN savietojamības labojums nav veikts/deployots;
to jāsaskaņo ar operatora LIVE lēmumu. Veco observer lauku nedrīkst izmantot
kā pierādījumu globālam LIVE OFF.

## VALIDATION_HOLDOUT_SHADOW

**NO_CHANGE.** Training runs **133** = 74 rejected + 1 reviewed bootstrap + 58 trained.
Model artifacts **59**, t.sk. 58 non-bootstrap artifacts.
Families: LOGISTIC 26, REGULARIZED_LOGISTIC 16, STUMP_ENSEMBLE 8,
CALIBRATED_ENSEMBLE 8, baseline 1. Pēdējais training: **2026-09-28**.

Embedded calibrator artifacts pēc esošā registry skaitījuma 0;
family nosaukums CALIBRATED_ENSEMBLE nav apstiprināts jauns calibration fit.
Validation results 0; holdout results 0; governance shadow runs/predictions/settlements 0/0/0;
candidate comparisons 0; promotion gates 0; promotion recommendations 0;
production promotions 0; rollbacks 0. Activation event 1 ir bootstrap.

DC research forecasts ir atsevišķa plūsma un neaizstāj governance gates.
VALIDATION sākums 2026-10-11 00:00 UTC; SEALED_HOLDOUT 2026-10-19 00:00 UTC.
Iepriekš rezervētie/izlietotie holdout ierobežojumi saglabāti.

## PROMOTION_ELIGIBILITY

**BLOCKED_NEEDS_MORE_EVIDENCE — NOT_ELIGIBLE.**
VALIDATION=0 un SEALED_HOLDOUT=0. Activation/promotion/rollback nav veikti.
Auto-training/calibration activation/promotion nav ieslēgti. Champion nemainīts.

## ACTION_ITEMS

1. **NO_CHANGE:** saglabāt sliekšņus, odds floors, staking un champion; nemainīt tos ROI dēļ.
2. **DATA_QUALITY_LIMITATION:** current odds coverage; neieviest blacklist no vienas fixture atkārtojumiem.
3. **BLOCKED_NEEDS_MORE_EVIDENCE:** pirms yield prioritizācijas pierādīt slot/budget konkurenci un reālu ieguvumu, pasargājot tracked/final review.
4. **SMALL_GITHUB_FIX — DONE:** read-only coupon/yield/disagreement exports un queue replay.
5. **BLOCKED_NEEDS_MORE_EVIDENCE:** calibration 246/300 plus atvērts logs; turpināt datu vākšanu.
6. **BLOCKED_NEEDS_MORE_EVIDENCE:** DC 14 fixtures/4 datumi; turpināt forward shadow bez modeļa maiņas.
7. **NO_CHANGE:** queue regression PASS; atkārtots queue fix nav vajadzīgs.
8. **DATA_QUALITY_LIMITATION:** pārceltos PST rezultātus turpināt pārbaudīt esošajos natural cycles.
9. **OPERATOR_ACTION_REQUIRED:** saskaņot LIVE DISABLED prasību ar jau aktivizēto vakara LIVE.
10. **SMALL_GITHUB_FIX — FOLLOW-UP:** pēc LIVE lēmuma sakārtot runtime health statusa un ADMIN readeru savietojamību.
11. **NO_CHANGE:** jauns classifier/dynamic DC/GNN nav pamatots un nav veidots.

## Reproducēšana un pārbaudes

Source commit 6e7ae9f64792c0152d7a90cc7b1da3f2467cf917 satur četrus jaunus read-only source/test failus.
Production nav jādeployo, lai atkārtotu auditu. Šīs komandas neizsauc worker ciklu vai transportu.

~~~bash
cd /home/arvis/goalvision-worktrees/prematch-evidence-20261006
GV_AUDIT_ASOF='2026-10-07T17:47:33.519387+00:00'
GV_AUDIT_OUT=/home/arvis/goalvision-operations/prematch-quality-replay-20261007
mkdir -p "$GV_AUDIT_OUT"

/home/arvis/GoalVisionAI/.venv/bin/python -I -B operations/watch-reconciliation/snapshot.py --as-of "$GV_AUDIT_ASOF" --database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db --ledger /home/arvis/GoalVisionAI/var/lab_combo/ledger.db --output "$GV_AUDIT_OUT"
/home/arvis/GoalVisionAI/.venv/bin/python -I -B operations/prematch-quality/audit.py --as-of "$GV_AUDIT_ASOF" --shadow /home/arvis/GoalVisionAI/var/lab_v2/shadow.db --ledger /home/arvis/GoalVisionAI/var/lab_combo/ledger.db --output "$GV_AUDIT_OUT"
/home/arvis/GoalVisionAI/.venv/bin/python -I -B operations/prematch-quality/queue_audit.py --as-of "$GV_AUDIT_ASOF" --shadow /home/arvis/GoalVisionAI/var/lab_v2/shadow.db --output "$GV_AUDIT_OUT/queue_replay.json"
/home/arvis/GoalVisionAI/.venv/bin/python -I -B operations/watch-reconciliation/incremental_report.py --as-of "$GV_AUDIT_ASOF" --research /var/lib/goalvision-dixon-coles-forward/research.db --audit /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db --ledger /home/arvis/GoalVisionAI/var/lab_combo/ledger.db > "$GV_AUDIT_OUT/dixon_coles.json"
/home/arvis/GoalVisionAI/.venv/bin/python -I -B operations/prematch-evidence/publication_audit.py --as-of "$GV_AUDIT_ASOF" --output "$GV_AUDIT_OUT/publication.json"
/home/arvis/GoalVisionAI/.venv/bin/python -I -B operations/watch-reconciliation/runtime_audit.py --as-of "$GV_AUDIT_ASOF" --output "$GV_AUDIT_OUT"
systemctl show goalvision-lab-live-evening.timer --property=ActiveState,UnitFileState
~~~

Dzīvā DB claim-inventory, champion-pointer vai vēlākā correction evidence var mainīties;
šī audita Git snapshot/report fingerprints saglabā sākotnējo evidence.
Arhivēts JSON bez timestamp nedrīkst tikt uzskatīts par pašreizējo statusu.

Testi: **130 PASS** focused matrix (10,13 s), **17 PASS** final changed-module tests (0,07 s).
17 testi pārklājas ar iepriekšējo matricu; tas nav 147 unikālu testu skaits.
Pārbaudīti receipt/cutoff/VOID/early-loss/provenance/no-COMBO-learning;
yield denominators/dedup/prior failure/missingness; disagreement;
esošā performance, frozen calendar/calibration, final queue un DC forward regresija.
Outbound sockets bloķēti, credentials sintētiski. Full suite nav palaists.
Real read-only smoke: 190 coupons, 24 odds cycles, 12 queue replay, sešu metožu DC report.
Production 857-file preflight atkārtoti PASS.

Changed source files:

- app/adaptive_lab/combo_evidence.py
- operations/prematch-quality/audit.py
- operations/prematch-quality/queue_audit.py
- tests/test_prematch_quality_evidence.py

Docs/evidence: šis handoff, TASKS.md audita ieraksts,
docs/evidence/prematch_quality_20261007/*.json un SHA256 manifest.

**Audit effects:** provider requests 0; Telegram sends 0; manual cycles 0;
production DB writes 0; deployments 0; champion/threshold/bankroll changes 0;
holdout fit/read 0. Jau instalētie natural timers turpināja darbu neatkarīgi.
Official pilnīgi neskarts; ADMIN Codex DISABLED; LIVE faktiski ENABLED.
Git publicēšana tikai audita branch, nekāda production branch maiņa.

Pabeigšanas Git statuss: audita darba branch ir tīrs pēc source/evidence commit;
abi commit publicēti GitHub branch work/prematch-quality-evidence-20261007.
Precīzais source commit norādīts augšā; handoff commit ir šī faila Git versija.
Oriģinālā runtime checkout 220 agrākie dirty paths saglabāti neskarti.
