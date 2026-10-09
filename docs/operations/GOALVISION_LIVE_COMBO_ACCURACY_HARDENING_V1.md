# GOALVISION_LIVE_COMBO_ACCURACY_HARDENING_V1

Fiksētais datu griezums: **2026-10-09 13:15:18.755867 Europe/Riga** (`2026-10-09T10:15:18.755867+00:00`).
Repository: https://github.com/ProjectX-oss/GoalVisionAI-v2

**Galvenais secinājums:** pašlaik prioritāte ir labāki pārbaudāmi dati, atsevišķa LIVE/PREMATCH kalibrācija un korekti salīdzināma atlase. Jauna sarežģīta AI modeļa nepieciešamība vai kvalitātes uzlabojums nav pierādīts. LIVE red-card konteksta modelēšanā ir reāls ierobežojums, bet nav pietiekamu datu, lai droši novērtētu tā parametrus. Nekas no šī darba nav production aktivizēts.

Pabeigts audits, trīs izolēti research papildinājumi, konkrēts offline replay labojums, testi un reproducējams evidence. Pilnvērtīgs fitted red-card modelis, calibrated C ranker un empīrisks COMBO joint modelis **nav pabeigts/pierādīts**: zemāk norādīti konkrētie datu bloķētāji. Fail-closed rezultāts nav kvalitātes uzlabojuma pierādījums.

## 1. ACTUAL_REPOSITORY_STATE

**NO_CHANGE** — sākotnējais VPS checkout `/home/arvis/GoalVisionAI` ir branch `codex/lab-v2-global-overhaul-2026-09-17`, HEAD `fadd59d7d9492133f84d9d80c9a72dad14c57c67`. Tajā ir **220 iepriekš pastāvējušas dirty status rindas**; pirms/pēc statusa SHA-256 vienāds. Tās netika rediģētas, stage-otas vai push-otas.

**SMALL_GITHUB_FIX** — atsevišķs worktree `/home/arvis/goalvision-worktrees/live-combo-hardening-20261009`, branch **`research/live-combo-accuracy-hardening-20261009`**. Bāze `94d81625ad8a9c1e0353a1a93850db5033ce1459` pirms darba sakrita ar GitHub remote. Pārskatītā source commit: **`5de7c646f3823d4abd39254703739a31278a2863`**. Source push ir autorizēts tikai šim research branch; production branch vēsture nav mainīta. Gala evidence commit/push SHA pievienots piegādes atbildē; pašreferējošs Git SHA nav ierakstīts faila saturā.

Repo AGENTS, PRODUCT_RULES, ROADMAP, TASKS un iepriekšējais operatora evidence ņemti vērā. Veco de-vig/DC/package repair darbu atkārtota ieviešana netika veikta.

## 2. INSTALLED_RELEASE_AND_CONFIG

**NO_CHANGE** — read-only wrapper atgriež `current_mode=ENABLED`, `ADMIN_CODEX_SYSTEMD_DISABLED=PASS`.

- LIVE: `/opt/goalvision-live-probability-band-bfe6d40-20261009`, source `bfe6d40d57be33e5f494b5576fce622aa6ce9788`.
- LIVE jaunā policy `LAB_LIVE_PROBABILITY_60_70_V1`; cohort `LIVE_P60_70_20261009_V1`.
- Inclusive p 0.60–0.70, ranking pēc p, EV filtrs/ranking izslēgti. Quote age tikai diagnostika. Nav jauna LIVE odds floor/cap.
- Final quote refresh, state/event freshness, score/minute/market un exposure pārbaudes saglabātas.
- LIVE timers **enabled/active**, `*:02/5:00 Europe/Riga`; discovery 18:00–23:00, pending results ārpus loga. Šodienas pirmais vakara cikls 18:02.
- PREMATCH release `/opt/goalvision-live-evening-4f547cf-20261007`; discovery 10:00–18:00, settlement turpinās. SINGLE≥1.50, private SINGLE un Double kāju politika saglabāta, DC COMBO kājas≥1.30.
- **143 GoalVision systemd failu SHA-256 pirms/pēc sakrīt**. Servisi/timeri nav kontrolēti vai restartēti. Official, champion, bankroll un staking nav mainīti.

## 3. LIVE_FAILURE_ROOT_CAUSE

**NO_CHANGE** — vecā EV-first cohort: **9 publikācijas, 7 spēles, 1W/8L, 0 pending**. Flat P/L **−7.556u**, ROI **−83.9556%** uz saglabātajām indikatīvajām cenām. Visām deviņām ir rezultāta receipt; kandidāta Poisson aprēķins, rates un settlement reproducējas. Nav konstatēta aritmētiska vai rezultāta piesaistes kļūda šajās deviņās prognozēs.

| Spēle | Min. / score | Kartītes H:A | Tirgus | Odds | p | 1/odds | EV | FT | Iznākums |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Holon Yermiyahu – Nordia Jerusalem | 60 / 2:0 | 0:0 | UNDER_3_5 | 1.525 | 82.07% | 65.57% | 25.16% | 5:0 | LOST |
| Atlético Tucumán Res. – Talleres Córdoba Res. | 19 / 0:0 | 0:1 | AWAY_WIN | 4 | 42.90% | 25.00% | 71.61% | 2:0 | LOST |
| Atlético Tucumán Res. – Talleres Córdoba Res. | 24 / 0:0 | 0:1 | UNDER_1_5 | 2.25 | 57.87% | 44.44% | 30.22% | 2:0 | LOST |
| Atlético Tucumán Res. – Talleres Córdoba Res. | 39 / 0:0 | 0:1 | AWAY_WIN | 5.5 | 36.72% | 18.18% | 101.96% | 2:0 | LOST |
| Hapoel Herzliya – Hapoel Mahane Yehuda | 79 / 0:0 | 0:0 | DRAW | 1.444 | 77.78% | 69.25% | 12.32% | 0:0 | WON |
| Belgrano Córdoba Res. – San Martín San Juan Res. | 49 / 2:2 | 0:0 | AWAY_WIN | 7 | 17.85% | 14.29% | 24.94% | 3:2 | LOST |
| Txantrea – Cortes | 58 / 0:0 | 0:0 | AWAY_WIN | 5 | 25.22% | 20.00% | 26.12% | 0:0 | LOST |
| Shamrock Rovers – Drogheda United | 27 / 2:0 | 0:0 | AWAY_WIN | 51 | 5.99% | 1.96% | 205.63% | 3:1 | LOST |
| Flamengo U20 – Vasco da Gama U20 | 23 / 0:0 | 0:0 | HOME_WIN | 3.1 | 36.94% | 32.26% | 14.52% | 2:2 | LOST |

`1/odds` ir raw price-implied probability, **nav de-vig fair probability**. EV aprēķināts no nevalidētas model probability un feed quote, nevis garantētas izpildāmas cenas.

**BLOCKED_NEEDS_MORE_EVIDENCE** — riska mehānismi, nevis pierādīta katra zaudējuma cēlonība:

1. Vecā max-EV atlase deva priekšroku arī ļoti zemai p: sešām publikācijām p<50%; viena bija odds 51.00 ar p≈5.99%. Jaunajā policy šis EV ranking jau izslēgts operatora darbībā.
2. Trīs Atlético Tucumán–Talleres izvēlēm bija away sarkanā kartīte. Baseline goal intensity no kartītēm nemainījās; tikai uncertainty pieauga līdz 0.11, zem esošā 0.12 limita. Tas ir konkrēts modelēšanas ierobežojums, nevis koeficienta vērtības novērtējums.
3. Vienai spēlei bija trīs izvēles, tostarp divas AWAY_WIN. Esošie rebet/exposure noteikumi tās pieļāva; tas nebija nejaušs transporta dublikāts. Šie rezultāti nav deviņi neatkarīgi notikumi.
4. Baseline izmanto ierobežotu iepriekšējo FT rezultātu izlasi; nav xG/shots/lineups efekta, opponent-strength regression vai fitted red-card efekta. Dažos frozen history datos vecākā spēle ir ap 730 dienām veca. Current/future fixtures baseline filtrē ārā — to klātbūtne raw API vēstures atbildē pati par sevi nav leakage.
5. Holon 2:0 pie 60. minūtes/UNDER3.5 beidzās 5:0; Belgrano 2:2/AWAY beidzās 3:2; Txantrea 0:0/AWAY beidzās 0:0; Shamrock 2:0/AWAY beidzās 3:1; Flamengo HOME beidzās 2:2 regulārajā laikā. Šie iznākumi nepierāda datu kļūdu. Pilna turpmāko notikumu laika secība nav saglabāta katrai spēlei; papildu provider dati netika pieprasīti.

Vecās cohort model Brier **0.179145**, log loss **0.540302**, ECE **0.364211**, bias **+0.314841**. Raw-price baseline Brier **0.109164**, log loss **0.366274** uz tām pašām deviņām izvēlēm. Šī mazā atlasītā izlase nedod statistiski drošu modeļa verdict.

## 4. LIVE_CONTEXT_MODEL_V2

**SMALL_GITHUB_FIX / BLOCKED_NEEDS_MORE_EVIDENCE** — ieviests `LIVE_CONTEXT_AWARE_POISSON_V2` kā izolēts **zero-card venue/competition ablation prototips**. Tas izmanto actual score, minute, atlikušās regulārās spēles minūtes, tās pašas līgas home/away vēsturi, novērotus attack/defence rates; atkārtoti izmanto esošo Poisson evaluatoru.

Validēta as-of secība, score/goal-event atbilstība, kartīšu skaits, event minūte, source hashes, dubultoti history ID. Future/current history rindas tiek izslēgtas; trūkstoši signāli netiek izgudroti. Atteikums pie sarkanās kartītes bez novērtēta efekta, nepietiekamas venue/competition vēstures, neatbalstītas own-goal/goal semantikas vai nenomodelēta atlikušā stoppage time. Nav default league rate vai fiksēta card multiplier.

Reālajā replay: **563 kandidātu versijas / 41 spēle**, tikai **7 forecast versijas / 1 spēle** ar pietiekamu prototipa input. **556** versijām nepietiek venue/competition history, **67** ir kartītes bez fitted efekta, **19** neatbalstīta goal-event semantika, **11** neatbalstīts atlikušais laiks; iemesli pārklājas. Paired resolved sample **0**, tādēļ Brier/log-loss/hit-rate uzlabojums **nav aprēķināms**. Neviens trūkstošs rezultāts nav aizstāts ar pieņēmumu.

**LARGER_CODEX_TASK** — pilns fitted red-card/context modelis tikai pēc atbilstošas as-of event/exposure datu kopas, league/strength/time coverage un atsevišķi deklarēta forward protokola. Šajā darbā nav piedēvēts literatūras koeficients mūsu līgām. V2 nav pieslēgts worker.

## 5. LIVE_POLICY_COMPARISON

**SMALL_GITHUB_FIX** — A/B/C salīdzina vienus un tos pašus 108 saglabātos snapshot pool. A atkārto jaunās band/ranking sākotnējos gates; B research režīmā pievieno pozitīvu EV, pozitīvu multiplicative fair edge un esošo divergence bound pret complete current market. C skaidri bloķējas bez LIVE kalibrācijas un context evidence.

| Research screen | Snapshot pool | Nominācijas | No-pick pool | W/L/pending | Brier | Log loss | Indikatīvs P/L / ROI |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A_CURRENT_60_70 | 108 | 43 | 65 | 4/6/33 | 0.2963 | 0.7898 | -4.5140 / -45.14% |
| B_VALUE_CONTROL | 108 | 25 | 83 | 1/4/20 | 0.3470 | 0.8932 | -3.5250 / -70.50% |
| C_CONTEXT_CONFIDENCE | 108 | 0 | 108 | 0/0/0 | — | — | 0.0000 / — |

**BLOCKED_NEEDS_MORE_EVIDENCE** — šīs **nav 43 vai 25 reāli izpildītas likmes**. Tie ir atkarīgi snapshot nomināciju replay, ar actual historical exposure un daudziem nenovērotiem rezultātiem. Saglabātajām rindām trūkst precīza initial-vs-final-refresh cycle pool taga; counterfactual final quote nav pieejams. Tas neļauj apgalvot precīzu cikla backtest, ievērot hipotētisku 1/cycle izpildi vai izvēlēties uzvarētāju pēc šo apakškopu ROI. Publicēti/sūtīti šajā research = 0; paired strategy delta/CI nav piešķirts.

Jaunais prospective cohort atsevišķi: **0 publikāciju, 0 settled, 0 W/L/VOID**, jo griezums ir pirms šodienas vakara discovery. Vecie 1W/8L nav pārnesti uz to. Jaunā 60–70% politika pagaidām ir operatora eksperiments, nevis pamatota kalibrēta win-rate garantija.

## 6. COMBO_PERFORMANCE

**NO_CHANGE** — authoritative receipt-backed current evidence: **199 publicēti, 195 settled, 69W/126L, 0 VOID/partial, 4 pending**. Flat P/L **−21.350797u**, ROI **−10.9491%**. Prospective cohorti un vēsturiskie rezultāti saglabāti.

| Cohort | Publicēti | Settled | W / L / VOID / partial | Pending | Vid. odds | Mediāna | P/L, u | ROI | Max L sērija |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Legacy | 19 | 19 | 1 / 18 / 0 / 0 | 0 | 72.2258 | 39.2126 | -5.5729 | -29.33% | 9 |
| Singles-Based V1 | 68 | 66 | 32 / 34 / 0 / 0 | 2 | 2.0604 | 1.7161 | -6.2439 | -9.46% | 4 |
| Singles-Based V2 | 53 | 51 | 21 / 30 / 0 / 0 | 2 | 2.7807 | 2.6991 | 4.9831 | 9.77% | 6 |
| Market V1 | 39 | 39 | 10 / 29 / 0 / 0 | 0 | 2.7708 | 2.6277 | -10.5250 | -26.99% | 7 |
| DC Agreement | 20 | 20 | 5 / 15 / 0 / 0 | 0 | 3.1213 | 2.9732 | -3.9921 | -19.96% | 6 |
| Double 1.70 / 70–80% | 0 | 0 | 0 / 0 / 0 / 0 | 0 | — | — | 0.0000 | — | 0 |

Pilni probability, reliability, market/league, odds, lead-time un quality griezumi atrodas `current/combo.json`, `prematch/combo_calibration.json`, `hardening_reviewed.json`. VOID/partial VOID binary score neietver; testa coverage tiem ir arī tad, ja pašreizējā griezumā šādu iznākumu nav.

## 7. COMBO_ROOT_CAUSES

**BLOCKED_NEEDS_MORE_EVIDENCE** — visi 195 settled kuponi un to saglabātās kājas pārbaudītas. No 126 zaudētiem kuponiem **70** zināma viena zaudējusi kāja, **43** divas un **13** trīs. Pieciem publicētiem kuponiem kāda kāja vēl ir UNKNOWN; tas ietver pending/remaining-leg stāvokli un netiek pārrakstīts.

| Tirgus | W | L | Unknown/VOID | Candidate versijas |
| --- | --- | --- | --- | --- |
| UNDER_3_5 | 111 | 54 | 4 | 169 |
| OVER_1_5 | 162 | 48 | 2 | 212 |
| OVER_2_5 | 48 | 21 | 0 | 69 |
| BTTS_YES | 18 | 17 | 0 | 35 |
| DRAW | 7 | 16 | 0 | 23 |
| UNDER_2_5 | 27 | 15 | 0 | 42 |
| AWAY_WIN | 3 | 10 | 0 | 13 |
| BTTS_NO | 10 | 7 | 0 | 17 |

Tabulas vienība ir deduplicēta `(fixture, market, candidate_id)` kājas versija, ne neatkarīga spēle. Absolūts zaudējumu skaits bez exposure denominātora un paired salīdzinājuma nepierāda, ka tirgus ir slikts. Visbiežāk zaudējušo kāju līgu ID ir 5, 36, 10 un 46; cohort/league denominatori un calibration ir JSON. No šī netiek veidota blacklist.

83 kuponiem dalīta līga, 193 dalīta market family, 199 dalīta signal family. Nav konstatēts shared fixture/team vienā kuponā. Šie ir **riska indikatori**, ne izmērīts kļūdu korelācijas koeficients. Kopīga modeļa kļūda var skart vairākas kājas, bet precīzs pieaugums datos nav identificēts.

Nedrīkst vainot tikai pārlieku p: kopējais scored naive joint vidējais ir **33.15%**, novērotais hit rate **35.38%**, bias **−2.23 procentpunkti**. Atšķirīgi cohorti, agrīni zaudējumi un neliels efektīvais sample padara kopējo vidējo nepietiekamu kalibrācijas spriedumam. Verified frozen calibrated leg probabilities/artifacts nav pieejami; raw/ensemble p nav pārdēvēta par calibrated.

## 8. COMBO_STRATEGY_COMPARISON

**NO_CHANGE** — atkārtoti izmantotas esošās Double un V2 Singles-Based atlases; netika veidota otra arhitektūra. Atjaunots 24 dabisko PREMATCH ciklu replay uz vienādiem **18 430 candidate-cycle ierakstiem**. Katram variantam ir atsevišķs in-memory exposure carry-forward; original prices, source hashes un recorded preparation-end clock saglabāti.

- A Double: **0 izvēļu, 24 no-pick cikli**. Gan actual, gan šī replay kvalitātes evidence nepietiek.
- B V2: **35 hipotētiski kuponi**, 11 ar zināmu iznākumu (**1W/10L**), **24 pending**, 11 no-pick cikli. Pašreizējais indikatīvais P/L −6.9808u / ROI −63.46% ir **nenobrieduša retrospective sample**, ne prospective performance un ne pamats production maiņai.
- C Quality/Value-First: **0 izvēļu, 24 no-pick cikli**. Verified as-of leg calibration un validated joint model trūkst; ranker nav ieslēgts vai uzdots par gatavu.

**BLOCKED_NEEDS_MORE_EVIDENCE** — actual V2 ROI +9.77% uz 51 settled kupona nav statistiski ticami pierādīts pārākums: tikai **2 day/fixture-connected clusters**, vēl 2 pending. Esošais CI minimums 30 kuponi/7 clusters nav mīkstināts. Market ir 3 clusters, DC 5. Dažādu atlasītu kuponu Brier/ROI nav paired delta. Neviens comparator nav pieslēgts publikācijai.

## 9. JOINT_PROBABILITY_ANALYSIS

**SMALL_GITHUB_FIX** — saglabāta naive product/Frechet bounds diagnostika un pievienota precīza finite-score scenario integrācija ar pinned artifact hash, as-of, fixture/market, input provenance un total mass=1 pārbaudi. Tests ar vienādām marginals 0.6/0.6 parāda joint **0.6** korelētā synthetic scenario pret product **0.36**; tas ir matemātikas tests, ne GoalVision correlation novērtējums. Arī 1e−41 mass neatbilstība netiek noapaļota prom.

**BLOCKED_NEEDS_MORE_EVIDENCE** — production kuponiem nav verified joint scenario artifact, empīriska joint calibratora vai pierādīta cross-fixture dependence modeļa. Atsevišķu Poisson/DC spēļu sadalījumu reizināšana joprojām pieņem neatkarību; nav pamata to pārdēvēt par correlation-adjusted modeli. Empīrisks fit netika veikts. Positive COMBO EV **nav pierādīts**.

| Cohort | Scored n | Vid. joint p | Hit rate | Brier | Log loss | ECE | Bias p−y |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Legacy | 19 | 11.46% | 5.26% | 0.0538 | 0.2165 | 0.0620 | 0.0620 |
| Singles-Based V1 | 66 | 44.98% | 48.48% | 0.2318 | 0.6547 | 0.1082 | -0.0350 |
| Singles-Based V2 | 51 | 31.80% | 41.18% | 0.2563 | 0.7094 | 0.1157 | -0.0938 |
| Market V1 | 39 | 29.01% | 25.64% | 0.1971 | 0.5835 | 0.1174 | 0.0336 |
| DC Agreement | 20 | 26.24% | 25.00% | 0.1970 | 0.5876 | 0.0741 | 0.0124 |
| Double 1.70 / 70–80% | 0 | — | — | — | — | — | — |

Legacy mazākais Brier neatļauj to nosaukt par labāko stratēģiju: atšķiras outcome frequency, odds, selekcija un neatkarīgo datu apjoms. Reliability bins, MCE, bias un scope ir evidence; nevienā cohort nav dota ranking eligibility.

## 10. CALIBRATION_READINESS

**NO_CHANGE** — PREMATCH bootstrap generation `generation-aa7e535b86267741aabc967e8044de2ab94a4334b1520a829414dd55ebc7371a`, family `EXISTING_PREMATCH_BASELINE_V1`, feature schema `LAB_FROZEN_FEATURES_V1`, sākotnējā aktivācija 2026-09-18 19:53:42 UTC, stage **CHALLENGER_RESEARCH**.

**BLOCKED_NEEDS_MORE_EVIDENCE** — total observations **2885**, resolved eligible **2872**, independent resolved fixtures **1166**. TRAIN **1804 observations / 560 fixtures**; CALIBRATION_FIT **299 / 299 independent fixtures**; VALIDATION **0**, SEALED_HOLDOUT **0**, PURGED **760 / 298**, EXCLUDED **22 / 20**. 12 legacy COMBO_LEG ieraksti ir izslēgti no neatkarīgas PREMATCH mācīšanās; jauni COMBO learning ieraksti = 0.

Readiness **NOT_READY**: pietrūkst vienas neatkarīgas fixture un logs vēl nav aizvērts. Fit close **2026-10-10 03:00 Riga**; VALIDATION no 2026-10-11 03:00 Riga, HOLDOUT no 2026-10-19 03:00 Riga (frozen JSON robežas ir UTC). Nav fit, jauna calibration artifact, holdout patēriņa vai promotion.

Nākamā atļautā darbība: pēc abiem gates izpildītiem palaist esošo research-only identity/Platt/temperature salīdzinājumu tikai CALIBRATION_FIT. Isotonic esošais minimums ir 1000, nevis 300. Saglabāt model generation, partition, feature schema, fingerprint un timestamps. PREMATCH fit nevar automātiski kalibrēt atšķirīgo LIVE baseline vai COMBO joint.

Dataset fingerprint: `437cc88bf101222b9dbf426e10a9d5442d9ceb855060c21cb7dca72f7ee831d2`. Partition overlap visos pāros 0.

## 11. ODDS_AND_DATA_QUALITY

**NO_CHANGE / BLOCKED_NEEDS_MORE_EVIDENCE** — LIVE auditā 563 saglabātās versijas/41 fixture; quote-age buckets: 0–10s **17**, 10–20 **147**, 20–30 **231**, 30–45 **116**, 45–60 **45**, >60 **7**. Aktīvā quote age politika netika mainīta. Initial candidate quote-retrieval→preparation vidēji **0.0862s**, mediāna **0.0653s**; tas **nav HTTP latency**. Precīzs HTTP start/end nav saglabāts.

LIVE kopš 07.10. 03:00 Riga līdz griezumam: 2058 fixture-discovery exposures, 1720 odds rows, 336 reviewed fixture exposures; 250 state/quote mismatch, 111 unsupported market, 5 review unavailable. Atkārtotas exposures nav neatkarīgas spēles. Final refresh: 14 missing quote, 4 readiness blocked, 1 failure. 9 prediction + 9 result sends jau esošajā vēsturē; 9 claims/9 confirmed publications un nav claims bez receipt. Agent sends=0.

LIVE dabisko ciklu provider calls šajā logā **2173**, ap **241.44/publication**; šis nav jauns dienas budžets vai agent calls. Tikai 11 vienāda observable state quote pāri; tajos nav cenas izmaiņas, bet ar to nepietiek slippage vai cenu izpildāmības secinājumam. 543/563 versijām var salikt pilnu vienlaicīgu current feed market de-vig diagnostikai; 13 nepilnīgas, 7 inactive market. Feed nav verificēta bookmaker izpildāma cena.

PREMATCH 24 ciklu broad-scope **4831 fixture-observation / 628 unique fixtures**: fresh usable **1937 (40.10%)**, stale **993 (20.55%)**, no-record **558 (11.55%)**, mainījusies pagination **911**, final-review reserve-limited pagination **283**, bookmaker filter **110**, incomplete comparable books **39**. Tās ir atšķirīgas kļūmju klases.

Exact: **510 HTTP calls**, **447 reģistrēti fixture outcomes**, **222 fresh successes (49.66%)**, **2.297 calls/zināmu fresh success**. 54 stale, 171 bez pietiekami detalizēta failure reason. Atkārtots no-yield **106/148 (71.62%)** pēc iepriekšējas neveiksmes; tracked exact **124/207 (59.90%)**. Breakdown pa league/competition/country/lead-time/status ir `prematch/odds_yield.json`; date-sweep calls **402** netiek sajaukti ar exact denominatoru.

**BLOCKED_NEEDS_MORE_EVIDENCE** — nav izmērīts drošs API secības/budžeta optimizācijas ieguvums vai precīzs duplicate HTTP calls skaits: trūkst request-phase/latency/raw mismatch provenance. Tādēļ netika ieviesta spekulatīva prioritātes vai budget maiņa. Nākamais konkrētais solis ir pasīva phase/HTTP timing diagnostika esošajās atbildēs, ar atsevišķu operatora release lēmumu; papildu API calls tai nevajadzētu.

PREMATCH jaunākie 12 rehearsal: 13 408 candidate rows / 322 fixtures, MATERIAL_SIGNAL_DISAGREEMENT **4428 (33.03%)**, SEVERE_MODEL_MARKET_CONTRADICTION **447 (3.33%)**, ENSEMBLE_MARKET_DIVERGENCE_TOO_LARGE **351 (2.62%)**, PROVIDER_ZERO_PROBABILITY **11**. Vidējā absolute divergence **0.05610**. Segments/freshness/context quality ir JSON; tie nepierāda vienīgi modeļa vai vienīgi stale-data cēloni. Zero nav clamp-ots.

Runtime 24h pārskatā nav journal match DB lock, quota contention/exhaustion vai FileNotFoundError. Septiņas settlement `DISCOVERY_ACTIVE` deferrals ir guard darbība, ne pierādīts deadlock. PREMATCH observer 16 cikli DEGRADED data-quality dēļ; 2166 recorded natural provider calls, UTC dienas quota claims 2073. Šie logi/denominatori nav jāsaskaita ar divu dienu LIVE logu. Admin pilnais privātais incidentu reģistrs netika atvērts; zero journal matches nav absolūts visu kļūdu neesamības pierādījums.

## 12. EXTERNAL_TECHNICAL_RESEARCH

**NO_CHANGE** — izmantoti principu un datu prasību salīdzinājumi; ārējs prediction kods vai koeficienti nav kopēti, jaunas atkarības/nav abonementu.

| Avots | Tehniskais/reproducējamības vērtējums | Licence/dati/izmaksas | GoalVision lēmums |
| --- | --- | --- | --- |
| [Maia et al., dynamic scoring](https://arxiv.org/abs/2312.04338) un [autorreplication](https://github.com/luizfgnmaia/football-dynamic-regressors) | Context/event intensities un empīriski rezultāti uz Brazīlijas datiem; ir R scripts un scoring-rule analīze. Tas nav mūsu līgu out-of-sample pierādījums. | Repo inspection neidentificēja licence failu; reproducēšanā izmantots MOSEK ar academic licence. Vajadzīga event/minute ekspozīcija. | Pārņemt as-of/context ideju, nepārņemt fiksētu card % vai šo atkarību stack. |
| [scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html), [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html), [issue #8043](https://github.com/scikit-learn/scikit-learn/issues/8043) | Reproducējams kods/testi; disjoint fitting, chronology un CV-partition ierobežojumi. Zemāks Brier viens pats nepierāda labāku calibration. | [BSD-3-Clause](https://github.com/scikit-learn/scikit-learn/blob/main/COPYING); izmantojami esošie dati, 0 jaunu provider calls. | Saglabāt frozen calendar un fixture purge; neatjaunināt bibliotēkas šajā darbā. Issue ir vēsturiska diskusija, ne aktuāla buga apgalvojums. |
| [penaltyblog](https://github.com/martineastwood/penaltyblog), [de-vig docs](https://penaltyblog.readthedocs.io/en/latest/implied/implied.html) | Reproducējami goal un margin-removal komponenti. Nav pierādīta GoalVision incremental priekšrocība. | MIT; current quotes der jau esošajai implementācijai; nav vajadzīgi jauni API calls. | Esošos multiplicative/Shin/Power/OO-EPC comparatorus atkārtoti izmantot. |
| [StatsBomb Open Data](https://github.com/hudl/open-data) | Event/lineup dati noteiktiem vēsturiskiem mačiem var palīdzēt context pētniecībai, bet nav mūsu aktuālo spēļu LIVE xG. | Publiski research dati ar attribution/atsevišķiem licence nosacījumiem; nav historical bookmaker odds. Dati šeit netika lejuplādēti vai fit-oti. | Iespējams atsevišķs vēlākas datu piemērotības darbs; ne jauns maksas LIVE feeds. |
| [Accumulator stochastic search paper](https://arxiv.org/abs/2004.08607) | Kombināciju optimizācijas pētījums ar eksperimentu; tas nepierāda pareizas marginal p vai cross-fixture dependence mūsu datos. | Papildu bibliotēka netika instalēta; mūsu as-of candidate pool jau pieejams. | Vispirms probability/data kvalitāte, ne sarežģītāks kuponu meklētājs. |
| [Reddit calibration](https://www.reddit.com/r/algobetting/comments/1qm5fyz/advice/), [joint/parlay diskusija](https://www.reddit.com/r/algobetting/comments/1pqwuqj/calculating_odds_for_single_game_parlay/) | Anektodiski argumenti; nav pārbaudīta reproducējama OOS evidence. | Nav izmantots kods, dati vai licences pieņēmumi. | Nav implementācijas pamats; tehniskās izvēles balstītas primārajos avotos un mūsu testos. |

Pilns URL/provenance saraksts un fingerprint: `external_research.json`.

## 13. IMPLEMENTED_CODE

**SMALL_GITHUB_FIX** — source commit `5de7c646f3823d4abd39254703739a31278a2863`:

- `app/live_lab/context_research.py`
- `app/live_lab/policy_research.py`
- `app/adaptive_lab/joint_scenarios.py`
- `operations/live-combo-hardening/audit.py`
- `operations/live-combo-hardening/README.md`
- `operations/live-combo-research/audit.py`
- `tests/adaptive_lab/test_accuracy_hardening.py`

Konkrētais labojums: iepriekš 24-ciklu COMBO replay beidzās `sqlite3.OperationalError: interrupted`, jo 60s read timeout turpinājās CPU-intensive selection laikā. Tagad vispirms materializē bounded immutable source rindas un aizver DB, pēc tam rēķina. Query-only režīms, integrity checks un publication gates nav mīkstināti. Tas ir offline rīka, ne production SQLite contention labojums.

Trīs research moduļiem nav runtime caller; tikai offline adapteris tos importē. C production selector, fitted card modelis, validēts joint calibrators vai automātisks capture job nav ieviests. Pārējais šī commit apjoms ir diagnostika, tests un dokumentācija.

## 14. TEST_RESULTS

**NO_CHANGE** — **737 passed / 0 failed**, 30 focused/adjacent test faili, 39.87s. Tas nav visas repository testu kopas izpildes apgalvojums. Jaunie focused gadījumi sedz 0/1/vairākas kartītes, future/missing/context/goal/score konfliktus, venue sample, exact 60–70 robežas, EV-off vs value screen, complete market chronology, duplicate/exposure, labels-in-input, immutable replay un joint scenario precision.

Adjacent pārbaudes: LIVE initial/final pipeline, quota reserve/contention, PREMATCH un COMBO Double/aggregate/early loss, VOID/partial VOID, result replies, delivery claims/dedup, final review, de-vig, calibration chronology, holdout isolation, no-COMBO-learning un operator installer regression. Visi tīkla transporti fake/mock; socket connect aizliegts.

Offline E2E uz reāliem **read-only** avotiem: LIVE postmortem, actual coupon report, 24-ciklu COMBO replay, current odds/disagreement/learning/DC/runtime un jaunais hardening report. `live.json`, `combo.json`, `replay.json`, `hardening_reviewed.json` atkārtotā fiksēta-cutoff izpildē ir **byte-identical**. Pirmā kļūda, tās cēlonis un labojums saglabāti `validation.json`.

Reproducēšanas komandas ir `operations/live-combo-hardening/README.md`; pilna precīza 30-failu test komanda — `validation.json` laukā `test_command`. Nav jāpalaiž production worker vai jāizmanto `--send`.

## 15. PERFORMANCE_EVIDENCE

**NO_CHANGE** — old LIVE, new LIVE cohort, shadow screens un actual COMBO cohorti netiek sajaukti. Paired baseline/V2 model sample=0; alternatīvu strategy ROI nav paired performance. All-time SINGLE/PREMATCH performance un segmenti saglabāti `learning/performance.json`, bez threshold tuning.

Dixon–Coles forward **29 paired fixtures / 5 kickoff dates**:

| Metode | Fixture n | Brier (1X2 sum) | Log loss | RPS | ECE |
| --- | --- | --- | --- | --- | --- |
| CHAMPION | 29 | 0.5539 | 0.9298 | 0.1761 | 0.0788 |
| DIXON_COLES | 29 | 0.6074 | 1.0166 | 0.1929 | 0.1176 |
| MARKET | 29 | 0.5897 | 0.9783 | 0.1886 | 0.0578 |
| OO_EPC | 29 | 0.5896 | 0.9738 | 0.1882 | 0.0960 |
| POWER | 29 | 0.5899 | 0.9754 | 0.1881 | 0.0898 |
| SHIN | 29 | 0.5893 | 0.9755 | 0.1882 | 0.0896 |

**BLOCKED_NEEDS_MORE_EVIDENCE** — DC šajā sample zaudē champion/market pēc Brier/log loss/RPS, bet 30 fixtures/7 dates CI gates nav sasniegti. Optimal forward pool weight nav pierādīts/fit-ots. Capture worker, DC algoritms un champion nav mainīti. Draw/favourite/longshot calibration un paired deltas ir `dc_forward.json`.

Governance: training runs **133** (74 REJECTED, 1 REVIEWED_BOOTSTRAP, 58 TRAINED), model artifacts **59**, verified calibration artifacts **0**, validation results **0**, holdout results **0**, governance shadow runs/predictions/results **0**, candidate comparisons **0**, promotion gates **0**, rollback events **0**. Viena activation ir sākotnējais bootstrap; **0 jaunu promotions**. Research forward forecasts nav governance shadow validation aizstājējs.

**PROMOTION_ELIGIBILITY = NOT_ELIGIBLE**. Atvērts calibration logs un validation/holdout=0 aizliedz activation secinājumu.

Source fingerprints:

- LIVE postmortem: `6e22d5b635beffe41ec267d8d7d580296111018cb76cb67dd19be97edf7ce100`.
- New hardening source: `f6137a6cb42409a7f356d97d3633b05b2058a7f7b34018da5fae6460a926c73a`.
- COMBO source: `1712e99af4c73ea69be328022b0132fd147640458057770a94638779da9eb026`.
- Hardening report: `5ca6163579a9ef145363cbb2c4b5a55631768004023ed4a6836aa9e0d0771c0c`.
- Calendar dataset: `437cc88bf101222b9dbf426e10a9d5442d9ceb855060c21cb7dca72f7ee831d2`.
- Visu reviewed evidence failu SHA-256: `manifest.json`.

## 16. RISKS_AND_LIMITATIONS

**BLOCKED_NEEDS_MORE_EVIDENCE** — 9 veci LIVE rezultāti, 0 jauni LIVE results, 0 Double kuponi un 2 neatkarīgi savienoti V2 COMBO clusters nav pietiekami stratēģijas izvēlei. Snapshot replay nav prospective trial; initial/final phases un counterfactual transporti nav atjaunojami. Nezināmi rezultāti paliek pending. Agrīni zaudējumi var nobriest ātrāk par uzvarām. Netiek slēpti zaudējumi vai pārrakstītas izvēles.

V2 data rejection samazina coverage, bet tas pats par sevi nepalielina precizitāti. Kvalitatīvākam red-card modelim vajadzīgs novērtēts event-time efekts, ne fiksēts procents. Scenario integrācijas korektums nepierāda, ka scenario distribution ir patiess. Complete de-vig feed nav executable bookmaker quote.

## 17. NEXT_OPERATOR_ACTIONS

1. **NO_CHANGE** — ļaut esošajam LIVE 18:00–23:00 timeram dabiski krāt jauno `LIVE_P60_70_20261009_V1`; salīdzināt to atsevišķi. Šajā auditā nekāds cikls nav forsēts.
2. **BLOCKED_NEEDS_MORE_EVIDENCE** — pēc 10.10. 03:00 Riga pārbaudīt CALIBRATION_FIT≥300; tikai tad esošais research-only identity/Platt/temperature salīdzinājums. Šodienas 299 un open window vēl neatļauj fit.
3. **OPERATOR_APPROVAL_REQUIRED** — ja grib pilnu natural-cycle shadow trial, vajag atsevišķu pasīvas initial/final phase, HTTP latency un original pool evidence capture release. Nemainīt thresholds; nepalielināt API budget; šajā darbā nav deployment paketes vai apply komandas.
4. **BLOCKED_NEEDS_MORE_EVIDENCE** — pirms C ranker vai empīriska joint fit savākt pietiekamus neatkarīgus kalibrētus kāju/coupon inputs un paired prospective outcomes. Pašreizējais no-pick ir pareizs fail-closed stāvoklis.
5. **LARGER_CODEX_TASK** — tikai pēc konkrētas datu pieejamības pārbaudes plānot fitted red-card/opponent-context parametru darbu. Nav pamata uzreiz būvēt GNN vai vēl vienu classifier.
6. **NO_CHANGE** — neveikt DC, champion, Official, staking vai aktīvās LIVE/COMBO stratēģijas maiņu no šī ziņojuma.

Noslēgums: **0 production deployment, 0 agent API-Football calls, 0 Telegram calls/sends, 0 Official/champion/bankroll izmaiņu**. LIVE timers/config nemainīti, aktīvi. Pārskatīts tikai izolētais research branch; sākotnējās 220 dirty rindas saglabātas. Gala research worktree pēc evidence commit ir tīrs, precīzs GitHub push rezultāts norādīts piegādes atbildē.
