# PREMATCH — dabisko ciklu pārbaude pēc izvietošanas

**PASS / NO_CHANGE.** Snapshot cutoff: 2026-10-06 **15:39:23 Europe/Riga**.
Release: `/opt/goalvision-prematch-evidence-574f55f-20261006`.
Saglabātā evidence: `docs/evidence/prematch_evidence_natural_cycles_20261006/`.

## Darbība pēc operatora izvietošanas

| Discovery cikls, Riga | Provider calls / limits | Review attempts | SINGLE | COMBO |
|---|---:|---:|---:|---:|
| 14:00 | 89 / 300 | 10 | 3 | 1 |
| 14:30 | 68 / 300 | 9 | 3 | 1 |
| 15:00 | 172 / 300 | 7 | 1 | 0 |
| 15:30 | 95 / 300 | 9 | 3 | 1 |
| Kopā | 424 dabiskie calls | 35 pārbaudes | 10 | 3 |

Visas 13 jaunās publikācijas ir SENT ar saglabātiem receipts; jauna delivery
uncertainty nav. Publication floor, probability, time-window un quality noraidījumi
paliek spēkā. Visos četros discovery health ierakstos `failure=null`.

Health ir DEGRADED current-odds kvalitātes dēļ. Kvotas statuss
REDUCED_TO_PRESERVE_QUOTA nozīmē esošā budžeta ievērošanu. Nevienā no četriem
cikliem limits nav pārsniegts. Pārskatītajos operatoram pieejamajos journal
ierakstos kopš izvietošanas nav DB lock, quota-contention/exhaustion,
protected-reserve atteikumu, FileNotFoundError vai service failure atradumu.
Journal vaicājumi nepārsniedza 2000 ierakstu limitu.

Discovery, settlement un observer pēdējie sistēmas rezultāti ir success/exit 0.
Nakts learning serviss vēl nav izpildījis ciklu ar jauno release; tas nav startēts
manuāli. Oficiāli 854 application faili, routes un protected commands saglabāti.

## Queue — reāls pending gadījums

14:00 bija 21 due fixture, no tiem 12 ar tracked kandidātiem. Divi bloki pa
piecām pārbaudēm apstrādāja 10 spēles, 11 palika rindā. Frozen due fixture
secība reproducēta ar **uzstādītā release** helperi, tīklam esot bloķētam.
Reproducēta ierakstītā due populācija, ne no jauna iegūti provider dati.

Tracked kandidāti bija pirms jaunas discovery; agrāki kickoff — pirms vēlākiem.
Pie vienāda 14:30 kickoff iepriekš nepārbaudītie 1638470 un 1638513 bija pirms
13:30 jau pārbaudītajiem. Pēdējo review laiki pārbaudīti ar precīziem indexed
fixture-prefix vaicājumiem. Abi atliktie final-review kandidāti 1619160 un
1619254 tika pārbaudīti 14:30 ciklā pirms sava 15:00 kickoff.

Visos četros ciklos same-cycle repeats=0 un invalid-window attempts=0. Abi batch
limiti ievēroti. **PASS šim novērotajam gadījumam; queue fix nav vajadzīgs.**

## Diagnostikas un performance izmaiņas darbojas

Četri cycle-health un četri scheduled observer ieraksti satur
`LAB_PERFORMANCE_SNAPSHOT_V2`, status COMPLETE, calibration bias, policy cohorts,
EV sign un visus 16 segmentu tipus, tostarp frozen data-quality state. Observer
ieraksti norāda API calls=0, Telegram sends=0, LIVE=DISABLED.

Jaunais PROVIDER_ZERO_PROBABILITY iemesls parādās 10 kandidātu noraidījumos.
Septiņiem 14:00 piemēriem tieši pārbaudīts persisted trace: raw provider `0%`,
normalized/ensemble `0E+1`, API_FOOTBALL_PREDICTION provenance, REJECTED un
probability_modified=false. Nulles nav clampotas.

15:38 observer authoritative kopējās vēstures totals:

| Metrika | SINGLE | COMBO |
|---|---:|---:|
| Published | 405 | 176 |
| Settled | 367 | 158 |
| WON / LOST | 197 / 170 | 61 / 97 |
| VOID / partial VOID | 0 / 0 | 0 / 0 |
| Pending | 38 | 18 |
| Average odds | 2.313827 | 9.986812 |
| Median odds | 1.54 | 2.571080 |
| Flat P/L | −37.03 | −7.756958 |
| Flat ROI | −10.09% | −4.91% |
| Hit rate | 53.68% | 38.61% |
| Brier | 0.223807 | Nav binary calibration sample |
| Log loss | 0.638415 | Nav binary calibration sample |
| ECE | 0.077512 | Nav binary calibration sample |
| Calibration bias | +0.069432 | Nav binary calibration sample |

Tie ir visu saglabāto policy periodu totals, ne jaunā release kvalitātes
novērtējums. Trīs legacy SINGLE trūkst frozen probability; probability sample=364.
Privātā >=1.70 līnija nav iekļauta šajos public-ledger totals. Threshold tuning nav.

## Datu kvalitāte un learning

15:30 broad odds scope bija 129 spēles: 53 stale (41.09%), 22 ar
ODDS_PAGINATION_CHANGED_DURING_SWEEP. Complete date sweep=false; nulle ierakstu
ar missing reason šajā broad snapshot **nav pierādījums pilnam provider coverage**.
Global/post-review skaitītāji ir atšķirīga populācija. Quota pieaugums vai
freshness sliekšņu mīkstināšana nav veikta.

Learning: 2749 total observations, 2737 resolved eligible, 1031 independent
fixtures. TRAIN=1804/560; CALIBRATION_FIT=**164/164 no vajadzīgajiem 300**;
VALIDATION=0, SEALED_HOLDOUT=0, PURGED=759/297, EXCLUDED=22/20.
Champion paliek generation-aa7e535…; governance counts nemainīti.
Kalibrācijas fit nav gatavs; promotion NOT_ELIGIBLE. Training, DC algoritma
izmaiņas, activation un holdout patērēšana nav veikta.

## Vecā COMBO piegāde — operatora apstiprinājums

**OPERATOR_ACTION_REQUIRED / BLOCKED_NEEDS_MORE_EVIDENCE.** Lietotāja 15:38
atsūtītais COMBO #1 teksts pilnībā sakrīt ar frozen claim tekstu, ieskaitot
komandas, tirgus, koeficientus un statistikas periodu. Normalizētā teksta SHA-256:
`3fe9f6530daee2dce50bbaf83a37f4e4cbc41c8519436121b7b7a014f8e137a3`.

Tas saglabāts kā **operatora apliecinājums**, ne izdomāts Telegram API receipt.
Konkrētajam prediction `lab-v2-combo-accuracy-e1f7df2f5ab623619b141a4045aaf627cb287cd813124a887ba04ce6ce61f808`
joprojām ir claim/unknown marker, bet nav receipt, settlement vai result receipt.
Current authoritative statistics tādēļ šo ticket vēl neiekļauj.

Nākamais vajadzīgais pierādījums ir **oriģinālais Telegram message_id esošajā
destination**. Kopētais teksts to nesatur. Ja Telegram piedāvā oriģinālās ziņas
saiti, tā var dot nepieciešamo ID. Private sarunā var būt vajadzīgs atsevišķs
operatora ID iegūšanas solis; jaunu ID nedrīkst minēt. Pēc tam jāsagatavo konkrēts
reviewed, append-only reconciliation, saglabājot sākotnējo timeout vēsturi.

Šajā darbā receipt nav pievienots, claim nav dzēsts un nekas nav pārsūtīts.
Tas arī novērš nepareizu Reply sasaisti ar citu COMBO.

## Izpildītais un robežas

NO_CHANGE runtime kodam. Pārbaudīti dabiskie cikli, real-data queue replay,
scheduled performance, provider-zero trace un operatora COMBO teksta precīza
atbilstība; saglabāta sanitizēta evidence. Jauna testu suite nebija vajadzīga,
jo application/installer kods nav mainīts.

Vienu pārāk plašu read-only diagnostikas vaicājumu apturēju, pārtraucot tikai
paša analīzes Python REPL. Production servisi netika apturēti. Turpmākie
vaicājumi bija query_only, ar laika limitu un indexed/bounded lookup.

Aģenta provider calls=0, Telegram sends=0, manual cycles=0, deployments=0.
Šajā reportā 424 provider calls un 13 publikācijas ir jau notikušu **dabisko
timer ciklu** novērojumi. LIVE un ADMIN Codex DISABLED; Official neskarts.
