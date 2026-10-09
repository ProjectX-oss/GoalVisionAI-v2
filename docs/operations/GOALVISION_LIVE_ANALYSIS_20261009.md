# GoalVision AI — LIVE analīze, 2026-10-09

## Secinājums

**LIVE publicē, bet pašreizējā atlase nav augstas uzvaras varbūtības stratēģija.**
Darbībā esošais kods kārto kandidātus pēc nekalibrēta modeļa aprēķinātā EV.
Tas ļauj izvēlēties arī ļoti mazvarbūtīgus iznākumus. Zaudējumu uzskaite un
piegāde pārbaudītajā izlasē darbojas korekti. Atrastie modeļa ierobežojumi ir
konkrēti, taču 9 likmes / 7 atšķirīgas spēles nepierāda ilgtermiņa rezultātu.

Pārbaude: 2026-10-09 07:53:37 Europe/Riga.
Analīzes sākums: 2026-10-08 18:00 Riga; rezultāti iekļauti līdz pārbaudes laikam.
Visas publikācijas bija 8. oktobra vakara logā un pēc quote-age V2 ieviešanas.
Avots: VPS saglabātie immutable kandidāti, claims, receipts, settlement un systemd journal.
Nekādi papildu futbola provider vai Telegram pieprasījumi netika veikti.

## 1. Visas publicētās likmes

| Spēle | Min. / rezultāts | Likme | Koef. | Modelis | Beigu rezultāts | Iznākums |
|---|---|---|---:|---:|---|---|
| Holon Yermiyahu – Nordia Jerusalem | 60′ / 2:0 | Mazāk par 3.5 | 1.525 | 82.07% | 5:0 | LOST |
| Atlético Tucumán Res. – Talleres Córdoba Res. | 19′ / 0:0 | Viesu uzvara | 4 | 42.90% | 2:0 | LOST |
| Atlético Tucumán Res. – Talleres Córdoba Res. | 24′ / 0:0 | Mazāk par 1.5 | 2.25 | 57.87% | 2:0 | LOST |
| Atlético Tucumán Res. – Talleres Córdoba Res. | 39′ / 0:0 | Viesu uzvara | 5.5 | 36.72% | 2:0 | LOST |
| Hapoel Herzliya – Hapoel Mahane Yehuda | 79′ / 0:0 | Neizšķirts | 1.444 | 77.78% | 0:0 | WON |
| Belgrano Córdoba Res. – San Martín San Juan Res. | 49′ / 2:2 | Viesu uzvara | 7 | 17.85% | 3:2 | LOST |
| Txantrea – Cortes | 58′ / 0:0 | Viesu uzvara | 5 | 25.22% | 0:0 | LOST |
| Shamrock Rovers – Drogheda United | 27′ / 2:0 | Viesu uzvara | 51 | 5.99% | 3:1 | LOST |
| Flamengo U20 – Vasco da Gama U20 | 23′ / 0:0 | Mājinieku uzvara | 3.1 | 36.94% | 2:2 | LOST |

Regulārā spēles laika rezultāti izmantoti arī Flamengo U20–Vasco spēlei, kur
provider gala statuss ir PEN. Mājinieku uzvara pie 2:2 regulārajā laikā pareizi
uzskaitīta kā LOST; pēcspēles sitienu uzvarētājs šo tirgu nepārvērš par WON.

| Rādītājs | Rezultāts |
|---|---:|
| Publicētas / settled / pending | 9 / 9 / 0 |
| Atšķirīgas spēles | 7 |
| WON / LOST / VOID | 1 / 8 / 0 |
| Hit rate | 11.11% |
| Flat P/L, 1u par likmi | −7.556u |
| Flat ROI | −83.96% |
| Vidējais / mediānas koeficients | 8.9799 / 4.00 |
| Vidējā prognozētā varbūtība | 42.60% |
| Modelis: Brier / log loss | 0.179145 / 0.540302 |
| Modelis: ECE, 10 vienādi intervāli | 0.364211 |
| Calibration bias: predicted − observed | +31.48 procentpunkti |
| Likmes ar modeļa p < 50% | 6 no 9 |
| Prediction claims / receipts | 9 / 9 |
| Settlement / result receipts | 9 / 9 |

P/L ir hipotētiska uzskaite pēc orientējošās API-Football cenas, nevis pierādīts
izpildītu likmju ienesīgums. Nav zināms identificēts izpildošais bukmeikers.

**Klasifikācija: PASS uzskaitei; BLOCKED_NEEDS_MORE_EVIDENCE ilgtermiņa kvalitātei.**

## 2. Kāpēc tika izvēlētas šādas likmes

### A. EV prioritāte pieļauj ļoti zemu uzvaras varbūtību

`app/adaptive_lab/worker.py::live_cycle` vispirms atmet kandidātus ar blockers,
pēc tam kārto pēc `-expected_value` un vienā ciklā izvēlas ne vairāk par vienu.
LIVE nav PREMATCH privātās 70–80% varbūtības prasības. Šīs ir atsevišķas politikas.

Shamrock–Drogheda: 27. minūtē 2:0, viesu uzvara, odds 51.00.
Modelis deva p=0.059927, tādēļ EV = 0.059927×51−1 = ap +205.63%.
Šāds lielums atlases rangā ir pievilcīgs, lai gan pats modelis prognozē aptuveni
94% zaudējuma iespēju. Vienas šādas likmes zaudējums pats par sevi nav pierādījums
nepareizai 6% prognozei. Problēma ir nevalidēta EV un vēlamā produkta mērķa neatbilstība.

Absolūtais model–market ierobežojums ir 0.22. Šajā piemērā p−1/odds ir tikai
0.04032, tāpēc tas iziet pārbaudi, lai gan modeļa p ir ap trīsreiz lielāka par
raw 1/odds. Tas nav bojāts gate aprēķins; tā ir esošā noteikuma uzvedība.

**Klasifikācija: OPERATOR_APPROVAL_REQUIRED publikāciju politikas izmaiņai.**
Šajā darbā nav mainīts p minimums, odds robežas, EV rangs vai divergence slieksnis.

### B. Sarkanās kartītes neietekmē Poisson varbūtības

Atlético Tucumán Res.–Talleres Córdoba Res. viesiem bija saglabāta sarkanā kartīte
visās trijās publikācijās. Divreiz tika izvēlēta šīs komandas uzvara:
42.90% pie 4.00 un 36.72% pie 5.50. Trešā likme bija UNDER 1.5.

`remaining_goal_probabilities` kartītes vārtu intensitātē neizmanto.
Offline atkārtojumā kartīšu skaita nomaiņa uz nulli dod precīzi tās pašas
varbūtības. Tās tikai palielina fiksēto uncertainty no 0.07 uz 0.11.
Maksimālais atļautais uncertainty ir 0.12, tāpēc šis vienīgais pieaugums likmi
nebloķē. Tas nav empīriski novērtēts prognozes ticamības intervāls.

**Klasifikācija: LARGER_CODEX_TASK izolētai, as-of izpētei.**
Nedrīkst izdomāt kartīšu koeficientu. Piesardzīgs pagaidu red-card veto arī mainītu
publikāciju politiku un prasa atsevišķu operatora lēmumu.

### C. Trīs likmes vienā spēlē koncentrē risku

Tā pati Argentīnas spēle radīja 3 no 8 zaudējumiem. Divas AWAY_WIN likmes ir
viena un tā paša gala iznākuma atkārtota ekspozīcija, nevis neatkarīgi mēģinājumi.
Pašreizējais limits ir 3 selections uz fixture. Atkārtotā viesu uzvara tika
publicēta pēc 20 spēles minūtēm, cenai mainoties 4.00→5.50 (+37.5%); tas atbilst
esošajam 15 minūšu un 15% cenas kustības izņēmumam. UNDER 1.5 ir cita tirgus saime.
Precīzu prediction ID dubultpiegāžu nav.

**Klasifikācija: NO_CHANGE attiecībā uz programmas izpildi;
OPERATOR_APPROVAL_REQUIRED, ja maina fixture ekspozīcijas politiku.**

### D. Modeļa konteksts ir ļoti ierobežots

Visas 9 prognozes izmanto LIVE_POISSON_BASELINE_V1. Tas kombinē komandu gūto un
ielaisto vārtu vidējos no 5–10 derīgām FT spēlēm un reizina ar (90−minute)/90.
Pašreizējais rezultāts tiek pieskaitīts modelētajiem atlikušajiem vārtiem.

Visām 9 publikācijām `optional_features={}`. Nav izmantotu live xG, sitienu,
bīstamo uzbrukumu vai sastāva īpašību. Kartītes ir zināmas, bet neietekmē intensitāti.
Nav opponent-strength/competition normalization, venue-specific vai vecuma svaru.
Kompensācijas laiks formulā netiek pieskaitīts. Tas ir ierobežojums, ne pierādīts
katras atsevišķās zaudētās likmes cēlonis.

Vēstures pārbaude: nav atkārtotu fixture ID, pašreizējā spēle ir izslēgta un visi
izmantotie kickoff ir pirms prognozējamās spēles. Tomēr:
- Vienai Hapoel Mahane Yehuda izlasei vecākais ieraksts ir 730 dienas vecs.
- Shamrock/Drogheda un U20 piemēros sajauktas vairākas sacensības.
- Vecākie un jaunākie mači vidējā saņem vienādu svaru.
- PREMATCH kalibrācija automātiski neizlabo šo atsevišķo LIVE modeli.

**Klasifikācija: DATA_QUALITY_LIMITATION / BLOCKED_NEEDS_MORE_EVIDENCE.**

## 3. Svaigums un piegāde

Publicēto cenu vecums sūtīšanas brīdī: **13.07–33.74 s**.
Spēles stāvokļa vecums: **1.81–2.40 s**; notikumu stāvoklis: **1.03–1.23 s**.
Quote retrieval→send aizture ir daudz mazāka par provider cenas sākotnējo vecumu.

Deviņām publikācijām:
- Poisson varbūtība atkārtojas precīzi: absolūtā kļūda 0.
- Vārtu intensitātes no sasaldētās vēstures atkārtojas precīzi.
- Esošie readiness gates iziet arī vēlākajā receipt timestamp.
- WON/LOST precīzi atkārtojas no saglabātā regulārā laika rezultāta.
- Ir visi 9 rezultātu receipts; pēc settlement tie pienāca 0.40–52.64 sekundēs.

Receipt-time pārbaude ir stingrāka vēlākā diagnostika, ne izdomāts oriģinālais
claim-time audit event. Pilns raw gala rezultāta API payload šajā auditā nav
pieejams; tiek pārbaudīts saglabātais immutable rezultāts.

| Tikai fiksēto 9 publikāciju vecuma filtrs | Paliktu | W/L |
|---|---:|---:|
| ≤20 s | 2 | 0/2 |
| ≤30 s | 5 | 1/4 |
| ≤45 s | 9 | 1/8 |

Tas nav alternatīvas stratēģijas backtests: nav citu kandidātu pāratlases.
No tā nevar apgalvot, kāds būtu viss vakars ar citu age limitu. Taču abi zem
20 sekundēm publicētie piemēri arī zaudēja, ieskaitot odds 51.00.

**Klasifikācija: NO_CHANGE.** Faktiskais quote-age režīms paliek diagnostic-only.

## 4. Neizsūtītie kandidāti un API efektivitāte

60 discovery cikli; papildus 22 results-only un 85 idle cikli līdz cutoff.
1,351 fixture discovery parādīšanās / 286 fixture reviews nav unikālu spēļu skaits.
Saglabātas 448 kandidātu versijas no 29 atšķirīgām spēlēm.

| Politika | Kandidātu versijas | READY versijas |
|---|---:|---:|
| Vecā V1 ar 20 s limitu | 76 | 5 |
| Pašreizējā age-diagnostic V2 | 372 | 107 |

V2 blocker counts pārklājas:
- NON_POSITIVE_EV: 233;
- SEVERE_MODEL_MARKET_CONTRADICTION: 24;
- DUPLICATE_LIVE_OPPORTUNITY: 17;
- LIVE_FIXTURE_SELECTION_LIMIT: 12;
- PROBABILITY_OR_ODDS_CONTRACT: 11;
- LIVE_MARKET_SUSPENDED: 7.

Vecajā V1 28 versijām vienīgais saglabātais blocker bija stale odds. V2 vecums
vairs nav veto. 107 READY versijas nav 107 neatkarīgas vai garantēti publicējamas likmes.

Pipeline diagnostika:
- LIVE_STATE_QUOTE_MISMATCH: 220;
- UNSUPPORTED_LIVE_MARKET: 88;
- LIVE_FIXTURE_REVIEW_UNAVAILABLE: 5;
- final publication attempt: 13 refresh-quote-missing, 2 readiness-blocked,
  1 final-refresh-failed;
- 18 SENT ieraksti = 9 prognozes + 9 rezultāti, nevis 18 likmes.

1,816 provider calls izpildīja dabiskie timeri aplūkotajā periodā, ieskaitot
rezultātu pārbaudes. Aptuveni 201.8 zvani uz publicētu prognozi nav vienas likmes
tiešās izmaksas: skaits ietver visu discovery, noraidījumus un settlement.
Šī analīze veica **0** jaunus provider izsaukumus.

Pašlaik nav saglabāti HTTP request-start/end un abu nesakrītošo raw
state/quote payload laiki. Tāpēc 220 mismatch nevar godīgi sadalīt provider lag,
minūtes pārejas un mūsu pieprasījumu secības cēloņos. Atrasts mērīšanas trūkums;
precīzs mismatch producer šajā izlasē paliek neatrisināts.

**Klasifikācija: SMALL_GITHUB_FIX diagnostikas turpinājumam;
DATA_QUALITY_LIMITATION retrospektīvai HTTP analīzei.**
Ieteicamais nākamais šaurais darbs: esošajiem zvaniem pievienot sanitizētu laiku,
state/quote atšķirību un final-refresh exception reason uzskaiti. Bez jauniem
provider calls, bez credentials vai transporta payload publicēšanas. Runtime
pievienošana/deploy joprojām nav autorizēta.

## 5. Modeļa kvalitātes secinājumu robežas

Tajā pašā 9 likmju izlasē raw 1/odds Brier=0.109164 un log loss=0.366274,
salīdzinot ar modeļa 0.179145 un 0.540302; šajā mazajā izlasē modelis ir sliktāks.
Raw 1/odds satur nezināmu maržu. Tas nav de-vig market benchmark un nav
pierādījums ilgtermiņa market superiority.

Vidēji modelis deva 42.60%, faktiski uzvarēja 11.11%. Tas ir aprakstošs
pārliecības pārvērtējums šajā izlasē, ne pietiekams calibration fit.
Divas vienas spēles AWAY_WIN prognozes dala identisku outcome; tāpēc neatkarīga
9-Bernoulli testa vai parasta bootstrap pārliecības intervāla pielietošana būtu maldinoša.
CI un stratēģiju ranking nav izveidots.

Tikai viena DRAW likme uzvarēja; tas nav pamatojums pāriet uz neizšķirtiem.
Piecas AWAY_WIN zaudēja; tas nav pamatojums automātiski aizliegt viesu uzvaras.
Negatīvs ROI nav izmantots threshold tuning.

**Klasifikācija: BLOCKED_NEEDS_MORE_EVIDENCE.**

## 6. Izpildītais darbs un pārbaudes

- Jauns reproducējams read-only `operations/live-postmortem/audit.py`.
- JSON ietver visas 9 likmes, input/source fingerprints, exact Decimal P/L,
  per-fixture/market/league segmentos, varbūtību metrics, age counterfactual,
  history provenance, replay pārbaudes un pipeline kopsavilkumu.
- 9 jauni testi par as-of robežām, future settlement/receipt izslēgšanu,
  settlement provenance/conflict, dubultām publikācijām, Decimal P/L, VOID un
  probability boundary noraidījumiem.
- Ar blakus LIVE un research regresijām: **140 PASS, 7.26 s**.
- Tests izmanto fake/mock un liegtus outbound sockets.
- Vienāda cutoff atkārtojums deva identisku evidence failu.
- Seši model/selection/settlement avota faili SHA-256 precīzi sakrīt ar
  instalēto LIVE immutable release. Esošie `app/` faili šajā branch nav mainīti.

Source commit: `27f150e06a223f745dfd817122e082514581d9c9`.
Branch: `research/live-postmortem-20261009`.
Evidence fingerprint: `e4a30895a9296a37872a5da46193cfd2f9d4d839ecb66ab8fa507e3e8fda4091`.
Source fingerprint: `6e22d5b635beffe41ec267d8d7d580296111018cb76cb67dd19be97edf7ce100`.

Reproducēšana no šī branch worktree:

```bash
/home/arvis/GoalVisionAI/.venv/bin/python -I -B operations/live-postmortem/audit.py \
  --database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db \
  --since 2026-10-08T15:00:00+00:00 \
  --until 2026-10-09T04:53:37.027928+00:00 \
  --output /tmp/goalvision-live-postmortem-20261009.json

/home/arvis/GoalVisionAI/.venv/bin/python -I -B operations/live-combo-research/offline_tests.py \
  tests/adaptive_lab/test_live_postmortem.py \
  tests/adaptive_lab/test_live.py \
  tests/adaptive_lab/test_evening_live.py \
  tests/adaptive_lab/test_live_quote_age_policy.py \
  tests/test_live_combo_research.py
```

Journal saglabāšanas termiņš ietekmē vēlākas pilnā pipeline replay iespējas.
Publicētā JSON snapshot un tā fingerprints saglabā šīs pārbaudes evidence.

## 7. Runtime saglabāts

LIVE release: `/opt/goalvision-live-quote-age-42a441f-20261008`.
LIVE timer pirms/pēc: **enabled / active**; discovery 18:00–23:00 Riga.
Results darbs ārpus discovery loga saglabāts.
142 aizsargātu GoalVision systemd failu hash nav mainījies.
Sākotnējā checkout nepārskatītās izmaiņas saglabātas.

Deployment 0; restart 0; timer changes 0; provider calls 0;
Telegram calls/sends 0; champion activation 0; promotion/rollback 0;
Official mutations 0; bankroll/staking izmaiņas 0.
Tas ir Official darbību/routing neaizskaršanas apstiprinājums, ne pilns Official DB audits.

## 8. Ko darīt tālāk

1. **SMALL_GITHUB_FIX:** pabeigt pasīvo LIVE datu/laika un final-refresh kļūdu
   diagnostiku izolētā kodā. Tā nevar pati palielināt modeļa precizitāti, bet ļauj
   pierādīt, kur pazūd kandidāti un API budžets.
2. **OPERATOR_APPROVAL_REQUIRED:** pirms turpmākām LIVE selection izmaiņām
   skaidri definēt, vai produkts grib augstu hit rate vai nekalibrētas longshot
   value idejas. Sagatavot red-card un fixture ekspozīcijas politikas variantus
   review/offline režīmā; neaktivizēt no šīs vienas dienas rezultātiem.
3. **BLOCKED_NEEDS_MORE_EVIDENCE:** vākt pietiekami daudz neatkarīgu LIVE
   fixture outcomes ar as-of prognozēm. Tikai tad atsevišķi vērtēt LIVE
   calibration un salīdzinājumu ar pilnu current-market cenu kopu.
4. PREMATCH calibratoru vai COMBO pierādījumus nepārnest uz LIVE kā validētu
   kalibrāciju. Champion, PREMATCH/COMBO, Official un esošie timeri nav mainīti.
