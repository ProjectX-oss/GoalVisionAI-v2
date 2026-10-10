# GoalVision ADMIN — kvotas incidentu dublēšanās, 2026-10-10

## Rezultāts

**SMALL_GITHUB_FIX / OPERATOR_ACTION_REQUIRED.** Operatora eksports nolasīts
read-only. Laiks: **10.10.2026 15:00:08 Europe/Riga**, pārklājums 72 stundas un
visi eksportētāja atlasītie neatrisinātie incidenti. Eksports nav truncēts.

| Rādītājs | Skaits |
|---|---:|
| Eksportēti neatrisināti ieraksti | 191 |
| OPEN / REPEATED | 190 / 1 |
| Vēsturiski, bez atkārtošanās pēdējās 72 h | 175 |
| Šodienas četru PREMATCH avāriju ieraksti | 16 |
| ADMIN sūtījumi ar saglabātu receipt 72 h logā | 8 |
| Izolētā atkārtojumā execution grupas pirms / pēc | 8 / 4 |

191 nav 191 neatkarīga pašreizēja avārija. Šis eksports nav visu jebkad bijušo
RECOVERED/CLOSED incidentu arhīva inventarizācija. Vēsturiskie OPEN ieraksti
netiek automātiski pasludināti par atrisinātiem.

## Precīzais papildu brīdinājumu cēlonis

**SMALL_GITHUB_FIX.** Katrā no četriem pārtraukumiem journal ieraksts satur
pareizu systemd invocation. Tas pats QUOTA_DB_CONTENTION_EXHAUSTED nonāk health
pārskatā ar Invocation UNKNOWN tikai 3.569–4.322 ms vēlāk. Uzstādītā korelācija
piesaista UNKNOWN health tikai ANALYSIS_FAILURE, nevis QUOTA_DB_CONTENTION.
Tādēļ katrs kvotas konflikts tiek paziņots divreiz.

| Rīgas laiks | Journal incident ID | Dublējošais health ID |
|---|---|---|
| 11:38:05 | 206b1b5d5461ad0f2cbd83af | 0077af43f226024a7468646e |
| 12:38:02 | faf4ccb36d11d435d466c304 | 41bc0aa7ea0b23b22e2b3053 |
| 14:08:03 | b4951a0c0acb777ea3d19187 | 47369a2aebe65abcc41ce66b |
| 14:38:02 | 1843e6b0095510e66d0fe2e9 | 7a7bd5b7b1db203042e6f3d5 |

SERVICE_FAILURE un MISSING_OUTPUT ieraksti jau pareizi piesaistīti attiecīgajām
invocation un tiem papildu sūtījumu nav. Kopsummā katrai avārijai četri
pierādījumu ieraksti, divi sūtījumi.

## Izolētais monitora labojums

**SMALL_GITHUB_FIX.** Tikai health QUOTA_DB_CONTENTION ar precīzu kodu
QUOTA_DB_CONTENTION_EXHAUSTED var piesaistīties journal kvotas ierakstam:

- tas pats serviss;
- precīzs typed kļūdas kods abos avotos;
- zināma journal invocation;
- esošais 30 sekunžu logs;
- tikai viena iespējamā invocation šajā logā.

Otrs tuvumā esošs izpildījums, trūkstošs kods, cits avots vai cits serviss atstāj
incidentu neatkarīgu. Vēlāks konkurējošs pierādījums atceļ tikai korelācijas
projekciju; iepriekšējās audit rindas saglabājas.

Jaunā asociācija: UNIQUE_TEMPORAL_SAME_SERVICE_QUOTA_CODE.
Incidenta ID un UNKNOWN avota invocation netiek pārrakstīti. Jau nosūtītas,
acknowledged vai UNCERTAIN piegādes netiek dzēstas, labotas vai atkārtoti sūtītas.
Nav mainīti delivery limiti, activation epoch, alert reālo kļūdu noteikumi
vai monitorēšanas biežums. Aktīvajā servera release labojums vēl nav.

## Vēsturiskie ieraksti

**NO_CHANGE.** 175 vēsturiskajiem ierakstiem šajā 72 h logā nav jaunu
atkārtojumu vai outbox sūtījumu:

| Kategorija | Ieraksti |
|---|---:|
| SERVICE_FAILURE | 90 |
| QUOTA_DB_CONTENTION | 50 |
| MISSING_OUTPUT | 17 |
| INTEGRITY_FAILURE | 12 |
| ANALYSIS_FAILURE | 4 |
| DATABASE_LOCK | 1 |
| MONITORING_COVERAGE_DEGRADED | 1 |

Vecais rotation incidents c7df1386cf441d629cbc83b9 ir saglabāta vēsture;
šajā eksportā nav jauna rotation brīdinājuma. Nekas nav masveidā aizvērts.

## Atsevišķais DB lasītāja defekts

**SMALL_GITHUB_FIX / OPERATOR_ACTION_REQUIRED.** Kvotas rezervācijas problēmu
risina atsevišķi pārskatītais commit
3d4f5c541c79873208ec2bb8ca8c83a0118f546b,
branch fix/quota-reader-lock-20261010. AuditRepository.all atbrīvo ID SELECT
lasīšanas kursoru pirms dokumentu pārbaudes. Reproducēts ar diviem SQLite
savienojumiem; 33 focused un 872 blakus regresiju testi PASS (pārklājas).

Šodienas četras avārijas sakrita ar observer sākumu. Konkrētā lock turētāja PID
toreiz nav reģistrēts; dabisko ciklu pārbaude pēc operatora rollout joprojām
vajadzīga. ADMIN korelācijas labojums samazina dublētus ziņojumus; tas pats
nenovērš SQLite konfliktu.

## Tests un reproducēšana

**NO_CHANGE.** Pārbaudītās bāzes commit:
ea94dfec4d72334c93e3133a31fd6509a41c3ebc,
origin/fix/admin-mixed-delivery-20261004. Izolētais branch:
fix/admin-quota-correlation-20261010.

193 ADMIN testi PASS, 0 failures/errors, 17.893 s. Reāli network mēģinājumi = 0.
Jauno sākotnējo 11 testu kopā pirms labojuma bija 9 assertion failures, ieskaitot
subtests; pēc labojuma šie scenāriji un trīs replay testi PASS.
Pārbaudīta avotu pienākšanas secība, ambiguity, 30 s robeža, restart idempotence,
UNCERTAIN aizsardzība, veco receipt un audit nemainība.

Pilna faktiskā eksporta un minimizētā reproducējamā input projekcijas sakrīt.
Uzstādītā kodā iegūtas 8 execution grupas, labotajā 4. Sintētiskā laika secības
testā 16 incidenti dod 4 fake ziņas. Tas nav production nosūtīts tests un
neatceļ vēsturiskās astoņas īstās ziņas.

    cd /home/arvis/goalvision-worktrees/admin-quota-correlation-20261010
    PYTHONPATH=. /home/arvis/GoalVisionAI/.venv/bin/python -B operations/admin-alerts/test_v1_3_offline.py --output /tmp/admin-quota-validation.json
    /home/arvis/GoalVisionAI/.venv/bin/python -I -B operations/admin-alerts/replay_quota_correlation.py --input docs/evidence/admin_quota_correlation_20261010/incident_projection_input.json --output /tmp/admin-quota-replay.json

Replay output jābūt jaunam failam; avots netiek pārrakstīts.
Visi transporti testos fake/mock; reāli socket savienojumi aizliegti.

Mainītie faili:

- app/admin_alerts/correlation.py
- tests/admin_alerts/test_quota_health_correlation.py
- operations/admin-alerts/replay_quota_correlation.py
- docs/evidence/admin_quota_correlation_20261010/incident_projection_input.json
- docs/evidence/admin_quota_correlation_20261010/replay.json
- docs/evidence/admin_quota_correlation_20261010/validation.json
- docs/operations/ADMIN_QUOTA_CORRELATION_20261010.md
- TASKS.md

## Fingerprints

Oriģinālā sanitizētā operatora eksporta SHA-256:
03a580ea492b4a7995a9488a9e4efe53d1900da9e84373fb367cff1c834b22dc.

Pārskatītā eksportētāja SHA-256:
2e65e4f4af6bbca42b164797a8d3b3e7ecc468280869b17a2b9ba2a0124c4861.

Minimizētā replay input un korelācijas koda SHA-256 ir replay.json;
uzstādītā koda un testu fingerprints ir validation.json.
DB, raw journal, recipient IDs, tokens un receipt saturs nav commitoti.

## Nākamā operatora darbība un robežas

**OPERATOR_ACTION_REQUIRED.** Atsevišķi sagatavot immutable release pakotnes
DB lasītāja un ADMIN korelācijas commit, balstoties uz faktiski uzstādītajiem
PREMATCH/observer/LIVE un ADMIN release. Izolēts package smoke un operatora
apstiprinājums pirms uzstādīšanas. Šajā solī apply pakotne nav izveidota.

Pēc operatora rollout pārbaudīt dabiskos ciklus: kvotas rezervācija bez
500 ms konflikta un katrai viennozīmīgi saistītai avārijai ne vairāk kā viens
ADMIN paziņojums. Nedzēst vēsturi un neveikt manuālu cycle vai test send.

Production deployment = NONE; provider calls = 0; Telegram calls/sends = 0;
Official/champion/bankroll/threshold izmaiņas = NONE. LIVE joprojām operatora
ieslēgts ar esošo vakara konfigurāciju. ADMIN Codex paliek DISABLED.
144 GoalVision systemd failu hashi saglabāti. Galvenās checkout 220 iepriekšējās
nepārskatītās izmaiņas neaiztiktas.
