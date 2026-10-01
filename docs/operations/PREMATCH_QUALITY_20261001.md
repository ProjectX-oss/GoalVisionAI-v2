# PREMATCH Lab kvalitātes pakotne — 2026-10-01

Statuss: koda integrācija, testi un read-only pārbaude PASS. Operatora izvietošana
un nākamie dabiskie cikli NEEDS_MORE_EVIDENCE. Šī pakotne vēl nav production.

## Ko pakotne maina

- Saglabā aktīvo TODAY_RIGA: discovery un katra jaunā SINGLE/COMBO sastāvdaļa
  attiecas uz nosūtīšanas datumu Europe/Riga. CPU konteksta indeksa labojums paliek.
- Jaunām Lab atlasēm noņem neatbilstošo 1.30 koeficienta minimumu. Decimālajam
  koeficientam joprojām jābūt galīgam skaitlim virs 1; probability slieksnis 0.55
  nemainās. 1.70 SINGLE un 2.00 COMBO minimumi netiek atjaunoti.
- Saglabā veco iesaldēto V1 prognožu pārbaudi un tekstu; jaunās izmanto atsevišķu
  V2_NO_ODDS_FLOOR politikas identifikatoru. Vēsture netiek pārrakstīta.
- Novērš atkārtotu SINGLE vienai fixture starp cikliem; nepieļauj dublētu signāla
  producentu, neizmantojamu signālu vai neatbilstošu market. Freshness, severe
  contradiction, independence, correlation, quality un drošības pārbaudes paliek.
- Vienots Lab performance audits: SINGLE/COMBO settled, W/L/VOID/partial void,
  pending, hit rate, 1u P/L/ROI, average/median odds un probability diagnostika.
  Segmenti: odds, probability, market, league/competition, lead time, odds age,
  confidence, disagreement, EV, signal basis, probability kind un selection policy.
- Negative/zero/positive EV un market-only atlases ir atsevišķi pārskatāmas.
  COMBO nekļūst par model-learning vai calibration observations.
- Saglabā iesaldētos timing bucket. Daļēji anulēts LOST COMBO paliek zaudējums un
  ietekmē P/L/ROI, bet netiek ieskaitīts binārajā hit rate.
- Observer izmanto ierobežotu konsekventu atmiņas snapshot un aizver avota SQLite
  savienojumu pirms aprēķiniem.
- Katrs PREMATCH research mēģinājums atklāj readiness skaitļus arī cooldown vai
  jau esoša shadow challenger gadījumā. Nepietiekami dati nepatērē cycle/holdout.
- Kalibrācijas pamats: TRAIN-only raw modelis, fixture-disjoint calibration fit,
  vēlākā VALIDATION evaluation, untouched SEALED_HOLDOUT un 24h embargo.
  Platt/temperature/isotonic kvalificējas tikai ar savu sample un quality evidence.
- Scheduled coordinator izdod promotion rekomendāciju, nevis automātiski maina
  champion. Promotion prasa pilnu evidence un konkrētai rekomendācijai piesaistītu
  manuālu apstiprinājumu. Rollback mehānisms saglabājas.
- Iesāktu/nepabeigtu adaptive shadow un publication preparation fāžu diagnostika.

De-vig comparator, xG un dynamic-strength pieslēgumi šajā pakotnē nav iekļauti.
Official, LIVE, bankroll vēsture, champion pointer un historical odds netiek mainīti.

## Izvades savietojamība

Pilns svaigais performance JSON bija 168,734 baiti kompaktā formā, kamēr ADMIN
viena ieraksta robeža ir 131,072 baiti. Tāpēc automātiskie observe/research CLI
izvada tikai performance kopsavilkumu, pilnā snapshot fingerprint un segmentu
skaitu. Pilnie segmenti saglabājas observer_runs un cycle_health dokumentos.
Research gatavības atteikums neizveido mākslīgu research cycle.

Manuālie status/why-no-picks auditi saglabā pilno performance izvadi; CLI opcija
--full-performance ļauj pilno izvadi arī observe/research, bet nepārvērš šo komandu
par read-only komandu. Šajā darbā observe/research uz production nav palaists.
Kompaktās izvades regressions pārbauda izmēru zem 8192 baitiem arī pie 20,000
segmentiem un apliecina, ka pilnais pierādījumu dokuments netiek mutēts.

## Svaigā read-only evidence

Precīzs as-of laiks un fingerprints:
docs/evidence/prematch_quality_20261001/readiness_projection.json un performance_snapshot.json.

Dati ap 22:01–22:06 Europe/Riga:

| Sadalījums | Ieraksti |
| --- | ---: |
| TRAIN | 583 |
| VALIDATION | 10 |
| Fresh SEALED_HOLDOUT | 345 |
| PURGED | 865 |
| CALIBRATION_FIT | 0 |
| VALIDATION_EVALUATION | 3 |
| CALIBRATION_PURGED | 7 |

Dataset BLOCKED: VALIDATION minimums ir 30. Kalibrācija arī BLOCKED.
1815 avota observations ietver 12 learning neizmantojamus ierakstus; pieņemti 1803.
Nav observation vai fixture pārklāšanās starp sadalījumiem. TRAIN rezultāti ir
pieejami pirms validation robežas ar 24h embargo; validation rezultāti — pirms
holdout robežas ar 24h embargo. Holdout rezultātu tabulā 0 ierakstu un patērēti
0 holdout observations. Šeit veikta tikai projekcija, ne nākamais research attempt.
Chronological robežas pārvietojas līdz ar resolved observations, tādēļ VALIDATION
skaits nav monotoni augošs. Minimumus vai embargo nemīkstinām.

| Kopējā Lab vēsture | Settled | WON | LOST | VOID | Pending | Flat P/L | Flat ROI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SINGLE | 120 | 34 | 86 | 0 | 24 | -26.15u | -21.79% |
| COMBO | 19 | 1 | 18 | 0 | 13 | -5.572924u | -29.33% |

Šie ir visu saglabāto Lab politiku kopējie rezultāti; tie neatbilst tikai Telegram
V2 marķēto likmju kohortai un nepierāda jaunās politikas efektivitāti. Negative-EV
SINGLE kohortā noslēgušās tikai 3 likmes (2 W / 1 L; -0.32u); 23 vēl pending.
13 jaunās negative-EV COMBO vēl pending. Tas nav pietiekams kvalitātes pierādījums.

## Apvienotās prioritātes

| Posms | Statuss |
| --- | --- |
| INVALID_MODEL_PROBABILITY | PASS iepriekš izpētītajiem 63 incidentiem: provider raw 0%, ne Decimal bugs; rejection saglabājas bez clamp. |
| Readiness | Kods PASS; svaigie dati BLOCKED; nākamais dabiskais research attempt vēl jāpārbauda pēc deploy. |
| Performance snapshot | Kods, accounting un read-only snapshot PASS; runtime pieslēgums gaida deploy. |
| Accuracy-first | Saderība un quality gates PASS testos; forward kvalitāte NEEDS_MORE_EVIDENCE. |
| Lead time / odds age | Diagnostika PASS; publikācijas laika sliekšņi nemainās. |
| Current-odds de-vig | Sagatavots atsevišķajā research zarā, šajā paketē nav aktivizēts. |
| Probability calibration | Pamats PASS; reālu challenger datu gatavība BLOCKED. |
| xG shadow | Sagatavots atsevišķi; svaigs īsts xG ievads BLOCKED. |
| Dynamic strength shadow | Sagatavots atsevišķi; forward rezultātu kvalitāte NEEDS_MORE_EVIDENCE. |
| Promotion | BLOCKED bez pilnas ķēdes un manuāla approval; automātiska promotion nav. |

Iepriekšējais TODAY_RIGA runtime PASS paliek spēkā: 21:00 un 21:30 dabiskajos
ciklos pārbaudīti 6 SINGLE, 2 COMBO un visi astoņi receipt ieraksti (07ffaf1).
ADMIN monitor un worker izmanto jau izvietotos admin-io-startup-0a3e42a un
admin-worker-clone-eebed21 maršrutus; šī pakotne tos nepārslēdz.

## Testi

- Integrācijas komplekts: 1475 PASS + 34 subtests PASS, 264.27 sekundes.
- Pēc integration korekcijām: 41 PASS, 7.01 s (ietver installer; pārklājas).
- Pēc stdout korekcijas: 74 PASS, 1.74 s (pārklājas).
- Gala četru maršrutu installer komplekts: 17 PASS; precīzs laiks test_summary.json.
- Pilna 803 Python moduļu aktīvā pamata salīdzināšana; tikai 21 paredzēts modulis
  atšķiras, papildinot pamatu ar diviem jauniem moduļiem. TODAY_RIGA/CPU pamats sakrīt.
- Testi pārbauda tamper/symlink, daļēju kļūmi otrajā drop-in, daemon-reload kļūmi,
  timer atjaunošanas kļūmi, aizņemta servisa atteikumu, inactive timer saglabāšanu,
  replay un rollback; neviens tests nevada īstu production servisu.
- Tika veikta Git diff pārbaude un Python sintakses pārbaude.

Engineering PASS nav prediction-quality PASS.

## Operatora uzstādīšana un rollback

Pakotne: /home/arvis/goalvision-operations/prematch-quality-20261001
Īsā ieeja: /home/arvis/goalvision-operations/quality-fix.py

Read-only pakotnes pārbaude:

    python3 ~/goalvision-operations/quality-fix.py

Atsevišķi operatora autorizēta uzstādīšana:

    sudo python3 ~/goalvision-operations/quality-fix.py --apply

Sagaidāmais apliecinājums: PREMATCH_QUALITY_DEPLOYED.

Atsevišķi operatora autorizēts rollback:

    sudo python3 ~/goalvision-operations/quality-fix.py --apply --rollback

Instalators piesprauž kodu, pilno pamatu, sākotnējos maršrutus un rollback avotus
ar SHA-256. Izveido atsevišķu /opt release un četrus jaunus EnvironmentFile drop-in.
Netiek mainīti ExecStart, WorkingDirectory, service User/Group, taimeru grafiki vai
ieslēgšanas statuss. Nav .env rediģēšanas vai datubāzes migrācijas.

| Maināmais serviss | Sākotnējais release |
| --- | --- |
| goalvision-lab-v2-discover | prematch-today-scope-f5d7968 |
| goalvision-adaptive-learning-observer | prematch-accuracy-delivery-fc4a740-r4 |
| goalvision-lab-combo-settle | prematch-accuracy-delivery-fc4a740-r4 |
| goalvision-adaptive-learning | prematch-priority-3cb8ada (research) |

Tiek apturēti tikai šo četru servisu taimeri; aktīvajiem darbiem ļauj pabeigties
līdz 60 sekundēm. Nav service kill/start, manuāla cikla, provider pieprasījuma
vai testa Telegram sūtījuma. Ja darbs nepabeidzas, instalācija atsakās un atjauno
taimeru sākotnējo stāvokli. Kļūmes ceļi atjauno iepriekšējos maršrutus. Rollback
noņem tikai pakotnes četrus drop-in, atstājot release un vēsturisko evidence.
ADMIN, weekly un neaktīvā vecā discovery maršruti ir aizsargāti ar salīdzinājumu.

## Pēc uzstādīšanas

1. Pārbaudīt visus četrus effective route, release hashes un taimeru stāvokļus.
2. Nākamajā dabiskajā discovery apstiprināt TODAY_RIGA, jauno V2_NO_ODDS_FLOOR
   politiku un receipt ķēdi. Pick/COMBO nav obligāts, ja quality gates neiziet.
3. Nākamajā observer/cycle_health pārbaudīt PERFORMANCE un COMBO learning izolāciju.
4. Nākamais research timer pēc pārbaudes bija 2026-10-02 05:12 Europe/Riga.
   Pārbaudīt faktiskā attempt counts/status un ka not-ready gadījumā cycle/holdout
   tabulas nav papildinātas. Cooldown var arī nepieļaut trenēšanas mēģinājumu.
5. Tikai pēc tam turpināt atsevišķo research comparatoru pieslēgšanu.

Git zars: fix/prematch-quality-20261001. Pakotnes metadata.json satur pilno source
commit. Nav push, merge, deploy, champion maiņas vai manuālu provider/send darbību.

## Mainītie application faili

- app/adaptive_lab/automl.py
- app/adaptive_lab/calibration_research.py
- app/adaptive_lab/contracts.py
- app/adaptive_lab/coordinator.py
- app/adaptive_lab/datasets.py
- app/adaptive_lab/governance.py
- app/adaptive_lab/health.py
- app/adaptive_lab/metrics.py
- app/adaptive_lab/models.py
- app/adaptive_lab/observations.py
- app/adaptive_lab/observer.py
- app/adaptive_lab/performance.py
- app/adaptive_lab/policy.py
- app/adaptive_lab/prematch.py
- app/lab_combo/service.py
- app/lab_v2_shadow/accuracy_combo.py
- app/lab_v2_shadow/audit.py
- app/lab_v2_shadow/cli.py
- app/lab_v2_shadow/public_presentation.py
- app/lab_v2_shadow/publication.py
- app/lab_v2_shadow/publication_policy.py

Papildus mainīti atbilstošie tests/adaptive_lab un Lab policy testi,
operations/prematch-quality/update.py, installer regresijas, TASKS.md un šie pārskati/evidence.
