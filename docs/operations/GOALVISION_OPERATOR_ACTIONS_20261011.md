# GoalVision operatora atsevišķais plāns — 2026-10-11

**OPERATOR_APPROVAL_REQUIRED. Šīs production darbības nav izpildītas.**
Šis dokuments nav auto-installer. Šī Watch uzdevuma LIVE vēlamais stāvoklis ir DISABLED;
tas aizstāj agrāko vēlamā schedule norādi, bet neautorizē šajā auditā timeru maiņu.

## A. LIVE reserve: nekas nav jāinstalē

Uzstādīts `/opt/goalvision-live-quota-reader-3d4f5c5-20261010`.
Tas jau satur `a4cdfa1` final-review reserve labojumu. Neizmantot veco
`live-final-review-budget` installer virs šī successor. Neizpildīt worker smoke,
`--send`, Telegram testu vai provider /status.

Read-only preflight:

```bash
systemctl show goalvision-lab-live-evening.timer --property=LoadState,ActiveState,SubState,UnitFileState
systemctl show goalvision-lab-live-evening.service --property=ActiveState,SubState,Result,EnvironmentFiles
systemctl show goalvision-adaptive-learning-observer.service --property=EnvironmentFiles
systemctl show goalvision-lab-v2-discover.service --property=EnvironmentFiles
```

Faktiskie hashes ir `docs/evidence/calibration_live_recovery_resume_20261011/runtime.json`.
UnitFileState=enabled un ActiveState=active ir faktiskais LIVE stāvoklis;
vecais observer LIVE=DISABLED to neatspoguļo.

## B. Droša timer deaktivizācija — tikai pēc atsevišķas autorizācijas

Timeris arī pārbauda LIVE settlement ārpus 18:00–23:00 Riga. Apturot to,
nepabeigti rezultāti vairs netiks automātiski apkalpoti ar šo servisu.
At audita cutoff 25 publikācijas bija settled, un visām 25 bija result receipts.
Šis skaitlis jāapstiprina no jauna pirms izmaiņas.

Read-only pārbaude (drukā tikai skaitļus, ne receipt saturu):

```bash
python3 - <<'PY'
import sqlite3
from pathlib import Path
path = Path('/home/arvis/GoalVisionAI/var/adaptive_lab/audit.db')
db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.2)
db.execute('PRAGMA query_only=ON')
try:
    db.execute('BEGIN')
    tables = ('live_claims', 'live_publications', 'live_settlements',
              'live_result_claims', 'live_result_receipts')
    ids = {t: {r[0] for r in db.execute('SELECT id FROM ' + t)} for t in tables}
    failed_receipts = sum(db.execute(
        "SELECT count(*) FROM " + t +
        " WHERE json_extract(document,'$.status') IS NOT 'SENT'"
    ).fetchone()[0] for t in ('live_publications', 'live_result_receipts'))
finally:
    db.close()
print({
    'pending': len(ids['live_publications'] - ids['live_settlements']),
    'publication_claims_without_receipt': len(ids['live_claims'] - ids['live_publications']),
    'settlements_without_result_receipt': len(ids['live_settlements'] - ids['live_result_receipts']),
    'result_claims_without_receipt': len(ids['live_result_claims'] - ids['live_result_receipts']),
    'non_sent_receipts': failed_receipts
})
PY
```

Deaktivizācijas priekšnosacījumi:
1. Atsevišķa operatora autorizācija un saglabāts šīs pārbaudes receipt.
2. Visi pieci skaitļi ir 0; esošā LIVE service nav running/activating.
3. Darbība notiek ārpus discovery loga; timezone ir Europe/Riga.
4. Read-only SQLite backup un tā hash saglabāti operatora privātajā glabātuvē.
5. Nemainās DB, model pointers, settlement, Official vai PREMATCH routes.

Ja ir pending vai neskaidra delivery, šis timer-only plāns ir BLOCKED:
vajadzīgs atsevišķi pārskatīts settlement-only operatora risinājums. Nekādu
forced VOID, datu dzēšanas, manuālu `live-cycle --send` vai klusu timer restartu.

Tikai pēc šo priekšnosacījumu izpildes operatoram paredzētās komandas:

```bash
sudo systemctl stop goalvision-lab-live-evening.timer
systemctl show goalvision-lab-live-evening.service --property=ActiveState,SubState
sudo systemctl disable goalvision-lab-live-evening.timer
systemctl show goalvision-lab-live-evening.timer --property=ActiveState,UnitFileState
```

Ja starp pārbaudēm service sācis darboties, to nenogalināt: sagaidīt dabisku
beigšanos, atkārtoti pārbaudīt pending/receipts un tikai tad pabeigt plānu.
Sagaidāmais gala stāvoklis: timer inactive + disabled. Vecie immutable audit un
settlement ieraksti paliek. Nav automatic rollback vai automātiskas atkārtotas
ieslēgšanas. PREMATCH un COMBO settlement timeri paliek ārpus šī scope.

## C. Calendar reader un health diagnostikas successor

**SMALL_GITHUB_FIX — source gatavs; production deploy nav veikts.**

Precīzs atļautais iespējamā successor overlay:
- `app/adaptive_lab/calendar_audit.py` no `07775d7`;
- `app/adaptive_lab/health.py` un `observer.py`: esošais `03ea4b9` fix,
  saglabāts branch `research/calibration-live-recovery-20261010`.

Pret abiem faktiskajiem installed applications sagatavotas privātas izolētas
kopijas. Tām mainīti tikai šie trīs faili; import smoke iziet ar outbound network
bloķētu. Manifest: `docs/evidence/calibration_live_recovery_resume_20261011/operator_overlay_smoke.json`.
Šīs kopijas nav servisu PYTHONPATH un nav aktivētas.

Operatora vēlākas instalācijas secība:
1. Atsevišķi autorizēt tieši šo trīs failu diagnostikas/reader scope.
2. Pārbaudīt, ka base routes vēl ir auditā fiksētie `3d4f5c5` successors un
   to hashes nav mainīti. Ja ir drift — apstāties un pārskatīt jauno base.
3. Veidot atsevišķus jaunus immutable successors no attiecīgajiem LIVE un
   PREMATCH bases. Nepārkopēt visu research branch application: abu bases
   worker/daypart vēsture atšķiras.
4. Overlay tikai trīs manifestā norādītos failus. Atkārtot isolated imports un
   calendar/health testus. Neiekļaut calibration_fit, research adapter vai artifacts.
5. Pirms route maiņas saglabāt vecās references, pending/receipts, champion ID,
   timer stāvokļus un auditsnapshot. Nemainīt policy, kvotas, timer enabled/disabled
   stāvokli vai esošus release failus in-place.
6. Route maiņu veikt tikai ar atsevišķi autorizētu, pārskatītu release update.
   Šim auditam nav palaista vai izveidota automātiska apply darbība.
7. Pārbaudīt read-only health: evening timer faktiskā vērtība, Riga window atsevišķi,
   observer LIVE=NOT_EVALUATED ar PREMATCH_OBSERVER scope. Tas nav LIVE enable.
8. Vērot tikai jau autorizētus dabiskus PREMATCH/observer ciklus pie :08/:38,
   salīdzināt quota-contention incidentus un receipt uzskaiti. Neiedarbināt
   manuālus provider/Telegram ciklus. Ja LIVE deaktivizēts, to neieslēgt testēšanai.

Ja runtime kļūdas saglabājas, savākt lock-owner pierādījumus read-only;
nepalielināt limits/timeouts un nepārplānot timerus bez atsevišķa izvērtējuma.
Automātisks rollback nav paredzēts.

## D. Research turpinājums

Kalibrācijas artifact paliek fiksēts no 10. oktobra; jaunus fits pēc validation
sākuma nebackdatēt. VALIDATION pašlaik 0; holdout nav atvērts.
Pirms neatkarīga validācijas/holdout rezultāta — nav calibration activation vai
champion promotion.

LIVE V2: nepieciešamas daudzas neatkarīgas resolved fixtures ar pilnu as-of
state/events/quotes; red-card effects jāestimē, nevis jāpiešķir fiksēts procents.
COMBO quality-first turpina abstain bez validated joint evidence.
DC sešu metožu paired izlasē vajag vismaz septīto kickoff date un turpmāku
neatkarīgu incremental-information pārbaudi. Pašreizējais verdict saglabājas.

Neviena šī dokumenta production komanda audita laikā nav izpildīta.
