# PREMATCH evidence — operatora pakete, 2026-10-06

Statuss: **SMALL_GITHUB_FIX / OPERATOR_ACTION_REQUIRED**. Sagatavota operatora
pakete jau pārskatītajām observability izmaiņām. Aģents production neizvieto.

Gatavās paketes source commit: `574f55fb50ae5bae1b9236978cf7e98b26d982d3`.
Pakete: `/home/arvis/goalvision-operations/prematch-evidence-574f55f-20261006`.
Mērķis pēc operatora apply: `/opt/goalvision-prematch-evidence-574f55f-20261006`.
Gatavās paketes 7/7 checksums PASS; read-only preflight PASS, `current_mode=BASE`.
Mērķis nav instalēts; esošās production routes un 852 application hashi pārbaudīti.

## Operatora komandas

Pārbaude neko neinstalē un nestartē nevienu ciklu:

```bash
python3 ~/goalvision-operations/prematch-evidence.py
```

Sagaidāms `PREMATCH_EVIDENCE_PLAN_VALIDATED`, `current_mode=BASE` un
`ADMIN_CODEX_SYSTEMD_DISABLED=PASS`. Root-only ADMIN failu pārbaude šajā režīmā
ir atlikta līdz apply (`ROOT_GUARD=CHECKED_AT_APPLY`).

Izvietošanu veic tikai operators:

```bash
sudo python3 ~/goalvision-operations/prematch-evidence.py --apply
```

Sagaidāms `PREMATCH_EVIDENCE_DEPLOYED`. Pēc tam pārbauda ar to pašu pirmo komandu:
`current_mode=ENABLED`. Pakete ir idempotenta; jau uzliktai versijai izvada
`PREMATCH_EVIDENCE_ALREADY_ENABLED`, neveicot jaunu pārslēgšanu.

Ja parādās route/hash/configuration drift, neko neapiet un nelieto vecāku apply
wrapper. `PREMATCH_RUNNING_RETRY_AFTER_COMPLETION` nozīmē, ka serviss vēl strādā;
tas netiek nogalināts, timer stāvokļi tiek atjaunoti, operatoram jāatkārto vēlāk.
Šim update nav sagatavota rollback komanda un netiek veikts automātisks rollback.
Neizdevušās route transakcijas atjauno sākotnējos drop-in/timer stāvokļus.

## Precīzais scope

Bāze ir `/opt/goalvision-prematch-final-review-queue-76d96c1-20261005`.
Visi 852 bāzes application faili un esošais release.env ir pinned. Pārskatītā
application atšķirība ir tieši pieci faili (divi no tiem jauni):

- `app/lab_v2_shadow/runner.py`
- `app/lab_v2_shadow/global_evaluation.py`
- `app/adaptive_lab/performance.py`
- `app/dixon_coles_forward/incremental.py`
- `app/dixon_coles_forward/incremental_plan_20261004.json`

Jaunā application satur 854 Python/JSON failus. Saglabā reviewed competitions,
calendar plan, forward plan un constrained protocol resursus. Builder atsakās,
ja actual source ir citas atšķirības vai šie faili/build/updater nav commitoti.
Wrapper pin hashus glabā konkrētai immutable paketei; update pārbauda visus
overlay, bāzes application, source routes un servisu configured commands.

Pārslēdz tikai esošo četru PREMATCH servisu EnvironmentFile/PYTHONPATH. Tie ir
discovery, observer, COMBO settlement un learning serviss. Esošie flags,
ExecStart, darba direktorijas, lietotāji un timer kalendāri nemainās. Pirms
route maiņas aptur tikai to timerus, līdz 45 s gaida esošā darba pabeigšanos,
pēc pārbaudes atjauno iepriekšējos active/inactive stāvokļus. Servisu manuāli
nestartē un neaptur. DB migrācija vai delivery ledger izmaiņa nav vajadzīga.

Scheduled PREMATCH health/status/observer iegūs provider-zero reason un jaunās
performance diagnostikas laukus. Paired DC comparator kļūst pieejams application
read-only auditam; DC forward capture worker, tā timer un algoritms nemainās.
Nav jauna research vai audit taimera.

Saglabā public SINGLE >=1.50, COMBO katrai kājai >=1.30, abus COMBO variantus,
private SINGLE >=1.70 / p70–80%, visus quality/freshness/publication guards,
today-only, quota reserve, early COMBO loss, remaining legs, reply rezultātus,
atsevišķos statistikas periodus un visu vēsturi. Champion, Official, LIVE un
ADMIN darbība netiek mainīta. ADMIN Codex disabled guard joprojām obligāts.

## Pārbaudes

- Iepriekšējā runtime/research koda pārbaude: 475 PASS; nav mainīta šajā paketē.
- Operatora installer/regression grupa: 46 PASS, tīkls bloķēts.
- Exact-base overlay manifest sakrīt ar reviewed repo: 852 -> 854 faili.
- Izolētā assembled application import/smoke: 553 moduļi, PASS, bez source
  checkout fallback; provider/Telegram connect bloķēts.
- Pazudis incremental JSON resurss izolētajā kopijā tiek korekti noraidīts.
- Installer testi pārbauda replay, hash/route/command drift, missing resource,
  symlink, disabled ADMIN, root guards, busy worker un failure recovery.
- Gatavās paketes hash/preflight un aizsargātā stāvokļa evidence saglabāta
  `docs/evidence/prematch_evidence_package_20261006/`. Protected governance
  skaiti pirms/pēc sagatavošanas sakrīt; source application nav papildus mainīta.

## Atlikusī delivery uncertainty

**OPERATOR_ACTION_REQUIRED.** 2026-10-05 plkst. 12:01:59 Europe/Riga COMBO
transporta pieprasījums beidzās ar TIMEOUT. Claim un unknown marker ir, receipt
nav. Tas nav pierādījums, ka Telegram ziņa noteikti nav piegādāta.

Meklē oriģinālajā COMBO sarunā **Tirgus tests #1**, kopējais koeficients aptuveni
**3.53** (precīzi 3.534912), ar šīm trim kājām:

| Spēle | Tirgus | Koeficients |
|---|---|---:|
| France – Belgium | Vairāk par 2.5 vārtiem | 1.52 |
| Northern Ireland – Georgia | Mazāk par 2.5 vārtiem | 1.53 |
| Liptovský Mikuláš – Šamorín | Abas komandas gūs vārtus | 1.52 |

Prediction ID:
`lab-v2-combo-accuracy-e1f7df2f5ab623619b141a4045aaf627cb287cd813124a887ba04ce6ce61f808`.
Šis ID un kāju dati ir izgūti read-only no jau saglabātā publicēšanas ledger.
Recipient/chat ID, tokens un credentials nav iekļauti reportā vai Git.

Līdz oriģinālās ziņas pārbaudei receipt nedrīkst izgudrot, claim dzēst vai COMBO
pārsūtīt atkārtoti. Ja ziņa ir redzama, nākamais vajadzīgais pierādījums ir tās
oriģinālā saite vai ekrānattēls; pēc tam var sagatavot konkrētu reconciliation.
Šī pakete piegādes vēsturi nepārraksta.

## Datu vākšanas robežas

Atkārtotā read-only pārbaudē **13:33 Riga** CALIBRATION_FIT joprojām 163/300,
TRAIN 1804/560, VALIDATION/HOLDOUT 0. Champion nemainīts; fit nav atļauts.
13:00 dabiskajā queue ciklā bija **10 unikāli review attempts**, 0 atkārtojumu,
0 nepieļautu time-window attempts, 73 provider calls pret 297 effective ceiling.
Tādējādi maksimālais divu batchu apjoms novērots reālā ciklā; pending kandidātu
joprojām 0, tādēļ pending prioritātes/least-recent tie pārbaude paliek atvērta.

Kalibrāciju netrenē, DC modeli nemaina un jaunus pickus neforsē. Šie datu vākšanas
nosacījumi nav izlaižami, lai uzdevumu formāli atzīmētu kā pilnībā gatavu.
