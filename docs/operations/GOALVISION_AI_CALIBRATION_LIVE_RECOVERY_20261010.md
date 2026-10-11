# GOALVISION AI — CALIBRATION & LIVE RECOVERY V1

Pabeigts 2026-10-11, turpinot nepabeigto 2026-10-10 darbu. Faila datums saglabāts pēc uzdevuma prasības.

**Galvenais secinājums:** LIVE final-review budžeta labojums ir pareizs un jau uzstādīts. Kalibrācijas eksperiments reproducējas, bet nav neatkarīgi validēts. LIVE/COMBO/DC kvalitātes uzlabošanās nav pierādīta. LIVE faktiski paliek ieslēgts, pretēji šī Watch uzdevuma vēlamajam stāvoklim; timeri netika mainīti.

Autoritatīvo DB kopiju cutoff: **2026-10-11 11:05:21.700896 UTC / 14:05:21 Riga**.
Systemd/release pārbaude: 11:07 UTC; aizsargāto failu atkārtota pārbaude: 11:26:33 UTC.
Odds diagnostikai izmantoti pēdējie 12 cikli pirms 10:59:59.999999 UTC. 11:00 cikls cutoff brīdī vēl strādāja: 44 tā quotes pienāca vēlāk. Šis cikls izslēgts pilnībā. COMBO replay pats pārbauda preparation completed_at un vēlākus ciklus neizmanto.
Kalibrācija ir sākotnējā **10. oktobra** eksperimenta reproducēšana no tā oriģinālās DB kopijas, nevis jauns atpakaļdatēts fit.

Pierādījumi:
- `docs/evidence/calibration_live_recovery_20261010/` — saglabātais iepriekšējais eksperiments un audits.
- `docs/evidence/calibration_live_recovery_resume_20261011/` — aktuālais turpinājums, manifesti, metrics un pārbaudes.
- Privātās immutable DB kopijas nav GitHub. Saglabāti sākotnējie audit/settlement ieraksti.

## 1. CURRENT_GITHUB_AND_VPS_STATE

**PASS; NO_CHANGE — production.**

Repository: https://github.com/ProjectX-oss/GoalVisionAI-v2

| Objekts | Faktiski pārbaudītais stāvoklis |
|---|---|
| GitHub default branch | `clean`, `64c950d6d3b2b890b1c79e1fa7bfe2edb64f2aff` (Initial clean commit; nav pašreizējais VPS release) |
| Iepriekšējais LIVE fix branch | `fix/live-final-review-budget-20261009`, `2a5f6887bc3d8b39975653952b79c30144fbaae3` |
| LIVE rezervācijas implementācija | `a4cdfa1043ec69c2838794371ba0a57d4163f50d` |
| Darba branch | `research/calibration-live-recovery-20261010` |
| Atjaunotā worktree sākums | `9c06eaa`; iepriekš nepabeigtās izmaiņas saglabātas un pārskatītas |
| LIVE installed release | `/opt/goalvision-live-quota-reader-3d4f5c5-20261010` |
| PREMATCH/observer/settlement release | `/opt/goalvision-prematch-quota-reader-3d4f5c5-20261010` |
| Galvenā darba kopija | `/home/arvis/GoalVisionAI`, branch `codex/lab-v2-global-overhaul-2026-09-17`, HEAD `fadd59d`; 220 iepriekšēji status ieraksti saglabāti |

Installed release identitāte pārbaudīta caur reālajiem systemd EnvironmentFile/PYTHONPATH un failu SHA256, nevis secināta no repo HEAD. LIVE worker, runner, service, engine, policy, selection un daypart atbilst pārskatītajam avotam. PREMATCH release apzināti ir atsevišķs; tā atšķirīgais worker nav pamats visu release aizstāt ar LIVE branch.

Audit DB kopijas SHA256:
`fddd4f57faf2d890bf1afcf8e08d388570baeffd783a1d0b5675731cbcbc98f2`.

Ledger kopijas SHA256:
`7e166a3a7edf1c65769d8d53e9bed61322a1d1ad070d81a5f8df4dbaa193301c`.

## 2. LIVE_FINAL_REVIEW_ROOT_CAUSE

**PASS — sakne apstiprināta; atsevišķs DB risks paliek.**

Sākotnējais discovery varēja iztērēt cikla pieprasījumu allowance pirms obligātās gala pārbaudes. Esošais labojums rezervē 9 HTTP mēģinājumus: fixture state, events, exact live odds; katram līdz 3 mēģinājumiem.

Ja kopējais cikla limits ir B, discovery attempt ceiling ir max(0, B−9). Request authorizer darbojas pirms katra reālā HTTP mēģinājuma, ieskaitot retry. Status un settlement jau iztērētie mēģinājumi paliek kopējā skaitītājā; tie nerada papildu limitu. Scan pagaidu ceiling tiek noņemts finally; gala pārbaude atkārtoti izmanto jau iegūto history/catalog.

Rezervācija garantē lokālu vietu līdz deviņiem mēģinājumiem, ja pietiek kopējā atlikuma. Tā negarantē globālo dienas/minūtes kvotu, pieejamu provider atbildi vai derīgu quote. Quota exhaustion, trūkstoši dati un HTTP failures joprojām droši bloķē publikāciju.

Pēdējās 24h: 6 final-refresh failures — **5 QUOTA_DB_CONTENTION_EXHAUSTED un 1 LIVE_SHARED_OR_PROVIDER_QUOTA_BLOCKED**. Atsevišķi 19 gala quote trūkumi. Tos nedrīkst uzdot par 6 Telegram delivery failures vai par pierādījumu, ka rezervācijas matemātika joprojām kļūdaina.

## 3. LIVE_FIX_READINESS

**PASS_READY_FOR_OPERATOR / NO_CHANGE.**

Pieņēmums “labojums joprojām nav izvietots” vairs neatbilst serverim. Esošais successor release to satur; atkārtota instalācija nav vajadzīga. Vecā release instalēšana virs jaunā būtu nepareiza.

Fake-provider end-to-end tests:
- discovery retry nevar patērēt rezervēto daļu;
- katrs no 3 gala endpointiem var izmantot visus 3 mēģinājumus;
- veiksmīgais replay izmanto tieši 9 gala mēģinājumus;
- pilna HTTP kļūme, tukšs gala fixture un kvotas izsīkums nerada claim/publication/send;
- visi gadījumi paliek sākotnējā 35 mēģinājumu testa limitā;
- 0.60/0.70 robežas, tirgi, modeļa aprēķini un publication safeguards nemainīti.

Papildu instrukcija: `docs/operations/LIVE_FINAL_REVIEW_BUDGET_REVIEW_20261010.md`.
Nevajag manuālu worker vai “test send”.

## 4. PREMATCH_CALIBRATION_READINESS

**PASS — sākotnējais izolētais FIT; BLOCKED_NEEDS_MORE_EVIDENCE — neatkarīga kvalitāte.**

Champion:
`generation-aa7e535b86267741aabc967e8044de2ab94a4334b1520a829414dd55ebc7371a`.

Model artifact:
`bootstrap-artifact-694ab4cc98179ddb0bb2e62d9d77a01c0fee5f3e6d3eff28f9e240e34f929f8d`.

Internal artifact fingerprint:
`85ad28129ec1581a9ce3d6f72cc1551fe5cf4df401b1dc1fd0965999d4892a49`.

Feature schema: `LAB_FROZEN_FEATURES_V1`; model family: `EXISTING_PREMATCH_BASELINE_V1`.

| Partition | Novērojumi | Neatkarīgas spēles |
|---|---:|---:|
| TRAIN | 1804 | 560 |
| CALIBRATION_FIT | 346 | 346 |
| VALIDATION | 0 | 0 |
| SEALED_HOLDOUT | 0 | 0 |
| PURGED | 782 | 320 |
| EXCLUDED | 22 | 20 |

FIT minimums 300 ir izpildīts; visi seši partition fixture šķēlumi ir 0.
Frozen UTC robežas: TRAIN 09-18–10-02; FIT 10-03–10-10; VALIDATION 10-11–10-18; HOLDOUT 10-19–10-26. Tās ir pusatvērtu intervālu robežas, nevis ieskaitīti abi gala datumi. UTC pusnakts oktobrī atbilst 03:00 Riga.

Plan fingerprint:
`9b154abc5b1ca4f18187150c2ca0a8d4d37b93b9c3893e97b2e61457329ca439`.

Vēlāki validation/holdout dokumenti izslēgti pirms fit deserializācijas. 346 raw probabilities precīzi reproducējas ar Decimal no frozen model context. SEALED_HOLDOUT rezultāti nav atvērti.

## 5. CALIBRATION_RESEARCH_RESULTS

**PASS — reproducējams research artifact; NO_CHANGE — activation.**

Visas zemākās metrics ir **CALIBRATION_FIT in-sample**. Tās nepierāda forward uzlabojumu.

| Metode | Brier | Log loss | ECE | MCE | Bias p−y |
|---|---:|---:|---:|---:|---:|
| Identity/raw | 0.230160 | 0.654071 | 0.024123 | 0.421179 | −0.008563 |
| Platt | 0.229341 | 0.651289 | 0.010801 | 0.169861 | −0.000001 |
| Temperature | 0.230215 | 0.653973 | 0.023134 | 0.488650 | −0.014661 |
| Isotonic | NOT_FITTED | — | — | — | — |

Platt fit Brier uzlabojums ir tikai 0.000819. Metodes uzvarētājs nav izvēlēts. Isotonic neizpilda 1000 neatkarīgu piemēru minimumu, un nav neatkarīgas novērtēšanas.

Raw reliability: n=99 pie mean p=0.575782 / observed=0.585859; n=199 pie 0.634889/0.658291; n=43 pie 0.734558/0.720930; n=5 pie 0.821179/0.400000. Pēdējais bins ir ļoti nenoteikts.

Market families: TOTAL 234, BTTS 102, 1X2 tikai 10 (HOME 8, AWAY 2, DRAW 0).
Globālais binary fit nav validēta, summā uz 1 normalizēta 1X2 transformācija.
Slope/intercept, visu metožu bins, extremes un per-market metrics ir atsevišķajā pārskatā un calibration.json.

Frozen experiment dataset:
`c3d15632ee63c6354703d893ce98246962148f19d7b8d6762779cb4be165d534`.

Byte-identical artifact:
`db7397acf8cf924cb544bf502ad8663ec7658a15e3b5ca3f9257c198bed40aaf`.

`production_eligible=false`, `activation_allowed=false`, `promotion_allowed=false`, `method_selection=null`. Nav registry/pointer/worker integrācijas. Jauns fit pēc VALIDATION sākuma tiek noraidīts. Precīzā reproducēšanas komanda:
`docs/operations/PREMATCH_CALIBRATION_RESEARCH_20261010.md`.

## 6. LIVE_MODEL_COMPARISON

**SMALL_GITHUB_FIX; BLOCKED_NEEDS_MORE_EVIDENCE.**

Izmantotas esošās research komponentes. Jauna LIVE sistēma nav būvēta.
A: LIVE_POISSON_BASELINE_V1. B: LIVE_CONTEXT_AWARE_POISSON_V2, pašreiz tikai zero-card venue/competition ablation.

2934 retained kandidatūras versijas / 139 spēles. B spēj izdot 173 versiju prognozes; daudzi atkārtojumi nav neatkarīgi piemēri.
Galvenie pārklājošies blockers: history insufficient 2761, own-goal semantics 157, red cards 152, goal-event/score mismatch 100, minute unsupported 25.

V2 izmanto faktiskos home/away vēsturiskos rates tajā pašā competition, spēles rezultātu un atlikušo laiku; minimums 5 atbilstoši noslēgti vēstures mači katrai pusei. Neuzticams vai neesošs konteksts netiek aizstāts ar izdomātiem svariem. Red-card intensity efekts nav novērtēts — RED_CARD_EFFECT_NOT_ESTIMATED. Live xG efekts nav ieviests bez pārbaudāmiem as-of datiem un koeficientiem.

Sasaistes labojums research auditā pievieno jau verificētus LIVE terminal score facts tikai pēc prognožu un nomināciju fiksēšanas. SENT receipt, identitātes, odds, chronology, outcome un provenance tiek pārbaudīti; konfliktējoši rezultāti izslēgti. PREMATCH learning source nav mainīts.

Stingri vienādi pirmie retained fixture/market snapshots: **7 market rindas, 1 neatkarīga spēle**.

| Modelis | Brier | Log loss | ECE |
|---|---:|---:|---:|
| Baseline A | 0.238913 | 0.667160 | 0.109406 |
| Context B | 0.231174 | 0.651001 | 0.164923 |

Δ Brier B−A = −0.007738; Δ log loss = −0.016160; ECE pasliktinās.
Mean absolute model disagreement = 0.061352. Uz vienādiem frozen quotes mean indicative EV: A −0.069496, B −0.075224. Tās ir savstarpēji saistītu tirgu diagnostikas, nevis 7 neatkarīgas likmes vai izpildīta peļņa. CI un modeļa izvēle nav pamatota.

Actual cohorts:
| Cohort | Published/settled | W/L/VOID | Pending | P/L | ROI |
|---|---:|---:|---:|---:|---:|
| Legacy EV-first | 9/9 | 1/8/0 | 0 | −7.556u | −83.96% |
| LIVE_P60_70_20261009_V1 | 16/16 | 8/6/2 | 0 | −1.621u | −10.13% |

Jaunajam cohortam 14 binary outcomes: Brier 0.258970, log loss 0.713713, ECE 0.091404; mean p=0.662833 pret observed 0.571429. ROI denominator ietver 16 settled tickets, ieskaitot 2 VOID. Cohorti nav apvienoti stratēģijas vērtējumā.

No 10-07 līdz cutoff: 1076 dabiskie cikli; 833 idle, 32 results-only, 207 scan-complete, 4 quota-bounded. 48 cumulative final-refresh failures un 33 quote-missing nav jaunu publikāciju skaits. 25 claims/publications/settlements/result receipts; task iniciētu nosūtījumu 0.

## 7. COMBO_PERFORMANCE

**PASS — autoritatīva uzskaite; BLOCKED_NEEDS_MORE_EVIDENCE — kvalitātes ranking.**

| Cohort | Pub./settled | W/L/VOID | Pending | Flat P/L | ROI |
|---|---:|---:|---:|---:|---:|
| Double 20261006 V1 | 1/1 | 0/1/0 | 0 | −1.000000u | −100.00% |
| V2 Singles-Based, leg min 1.30 | 53/51 | 21/30/0 | 2 | +4.983138u | +9.77% |
| DC Agreement | 20/20 | 5/15/0 | 0 | −3.992140u | −19.96% |
| Market 20261004 | 39/39 | 10/29/0 | 0 | −10.524984u | −26.99% |
| V1 Singles-Based | 68/66 | 32/34/0 | 2 | −6.243887u | −9.46% |
| Legacy | 19/19 | 1/18/0 | 0 | −5.572924u | −29.33% |
| Kopā | 200/196 | 69/127/0 | 4 | −22.350797u | −11.40% |

Coupon calibration, n=196: Brier 0.210880; log loss 0.606277; ECE 0.050395. Mean naive joint p=0.332671, observed=0.352041. Šis apvienotais rādītājs nav neatkarības pierādījums un neaizstāj cohort metrics.

V2 n=51: mean p=0.317975, observed=0.411765, Brier 0.256337, ECE 0.115654. DC n=20: mean p=0.262406, observed=0.25. Double n=1: p=0.559536, outcome LOST. Viena kupona rezultāts nevar noteikt stratēģijas kvalitāti.

Neviena cohort CI gate nav izpildīta: vajadzīgi vismaz 30 kuponi un 7 neatkarīgi date clusters, ar nobriedušu izlasi. V2 ir 2 clusters, DC 5, Market 3, V1 3, Double 1; Legacy ir 10 clusters, bet tikai 19 kuponi. CI nav izdomāti.

## 8. COMBO_QUALITY_RESEARCH

**NO_CHANGE — production; BLOCKED_NEEDS_MORE_EVIDENCE — INSUFFICIENT_EVIDENCE.**

Esošais shadow comparator C_QUALITY_VALUE_FIRST atkārtoti izmantots.
Vienāds candidate pool visām metodēm, katrai atsevišķa hipotētiskā exposure vēsture.
12 pēdējo ciklu kandidātsarakstā: 10 reproducējami pabeigti cikli, viens ar trūkstošu preparation time, viens vēlāk pabeigts un izslēgts. Kopā 10502 kandidatūru rindas.

| Shadow comparator | Atlasīti | No-pick cikli | Zināmais rezultāts |
|---|---:|---:|---|
| A current Double | 0 | 10 | INSUFFICIENT_EVIDENCE |
| B Singles-Based V2 | 25 | 1 | 2 LOST, 23 pending; tikai hipotētiski |
| C quality/value-first Double | 0 | 10 | INSUFFICIENT_EVIDENCE |

C apzināti neizvēlas kuponu bez verified frozen leg calibration un joint independence evidence.
B nav pārāks tāpēc, ka izvēlas vairāk; atšķirīgu kuponu Brier nav paired strategy delta.

Visiem 200 kuponiem ir shared-signal-group riska pazīme; 194 shared market family, 83 shared league. Konstatēto shared fixture/team riska karogu nav, taču tas nepierāda statistisku neatkarību. Losing-leg sadalījums 127 zaudētiem kuponiem: 70 ar vienu, 44 ar diviem, 13 ar trim zināmiem zaudētiem legs.

Naive joint p ir probabilities reizinājums tikai ar neatkarības pieņēmumu. Diviem legs bez šī pieņēmuma p(joint) robežas ir max(0,p1+p2−1) līdz min(p1,p2). Calibrated joint p un uzticams joint EV nav identificēti; nav radīts nepamatots correlation koeficients vai joint calibrator. Esošo contemporaneous quotes kvalitāte pārbaudīta ar frozen provenance. Historical bookmaker odds datu kopas nav izmantotas.

## 9. DIXON_COLES_FORWARD

**BLOCKED_NEEDS_MORE_EVIDENCE — NEEDS_MORE_EVIDENCE.**

481 forecast-family ieraksts; 39 resolved fixtures, 7 kickoff dates; 115 pending fixtures. Jauns capture vai fit nav palaists.

Full-market pair pret ensemble: 308 binary market rows, DC Brier **0.246235**, ensemble **0.221793**. Visu esošo benchmarku kopīgajā 293-rindu intersection DC Brier 0.246990, ensemble 0.223880. Šīs ir binary market scores ar atkārtotiem tirgiem vienā spēlē.

Stingrs sešu metožu 1X2 intersection: **32 fixtures, 6 kickoff dates**, viens outcome vector katrai spēlei.

| Metode | Multiclass Brier | RPS | Log loss | ECE | Δ Brier pret champion |
|---|---:|---:|---:|---:|---:|
| Champion | 0.544714 | 0.176123 | 0.917113 | 0.087624 | 0 |
| Dixon–Coles | 0.573676 | 0.183787 | 0.967817 | 0.098324 | +0.028962 |
| Multiplicative market | 0.582040 | 0.190674 | 0.968216 | 0.074586 | +0.037326 |
| Shin | 0.580631 | 0.189852 | 0.964139 | 0.085483 | +0.035917 |
| Power | 0.580734 | 0.189611 | 0.963507 | 0.089814 | +0.036020 |
| OO-EPC | 0.580059 | 0.189451 | 0.961510 | 0.094641 | +0.035345 |

Multiclass Brier ir trīs squared errors summa, nevis viena binary tirgus score; 0.54 un 0.24 nedrīkst tieši salīdzināt.
Paired dataset fingerprint:
`77d79659c6bb5353add62d625556160c39ab9daa66b85fc1ce99cbbf7c44bf52`.

CI minimums 30 fixtures / 7 dates nav izpildīts, jo stingrajā izlasē ir tikai 6 dates.
Date-cluster CI=null. Frozen DC weight nav validēts uz unseen validation.
Incremental-information evidence nav pietiekams ne champion promotion, ne publication izmaiņām.

## 10. MODEL_DISAGREEMENT

**PASS — diagnostika; NO_CHANGE — thresholds.**

12 saglabāto operacionālo ciklu izlasē: 12738 kandidatūru rindas / 930 unikālas spēles.
Mean absolute ensemble-market divergence 0.035690; material signal disagreement 2888 (22.67%); severe contradiction 159 (1.25%); excessive ensemble-market divergence 113 (0.89%).
11409 rindām ir insufficient independent signals. Šie atkārtojumi nav neatkarīgu likmju denominators.

LIVE market diagnostics: 2866 AVAILABLE, 31 complete as-of market unavailable, 37 inactive.
State/event/quote consistency un score/minute mismatches tiek vērtēti pirms pēcaprēķina labels pievienošanas. Missing context neļauj apgalvot modeļa pārliecību.

Pārbaudītie primārie metodoloģiskie avoti un aktuālie projektu avoti:
- Guo et al., calibration/temperature scaling: https://proceedings.mlr.press/v70/guo17a.html — metode jāpārbauda uz mūsu datiem; neural-network rezultāti nav futbola pierādījums.
- Maia et al., match-state/Cox goal intensity: https://arxiv.org/abs/2312.04338 — score/red-card effects ir jānovērtē, nepārnesot fiksētu procentu.
- Dixon–Coles: https://rss.onlinelibrary.wiley.com/doi/10.1111/1467-9876.00065 — low-score dependence nav automātisks incremental value.
- Gneiting & Raftery, proper scoring: https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jasa.pdf — Brier/log loss uz vienādiem forecast targets.
- scikit-learn calibration: https://scikit-learn.org/stable/modules/calibration.html — nodalīti fit/evaluation dati un isotonic mazās izlases risks.
- penaltyblog: https://github.com/martineastwood/penaltyblog un https://penaltyblog.readthedocs.io/en/latest/implied/implied.html — pārbaudāmi Poisson/DC un margin-removal benchmarki.
- Shin reference implementation: https://github.com/mberk/shin — tirgus benchmarka aprēķins, ne pierādījums peļņai.

Jaunas bibliotēkas/modelis nav ieviests tikai modernuma dēļ. COMBO correlation novērtēšana prasa atbilstošu joint-outcome izlasi; kopīgs signāla nosaukums ir riska pazīme, ne estimēts correlation.

## 11. ODDS_DATA_QUALITY

**BLOCKED_NEEDS_MORE_EVIDENCE — nepilnīga provider coverage.**

Pēdējie 12 pirms-cutoff saglabātie operacionālie cikli:
- broad scope 12028 fixture-cycle novērojumi / 2418 unique fixtures;
- 1206 current odds available, 714 stale;
- 6229 pagination-changed, 2706 quota/request-limited, 1038 final-review-reserve-limited;
- 498 recorded exact outcomes: 171 available, 17 stale, 26 unavailable, 284 bez precīzi saglabāta failure detail;
- tracked exact: 72/170 available;
- 375 exact HTTP attempts / 171 zināmas sekmīgas fixture refreshes = 2.193 mēģinājumi uz zināmu sekmi; tas ir ierobežots observational rādītājs;
- 155/188 atkārtotu iepriekš nesekmīgu mēģinājumu atkal nedod svaigu rezultātu.

Missing/stale rates pilnai exact populācijai nav identificētas, jo 284 outcomes ir nepilnīgi izskaidroti. Null nav 0.
Provider zero probabilities: 3 retained kandidatūru rindas, ar invalid-probability trace; tās netiek klusi uzskatītas par ticamu 0% iespēju.
CURRENT_ODDS_UNAVAILABLE nav pierādījums HTTP failure. Quote age vērtēta prognozes laikā, nevis pēc tam pret audita pulksteni.

## 12. QUOTA_AND_RUNTIME

**SMALL_GITHUB_FIX; OPERATOR_APPROVAL_REQUIRED — production rīcībai.**

| Runtime elements | Faktiskais stāvoklis |
|---|---|
| LIVE evening timer | ACTIVE / ENABLED |
| Watch vēlamais LIVE | DISABLED |
| Installed observer LIVE lauks | Hardcoded DISABLED, nav autoritatīvs systemd stāvoklis |
| Installed health | Vecā timer nosaukuma pārbaude |
| PREMATCH discover | ACTIVE / ENABLED |
| COMBO settlement | ACTIVE / ENABLED |
| Learning observer / daily learning | ACTIVE / ENABLED |
| DC forward | ACTIVE / ENABLED |

Esošais source commit `03ea4b9` labo health uz faktisko evening timer, atdala Riga discovery window un PREMATCH observer scope. Tas neieslēdz/neizslēdz LIVE. Labojums nav uzstādīts; nav implementēts vēlreiz.

24h logu pārbaude: PREMATCH 8 atsevišķi quota-contention/traceback gadījumi, nevis 16 incidenti (vienas kļūmes atkārtotas teksta rindas). Pieci ir pēc iepriekšējās reader fix instalācijas; četri šodien 08:38, 09:38, 10:08, 10:38 UTC. LIVE 6 atsevišķi quota-affected invocations. Pieci gala review failures ir DB contention.

Calendar audit turēja explicit SQLite read transaction JSON decode/hash laikā. Tas izolēti reproducē writer COMMIT bloķēšanu arī pēc repository cursor fix. Jaunais labojums vispirms materializē vienu koherentu encoded snapshot, aizver connection, pēc tam decode/hash; integrity pārbaude saglabāta. Kļūmju sakritība ar observer :08/:38 atbalsta cēloņa hipotēzi, bet runtime lock īpašnieks nav tieši izmērīts. Neapgalvojam, ka visas production kļūmes jau novērstas.

UTC dienā līdz cutoff: 1905 quota claims — STATUS 9, PREMATCH_DISCOVERY 814, PREMATCH_REVIEW 963, SETTLEMENT 119.
Pēdējais claim 11:05:14 UTC: remaining_daily_before=5596, minute=284, protected_reserve=3438. Tās ir saglabātās kvotas vērtības; jauns /status nav pieprasīts. Quota observation tabula ir tukša; to neaizstāj izdomāts provider mērījums.
Audit DB kopijas quick_check=ok.

Delivery/settlement:
- public un private claims_without_receipt=0; LIVE 25 result receipts uz 25 settlements;
- public ledger saglabāts viens vēsturisks delivery_unknown marker, lai gan claim vairs nav bez receipt;
- current policy/COMBO dublētu confirmed kuponu pazīmju nav; 10 vēsturiski SINGLE fixture atkārtojumi ir vecos cohorts, atšķirīgos markets, ne 10 pierādīti duplicate Telegram sends;
- public pending=16 SINGLE + 4 COMBO; 4 SINGLE un 4 COMBO kickoff vecums >6h;
- saglabātajos diagnostics ir postponed/unsupported status (arī AWD), tāpēc kickoff vecums nav mērīts kavējums kopš reāla FT pieejamības;
- LIVE pending=0 šī snapshot ietvaros. Nekas nav piespiedu kārtā settled vai pārrakstīts.

## 13. CHAMPION_AND_PROMOTION_STATUS

**NO_CHANGE; BLOCKED_NEEDS_MORE_EVIDENCE — promotion.**

Learning stage CHALLENGER_RESEARCH. 2941 eligible resolved observations / 1235 independent fixtures; 2954 retained observations.
SHADOW 2373, SINGLE 569, legacy COMBO_LEG 12. COMBO_LEG immutable vēsture saglabāta, bet learning_source tos izslēdz. Šis darbs nerada COMBO learning observations.

59 model artifacts: 1 bootstrap, 26 logistic, 16 regularized, 8 stump, 8 calibrated ensemble.
133 training runs: 74 rejected, 1 bootstrap, 58 trained.
Production calibration artifacts=0; validation results=0; shadow comparisons=0; promotion gates=0; rollback events=0. Vienīgā activation ir sākotnējais bootstrap; šī darba activation=0.
Champion ID ir precīzi tas pats, kas 4. sadaļā.

PREMATCH SINGLE autoritatīvais read-only snapshot:
| Metrika | Vērtība |
|---|---:|
| Published / settled / pending | 588 / 572 / 16 |
| W/L/VOID | 328 / 243 / 1 |
| Flat P/L / ROI | −35.07u / −6.13% |
| Binary probability sample | 568; 3 binary outcomes bez probability |
| Brier / ECE / log loss | 0.226787 / 0.039682 / 0.645452 |

Pašreizējais SINGLE V4 1.50 cohorts atsevišķi: 339 published, 324 settled, 202 W / 121 L / 1 VOID, 15 pending; −4.43u, −1.37% ROI. Agrāki cohorts nav uzdoti par pašreizējās politikas rezultātu.

VALIDATION un SEALED_HOLDOUT pierādījumi vēl nepieciešami. Nav champion promotion vai rollback ieteikuma.

## 14. IMPLEMENTED_FIXES

**SMALL_GITHUB_FIX — source/research only.**

1. Task A: papildināti LIVE fake-provider end-to-end regressions; esošā rezervācijas implementācija saglabāta.
2. Task B: pabeigts detached calendar fit adapter, izmantojot esošo Platt/temperature foundation; pilns provenance, chronology, raw replay un inert artifact. Pabeigts calendar reader lock lifetime fix.
3. Task C: tikai research audit result join uz verified LIVE settlements; modeļa/ranking produkcijas kods nemainīts.
4. Health: izmantots jau esošais `03ea4b9` labojums; jauns dublikāts nav radīts.
5. Pabeigti iepriekšējie evidence assembly/DC read-only scripts un gala pārskati.

Work izmantots arhitektūras, avotu un rezultātu izvērtēšanai. Codex izmantots konkrētas Task C patch sagatavošanai; patch pārskatīts un pielāgots reālajai receipt shēmai. Codex tool-enabled runner konteinerī bija bwrap loopback ierobežojums; sandbox netika apiets. Lasīšana un testēšana veikta ar autorizēto Remote Desktop Commander un izolētām kopijām.

Galvenie mainītie faili:
- `app/adaptive_lab/calendar_audit.py`, `calendar_calibration_fit.py`;
- `operations/calibration-live-recovery/{calibrate,offline_tests,dixon_coles,assemble}.py`;
- `operations/live-combo-hardening/audit.py`;
- `tests/adaptive_lab/test_live_final_review_budget.py`, `test_calendar_audit.py`, `test_calendar_calibration_fit.py`, `test_live_research_result_sources.py`;
- šie operations pārskati, TASKS/ROADMAP continuation ieraksti un divas evidence direktorijas.

Nav production model, Official, bankroll, staking, publication threshold vai calendar boundary izmaiņu.

## 15. TEST_RESULTS

**PASS — visas gala focused/adjacent pārbaudes; production incidenti paliek atsevišķi.**

| Pārbaude | Rezultāts |
|---|---|
| Resumed LIVE/calendar/calibration/health focused | 64 passed, 0 failed |
| 36-file adjacent matrix | 841 passed, 0 failed |
| LIVE result-source + adjacent + Official regressions | 180 passed, 46 subtests passed, 0 failed |
| October 10 saglabātais plašais run | 1088 passed, 5 subtests passed; nav uzdots par šodienas run |
| Reālais izolētais calibration replay | Byte-identical artifact PASS |
| Fake-provider final-review end-to-end | 9 retry attempts success; HTTP/partial/quota safe no-send PASS |
| LIVE research real-data replay | 7 paired market rows / 1 fixture, NEEDS_MORE_EVIDENCE |
| Calendar lock regression | Vecais kods reproducē sqlite locked; labotais ļauj writer COMMIT |
| Trīs diagnostikas failu overlay pret abiem actual releases | Izolēts import smoke PASS; mainās tikai 3 faili |
| Protected source/systemd check | 150 systemd faili nemainīti; pārbaudītie installed source nemainīti |
| Git diff whitespace | PASS |

Testu kopas pārklājas; skaitļus nesummēt par unikālu testu skaitu.
Aptverts quota exhaustion/reserve/HTTP, probability boundaries, missing context/red cards, chronology/leakage, VOID/partial VOID, duplicate delivery, no selection, COMBO independence, Official un no-real-transport.
Testi izmanto fake transport un outbound socket deny. Pirmais research adapter drafts neatpazina faktiskās receipt timestamp lauku; tāpēc papildināta actual-schema regresija. Šī problēma gala replay ir novērsta.

## 16. GITHUB_COMMITS

**PASS — reviewed code commits pushed; NO_CHANGE — default branch un deployment.**

Branch: https://github.com/ProjectX-oss/GoalVisionAI-v2/tree/research/calibration-live-recovery-20261010

| Commit | Saturs |
|---|---|
| `fd6271c` | LIVE rezervācijas atkārtots audits un failure replay |
| `07775d7` | Detached calibration fit, calendar reader lock fix, reproducējamais artifact |
| `b7bdf8f` | Verified LIVE result-source join un actual-schema regressions |

Šie trīs code commits ir pushoti; gala report/evidence commit atrodams šī branch tip.
Pilns failu saraksts reproducējams ar:
`git diff --name-status 9c06eaa..research/calibration-live-recovery-20261010`.

Galīgais push/head un clean worktree receipt tiek pārbaudīts pie nodošanas. Galvenā darba kopija saglabā savus 220 iepriekšējos status ierakstus. Nav merge uz clean; šajā branch nav GitHub Actions workflow, kas push dēļ veiktu deployment.

## 17. OPERATOR_ACTIONS

**OPERATOR_APPROVAL_REQUIRED — tikai atsevišķi autorizētām production darbībām.**

Detalizētais, atsevišķais plāns:
`docs/operations/GOALVISION_OPERATOR_ACTIONS_20261011.md`.

1. LIVE rezervāciju pārinstalēt nevajag: tā jau ir successor release.
2. Ja šī Watch vēlamais DISABLED joprojām spēkā, operatoram atsevišķi jāpārbauda aktuālie pending/result receipts un jādeaktivizē tieši evening timer. Šajā darbā tas nav darīts. Iepriekšējā 10-07 evening-enabled autorizācija neatsver pašreizējo instrukciju; vienlaikus pašreizējā instrukcija aizliedz mums timeri automātiski mainīt.
3. LIVE timeris ārpus discovery loga nodrošina arī settlement. To nevar akli izslēgt, nepārbaudot vēl nenoslēgtus rezultātus. At cutoff visi 25 ir settled un tiem ir result receipts; operatoram šis fakts jāpārbauda no jauna tieši pirms darbības.
4. Calendar lock un esošais health fix ir gatavi source review un isolated overlay import smoke, bet nav uzstādīti. Iespējamam immutable successor atļautais scope ir tikai calendar_audit.py, health.py, observer.py uz katra attiecīgā current release. Production update vajag atsevišķu autorizāciju, route/hash preflight un dabisku nākamo ciklu novērošanu; nekādu manuālu provider/Telegram smoke.
5. Kalibrācijas artifact paliek frozen. VALIDATION dati tiek gaidīti esošajā logā, SEALED_HOLDOUT netiek atvērts pirms atļautā brīža un gate izpildes. Kalendāru nepārvietot.
6. LIVE V2 un COMBO quality comparator paliek research/shadow. Red-card intensity un joint correlation fit atlikts līdz piemērotai neatkarīgai as-of izlasei.
7. Settlement pending ar postponed/AWD pazīmēm pārskatāmi pēc esošās operatora kārtības; neradīt mākslīgu VOID vai pārrakstīt settlement.

**Šī darba darbību receipt:** production deployment=NONE; Telegram sends=0; neatļauti provider calls=0; task-initiated provider calls=0; Official changes=NONE; model activation=NONE; timer mutations=0; automatic promotion/rollback=NONE. Sistēmas iepriekš aktīvie dabiskie timeri turpināja darboties neatkarīgi; “0” attiecas uz šī darba iniciētajām darbībām.
