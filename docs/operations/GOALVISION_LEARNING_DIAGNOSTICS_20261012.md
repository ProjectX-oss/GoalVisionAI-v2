# GOALVISION — LEARNING DIAGNOSTICS — 2026-10-12

Datu cutoff: **2026-10-12 06:25:49.653250 UTC / 09:25:49 Europe/Riga**.
Runtime pārbaudīts atkārtoti pēc cutoff; jaunās dabiskās publikācijas nav sajauktas ar iesaldētā snapshot metriku.
Uzdevums: PREMATCH, learning, kalibrācija, LIVE, COMBO, DC un runtime diagnostika bez production deployment.

**Secinājums:** mācību dati un trīs izolēti apmācītie kandidāti pastāv, taču neatkarīgs uzlabojums vēl nav pierādīts. COMBO klusums ir reāls un pārbaudītajos ciklos saistīts ar atlases atteikumiem; nav nepabeigtu publicēšanas claims bez receipt. Atrasts un GitHub avotā labots atsevišķs DC research veiktspējas defekts. Operatora instalācija sagatavota, nav izpildīta.

## 1. CURRENT_GITHUB_AND_VPS_STATE

**PASS / NO_CHANGE**

- Jaunais izolētais branch: `research/learning-diagnostics-20261012`.
- Bāze: `4e464ade02ae7feca1cc282f45e338ada2218e04`.
- Galvenais checkout: `/home/arvis/GoalVisionAI`, `codex/lab-v2-global-overhaul-2026-09-17`, HEAD `fadd59d`; iepriekšējie aptuveni 220 status ieraksti nav laboti vai tīrīti.
- Operators pats jau uzstādījis `observer-quota-recovery-20261012.py`; tā nav šīs diagnostikas agent deployment.
- Aktuālie releases: `/opt/goalvision-prematch-quota-batch-20261012`, `/opt/goalvision-live-quota-batch-20261012`, ADMIN `/opt/goalvision-admin-alerts-releases/admin-observer-contract-20261012`.
- DC forward pašlaik: `/opt/goalvision-dixon-coles-forward-ebd0924-20261004`.
- Jaunā pakotne nav uzstādīta; preflight `DC_FORWARD_REPAIR_PLAN_VALIDATED; mode=BASE`.
- Iepriekšējie GitHub remotes pārbaudīti: observer package `352a702864cde513c46c1e624077b5dc3c19adb0`, ADMIN `772b7a310dbdaf6cae86792108c4d6b42930e1af`, quota reader `ba96299dfa68524d330df7babb3bd4cf96c4e903`.

Privātās read-only kopijas: `/home/arvis/goalvision-research/learning-diagnostics-20261012/`.

| Kopija | SHA256 |
|---|---|
| audit.db | 3e0191045ba964ab8e91cdb347f9905b70271f28ebae8edee11131e93e2fb91d |
| ledger.db | 19dc8c68ce463f79284f7d1b93dc3ba8d3c263ff2762648cea55385be3e747d0 |
| dc_forward.db | e22e6adbc211b4bf452f9725a8e3c6d66eac8d05194a4d5d7ef3ba458cc54b4c |

22.85 GB shadow DB pilna kopēšana sasniedza noteikto 60 s budžetu. Tā netika atkārtota. Izmantots ierobežots immutable rindu izvilkums `shadow-window-r2.db`: 11 294 kandidāti, 12 cycle phases, 40 publication cycles, 130 tracked odds ieraksti; saglabāti source rowids un fingerprints. Tas nav pilnas vēstures snapshot.

## 2. LIVE_FINAL_REVIEW_ROOT_CAUSE

**PASS / NO_CHANGE**

Esošais `fix/live-final-review-budget-20261009` labojums `2a5f6887bc3d8b39975653952b79c30144fbaae3` jau ietilpst installed successor. Atkārtota vecās versijas uzstādīšana nav vajadzīga.

Discovery ceiling ir max(0, B−9); 9 rezervētie HTTP mēģinājumi = fixture state, events, exact LIVE odds, katram līdz trim attempts. Authorizer pārbauda katru retry; jau patērētie status/settlement attempts paliek kopējā B skaitītājā. Pagaidu scan ceiling tiek noņemts finally; gala pārbaude atkārtoti izmanto iegūto history/catalog.

Rezerve garantē lokālu budžeta vietu, ja atlikums ir pietiekams. Tā negarantē provider datus, globālo kvotu vai HTTP panākumus. Kļūmju gadījumā publikācija paliek bloķēta.

## 3. LIVE_FIX_READINESS

**PASS_READY_FOR_OPERATOR / NO_CHANGE — jau uzstādīts**

Šodien 84 focused/adjacent testi izturēti, ietverot fake-provider end-to-end, quota exhaustion, reserve, HTTP failure, partial data un result-source regresijas. Reāli sockets bloķēti.

Installed LIVE runner, service, engine, policy, selection un daypart SHA256 sakrīt ar pārbaudīto avotu. Modeļa formulas, 60–70% policy, kopējais limits un publication safeguards netika mainīti.

## 4. PREMATCH_CALIBRATION_READINESS

**PASS — iesaldētā eksperimenta integritāte; BLOCKED_NEEDS_MORE_EVIDENCE — jauna kvalitātes atziņa**

Champion:
`generation-aa7e535b86267741aabc967e8044de2ab94a4334b1520a829414dd55ebc7371a`.

Artifact ID:
`bootstrap-artifact-694ab4cc98179ddb0bb2e62d9d77a01c0fee5f3e6d3eff28f9e240e34f929f8d`.

Artifact fingerprint:
`85ad28129ec1581a9ce3d6f72cc1551fe5cf4df401b1dc1fd0965999d4892a49`.

Feature schema: `LAB_FROZEN_FEATURES_V1`.
Calendar fingerprint: `9b154abc5b1ca4f18187150c2ca0a8d4d37b93b9c3893e97b2e61457329ca439`.

Esošie pusatvērtie UTC logi: TRAIN 09-18 līdz 10-02; FIT 10-03 līdz 10-10; VALIDATION 10-11 līdz 10-18; HOLDOUT 10-19 līdz 10-26. Robeža 00:00 UTC = 03:00 Riga. Robežas nav pārvietotas.

| Aktuālā dinamiskā partition | Novērojumi | Neatkarīgas spēles |
|---|---:|---:|
| TRAIN | 1804 | 560 |
| CALIBRATION_FIT | 18 | 18 |
| VALIDATION | 61 | 27 |
| SEALED_HOLDOUT | 0 | 0 |
| PURGED | 2907 | 895 |
| EXCLUDED | 22 | 20 |

**346 pret 18 nav datu zudums.** Sākotnējais FIT bija iesaldēts ar 346 spēlēm. Pēc tam 328 spēlēm pievienojās 810 SHADOW ieraksti ar label availability 2026-10-11 16:15:32.398158 UTC. Pašreizējā konservatīvā kalendāra pārrēķinā 310 spēles izslēgtas ar LABEL_NOT_AVAILABLE_BEFORE_EMBARGO un 18 ar FIXTURE_CROSSES_WINDOW. Vecie novērojumi pazuduši vai mainīti: **0**.

Frozen FIT šķēlums ar pašreizējo TRAIN/VALIDATION/HOLDOUT: **0/0/0**. Frozen dataset fingerprint `c3d15632ee63c6354703d893ce98246962148f19d7b8d6762779cb4be165d534`; current readiness dataset `a78d53b67ccc036fad2a1472c1ccf288df38d1e445786f792f80db42943dd8b2`.

VALIDATION vēl nav sasniegusi 30 neatkarīgu spēļu minimumu un logs vēl nav noslēdzies. Slēgto FIT nedrīkst “papildināt” ar jaunām nākotnes spēlēm. HOLDOUT nav atvērts.

## 5. CALIBRATION_RESEARCH_RESULTS

**PASS — reproducējamība; BLOCKED_NEEDS_MORE_EVIDENCE — neatkarīga efektivitāte**

Oriģinālais eksperiments šodien atkārtots tikai uz oriģinālās immutable Oct10 DB kopijas ar oriģinālajiem laikiem. Rezultāts **byte-identical**; tas nav jauns atpakaļdatēts fit uz Oct12 datiem.

Artifact fingerprint: `db7397acf8cf924cb544bf502ad8663ec7658a15e3b5ca3f9257c198bed40aaf`.

| Metode | FIT n | Brier | Log loss | ECE |
|---|---:|---:|---:|---:|
| Identity/raw | 346 | 0.230160 | 0.654071 | 0.024123 |
| Platt | 346 | 0.229341 | 0.651289 | 0.010801 |
| Temperature | 346 | 0.230215 | 0.653973 | 0.023134 |
| Isotonic | — | NOT_FITTED | n < 1000 | nav neatkarīga vērtējuma |

Visi šie skaitļi ir **FIT in-sample**, nevis validation vai profitability pierādījums. Nav izvēlēts uzvarētājs.

Raw reliability: 50–60% n99 / observed58.59%; 60–70% n199 /65.83%; 70–80% n43 /72.09%; 80–90% n5 /40%. Pēdējais bins ir pārāk mazs stabilam secinājumam. Family n: TOTAL234, BTTS102, 1X2 tikai10 (home8, away2, draw0).

Pilnās MCE, bias, slope/intercept, family metrics, bins un extremes ir saglabātas `PREMATCH_CALIBRATION_RESEARCH_20261010.md` un tā evidence JSON. Nekādas raw probability pārrakstīšanas vai production loader/activation nav.

## 6. LIVE_MODEL_COMPARISON

**BLOCKED_NEEDS_MORE_EVIDENCE**

Cohorti netiek apvienoti:

| LIVE cohorts | Settled | W/L/VOID | Flat P/L | ROI |
|---|---:|---|---:|---:|
| Vecais EV-first | 9 | 1/8/0 | −7.556u | −83.9556% |
| Probability 60–70% | 22 | 12/8/2 | −1.573u | −7.15% |

Jaunā cohorta 20 binary observations: Brier0.247124, log loss0.688674, ECE0.063587; mean probability0.663587 pret hit rate0.60. 19 neatkarīgas spēles.

No 3600 kandidatūras versijām context V2 var iegūt 229 forecast versijas. Biežākie blockers (var pārklāties): history3371, red-card effect nav novērtēts198, goal semantics165, event-score mismatch115, remaining time35.

Vienāds A/B sample joprojām tikai **7 market rows no vienas spēles**:
A Brier0.238913 / log loss0.667160 / ECE0.109406;
B Brier0.231174 /0.651001 /0.164923.
Tas nepierāda B pārsvaru. Sarkanajām kartītēm nav izdomāta fiksēta procenta; neuzticams xG nav ieviests. As-of/context pārbaudes saglabātas.

## 7. COMBO_PERFORMANCE

**PASS — authoritative aprēķins; BLOCKED_NEEDS_MORE_EVIDENCE — stratēģijas kvalitāte**

200 publicēti,196 settled,69W/127L/0VOID,4pending; flat P/L **−22.350797u**, ROI **−11.4035%**.

| Cohorts | Published/settled | W/L | P/L u | ROI |
|---|---:|---:|---:|---:|
| COMBO_DOUBLE_20261006_V1 | 1/1 | 0/1 | −1 | −100% |
| V2 Singles-Based, leg min1.30 | 53/51 | 21/30 | +4.983138 | +9.7709% |
| DC Agreement | 20/20 | 5/15 | −3.992140 | −19.9607% |
| Market | 39/39 | 10/29 | −10.524984 | −26.9871% |
| V1 Singles | 68/66 | 32/34 | −6.243887 | −9.4604% |
| Legacy | 19/19 | 1/18 | −5.572924 | −29.3312% |

Pēdējais kupons: **2026-10-09 17:06:16 Riga**, pašreizējais Double. Pārbaudītajos 12 pēdējos slēgtajos ciklos esošais Double replay neizvēlas nevienu pāri. Pēdējo 24h deviņos saglabātajos publication cycles: 27 SINGLE sends ar receipts,0COMBO. Tas ir atlases klusums pārbaudītajā sample, nevis pierādīts Telegram transports bojājums.

## 8. COMBO_QUALITY_RESEARCH

**BLOCKED_NEEDS_MORE_EVIDENCE — INSUFFICIENT_EVIDENCE**

Esošais quality/value-first comparator jau ir realizēts; jauna sistēma nav būvēta. Vienādu 12 ciklu/11 294 kandidātu replay:
A current Double0, B Singles V2 31 hipotētisks kupons (3LOST,28pending), C quality/value-first0. Hipotētiskie kuponi nav publikācijas; nav kopīga noslēgta sample pārākuma pierādījuma.

196 coupon probability diagnostic: Brier0.210880, log loss0.606277, ECE0.050395. Varbūtības ir naive independence pieņēmums, nevis pierādīta joint calibration.

Neviens stratēģijas cohorts neizpilda abus esošos CI minimumus — 30 kuponus un7kickoff dates; V2 tikai2dates, DC5, Double1. Atkārtoti signālu avoti un tirgu ģimenes neapliecina neatkarību. Zaudējošo legu sadalījums:70kuponos1legs,44kuponos2,13kuponos3. Aktīvie thresholds nemainīti; COMBO nav PREMATCH training observations.

## 9. DIXON_COLES_FORWARD

**SMALL_GITHUB_FIX — runtime; BLOCKED_NEEDS_MORE_EVIDENCE — modeļa kvalitāte**

Full-market:54resolvedfixtures/8dates/413binary market rows; DC Brier0.249288 pret ensemble0.226747.

Strict all-six paired1X2: **33fixtures/7dates** (plašāks paired sample43, bet visiem sešiem kopīgs33).

| Modelis | Summed 3-class Brier | RPS | Log loss | ECE |
|---|---:|---:|---:|---:|
| Champion | 0.547485 | 0.174191 | 0.920401 | 0.087524 |
| Dixon–Coles | 0.575808 | 0.181566 | 0.970340 | 0.090161 |
| Multiplicative market | 0.584518 | 0.188278 | 0.971906 | 0.078258 |
| Shin | 0.583154 | 0.187488 | 0.967928 | 0.088746 |
| Power | 0.583266 | 0.187258 | 0.967325 | 0.092923 |
| OO-EPC | 0.582601 | 0.187105 | 0.965358 | 0.097564 |

Full-market binary Brier un summed3-class Brier nav savstarpēji aizstājami.
DC−champion Brier delta+0.028323,95%date-clusterCI[−0.152127,+0.107148].
30fixtures/7dates minimums tagad ir izpildīts tikai **EXPLORATORY_UNADJUSTED** CI; intervāls ietver0. Verdict **NEEDS_MORE_EVIDENCE**, nekādas promotion/publication izmaiņas.

## 10. MODEL_DISAGREEMENT

**PASS — diagnostika; NO_CHANGE — atlase**

11 294 atkārtoti candidate-market-cycle ieraksti/472fixtures: material signal disagreement3422(30.30%), severe model-market contradiction195(1.73%), ensemble divergence too large126(1.12%). Mean absolute model-market divergence0.048886. Šīs nav neatkarīgas likmes un nepierāda cēloni vai pareizo modeli.

## 11. ODDS_DATA_QUALITY

**BLOCKED_NEEDS_MORE_EVIDENCE**

472exact quote observations/253fixtures:211fresh(44.70%),26stale,17missing,218unknown(171notrecorded+47waiting). Unknown nedrīkst pieskaitīt precīzai missing/stale kategorijai.
Tracked refresh:130observations/33fixtures,83available(63.85%),47waiting.

Četri PROVIDER_ZERO_PROBABILITY candidate ieraksti saglabā provider 0% avota trace un tiek noraidīti. Saglabātā diagnostika rāda, no kurienes nāk nulle; modelis šajā darbā nav pārveidots. Nav veikts jauns provider pieprasījums.

## 12. QUOTA_AND_RUNTIME

**PASS — iepriekšējās instalācijas pārbaude; OPERATOR_APPROVAL_REQUIRED — jaunais DC fix; BLOCKED_NEEDS_MORE_EVIDENCE — pilna runtime atkopšanās**

Observer pēc operatora instalācijas 09:08–09:10:54 Riga izpildījās veiksmīgi. Tā `LIVE=NOT_EVALUATED,LIVE_SCOPE=PREMATCH_OBSERVER` nav LIVE systemd OFF apgalvojums. ADMIN jaunais līgums pieņem šo scoped rezultātu, saglabājot īstu fault atpazīšanu.

DC forward pie CPUQuota25%/Timeout50s vienā agrākā 08:42:30–08:43:20 Riga ciklā sasniedza timeout;09:12cikls pabeidzās ap47s. Atkārtotajā09:42ciklā pabeidzās09:43:15. Šaurā rezerve paliek; tāpēc sagatavots aprēķinu dublēšanās labojums.

Kopš Oct11 sākuma pieejamajā application journal:7distinctPREMATCH un31distinctLIVE quota-contention invocations. Pēc instalācijas06:03UTC šie kodi nav redzēti, taču snapshot brīdī jaunais PREMATCH discovery un LIVE daypart vēl nebija sākušies. Tas nav pierādījums pilnai atkopšanai pie slodzes. ADMIN root-private incident DB nav nolasāma; nav apgalvots, ka visi incidenti slēgti.

Pēdējais saglabātais quota claim:SETTLEMENT06:25:40UTC,remaining_daily_before6955,minute287,protected_reserve0. Tas nav jauns provider /status mērījums.

Actual LIVE timer **active/enabled**; vēlamais Watch stāvoklis DISABLED nav izpildīts. PREMATCH timer active/enabled. Nekādi timeri diagnostikā nav mainīti.

Public claims bez receipt0;LIVE31claims/31publications/31settlements. Public ledger satur vienu vēsturisku delivery_unknown marker, bet nav neatrisināta claim bez receipt. COMBO exact duplicates0;10vēsturiski SINGLE fixture atkārtojumi (9legacy,1Oct1policy; dažādi markets), nevis10pierādīti duplicate Telegram deliveries.

4SINGLE+4COMBO ir pending>6h. Saglabātā settlement diagnostika rāda PST,AWD/neatbalstītu statusu un spēles, kas pārceltas uzOct14/Nov4. Kickoff vecums nav nomērīts kavējums kopš provider gala rezultāta. Manuāls settlement vai statistikas labojums nav veikts.

LIVE kumulatīvi48final-refresh failures un47missing-final-quote ieraksti ir atsevišķi no faktiska Telegram delivery failure. Observer aptuveni173s un settlement153s zem esošā10min limita; papildu optimizācija nav uzminēta bez profila.

## 13. CHAMPION_AND_PROMOTION_STATUS

**NO_CHANGE / BLOCKED_NEEDS_MORE_EVIDENCE**

Stage CHALLENGER_RESEARCH,23dienas; esošais90dienu gate nav atcelts. 4812retained rows,4799eligible binary resolved/1509independentfixtures;12legacyCOMBO_LEG izslēgti no learning.
Registry59artifacts/133trainingruns (74REJECTED,58TRAINED,1BOOTSTRAP),3learningcycles,1bootstrapactivation.
0validation_results/holdout_results/shadow_runs/shadow_predictions/candidate_comparisons/promotion_gates/rollback_events;0productioncalibration.

Oct11 21:27Riga izolēti apmācīti trīs kandidāti uz TRAIN1804/560, četrām esošajām frozen features. Tie nav production registry vai aktivizēti:
LOGISTIC fingerprint3254e42d17f94ca464c2ca8f71963ab4c2545de3e288504d3bb51013decc01e8;
REGULARIZED f87e4a49abeec0e426e751385a331a5108e560998d336053e3a87349f5f2b250;
STUMP fd3cb58ad1a2e836423e7e8927e0458bf72748d7cbc7cea087456b1e78b74c03.

Tie izveidoti pēc VALIDATION loga sākuma. Jau pagājušu spēļu retrospektīvu scoring nedrīkst nosaukt par prospective forward pārbaudi. Nākamais mācību darbs: iesaldēt šo kandidātu nākotnes salīdzinājuma deklarāciju, izmantot esošo shadow sistēmu ar vienādiem fixture/market/as-of features un vērtēt tikai pēc deklarācijas iegūtu neatkarīgu sample. Neaiztikt esošo frozen calendar/holdout. Nepietiekama sample gadījumā saglabāt NEEDS_MORE_EVIDENCE.

Mācību jēga ir izmērīt un pārbaudīt uzlabojumu. Worker izpilde vai “research eligible” pati par sevi nenozīmē jaunu modeli, validāciju vai automātisku aktivizāciju.

## 14. IMPLEMENTED_FIXES

**SMALL_GITHUB_FIX**

`app/dixon_coles_forward/service.py`: novērsta dubulta pilna numerical artifact verifikācija. 537forecasts/537artifacts agrāk radīja1074checks. Reproduced forecast validējas predict; future/reserved ierakstiem paliek explicit pārbaude. Training exclusions tiek nodotas predictor. Integrity, hash un numerical certificate kļūmes joprojām fail closed.

Precīzi vienāds viss report; fingerprint631c33656ec9efe45b3885f9d12370e59e8d4234d2a490c08aea34ccb219ccb1. Izolētā unprofiled replay8.6173s→5.8798s,aptuveni31.8% ātrāk. Nav garantija pret visiem nākotnes timeout.

Pakotne kopē precīzu installed application un aizvieto vienu failu. Mainās tikai atsevišķā DC forward WorkingDirectory. CPU25%,Timeout50s,service commands,databases un timer schedules nemainās. Preflight pārbauda pilnu base manifest,visusgoalvisionunitfailus,loadedroutes,ADMINCodexdisabled un checksum. Root-private guard tiks pārbaudīts tikai operatora sudo izpildē.

## 15. TEST_RESULTS

**PASS**

| Pārbaude šajā diagnostikā | Gala rezultāts |
|---|---|
| DC source/numerical/worker matrix |173passed,0failed|
| Adjacent comparison/calendar/LIVE/COMBO |201passed,0failed|
| LIVE final-review/quota/result-source |84passed,0failed|
| Operator package safeguards |16passed,0failed|
| Precīza installed application + one-file overlay |97passed,0failed|
| Pirms/pēc DC replay |pilnīgi vienāds report|
| Oriģinālais frozen calibration replay |byte-identical|
| Seši esošie offline audits |6/6success|
| Operator wrapper read-only preflight |PASS,modeBASE|

Kopas pārklājas; nesummēt par unikālu testu skaitu. Reālais transports bloķēts. Aptverts reserve/quota/HTTP,probability/context/redcards,chronology/leakage,VOID/partialVOID,no-pick/independence,duplicate delivery un operator drift/drain/partial failure.

Sākotnējās testu palaidēja kļūmes:nepieejams --disable-socket spraudnis,viens nepareizs testa ceļš un trūkstoši fixture imports izolētajā smoke kopijā. Palaidēji laboti; gala testi augstāk izturēti. Tās nav paslēptas production vai assertion kļūmes. Mazs starpskripta SQL placeholder/JSON datetime errors labots pirms evidence saņemšanas.

## 16. GITHUB_COMMITS

**SMALL_GITHUB_FIX**

- `dd2e1c142ac75d418676cae3255ad7faa7e66711` — DC verification source fix/testi/tehniskais pārskats.
- `63afdb3ca35910317047eb1025ccede81e5e5618` — operator package builder/installer/16testi.
- Diagnostikas pārskats pievienots atsevišķā docs commit tajā pašā branch; precīzs gala HEAD/push/clean status ir gala piegādes pārbaudē.

Changed files:
`app/dixon_coles_forward/service.py`;
`tests/test_dixon_coles_forward_verification.py`;
`tests/test_dc_verification_repair.py`;
`operations/dixon-coles-forward/repair_evaluation.py`;
`operations/dixon-coles-forward/build_verification_repair.py`;
`docs/operations/DC_FORWARD_VERIFICATION_20261012.md`;
šis pārskats;
kalibrācijas pārskata Oct12 pielikums.
Privātās DB,receipts,credentials un package metadata netiek pushoti.

## 17. OPERATOR_ACTIONS

**OPERATOR_APPROVAL_REQUIRED — operatora instalācija; NO_CHANGE — modeļi/atlase**

Jaunā minimālā DC research pakotne gatava:

```bash
sudo /usr/bin/python3 -I /home/arvis/goalvision-operations/dc-forward-verification-20261012.py --apply
```

Sagaidāmais marker:`DC_FORWARD_VERIFICATION_REPAIR_DEPLOYED`.
WrapperSHA256:`fcc7d5b3f7767e53d8ac5e729c935014f652f671cdf3c408c8fd85a8ee8f23bb`.
MetadataSHA256:`ad8f198e20c6cfeb9768d2870f1b1f81a24eb2aef9d643ea57fe78a8c9277356`.
Target:`/opt/goalvision-dixon-coles-forward-verify-dd2e1c1-20261012`.

Pakotne tikai uz laiku aptur DC forward timeri, sagaida servisa dabisku pabeigšanu (nekill), pārslēdz vienu reviewed route un atjauno iepriekšējo timer activity. Nemaina enablement,schedule vai citu timeri. Nekādus worker/testsend nepalaiž. Drift gadījumā atsakās; daļējas route kļūmes gadījumā aptur DC timeri un saglabā operator journal, **neveic automātisku rollback**.

Pēc uzstādīšanas nolasīt systemctl/journal dabiskā nākamā DC cikla rezultātu. Šī diagnostika neizpilda nākotnes monitoringu.

LIVE deaktivizācija ir atsevišķa darbība, neietilpst pakotnē: vispirms operatoram pārbaudīt tieši `goalvision-lab-live-evening.timer` un pašreizējo MainPID, tad atsevišķi autorizēt timer stop/disable, ļaujot aktīvajam oneshot pabeigties. Nepārtraukt vai dzēst LIVE settlement/audit DB. Ja settlement piesaistīts tam pašam worker, pirms atslēgšanas jāapstiprina atsevišķā settlement turpināšana. Diagnostikā LIVE timer nav mainīts.

Atsevišķās operatora deaktivizācijas komandas (neizpildītas; vispirms jāpārbauda, ka nav pending LIVE settlements):
```bash
systemctl show goalvision-lab-live-evening.timer goalvision-lab-live-evening.service -p Id -p ActiveState -p UnitFileState -p MainPID
sudo systemctl disable --now goalvision-lab-live-evening.timer
systemctl show goalvision-lab-live-evening.timer -p ActiveState -p UnitFileState
```
Šī komanda apstādina tikai timeri, nevis jau darbojošos servisu; tam ļauj pabeigties. Cutoff brīdī LIVE 31/31 settled, bet pirms vēlākas operatora darbības pending inventory jāpārbauda atkārtoti. Ja ir pending un vienīgais settlement ceļš ir tas pats worker, deaktivizāciju atliek līdz atsevišķam settlement plānam. Neizmantot service kill, reset datubāzi vai manuālu send.

Tālāk prioritāri: neatkarīga frozen calibration VALIDATION, korekti deklarēts trīs kandidātu future shadow salīdzinājums,provider/context/quote completeness un COMBO independence evidence. Jaunas sarkanās kartītes koeficientus,kalibrētu jointEV vai promotion nedrīkst izdomāt datu trūkuma vietā.

Metodiskie avoti atkārtoti pārbaudīti Oct12:
- [Guo et al., calibration](https://proceedings.mlr.press/v70/guo17a.html): vienkāršas kalibrācijas salīdzināt neatkarīgi; publikācijas NN rezultāti nav tiešs mūsu futbola modeļa pierādījums.
- [Maia et al., dynamic football regressors](https://arxiv.org/abs/2312.04338): intensity var būt atkarīga no state/events; citā izlasē novērtētos procentus šeit nekopēt.
- [Gneiting & Raftery, proper scoring](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf): Brier/log loss kvalitātes novērtēšanai, kopā ar reliability.
- [Penaltyblog upstream](https://github.com/martineastwood/penaltyblog): salīdzināmu DC/market benchmark metožu atsauce; nekas nav instalēts, scraper vai vēsturiskie bookmaker odds nav izmantoti.

**Drošības kopsavilkums:** production deployment (agent)=NONE; Telegram sends=0; neatļauti provider calls=0; Official changes=NONE; model activation=NONE; champion/policy/threshold/statistics/calendar izmaiņas=NONE; automatic promotion/rollback=NONE.
