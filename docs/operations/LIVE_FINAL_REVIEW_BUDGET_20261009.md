# LIVE gala pārbaudes budžeta labojums — 2026-10-09

## Rezultāts

**CODE/TESTS/PACKAGE: PASS. PRODUCTION: NOT_DEPLOYED.**

Izolētais branch `fix/live-final-review-budget-20261009`, source commit `a4cdfa1043ec69c2838794371ba0a57d4163f50d`.
Pārbaudes datu griezums: **21:09 Riga** (`2026-10-09T18:09:03.379063+00:00`).
Aktīvā release paliek `/opt/goalvision-live-probability-band-bfe6d40-20261009`.

## Kāpēc šovakar nebija LIVE ziņu

38 dabiskie cikli atrada 721 kandidātu versiju 28 spēlēs. 65 versijas bija 60–70% diapazonā;
64 versijas **20 spēlēs** izgāja sākotnējās pārbaudes. 26 ciklos tika izvēlēts kandidāts gala
pārbaudei, bet visi 26 beidzās `LIVE_FINAL_REFRESH_FAILED`. **Claims=0, publications=0.**
Tādēļ nav evidence par prognozes nosūtīšanas/receipt problēmu — process apstājās pirms claim.

13 cikli izlietoja 35, 12 cikli 36 un 13 cikli 37 API pieprasījumus. Sākotnējā meklēšana
varēja iztērēt visu lokālo cikla limitu un pēc tam mēģināt obligāto exact refresh. Pēdējā
saglabātajā quota claim daily remaining-before bija 1424 pret aizsargāto rezervi 756;
tas **nav dienas kvotas izsīkuma pierādījums**.

**Apstiprināts koda defekts:** nav budžeta, kas pasargā gala pārbaudi no sākotnējā scan.
Tas reproducēts ar īsto FootballClient pieprasījumu skaitīšanu un fake HTTP pie visiem
trim šovakar novērotajiem limitiem. Vecie journal ieraksti nesaglabāja izņēmuma tipu,
tādēļ nevar godīgi apgalvot, ka katram no 26 vēsturiskajiem gadījumiem tips ir individuāli
pierādīts. Labojums papildus saglabā atsevišķu, sanitizētu failure reason.

656 kandidātu versijas bija ārpus diapazona; 27 bija severe model-market contradiction,
5 suspended market, 2 probability/odds contract kļūmes. Iemesli pārklājas. Šie atlases
nosacījumi netika mīkstināti. Quote-age veto netika atjaunots.

## Labojums

- Sākotnējā scan atstāj **9 HTTP mēģinājumus** vienai gala fixture/events/odds pārbaudei,
  ieskaitot esošos līdz trim mēģinājumiem katram endpoint.
- Nosacījums darbojas pirms katra HTTP mēģinājuma un retry. Tas nepatērē papildu shared slot.
- Saglabā jau sagatavotos kandidātus un apstājas, pirms iztērēta rezerve. Limits tiek noņemts
  tikai scan fāzei; kopējais cikla limits, shared 7500/day, 300/min un PREMATCH settlement
  rezerve paliek spēkā.
- Statusā ir cycle/scan ceilings un konkrēts gala kļūmes reason. Exception teksts/credentials
  netiek ierakstīti.
- Var tikt sākotnēji pārbaudīts mazāk spēļu, taču saglabātajam kandidātam paliek budžets
  obligātajai gala pārbaudei. Netiek forsēta izvēle vai izlaistas citas pārbaudes.

## Tirgu paplašinājums

Pievienota atsevišķa research matemātika **1X/X2/12, DNB, papildu totāliem un veselām/pusvārtu
Asian Handicap līnijām**. WON/LOST/VOID varbūtības ir atšķirtas. DNB EV rēķinās
`p_win*(odds-1)-p_loss`, saglabājot neizšķirta atmaksas varbūtību.

**Tas vēl nav ieslēgts bots.** Aktīvais saraksts joprojām ir 11 iznākumi. Šajā modulī nav
provider tirgu ID piesaistes vai publikācijas ceļa. Saglabātajos LIVE kandidātos jaunajiem
tirgiem nav nepieciešamo raw quotes, tādēļ cenu/ieguvumu nedrīkst izdomāt. Kartītes,
stūra sitieni, ceturtdaļu foras un correct-score publikācijas netiek pievienotas.
Research modulis **nav iekļauts šajā operatora labojuma paketē**.

## Pārbaudes un evidence

**793 PASS, 0 FAIL/ERROR**, 33 focused/adjacent faili, 41.02s. Nav visas repo testu kopas
apgalvojums. Testu tīkla transports aizliegts; visi provider un Telegram transporti fake.
Pārbaudīti 35/36/37 limiti pirms/pēc labojuma, retry rezerve, mazs budžets, 60–70 robežas,
EV-off, gala safety gates, duplicate/settlement/Reply/COMBO/calibration regressions un
operatora installer aizsargi. Tirgu testi sedz puses, līniju zīmes, DNB/handicap push,
precīzu masu, chronology/hash pārbaudes un bezcenu NO_EV.

Izolētais assembled release smoke: **576 moduļi PASS**. Vienāda base+overlay hash karte;
read-only preflight: **BASE / PASS**. Tikai trīs runtime faili paketē:
`app/adaptive_lab/worker.py`, `app/live_lab/runner.py`, `app/live_lab/service.py`.
Visi changed files, test command un fingerprints ir
`docs/evidence/live_final_review_budget_20261009/validation.json`.

## Operatora komandas

Pakete: `/home/arvis/goalvision-operations/live-final-review-budget-a4cdfa1-20261009`.

```bash
python3 ~/goalvision-operations/live-final-review-budget.py
sudo python3 ~/goalvision-operations/live-final-review-budget.py --apply
```

Pirmā komanda ir read-only. Otrā ir atsevišķa operatora uzstādīšana: briefly aptur/atjauno
tikai LIVE timeri, sagaida jau palaistā servisa beigas un pārslēdz LIVE immutable release.
Tā nesāk manuālu ciklu un nesūta testu. Pēc tam vērtēt nākamo dabisko ciklu; reāla publikācija
joprojām atkarīga no gala odds/state/market un pārējo esošo pārbaužu rezultāta.

## Saglabātais stāvoklis

Agent deployment **NONE**; iniciēti provider calls **0**; Telegram calls/sends **0**.
LIVE 18–23 timers/config, PREMATCH, COMBO, Official, champion, bankroll un staking nemainīti.
143 systemd failu hashes sakrīt. Galvenā checkout 220 iepriekšējās status rindas saglabātas.
Nekādi vēsturiskie W/L/VOID, kalibrācijas logi vai model-learning ieraksti nav pārrakstīti.
Faktiskā nākamā dabiskā cikla pārbaude pēc operatora deployment vēl ir PENDING.
