# GoalVision ADMIN incidentu audits — 2026-10-10

## Rezultāts un pārklājums

**SMALL_GITHUB_FIX / OPERATOR_ACTION_REQUIRED.** Pārbaudīti deviņu GoalVision
servisu 48 stundu žurnāli līdz **10.10.2026 14:43:49 Europe/Riga**, systemd stāvokļi,
PREMATCH/LIVE piegāžu un rezultātu uzskaite. Izolētā worktree labots reproducējams
SQLite lasītāja bloķēšanas defekts. Production labojums **nav uzstādīts**.

**Papildinājums 15:00:08 Riga:** operators izveidoja sanitizētu read-only ADMIN
eksportu. Tas nolasīts pilnībā, truncated=false: 191 neatrisināts ieraksts
(190 OPEN, 1 REPEATED), 175 bez atkārtošanās pēdējās 72 h un 16 šodienas
ieraksti no četrām avārijām. Piegādes logā 8 RECEIPT_PERSISTED.
Tas nav pilns visu vēsturisko RECOVERED/CLOSED ierakstu arhīvs. Nav veikta
incidentu aizvēršana, acknowledge vai monitor scan.

## Kvotas datubāzes konflikts

**SMALL_GITHUB_FIX.** Incidents 1843e6b0095510e66d0fe2e9, invocation
6d2489a6e6734a8e8856009e4b937daf, apstiprināts servisa žurnālā.

| Laiks Rīgā 10.10. | Kategorija | API mēģinājumi pirms pārtraukuma |
|---|---|---:|
| 11:38:05 | PREMATCH_DISCOVERY | 170 |
| 12:38:02 | PREMATCH_DISCOVERY | 153 |
| 14:08:03 | PREMATCH_REVIEW | 218 |
| 14:38:02 | PREMATCH_DISCOVERY | 206 |

Četri no desmit šodien sāktajiem discovery cikliem pārtrūka; seši pabeidzās ar
publikācijām. Neizdevušies cikli jau bija izmantojuši 747 atļautus provider
mēģinājumus. Bloķētais nākamais HTTP pieprasījums netika sākts.
Tas nav pierādījums, ka visas iespējamās atlases būtu publicējamas.

Pirms 14:38 kļūdas pēdējā rezervācija rādīja 4,786 dienas atlikumu, 3,375 aizsargātu
rezervi un 228 minūtes atlikumu. Cēlonis nav dienas kvotas iztērēšana.
Visi četri PREMATCH konflikti sākas 2–6 sekundes pēc observer sākuma; observer
vēlāk pabeidzas sekmīgi, aptuveni 74–81 sekundē.

AuditRepository.all tur dzīvu ID SELECT kursoru, kamēr get dekodē un pārbauda
dokumentus. SQLite rollback-journal (delete) režīmā lasīšanas locks kavē cita
savienojuma COMMIT pat tad, ja in_transaction ir False. Kvotas rezervācija
atkāpjas un pēc 500 ms atsaka HTTP. Izņēmums tālāk pārtrauc discovery ciklu.

Regresijas tests ar diviem reāliem SQLite savienojumiem reproducē RESERVE_COMMIT
atteikumu un pierāda, ka nav daļēja quota ieraksta. Pirms labojuma 5 jaunie testi
krīt, 2 iztur. Labojums savāc sakārtotos ID ar fetchall pirms dokumentu pārbaudes.
Saglabāta integritāte, kārtošana, stream filtrs, sākotnējā ierakstu kopa, ārējo
transakciju piederība, atomiskums, 500 ms limits un visi quota/publication noteikumi.

**Pierādījumu robeža:** offline defekts ir reproducēts; PREMATCH avāriju laiki
sakrīt ar observer. Konkrētā lock turētāja PID incidentu brīdī nav ierakstīts.
Dabisko ciklu apstiprinājums pēc operatora rollout vēl vajadzīgs. Neapgalvojam,
ka tas ir katra SQLite konflikta vienīgais iespējamais cēlonis.

48 stundās vēl ir trīs LIVE quota contention notikumi divās invocation:
08.10. 22:38 (LIVE_STATE un LIVE_REFRESH), 09.10. 22:27 (LIVE_STATE).

## Daudzi incidentu numuri

**SMALL_GITHUB_FIX.** Eksports pierāda četrus kvotas konfliktus un astoņas
ADMIN ziņas. Katram konfliktam journal QUOTA_DB_CONTENTION ir zināma invocation,
bet tas pats health notikums 3.569–4.322 ms vēlāk saglabāts ar UNKNOWN.
Uzstādītais monitors piesaista UNKNOWN health ANALYSIS_FAILURE, bet ne typed
QUOTA_DB_CONTENTION. SERVICE_FAILURE un MISSING_OUTPUT jau pareizi korelēti.

Jaunais izolētais labojums prasa to pašu servisu, precīzu kvotas kodu,
journal avotu un vienu vienīgu invocation esošajā 30 s logā. Faktiskā eksporta
replay dod 8 grupas pirms / 4 pēc, saglabājot visus 16 avota ierakstus un
8 agrāko sūtījumu vēsturi. 193 ADMIN offline testi PASS; reāli network mēģinājumi 0.
Branch fix/admin-quota-correlation-20261010; commit 9e321c397337e38f994b2dc424621af414acd58b.
Detalizētais pārskats šajā branch: docs/operations/ADMIN_QUOTA_CORRELATION_20261010.md.

**NO_CHANGE.** 175 vecajiem OPEN/REPEATED ierakstiem šajā 72 h logā nav
jaunu sūtījumu vai atkārtojumu. Tie saglabāti, nevis izdzēsti vai automātiski
aizvērti. ID skaits nenozīmē neatkarīgu aktīvu problēmu skaitu.

ADMIN pēdējais izpildījums success; timers enabled/active.
ADMIN Codex disabled preflight PASS. Brīdinājumi nav atslēgti vai slēpti.

## Piegādes un rezultāti

**NO_CHANGE.** Pēdējās 24 stundās 37 publicēšanas ieraksti ar SENT un saglabātu
receipt; šajā publication sample 0 transport failure / 0 reconciliation_required.
Public un private ledger nav pašreizēju claim bez receipt. Publiskajā ledger
saglabāts viens vecs delivery_unknown marķieris bez pašreizēja neatrisināta claim.

Visi deviņi LIVE prediction claims/publications/settlements un rezultātu
claims/receipts ir savienoti. Vecie public SINGLE fixture atkārtojumi
(10 papildu atlases) ir no 21.09.–01.10.; tie nav šodienas duplicate-delivery
kļūdas. Precīzi COMBO dublikāti = 0.

**OPERATOR_ACTION_REQUIRED.** Astoņām publicētām likmēm (4 SINGLE, 4 COMBO)
pagājušas vairāk nekā sešas stundas no sākotnējā pēdējā kickoff. Saglabātā
settlement diagnostika rāda PST, pārceltu nākotnes kickoff un vienu AWD:
fixture 1531002, NONTERMINAL_OR_UNSUPPORTED_STATUS. Atsevišķi jāizskata atļautā
postponed/AWD settlement politika. Neizdomāt WON/LOST/VOID un nepārrakstīt statistiku.

Settlement guard: 256 EXECUTED / 32 DEFERRED 48 stundās. DEFERRED ir paredzētais
180 s discovery aizsargs, nevis avārija. Pēdējais settlement serviss success;
nav jauna settlement traceback. Neviens settlement nav forsēts.

## Datu kvalitāte un research

**DATA_QUALITY_LIMITATION.** Jaunākajā pabeigtajā ciklā (13:30 sākums) 1,460
discovered fixtures: 1,008 ODDS_PAGINATION_CHANGED_DURING_SWEEP, 177 ODDS_STALE,
48 NEEDS_NEAR_KICKOFF_REFRESH. Tas nav neatkarīgu incidentu vai API zvanu skaits.
28 no 32 health ierakstiem ir DEGRADED, četri FAILED. DEGRADED nav automātiski
servisa crash. Publication gates nav mīkstināti.

**NO_CHANGE / BLOCKED_NEEDS_MORE_EVIDENCE.** DC forward: 88 COMPLETED,
4 BLOCKED (RESEARCH_INPUT_OR_BUDGET_UNAVAILABLE), 4 SKIPPED. Pēdējais izpildījums
success; vecais reviewed_competitions.json FileNotFoundError nav atrasts.
DC research: 92 COMPLETED / 4 SKIPPED. Algoritmi netika mainīti.

Observer: 96 pabeigti, de-vig AVAILABLE visos; nav traceback. CALIBRATION_FIT =
346 neatkarīgas spēles un logs CLOSED; VALIDATION = 0, SEALED_HOLDOUT = 0.
Kopējais readiness BLOCKED un NOT_ELIGIBLE promotion ir sagaidāmi governance
ierobežojumi. Šis incidentu audits neveica fit vai promotion.

## LIVE un VPS

**NO_CHANGE.** LIVE release:
 /opt/goalvision-live-final-review-budget-a4cdfa1-20261009.
Read-only wrapper: current_mode=ENABLED, ADMIN guard PASS. LIVE/PREMATCH timeri
aktīvi; 60–70%, EV-off un diagnostiska quote-age politika saglabāta.

Vakar bija 41 LIVE_FINAL_REFRESH_FAILED. Tos nedrīkst saukt par tikko uzstādītā
budžeta labojuma regresiju: ar jauno release vēl nav vakara candidate cikla.
22:47/22:52/22:57 ir trīs LIVE_QUOTA_BOUNDED_STOP; pēdējā rezervācija rādīja
568 remaining / 567 protected reserve. Rezerve saglabāta, nevis daily remaining=0.

Disks 55% aizņemts, aptuveni 133 GiB brīvi; ap 5.5 GiB available RAM.
Nav pierādījuma, ka šie četri GoalVision crash būtu diska pilnuma vai OOM dēļ.
Failed sarakstā ir arī cloud-init/network-wait un atsevišķā MarketEdge serviss;
tie nav mainīti un nav šā GoalVision incidenta daļa.

Papildu read-only pārbaude **15:11 Riga**: 15:00 discovery cikls pabeidzās
15:06:42 ar success, observer 15:08:01–15:09:15 arī success. Šie izpildījumi
nepārklājās; tas vēl nepierāda neuzstādītā lock labojuma runtime efektu.
Nav jaunas discovery kļūdas pēc eksportā fiksētajām četrām.

## Kods, testi un reproducēšana

Branch: fix/quota-reader-lock-20261010.
Base: 2a5f6887bc3d8b39975653952b79c30144fbaae3.
Izolēts worktree; galvenās checkout 220 jau esošās izmaiņas saglabātas.

Changed files:
- app/adaptive_lab/repository.py
- tests/adaptive_lab/test_audit_reader_lock.py
- docs/operations/ADMIN_INCIDENT_AUDIT_20261010.md
- docs/evidence/admin_incidents_20261010/snapshot.json
- TASKS.md

Pirms labojuma jaunie testi: 2 PASS / 5 FAIL. Pēc labojuma focused: 33 PASS.
Adaptive/LIVE/calibration/COMBO/PREMATCH regresijas: **872 PASS / 0 FAIL**,
122.35 sekundes. Skaiti pārklājas un nav summējami. Outbound sockets aizliegti;
provider/Telegram ir fake/mock. git diff --check PASS.
Jauna immutable-release smoke/deployment pakotne šajā auditā nav veidota.

Reproducēt ar esošo offline harness:

    cd /home/arvis/goalvision-worktrees/quota-reader-lock-20261010
    /home/arvis/GoalVisionAI/.venv/bin/python -I -B operations/live-combo-research/offline_tests.py tests/adaptive_lab tests/test_lab_combo.py tests/test_lab_v2_shadow.py

Read-only piegāžu pārskats ar fiksētu laiku:

    /home/arvis/GoalVisionAI/.venv/bin/python -I -B operations/prematch-evidence/publication_audit.py --as-of 2026-10-10T11:43:49.365626+00:00 --output /tmp/goalvision-publication-audit-20261010.json

Claim inventory ir pašreizējais, ne vēsturisks; dabiskās piegādes turpinās.
Sākotnējā eksporta fingerprint un sanitizētais saturs ir snapshot.json.
Žurnāli iegūti ar journalctl --all -o json fiksētā 48 h logā.
Raw journal, DB un test logs netiek commitoti.

## Operatora nākamā darbība

Operatora eksports pabeigts un pārbaudīts; atkārtota izpilde nav vajadzīga.
Oriģinālā eksporta SHA-256:
03a580ea492b4a7995a9488a9e4efe53d1900da9e84373fb367cff1c834b22dc.

**OPERATOR_ACTION_REQUIRED.** Atsevišķi sagatavot uz faktiskajām
PREMATCH/observer/LIVE release bāzētu reader-lock pakotni un ADMIN korelācijas
pakotni. Reviewed DB lasītāja commit: 3d4f5c541c79873208ec2bb8ca8c83a0118f546b.
Reviewed ADMIN commit: 9e321c397337e38f994b2dc424621af414acd58b.
Abu source labojumi ir pārskatīti; apply pakotnes šajā auditā nav veidotas.
Operators lemj par uzstādīšanu. Pēc rollout pārbaudīt dabiskos observer/discovery
pārklājumus, LIVE ciklus un vienu ADMIN ziņu katram viennozīmīgam notikumam.
Nemainīt timerus, neveikt manuālu cycle vai test send.

Production deployments = 0; papildu provider calls = 0; Telegram calls/sends = 0;
Official/champion/bankroll izmaiņas = NONE. 144 GoalVision systemd failu hash
nemainījās. Dabisko servisu autorizētā darbība nav šā audita manuāla darbība.
