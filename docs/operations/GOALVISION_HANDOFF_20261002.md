# GoalVision AI — pilna darba nodošana jaunajam čatam

Sagatavots 2026-10-02 Arvim. Šis ir pašpietiekams darba turpināšanas dokuments, nevis jauna deployment instrukcija. Jaunais čats nedrīkst pieņemt, ka tam automātiski ir vecā čata atmiņa vai vecās Python sesijas mainīgie.

Pēdējais pilnais kvalitātes datu griezums: **2026-10-02 12:50:18 Europe/Riga**. Pēdējais padziļinātais publication/settlement audits: **12:28:11 Riga**, par discovery 12:00, observer 12:08 un settlement līdz 12:25. Repo HEAD un research avoti atkārtoti pārbaudīti, gatavojot šo nodošanu. Vēlāki dabiski cikli var mainīt skaitļus; zemāk minētie skaitļi nav solījums par stāvokli jaunā čata atvēršanas brīdī.

## 1. Precīzs nākamais uzdevums un atļauju robeža

Arvis apstiprināja nākamo darbu: **pieslēgt jau sagatavotos current-odds de-vig salīdzinātājus research/shadow pierādījumu un metriku ķēdei**, saglabājot pašreizējo publication uzvedību. Pēc tam palūdza pāriet jaunā čatā un nodot visu kontekstu. Šajā nodošanas posmā jaunā integrācija vēl NAV implementēta pašreizējā production zarā un NAV deployota.

Jaunajā čatā jāsāk ar esošo avotu pārbaudi un integrāciju uz aktuālā PREMATCH pamata. Nav jāsāk viss projekts no nulles, nav jāatjauno ADMIN Codex, nav vēlreiz jāuzliek jau izvietotais SINGLE minimuma labojums.

Atļauts: read-only audits, izolēts worktree, koda labojumi, mērķēti offline testi, dokumentācija, Git commit, konkrētas operatora pakotnes sagatavošana. **Production deployment ir atsevišķa operatora darbība.** Lietotāja “pieslēdzam” šajā kontekstā nav atļauja automātiski izvietot nepārbaudītu research kodu.

## 2. Aktuālie noteikumi — jaunākās lietotāja izvēles ir noteicošās

| Joma | Aktuālā prasība |
|---|---|
| Official | Nemainīt; nejaukt tā bankroll vai statistiku ar Lab. Official esošā SINGLE politika ir 1.60; izņēmums līdz divām COMBO izvēlēm ar kopējo 2.00. Šie skaitļi nav Lab noteikumi. |
| LIVE | DISABLED. Neieslēgt. |
| ADMIN Codex / Auto-Repair | DISABLED; saglabāt marker, worker izslēgtu un tā timer disabled. Monitor drīkst turpināt esošo darbu. |
| PREMATCH Lab SINGLE | **Decimal odds >= 1.30, ieskaitot 1.30**, pirms noapaļošanas attēlošanai. Lietotājs to skaidri atjaunoja 2026-10-02. |
| PREMATCH Lab COMBO | Nav ekonomiska minimuma ne kopējam koeficientam, ne atsevišķām legs. Odds joprojām jābūt derīgiem (>1); quality, freshness, safety, independence un correlation pārbaudes paliek. |
| Vecie odds noteikumi | Neatjaunot 1.70 SINGLE / 2.00 COMBO Lab hard floor. Vecā prasība “Lab vispār bez minimuma” SINGLE gadījumā ir aizstāta ar jaunāko 1.30 atļauju. |
| Publication diena | Jaunas SINGLE un COMBO publikācijas tikai šodienas spēlēm pēc **Europe/Riga**. Esošais kickoff laika logs 09:00 ieskaitot līdz 23:00 neieskaitot saglabājas. |
| Vecās publikācijas | Saglabāt nemainīgu vēsturi, arī agrāk publicētās nākamo dienu vai zem-1.30 likmes; turpināt settlement. |
| Accuracy-first | Probability minimums 0.55 paliek. Non-positive EV var būt eligible tikai pēc esošajām quality pārbaudēm; auditā un mērījumos atsevišķi. |
| Thresholds | Nemainīt sliekšņus, līgu/market izslēgšanu vai laika politiku tikai sliktā pooled ROI vai maza sample dēļ. |
| Champion | Nemainīt, neveikt automātisku promotion. Pilna validation/calibration/holdout/shadow/stability ķēde un manuāls approval. Rollback jābūt iespējams. |
| Research dati | Nekādus historical bookmaker odds feed, download vai jaunu historical-odds projektu. Drīkst analizēt pašu jau forward laikā iesaldētās current quotes un vēlākos rezultātus. |
| COMBO learning | COMBO un COMBO_LEG nav model-learning vai calibration observations. Finanšu statistika ir atsevišķa. |
| Operacionālā darbība | Šajā darbā neizsaukt manuālus discovery, observer, settlement vai research ciklus; neveikt manuālus provider pieprasījumus vai Telegram testa sūtījumus. Esošie dabiskie timers darbojas. |
| Deployment | Nekāda automātiska deployment. Sagatavot pārskatāmu, testētu, hash-pinned pakotni; operators izpilda īsu komandu. |

Saziņa latviski, tieši un konkrēti. Arvis negrib atkārtotas nevajadzīgas atļaujas un garas Termius komandu sienas. Par katru posmu jāsniedz changed files, tests, evidence, Git commit un precīzs PASS / BLOCKED / NEEDS_MORE_EVIDENCE. PASS testos nav tas pats, kas forward kvalitātes vai deployment PASS.

Repo vispirms jāizlasa `AGENTS.md`, `PRODUCT_RULES.md`, `ROADMAP.md`, `TASKS.md`. Daļa veco roadmap/task ierakstu ir vēsturiski un nav aktuālā runtime stāvokļa avots. Lietotāja jaunākās skaidrās autorizācijas ir noteicošās pār veciem vispārīgiem dokumentu tekstiem; nedrīkst patvaļīgi paplašināt šo autorizāciju uz citām politikām.

## 3. Pieslēgums, direktoriji un Git stāvoklis

VPS: **vmi3558657**, lietotājs **arvis**. Remote Desktop Commander device ID:

`91e12ee5-803e-4b83-a04c-0c48aecbc273`

Ja connector ir pieejams, atrod tā process/file tools un sāk savu Python REPL (`python3 -i`). Vecajā čatā bija PID 1566739, bet uz tā vai tā mainīgajiem jaunais čats nedrīkst balstīties. Neizdrukāt `.env`, API atslēgas, bot tokenus vai citus secrets. Ja connector nav pieejams, nepaziņot par neizdarītu VPS pārbaudi kā pabeigtu; lietotājam dot vienu konkrētu trūkstošā artefakta vai pieslēguma pieprasījumu.

| Loma | Ceļš / zars / HEAD |
|---|---|
| Runtime WorkingDirectory | `/home/arvis/GoalVisionAI` |
| Python venv | `/home/arvis/GoalVisionAI/.venv/bin/python` |
| Aktuālais reviewed source worktree | `/home/arvis/goalvision-worktrees/prematch-single-floor-20261002` |
| Aktuālais source zars | `fix/prematch-single-floor-20261002` |
| Source HEAD pirms nodošanas dokumenta commit | `0b84eeedbe1ac73bdb957720e76f906d3c119a3e` — clean |
| Research source worktree | `/home/arvis/goalvision-worktrees/forward-ai-ml-20261001` |
| Research zars | `research/forward-ai-ml-20261001` |
| Research HEAD nodošanas pārbaudē | `938402ae7e2279f2e36a5abd8cb8124e793d7495` — clean |
| Operatora pakotnes | `/home/arvis/goalvision-operations` |

Jaunā implementācijas worktree pamatu veidot no aktuālā reviewed source, saglabājot vēlākos labojumus. Research worktree ir avots atlasītai integrācijai, nevis automātiski pareizs production pamats. Komiti ir saglabāti VPS Git worktrees. Push/merge uz GitHub nav apgalvots un nav jāpieņem kā veikts. Pārbaudīt lokālo Git stāvokli pirms izmaiņām; nesabojāt citu darbu.

Šis dokuments glabājas arī repo `docs/operations/GOALVISION_HANDOFF_20261002.md` un operatora direktorijā `/home/arvis/goalvision-operations/GOALVISION_HANDOFF_20261002.md`. Tā commit atrodams ar Git log; tas ir docs commit virs minētā source HEAD un nemaina runtime kodu.

## 4. Kas pašlaik izvietots

Aktīvais PREMATCH release:

`/opt/goalvision-prematch-single-floor-f81aa2c-20261002`

Source commit: `f81aa2c2c1aae4af8decaa9b454d182c82f74af8`.
Pilns application manifests: **807 Python modules**.
Operators izvietoja 2026-10-02 ap **11:54 Riga**; readback ap 11:54:48 bija PASS.

Visi četri PREMATCH services izmanto šī release `release.env`:

1. `goalvision-lab-v2-discover.service`
2. `goalvision-adaptive-learning-observer.service`
3. `goalvision-lab-combo-settle.service`
4. `goalvision-adaptive-learning.service`

Precīzie release parametri:

```text
PYTHONPATH=/opt/goalvision-prematch-single-floor-f81aa2c-20261002/application
GOALVISION_LAB_ACCURACY_COMBOS=1
GOALVISION_LAB_TODAY_ONLY=1
GOALVISION_LAB_EARLY_COMBO_LOSS=1
GOALVISION_LAB_SINGLE_MIN_ODDS_130=1
```

Visi četri timers pēdējā readback bija enabled/active. One-shot service `inactive` starp izsaukumiem pats par sevi nav kļūme.

Dabisko ciklu pēdējā zināmā cadence: discovery :00/:30, observer :08/:38, settlement :05/:15/:25/:35/:45/:55. Nākamais zināmais research timer bija 2026-10-03 **05:12 Riga**. Uz atsākšanas brīdi to vajag pārbaudīt, nevis garantēt pēc veca saraksta.

VPS `systemctl` laiku attēloja **CEST (UTC+2)**, bet šajā datumā Riga ir **UTC+3**. CEST 04:12 = Riga 05:12. Izvairīties no vienas stundas kļūdas auditā.

ADMIN monitor release:

`/opt/goalvision-admin-alerts-releases/admin-monitor-compat-a28f2a6-20261002`

ADMIN worker vēsturiskais source route:

`/opt/goalvision-admin-autorepair-releases/admin-worker-clone-eebed21-20261001`

Worker nedarbojas: inactive, MainPID=0; timer inactive/disabled, DISABLED marker saglabāts. Monitor timer paliek enabled/active. ADMIN un weekly routes netika mainīti ar pēdējo PREMATCH deployment. Arī aizsargātie citi/legacy routes jāsaglabā nākamajā pakotnē.

## 5. Installer un deployment vēsture — būtiski, lai neatkārtotu kļūdas

| Posms | Kas notika |
|---|---|
| Accuracy COMBO | `c490866` 2026-10-01: sākotnējās deviņas SINGLE, bet neviena COMBO bija policy mismatch; ieslēgtas Lab accuracy COMBO no quality-approved kandidātiem, arī non-positive EV. |
| CPU | `1a18dc0`: verified context scope indekss viena cutoff ietvaros; novērsta atkārtota visu lielo avotu validācija. |
| Today-only | `f5d7968`: discovery un jaunu publication preparation/delivery tikai Riga šodienai. Iepriekš varēja nonākt rītdienas/aizparītdienas fixtures. |
| Quality | `3ad346b`: performance, timing, readiness, calibration/manual promotion foundation un saderīga integrācija uz today/CPU pamata; četras PREMATCH routes. |
| Settlement | `04a0751`: operators to izvietoja PIRMS vecās floor pakotnes izpildes. Early COMBO loss un remaining-leg tracking. |
| Vecā floor pakotne | `d733591` bija sagatavota pret quality `3ad346b`; pēc settlement uzlikšanas pareizi noraidīja citu base ar `PREMATCH_ROUTE_MISMATCH:goalvision-lab-v2-discover.service`, pirms mutācijas. |
| Aktuālā floor pakotne | `f81aa2c` pamatota uz tiešām instalēto settlement release; operatora apply izdevās, floor un early settlement darbojas kopā. |

**Neatslābināt route/hash guards un nespiediet veco installer pāri jaunam release.** Nākamajai pakotnei jāpārbauda patiesais tagadējais base; nevar akli atstāt build.py veco konstantu. Neveikt wholesale cherry-pick no research runner, kas var atgriezt vecu no-floor vai pazaudēt CPU/today/settlement izmaiņas.

Aktuālais wrapper:

`/home/arvis/goalvision-operations/prematch-policy-compat.py`

Pakotne:

`/home/arvis/goalvision-operations/prematch-single-floor-f81aa2c-20261002`

Read-only pārbaude, ja tiešām nepieciešama:

```bash
python3 ~/goalvision-operations/prematch-policy-compat.py
```

Pēdējā atbilde:

```text
PREMATCH_SINGLE_FLOOR_PLAN_VALIDATED=/opt/goalvision-prematch-single-floor-f81aa2c-20261002
current_mode=ENABLED; ADMIN_CODEX_DISABLED=PASS
```

Tas **jau ir deployed**. Nedot lietotājam vēlreiz apply bez iemesla. Vecais `prematch-policy-fix.py` norāda uz novecojušo `d733591`; to nelietot. `settlement-fix.py` arī ir iepriekšēja, jau izpildīta posma komanda.

Aktuālās pakotnes metadata SHA-256:
`4a3a870ef03fc7d2093ce833e0b1a4128a3a1d6d2aec512dde6e1812593606bb`

Wrapper SHA-256:
`7449b07ff683425bf56fcac68145f6f935bb804134c2ac809ca5d49d038c59b7`

Installer saglabā:

- configured ExecStart/argv, WorkingDirectory, EnvironmentFiles un avota moduļu pinning;
- aizsargāto ADMIN/weekly/worker routes un ADMIN disabled pārbaudi;
- lock `/run/lock/goalvision-prematch-accuracy-combo.lock`;
- tikai četru PREMATCH timers pagaidu apturēšanu, iepriekšējā active/inactive stāvokļa atjaunošanu;
- dabīgu services drain līdz 45 sekundēm; nekāda service kill vai piespiedu cikla restartēšana;
- partial-failure rollback un symlink/source-integrity guards.

Aktuālais drop-in nosaukums `zzzzzzz-single-floor-20261002.conf`; iepriekšējais settlement `zzzzzz-settlement-20261002.conf`. Savietojamais floor rollback izslēdz tikai SINGLE-floor flag, saglabājot jau instalēto early loss un saderīgos readers. Rollback nav šobrīd pieprasīts.

Iepriekšējais CPU installer timeout `DISCOVERY_RUNNING_RETRY_AFTER_COMPLETION` bija aizsargāta atteikšanās mainīt route, kamēr discovery vēl strādā; nebija atļauja nogalināt procesu.

## 6. Pašreizējā SINGLE/COMBO koda uzvedība

SINGLE floor:

- `app/lab_v2_shadow/single_odds_policy.py`: flag un strict Decimal >=1.30, nevis display rounding; invalid konfigurācija fail-closed.
- `app/lab_v2_shadow/publication.py`: kopējs quality-approved `accuracy_pool`, atsevišķs pēc floor filtrēts `single_pool`; floor pirms best-market ranking pa fixture. COMBO saņem pilno atbilstošo pool.
- Jaunā SINGLE frozen policy `LAB_SINGLE_ACCURACY_FIRST_PER_FIXTURE_V3_MIN_ODDS_130`; minimums 1.30, probability minimums 0.55, atsevišķa decision identity.
- `app/lab_combo/service.py`: gala SINGLE floor pirms jauna delivery claim, arī veciem sagatavotiem, vēl nepublicētiem tickets. COMBO un jau publicēto settlement netiek filtrēti.
- Vecie V2 no-floor contracts paliek vēstures/replay un COMBO legs saderībai; nedzēst tos kā šķietami “nepareizu minimumu”.
- Public presentation atspoguļo jaunās V3 prasības; vecie frozen message bytes saglabāti.

Early COMBO settlement:

- Īsts apstiprināts zaudējošs rezultāts ar atbilstošu FT/AET/PEN statusu ļauj ekonomiski noslēgt visu COMBO kā LOST, -1u vienreiz, negaidot pārējās legs.
- Pirmajā immutable settlement ir zināmās `legs`, skaidri norādītas `pending_legs`; nepabeigtā stāvoklī nav jāizdomā galīgās effective combined odds.
- Pārējo legs pārbaude turpinās. Vēlāks `combo_result_detail` papildina pilno pierādījumu ķēdi, neveido otru finanšu settlement vai otru rezultāta sūtījumu.
- `combo_needs_results` nedrīkst pārtraukt pārējo legs uzraudzību tikai tāpēc, ka ekonomiskais COMBO jau LOST. Saderība saglabāta arī flag-off režīmā.
- Readers, presentation, CLI un `app/adaptive_lab/metrics.py` saprot partial un completed detail.
- `app/lab_combo/result_diagnostics.py` satur sanitizētu ierobežotu unresolved diagnostiku (līdz 100), provider status, aktuālo kickoff un schedule drift; bez jauniem manuāliem API pieprasījumiem.
- Rezultātu pārbaudes atbilstība attiecīgajā experimental ceļā sākas **90 minūtes pēc kickoff**. Dažos CLI guards ir 7200 sekundes; nedrīkst visai sistēmai nepamatoti piedēvēt vienu 2h noteikumu.

## 7. Pēdējais dabisko ciklu audits — kas reāli pierādīts

2026-10-02 discovery darbojās 12:00:02–12:03:02 Riga, exit success; analysis/delivery COMPLETED. Seši attempts un seši accepted receipts, Telegram message IDs **383–388**.

| SINGLE | Market | Odds | Kickoff Riga, 2026-10-02 |
|---|---|---:|---|
| Finn Harps – Kerry | OVER_1_5 | 1.36 | 21:45 |
| Gumi Sportstoto W – Suwon FMC W | UNDER_3_5 | 1.53 | 13:00 |
| Sturm Graz – Floridsdorfer AC | OVER_2_5 | 1.33 | 14:00 |

Blocked candidate **market** counts: 67 zem 1.30, 918 zem probability 0.55, 31 quality-policy rejection, 16 ārpus kickoff loga. Tie nav fixtures counts.

| COMBO message | Combined odds | Leg odds |
|---|---:|---|
| 386 | 4.134060 | 1.93 / 1.53 / 1.40 |
| 387 | 2.227680 | **1.17** / 1.36 / 1.40 |
| 388 | 2.822400 | 1.44 / 1.40 / 1.40 |

1.17 leg: Smedby–Nyköping OVER_1_5. Tas ir dabīga runtime pierādījums, ka SINGLE minimums neizmet derīgu COMBO leg. Trijās COMBO deviņas dažādas fixtures, 18 dažādas komandas. Visi 12 SINGLE/COMBO kickoff ieraksti bija Riga šodiena. Receipt, product, identity un dienas pārbaudēs kļūdu nebija.

Divi iepriekš zināmi zaudējuši COMBO 11:55:04 noslēgti vienu reizi, katrs LOST/-1u un divas pending legs:

- Germany–Serbia OVER_2_5, apstiprināts 2:0;
- British Virgin Islands–Montserrat OVER_2_5, apstiprināts 0:2.

Result receipts 11:55:37, message IDs **381 un 382**. Neviens publicēts COMBO ar jau saglabātu zaudējošu leg auditā nepalika ekonomiski pending. Frozen rezultāta ziņās pending 27 bija pareizi uz 11:55; pēc trim jaunām COMBO vēlāk pending 30 ir pareizi. Vēsturiskās message statistics ir momentuzņēmumi, nevis dzīvs skaitītājs.

12:08 observer: PERFORMANCE COMPLETE, LIVE DISABLED, heavy_training=false, api_calls=0, telegram_sends=0, COMBO calibration observations=0.

Visām **154** saglabātajām finanšu settlements bija accepted result receipt. Pārbaudīti **372** publication/result receipts: nulle invalid, nulle claims bez receipts, nulle duplicated destination/message IDs. Visi pārbaudītie source fingerprints reproducējas. Rezultāti un P/L neatkarīgi pārrēķināti no saglabātās immutable evidence un sakrita ar observer un settlement.

Receipt pierāda Telegram pieņemšanu, nevis to, ka ziņa vēlāk nav izdzēsta. Score reconciliation izmantoja jau saglabāto provider evidence; ārēji score API netika atkārtoti izsaukti.

Pending gadījumi:

- **Dayrout–Ismaily SC**, fixture **1594851**: frozen sākums Oct1 15:30 Riga, bet dabiskā provider diagnostika rāda **Oct2 15:30 Riga**, NS, `RESCHEDULED_FUTURE_KICKOFF`, `schedule_changed=true`. Tas izskaidro pending; vēsturi nedrīkst pārrakstīt vai izdomāt VOID.
- Četras citas started unresolved COMBO legs uz cutoff bija tikai 28–88 min pēc kickoff, zem 90 min pārbaudes sliekšņa. Tas nebija worker hang pierādījums.
- Pārējo agrīni zaudēto COMBO legs pilnā completion vēl jānovēro vēlākos dabiskos ciklos. Neatzīmēt šo nākotnes pierādījumu kā jau pabeigtu.

## 8. Pēdējie finanšu skaitļi un to pareiza interpretācija

Šie ir visu publicēto Lab cohorts skaitļi uz **12:50:18 Riga**, nevis tikai jaunākā release rezultāti.

| Produkts | Published | Settled | WON | LOST | VOID | Pending | Flat P/L | ROI uz settled |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SINGLE | 165 | 131 | 41 | 90 | 0 | 34 | -27.35u | -20.8779% |
| COMBO | 53 | 23 | 2 | 21 | 0 | 30 | -6.588824u | -28.6471% |

Pēdējais quality audit salīdzinātais observer snapshot: **12:38:01.880869 Riga**. Par šiem skaitļiem nekāda apgalvojuma, ka jaunā 1.30 politika “nestrādā”, nav: V3 vēl nebija settled iznākumu.

| SINGLE policy cohort | Published | Settled | WON / LOST | Pending | P/L |
|---|---:|---:|---:|---:|---:|
| Earliest experimental | 3 | 3 | 0 / 3 | 0 | -3.00u |
| Vecais broad-coverage ensemble | 109 | 109 | 31 / 78 | 0 | -21.58u |
| Probability-first V1 | 5 | 5 | 1 / 4 | 0 | -1.25u |
| Accuracy-first V1, sākotnējais 1.30 | 27 | 14 | 9 / 5 | 13 | -1.52u |
| Accuracy-first V2, bez minimuma | 18 | 0 | — | 18 | 0 settled |
| Accuracy-first V3, atjaunotais 1.30 | 3 | 0 | — | 3 | 0 settled |

V1 sākās Oct1. V2 publicētas Oct2 09:04–11:33; V3 12:02 Riga. Nulle settled nenozīmē breakeven.

## 9. Kvalitātes audita secinājumi — nākamā darba pamatojums

Vecā ensemble 109 settled SINGLE: hit rate 28.44%, ROI -19.80%, mean estimated probability 48.78%. Uz **tiem pašiem 109 tickets** Brier bija **model 0.23444269 pret current-market 0.18248059**; zemāks ir labāk. Šī selected forward sample liek prioritizēt calibration un model-market disagreement diagnostiku. Tā nav jauna holdout vai pierādījums, ka champion drīkst nomainīt.

128 settled ar frozen probabilities: mean p 50.72%, faktiskie wins 32.03%, Brier 0.23608997, log loss 0.66440634, ECE 0.19025164; paired market Brier 0.18986040. Trīs legacy tickets bez probability izslēgti tikai no probability metrics, nevis finanšu statistikas. 131 settlements aptver 121 fixtures, tāpēc visi rows nav neatkarīgi.

Positive EV:114 settled, 32 W / 82 L, -22.83u. Negative EV:14 settled, 9 W / 5 L, -1.52u. **Visi 14 negative-EV ir accuracy V1 market-only cohort**, model p == market p. Nav korekti secināt, ka negative EV ir labāks: salīdzināti atšķirīgi politiku/laika/market cohorts. Atsevišķs jaunās politikas positive-vs-negative salīdzinājums vēl nav pietiekams.

162 modern SINGLE ir `UNCALIBRATED_LAB_ENSEMBLE`, confidence LOW; confidence lauks šajā sample nediferencē grupas. Tas nenozīmē, ka ir pierādīta calibration. Neizdomāt artefaktu vai eligibility PASS, nepārdēvēt blending par pilnvērtīgu calibration. Ja atklājas konflikts ar veco vispārīgo “LOW never publish” dokumenta tekstu, nereformēt esošo autorizēto Lab politiku klusām — šeit dokumentēta faktiskā eksperimentālā uzvedība, nevis jauna exception autorizācija.

Svarīgākie segmenti:

- Pooled HOME_WIN 1/13,-10.90u; OVER 2.5 5/16,-8.04u. AWAY 5/17,+4.62u; DRAW 12/44,-0.04u. Tie pārsvarā ir vecās politikas, nevis pamats tūlītējiem whitelist/blacklist.
- AccuracyV1: OVER 1.5 4/5,+0.58u; OVER 2.5 2/5,-2.27u; UNDER 3.5 2/3,-0.18u; BTTS_NO 1/1,+0.35u. Mazs sample.
- Odds 2–<3: 3 W / 22 settled,-14.81u. Tas nav atļauja ieviest augšējo odds cap. Vecie zem 1.30 trīs wins arī nav pamats atcelt lietotāja minimumu.
- Visi 20 resolved ar ≥20 pp model-market disagreement ir vecais ensemble:2 W / 18 L,-14.40u. ≥30 pp seši visi LOST. Tie nav jaunā quality gate pārkāpumi.
- 73 līgas; tikai divām ≥10 settled. UEFA Nations League 10/26,+5.55u; AFCON Qualification 1/10,-6.20u. Nav pietiekama league-policy evidence.
- Lead time 10–25 min: 8/24,-6.27u;25–45 min: 14/47,-8.32u;45–90 min: 16/52,-8.84u;90+ min: 3/8,-3.92u un 32 pending;0–10 min nav sample.
- Provider quote age atlases brīdī 1–4h: 114 settled, 38 W / 76 L,-15.56u;30–60 min: 3/14,-8.79u. Age pats par sevi nepierāda freshness pārkāpumu; kohortas nevienmērīgas, threshold nemainīt.
- Vecie COMBO 19 settled, 1 W / 18 L,-5.572924u. Accuracy COMBO 34 published, 4 settled, 1 W / 3 L,-1.0159u,30 pending; divi no četriem ir early financial losses. **Maturity bias:** garantēts zaudējums kļūst zināms pirms iespējamie winners pabeidz visas legs. Grāmatvedība ir pareiza, bet nepabeigta cohort settled-only ROI nav godīgs predictive-quality rangs.

Audits neatrada konkrētu jaunu app bug, kura dēļ vajadzētu mainīt sliekšņus. Nekāda model promotion vai training netika veikta. Nākamais pamatotais darbs ir de-vig research un īsta calibration readiness, nevis tūlītēja izvēles politikas pārrakstīšana.

## 10. Apvienotais AI/ML plāns — visi desmit posmi

### 1. INVALID_MODEL_PROBABILITY root cause

Izpētīti **63 incidenti 20 fixtures**. Avots bija provider raw **0%**, kas nonāca Decimal attēlojumā `0E+1`; tas nebija serialization bugs. Saglabāta rejection un provenance, bez clamp. PASS attiecas uz izpētītajiem incidentiem, nevis garantiju par jebkuru nākotnes zero.

Turpmāk incidentam vajadzīga fixture, market, producer, raw/transformed/ensemble probability, provenance, independence group, missing/context inputs, calibration artefact/generation, precīzs solis, kur radās0. Ja konkrēts jauns math/serialization bugs, labot ar regression test, neslēpt cēloni.

### 2. Dataset readiness un nākamais reālais research mēģinājums

Preflight implementēts un iekļauts quality release: TRAIN readiness, vismaz 30 VALIDATION, vismaz 100 fresh SEALED_HOLDOUT, precīzi TRAIN/VALIDATION/HOLDOUT/PURGED counts, `RESEARCH_DATASET_NOT_READY`. Nav atļauts trenēt challenger vai patērēt cycle/holdout, ja dati nav gatavi. COMBO/COMBO_LEG izolēti.

Pēdējais auditētais dabiskais research **Oct2 05:12 Riga**: **TRAIN 626 / VALIDATION 3 / SEALED_HOLDOUT 313 / PURGED 984**. Dati BLOCKED. Tajā mēģinājumā bija arī `CYCLE_COOLDOWN`; tāpēc reāls training-due ceļš, kur gatavības guards vienīgais aptur darbu, vēl ir nākamais forward pierādījums. Nedrīkst apgalvot, ka vecais VALIDATION=0 risks runtime visos zaros jau pilnībā pierādīts tikai ar cooldown mēģinājumu.

Read-only replay fingerprint `341b842716d2dbbd3a848d4908070dfcf9f241ebba1000740b23c0631387436c`. 24h embargo, disjoint fixture groups, label availability un holdout consumption pārbaudes. Counts var krist, pārbīdoties chronology robežām; vecie 28 vai10 VALIDATION ir citi datu griezumi, nevis tagadējā garantija. Turpināt resolved observations; neņemt datus no TRAIN/holdout, lai mākslīgi aizpildītu validation.

### 3. Vienots performance snapshot

Implementēts, deployed un dabiskajā observer verificēts. SINGLE settled/W/L/VOID/pending/hit rate/flatP&L/ROI/average/median odds. COMBO settled/W/L/VOID/partialvoid/pending/P&L/ROI/averagecombinedodds. Atsevišķi odds, probability, market, league, lead-time, confidence un disagreement segmenti, arī negative-EV. Lab-only, atsevišķi noOfficial.

Saglabāt pilnu persisted evidence, bet ierobežotu stdout. Vecais pilnais 168KB observer output pārsniedza ADMIN 131072B robežu un radīja false missing-output. Compact stdout pārbaudīts arī20k segments gadījumā ar <8192B mērķi. Jauni research metrics nedrīkst atgriezt log spam vai izgriezt pilno datu auditu no persistence.

### 4. Accuracy-first quality policy audits

Esošie guards un tests pievienoti/integrēti; natural publication ceļš pierādīts. Jāturpina forward segments, nevis threshold tuning uz maza sample. Pārbaudāmais saraksts: non-positiveEV eligibility, probability 0.55 dominance, model-market contradiction, signal independence, staleodds/context, calibration eligibility, extreme probability, missingfeatures, league/data quality, duplicatefixture/marketexposure, combo correlation. SINGLE 1.30 jaunākais operatora noteikums paliek.

### 5. Lead-time un odds-age

Implementēti `prematch_lead_minutes`, `prematch_lead_minutes_bucket`, `odds_age_seconds`, `odds_age_seconds_bucket`. Lead buckets0–10, 10–25, 25–45, 45–90, 90+. Mērīt Brier/logloss/ECE/hitrate/flatROI/disagreement/no-pickreasons/invalid-stalerate. Tikai diagnostika; automātiski nepārbīdīt publication laiku.

### 6. Current-odds de-vig comparator — NĀKAMAIS IMPLEMENTĀCIJAS POSMS

Research branch jau ir math/contracts un sākotnējā offline integration. **Aktuālajā source worktree `app/adaptive_lab/devig_research.py` NAV, runner tajā nav devig bindings** — tas pārbaudīts tieši nodošanas gatavošanā. Šis darbs nav jau deployots.

Avots research HEAD 938402a satur sākotnējo 2b1319e un vēlākos fb52837 provenance labojumus. Nepārnest tikai pirmo commit, ignorējot vēlākos labojumus.

Precīzie avoti:

- `app/adaptive_lab/devig_research.py`
- `app/lab_v2_shadow/runner.py` ap 589–598 research branch (capture un repository.append)
- `tests/adaptive_lab/test_devig_research.py`
- `docs/operations/DEVIG_RESEARCH_20261001.md`

API: `VERSION = CURRENT_ODDS_DEVIG_RESEARCH_V1`, `METHODS = (MULTIPLICATIVE, SHIN, POWER, OO_EPC)`, `devig(odds)`, `capture(consensus, captured_at=..., kickoff=..., model_probabilities=...)`, `forward_metrics(captures, results, now=...)`.

Research dokumentētā uzvedība:

- Decimal multiplicative baseline;
- bounded numerical Shin root; underround skaidri inapplicable;
- Power bracketed normalization root;
- OO-EPC Algorithm 5, ar skaidri ierakstītu `FALLBACK_MULTIPLICATIVE` un `OO_EPC_NONPOSITIVE_OUTCOME`, ja adjusted outcome nav pozitīvs; nekāds silent clamp;
- pilns divu/trīs mutually-exclusive outcome market no viena bookmaker, fixture, quote timestamps/fingerprints;
- capture noraida stale, postkickoff, incomplete, duplicate un mismatched evidence;
- atsevišķs `devig_research` sibling pēc candidate selection, frozen modelp reference disagreement metrics; selection baseline nemainās;
- forwardmetrics ņem pirmo capture pa fixture/bookmaker/marketfamily un tikai vēlāk pieejamos resolved scores; atkārtoti cikli nav papildu samples;
- Brier, logloss, ECE, favourite/otherbias, differencesfrommultiplicative un model-marketdisagreement;
- bookmaker samples ir korelēti un nav jauni neatkarīgi model-learning observations.

Sākotnējais documented test kopums: 74 focused de-vig/runner tests PASS. Tas ir vecās research implementācijas tests, nevis jaunās integrācijas garantija; jātestē jaunais konkrētais pamats.

Math avotu norādes esošajā repo dokumentā: `https://www.sciencepublishinggroup.com/article/10.11648/j.ajss.20170506.12` un `https://arxiv.org/html/2604.17194v1` (Algorithms 2, 4, 5). Ja nepieciešams no jauna pārbaudīt publikāciju saturu vai algoritma pareizību, lasīt primāros avotus; šī nodošana tos no jauna nav verificējusi. Nav izmantots historical-odds dataset vai FL-GLM fitting.

### 7. Pilnvērtīga probability calibration foundation

Foundation implementēta quality source/deployment: rawTRAINmodel → atsevišķa calibration-fit partition → vēlāka VALIDATIONevaluation → untouchedSEALED_HOLDOUT, chronology un 24h embargo. Platt/sigmoid, temperature kurpiemērojams, isotonic tikai pietiekamam sample; calibration artefactprovenance, ECE/MCE/Brier/logloss/reliabilitybins/extremechecks/degradationgate. NeizmantotTRAINpartitioncalibration. Blending nav calibration.

Offline sintētiskā pilnā ķēde pārbaudīta, bet reālu datu readiness **BLOCKED**. Vienā agrākā Oct1 projekcijā bija0 CALIBRATION_FIT / 6 VALIDATION_EVALUATION / 22 CALIBRATION_PURGED; tas ir vēsturisks moments, nevis šodienas aktuāls projection. Pirms reāla training vajadzīga svaiga projection un pilna readiness, nevis manuāla mēģinājuma piespiešana.

### 8. xG → goal-distribution shadow

Kods sagatavots research branch, nav publication integrācijas. Svaigs īsts recent/venuexG, homeawaycontext, attackdefencestrength; Poisson goal distribution rada1X2/totals/BTTS, salīdzināms ar champion. Mērīt Brier/logloss/calibration/disagreement/incremental information.

Reāli ievaddati **BLOCKED**: vēsturiskajā auditā 423 CMI snapshots, jaunākais Sept15, jaunākajos 25 nav xG. Provider goal bounds vai izdomāti features nav xG aizstājējs. Nebūvēt “xG modeli” no nederīga proxy klusām.

### 9. Dynamic team-strength / Glicko shadow

Research code sagatavots: Glicko-2rating/RD/volatility, homeadvantage, recency/uncertainty, atsevišķs eksperimentāls drawlink. Tikai neatkarīgs shadow signal, salīdzinājums ar champion/xG/currentmarket. Currentcontextprobe:1650 upcoming fixtures,562 predictions,768 insufficient history,320 cache unavailable. Pilni forward captureinputs/fingerprints saglabāti. Šie skaitļi ir iepriekšējā probe, nevis tagadējās dienas fixturecounts. Predictivequality **NEEDS_MORE_EVIDENCE**; zemāka prioritāte nekā calibration.

Research faili: `dynamic_strength.py`, `shadow_cli.py`, `shadow_inputs.py`, `shadow_research.py` zem `app/adaptive_lab`; `tests/adaptive_lab/test_context_shadow_research.py`; `docs/operations/CONTEXT_SHADOW_RESEARCH_20261001.md`.

### 10. Champion / challenger / promotion

Pašreizējo champion saglabāt. Audita generation:

`generation-aa7e535b86267741aabc967e8044de2ab94a4334b1520a829414dd55ebc7371a`

Fingerprint:

`56498b2c53657b8ad66a016c91a91a51b6dd640a5d364d2f615171775188fe11`

Pēdējā auditā 3 learning cycles un 0 holdout results, bez jauna trainingactivation pēc qualitydeployment. Tas nav dzīvs counter.

Obligātā secība: datasetreadinessPASS → challengertraining → VALIDATIONevidence → calibrationqualityPASS → untouchedSEALED_HOLDOUT → champion-vs-challengercomparison → shadowevaluation → stability/degradationchecks → explicitrecommendation → konkrētai rekomendācijai piesaistīts manuālsapproval. Rollback. Nekāda autopromotion. Foundation aizvieto automātisku activation ar read-only rekomendāciju; nepareiza/stale/citasrekomendācijas atļauja nedrīkst mainīt champion.

## 11. Konkrēts darba plāns jaunajam čatam

1. Izlasīt šo dokumentu un repo instructions, pārbaudīt source status un read-only faktiskās četras PREMATCH routes/flags/ADMINdisabled. Svaigs stāvoklis var būt mainījies; neuzskatīt vecās sourcepath konstantes par pašreizējo patiesību bez readback.
2. Izveidot izolētu implementācijas worktree no aktuālā reviewedsource. Salīdzināt devigmodule un researchrunner fragmentus ar pašreizējo runner. Pārnest nepieciešamo math/provenance foundation, nezaudējot today/CPU/floor/settlement/boundedstdout integrāciju.
3. Same CURRENT quotes, ko scheduleddiscovery jau saņēmis; nekādu papildu providerrequests, ciklu vai budgetincrease. Pilns marketoutcomeset, bookmaker/fixture/line/timestamp/fingerprintbinding. Nejaukt atšķirīgas totalslines, bookmakerus vai dažādos laikos nesaderīgi paņemtus outcomes.
4. Atsevišķa immutable/append-only researchevidence ar methodversion, provenance, quoteFP, cutoff un modelreference. Skaidri UNAVAILABLE/INVALID/inapplicable/fallbackreasons. Deterministic replay/idempotence. Nepārrēķināt vēsturisku capture, pievienojot nākotnesdatus.
5. Research kļūda nedrīkst klusām pārslēgt selectionmetodi vai bloķēt veselīgu publication ceļu ar jaunu research-only exception. Vienlaikus neslēpt esošas pamatdatu quality kļūdas. Saglabāt fail-closed pārbaudes to paredzētajā publication robežā.
6. Forwardevaluation pieslēgt esošajai resolvedevidence bez manuālaresultfetch. Paired comparableevents un samplecounts; atkārtoti cycles, vairāki bookmakersonsamefixture un correlatedoutcomes nav neatkarīgu modelobservations pavairošana. COMBO izslēgti.
7. Persistēt fairprobabilities visām metodēm, Brier/logloss/ECE/reliability/favourite-longshotbias/model-marketdisagreement; atklāti missing/pending/invalid/staleN. Nepārliecināt ar tikai selektīvu winnerssample. Adekvāts N un chronology nepieciešami secinājumam, nevis clocktime.
8. Saglabāt segmentāciju pēc policy/market, salīdzināt uz vienādiem resolvedevents; pašreizējie 14 V1 vai 4 COMBO nav pietiekamsjaunasmetodessuperioritypierādījums.
9. Focusedoffline testi ar fakeproviders/transports un bloķētu network: mathboundaries/normalizations, zero/nonfinite/invalid/incompletequotes, stale/future/postkickoff, marketidentity/line/bookmaker mismatch, provenance, replay/dedup, resultsavailableatcutoff, researchfailureisolation, unchangedSINGLE/COMBOoutputs, unchangedAPIcallcount, boundedstdout. Paplašināt suites tikai konkrēta riska vai repo gate dēļ.
10. Changedfiles/tests/evidence/commit un statuss. Ja operatorrelease nepieciešams, sagatavot precīzi pret aktuālo base un ar saderīgu rollback; **nepalaist apply**. Īsa Termius komanda tikai jau sagatavotai un pārbaudītai pakotnei. Pēc atsevišķa operatorapply — readback un dabisko ciklu audit, bez testmessages/manualcycles.

Paralēli nākotnes pierādījumiem jāseko V2/V3 settledcohorts, abu earlylosscombo atlikušajām legs, Dayrout reschedule rezultātam un nākamajam naturalresearchattempt. Nesākt treniņu tikai tāpēc, ka ir pagājis noteikts laiks. User agrākie “ir jau12:26/kadvaram” nav iemesls solīt datareadiness uz konkrētu stundu.

## 12. ADMIN incidentu konteksts, lai to neatvērtu no jauna bez iemesla

Sākotnēji bija `MONITORING_COVERAGE_DEGRADED`, `WORKER_INTERRUPTED`, `CODEX_FAILED`, unavailable/rotated stdout. Operatora saved diagnostics:

- `/home/arvis/goalvision-operations/admin-diagnostic-20261001-I9hDdv.json`
- stdoutreadback bytes 37111, 17 records,reason`ROTATED_INODE_LOST`.
- CPUdiagnostic `/home/arvis/goalvision-operations/discovery-cpu-20261001-Zfd0vi.txt`.

I/O startup `0a3e42a`, workerclone `eebed21` izmaiņas tika izvietotas. Vēlāk lietotājs nepārprotami pieprasīja izslēgt ADMINCodex, jo tas tērē limitu un nelabo; izslēgšana apstiprināta ar `ADMIN_CODEX_DISABLED` un readbackautorepair_enabledfalse,historypreservedtrue,monitorunchanged,workerPID0,inactive,disabledtimer.

Vecais `admin-alert-fix.py` atteicās ar `PREMATCH_ROUTE_CHANGED`, jo guard salīdzināja arī systemctlExecStart runtimePID/timestamps, kas pēc daemonreload resetojas. Patiesie configuredargv nemainījās. Transakcija atjaunoja ADMINdropins; PREMATCHroute nebija mainīts. Labojums salīdzina configuredexecutable/argv/ignore_errors un vēl aizvien noraida īstu route drift.

Atsevišķā monitor-only `a28f2a6` pakotne tika izvietota, worker neiedarbinot. Journal--all, boundedhealthprojection un researchoutputcontract compatibility.64 focused tests PASS. Pēdējā apstiprinātā operatorreceipt diagnostika: **160 ziņas = 80 ADMIN + 80 Auto-Repair status messages**, nevis 160 neatkarīgas app kļūmes; deliveryRECOVERED/HEALTHY. Atsevišķi historicalfalseincidents recover tikai ar exactinvocationproof, līdz 2 per scan; līdz ar to īslaicīgi recovery paziņojumi nav jaunas kļūmes. Neizdzēst incident/job/receipt history, neretryoldjobs, neatjaunotworker.

## 13. Read-only datu audita tehniskās robežas

Production SQLite avoti:

| DB | Galvenais saturs |
|---|---|
| `/home/arvis/GoalVisionAI/var/lab_combo/ledger.db` | `evidence(kind,identity,fingerprint,document)`, append-only publiskā prediction/settlement/receipt evidence |
| `/home/arvis/GoalVisionAI/var/lab_v2/shadow.db` | `lab_v2_shadow_evidence(kind,identity,created_at_utc,content_fingerprint,document_json)` |
| `/home/arvis/GoalVisionAI/var/adaptive_lab/audit.db` | `observer_runs`, `cycle_health`; id/stream/created_at/fingerprint/document |

Atvērt ar `sqlite3.connect('file:/absolute/path?mode=ro', uri=True)`, savākt nepieciešamo boundedconsistent snapshot un drīz aizvērt savienojumu, pirms smagiem aprēķiniem. Neveidot garu readtransaction, kas atkal tur ledgerlocks.

**Neinstancēt `ComboRepository` uz production DB tikai lasīšanai**: konstruktors var radīt schema/triggers. Observer/researchCLI ir operacionāli mutējoši, pat ja karogam nosaukums “full-performance”; tie nav read-onlyinspection aizstājējs.

Ledger kinds: `single_prediction`, COMBO `prediction`, `single_settlement`, COMBO `settlement`, `leg_result`, `combo_result_detail`, `settlement_diagnostic`, `run`. Receipt identity sasaistes: `single_prediction:ID`, `combo_prediction:ID`, `single_settlement:ID`, `combo_settlement:ID`. Precīzu schema pārbaudīt pirms query, neizdomāt tabulas.

Shadow `publication_cycle` satur publicationfields, nevis automātiski visus discoverycounts. Pilnajam healthaudit jālasa īstais evidencekind. CanonicalJSON fingerprint: sortkeys, separators(',',':'), ensure_ascii=False, SHA256; nepieļaut nonfinite datu normalizēšanu klusām.

Systemctlshow/read ir read-only; service/timerstop/start/restart ir mutations un šajā handoff vai parastā audita solī nav vajadzīgi. VPS protecteddata pieejamība var būt ierobežota; rootonlydiagnostic veic operators ar īso sagatavoto skriptu, nevis apejot piekļuveskontroli.

## 14. Testi un Git pierādījumi, kas jau ir

Test counts pārklājas — tos nesummēt par vienu neatkarīgu suite:

- qualityintegration:1475 tests + 34 subtests;
- settlement:206 offline tests;
- SINGLEfloor:373 offline tests;
- settlement-compatiblefloorinstaller:126 offline tests;
- vecaisresearch/CPUbranch:1498 + 34 subtests; atsevišķiefocusedtests pārklājas;
- de-vig sākotnējaisfocusedresearch runner: 74;
- ADMIN monitor compat: 64.

Networkconnections testos bloķētas, providers/transportsfake. Jaunākie natural/qualityaudits bija read-onlyreconciliation un docscommits, nevis jaunsapplikācijaspatch. Nodošanas sagatavošanai nav jēgas atkārtot visu suite; jaunajai integrācijai savi meaningfultests ir vajadzīgi.

| Commit | Saturs |
|---|---|
| `df13f2c` | Observer avota snapshot/readlock atbrīvošana pirms metrics |
| `644d2ad` | Providerzero rootcause un regression |
| `7914a04` | Datasetreadiness, COMBOlearningisolation |
| `ee16392` | Performance/timing |
| `7a70f48` | Vēsturiska no-floorpolicy/signal/fixtureguards; SINGLE no-floor tagad superseded |
| `2b1319e` | De-vigresearchfoundation |
| `9cddccb` | Calibration/manualpromotionfoundation |
| `88acedb` | xG/dynamicshadowfoundation |
| `fb52837` | De-vigprovenance + cyclephase diagnostics; neaizmirst integrējot |
| `1a18dc0` | CPUcontextscopeindex |
| `938402a` | ResearchbranchHEAD: dabiskāCPUcikla evidence docs |
| `f5d7968` | TodayRigascope |
| `3ad346b` | Integrētaisqualityrelease |
| `04a075134b1c3d825bb3dbd029db77e20d3a6953` | EarlyCOMBOsettlement |
| `b62cf8002527975b500151c1fe65abc90f86d108` | Settlementpakotneschecksums/read-onlypreflightdocs |
| `d73359111532fb2bbf0bc2e2e3d6a94f465b3f29` | SINGLE 1.30implementation |
| `f7971d53ae21cb37a93f8798de7e67c25857710f` | Floorpakotnesvalidationdocs |
| `f81aa2c2c1aae4af8decaa9b454d182c82f74af8` | Floorinstaller pret reāliinstalētosettlement; aktīvaisruntimecodepin |
| `c7369eb` | Savietojamībastestudocs |
| `9b07c73` | Operatoradeploymentreadback |
| `207ccabf5bbd13f09b73e24a05a3cb9ba59fb662` | Naturalpublication/settlementaudit |
| `0b84eeedbe1ac73bdb957720e76f906d3c119a3e` | Segmentedqualityaudit, sourceHEAD pirms šīhandoff |

Nākamais source HEAD var būt jaunāks docscommit, kamēr runtime vēl ir f81aa2c. Šos divus nejaukt.

## 15. Dokumentu un evidence karte

Aktuālā source worktree `docs/operations`:

- `PREMATCH_SINGLE_FLOOR_DEPLOYED_20261002.md` — deployedflags/routes/timers;
- `PREMATCH_FLOOR_NATURAL_AUDIT_20261002.md` —12:00cycle,receipts,earlyloss,financialreconciliation,pendingreason;
- `PREMATCH_SEGMENTED_QUALITY_20261002.md` —12:50cohorts un qualityinterpretation;
- `PREMATCH_SINGLE_FLOOR_COMPAT_20261002.md` — installerbasefix; tā agrākais “activation pending” aizstāts ar deployed/naturalaudits;
- `PREMATCH_SINGLE_FLOOR_20261002.md` — floorcode untests, bet sākotnējā d733591pakotne superseded;
- `PREMATCH_SETTLEMENT_FIX_20261002.md`, `PREMATCH_SETTLEMENT_COMBO_AUDIT_20261002.md`;
- `PREMATCH_QUALITY_20261001.md`, `PREMATCH_QUALITY_NATURAL_CYCLES_20261002.md`;
- `PREMATCH_TODAY_SCOPE_20261001.md`, `CONTEXT_SCOPE_CPU_FIX_20261001.md`.

ADMIN source vēstures pārskati ir saglabāti arī handoff pielikumu kopijā: `ADMIN_CODEX_OFF_20261002.md`, `ADMIN_MONITOR_COMPAT_20261002.md`, `ADMIN_COMPAT_20261002.md`, `ADMIN_IO_STARTUP_20261001.md`, `ADMIN_WORKER_CLONE_20261001.md`. Vajadzības gadījumā meklēt konkrēto report pa VPSworktrees; nepieņemt, ka katrs ADMINdoc atrodas PREMATCHzarā.

Research worktree `docs/operations`: `FORWARD_AI_ML_STATUS_20261001.md`, `INVALID_PROBABILITY_ROOT_CAUSE_20261001.md`, `DATASET_READINESS_20261001.md`, `PERFORMANCE_TIMING_20261001.md`, `ACCURACY_POLICY_AUDIT_20261001.md`, `DEVIG_RESEARCH_20261001.md`, `CALIBRATION_AND_MANUAL_PROMOTION_20261001.md`, `CONTEXT_SHADOW_RESEARCH_20261001.md`, `FORWARD_STABILITY_20261001.md`.

**Vecais `FORWARD_AI_ML_STATUS_20261001.md` ir vēsturisks:** tā “onlyCPUdeployed”, “nofloor”, VALIDATION28 un vēlneizvietotiequalityguards vairs nav pašreizējais stāvoklis. Tas paliek noderīgs failu/commit/rootcause/researchkartēšanai, nevis aktuālādeploymentnoteikšanai.

Aktuālie machine-readable evidencefaili PREMATCHsourceworktree:

1. `docs/evidence/prematch_floor_natural_20261002/reconciliation.json`
   SHA256 `ac48b03aed99443ecab3ce3c6a88329617fcaa648a08cee2a148ad5450ba9e79`.
2. `docs/evidence/prematch_quality_segments_20261002/analysis.json`
   SHA256 `15f74061e312a1f909fd7dd98e7d650d5af7e54d4f9854392c30da811ff82aa8`.
   Satur normalized 165 SINGLE rows, 12 dimensions,policycrossgroups,COMBOgroups,confounders un constraints.
3. `docs/evidence/prematch_settlement_20261002/reconciliation.json` — iepriekšējaissettlementaudits.

Researchevidence zem `docs/evidence/forward_ai_ml_20261001`: `invalid_probability.json`, `dataset_readiness_projection.json`, `calibration_readiness_projection.json`, `performance_snapshot.json`, `accuracy_policy_audit.json`, `dynamic_strength_current_probe.json`, `dynamic_strength_forward_captures.json.gz`, `xg_input_readiness.json`, `test_summary.json`. Šiem datiem savi agrāki cutoff; nepasniegt tos kā jauno 12:50 snapshot.

## 16. Kas tieši vēl nav pabeigts

- De-vig integrācija aktuālajārelease un tās jaunie tests/evidence/operatorpackage — **nākamais apstiprinātais darbs**.
- Pietiekami resolvedV2/V3sample, adekvāts pairedcomparatorsample — **NEEDS_MORE_EVIDENCE**.
- Dataset/calibration readiness reālajiemdatiem — **BLOCKED** pēdējāprojection; nākamaistraining-duepreflightforwardproof vēl jāpārbauda.
- EarlyfinanciallossCOMBO pārējo legs finaldetail dabiskācompletion — nākotnes ciklievidence.
- Īsti svaigixGinputs — **BLOCKED**; dynamicstrength kvalitāte — **NEEDS_MORE_EVIDENCE**.
- Pilna challengercomparison/calibration/holdout/shadow/stability un manuālapromotion — nav autorizēta apvērstībā, nav veikta.

Nav uzdevums vēlreiz atjaunot nofloorSINGLE, atkal ieslēgtADMINCodex/LIVE, labotjauizvietotofloorinstaller, vai pārdeklarēt visus vecos taskunchecked kā vēlneizdarītus.

## 17. Jaunā čata sākuma teksts

Pievieno šo failu jaunajā čatā un ielīmē:

> Turpinām GoalVision AI. Vispirms pilnībā izlasi pievienoto GOALVISION_HANDOFF_20261002.md un repo instrukcijas. Nākamais apstiprinātais uzdevums: integrēt jau sagatavotos current-odds de-vig comparatorus research/shadow režīmā uz aktuālā PREMATCH pamata, ar offline testiem, evidence, Git commit un vajadzības gadījumā operatora pakotni. Pārbaudi faktisko VPS/source stāvokli. SINGLE >=1.30; COMBO bez minimuma; today-only Europe/Riga; early COMBO loss un remaining-leg tracking jāsaglabā. Official nemainīt, LIVE un ADMIN Codex paliek DISABLED. Nekādu historical bookmaker odds, manuālu provider/cycle/test Telegram izsaukumu, automātiska deploy vai champion promotion. Neatkārto jau pabeigtos darbus; turpini no handoff nākamā uzdevuma.

Ja pielikums nav pieejams, pilnais handoff ir VPS `/home/arvis/goalvision-operations/GOALVISION_HANDOFF_20261002.md`. Jaunajam čatam tas jāizlasa, nevis jāpaļaujas uz atmiņu par šo sarunu.
