# GoalVision AI — PREMATCH/Lab evidence handoff, 2026-10-06

**Rezultāts: prasītie observability/research labojumi sagatavoti un pārbaudīti; production nav deployots. Promotion: NOT_ELIGIBLE.**

Vienotais datu cutoff: **2026-10-06 12:42:27.795571 Europe/Riga** (`2026-10-06T09:42:27.795571+00:00`). Skaitļi attiecas uz šo cutoff, nevis vēlākiem dabiskajiem cikliem. Runtime logs aptver iepriekšējās 24 stundas; queue un odds analīze — astoņus jaunā release dabiskos ciklus 09:00–12:30 Riga; candidate analīze — pēdējos 12 completed rehearsal ciklus.

Implementation commit: **`c5fec8c52625e3fc2742265ad75fad82e59a3911`**. Branch: `audit/prematch-evidence-20261006`. Pilnā sanitizētā evidence ir `docs/evidence/prematch_evidence_20261006/`. Metodika un tikai read-only operatora komandas: `PREMATCH_EVIDENCE_METHODS_20261006.md`.

## CURRENT_STATE

**NO_CHANGE.** Operatora PREMATCH release ir `/opt/goalvision-prematch-final-review-queue-76d96c1-20261005`, source `76d96c1a374a35a2d8d7cd059d0363ac095be3eb`. Visi **852 application faili** sakrīt ar pinned manifestu. Read-only operatora preflight: `current_mode=ENABLED`, `ADMIN_CODEX_SYSTEMD_DISABLED=PASS`. Četri PREMATCH servisi izmanto šo release; aizsargātās weekly, ADMIN, agrākās COMBO un research komandas/routes ir saglabātas.

Darba bāze `6357a6996568731ff3c54a839aa50ac942fb25fe` un agrākais research/evidence branch `20be74f9e3197032567a092c0e88574c62293b7a` pārbaudīti arī GitHub remote. No agrākā reviewed branch pārņemti esošie read-only audit rīki un incremental comparator, nepārnesot nepārskatītu vēsturi. Sākotnējais `/home/arvis/GoalVisionAI` joprojām ir `fadd59d7…` ar **220 iepriekš pastāvējušām dirty takām**; tas nav tīrīts, mainīts vai pushots. Darbs ir izolētā worktree.

Champion paliek bootstrap:

- Generation `generation-aa7e535b86267741aabc967e8044de2ab94a4334b1520a829414dd55ebc7371a`.
- Family `EXISTING_PREMATCH_BASELINE_V1`.
- Registry `LAB_MODEL_REGISTRY_V1`; features `LAB_FROZEN_FEATURES_V1`; ensemble `LAB_V2_BROAD_COVERAGE_ENSEMBLE_V4`.
- Aktivācija `2026-09-18T19:53:42.075830+00:00`, reason `BOOTSTRAP`, iepriekšējas generation nav.
- Learning stage **CHALLENGER_RESEARCH**; 18 dienu pārklājums; automatic eligibility=false.

| Learning | Aktuālais skaits |
|---|---:|
| Total observations | 2 748 |
| Resolved eligible observations | 2 736 |
| Independent resolved fixtures | 1 030 |
| SINGLE source observations | 363 |
| SHADOW source observations | 2 373 |
| Legacy COMBO_LEG, izslēgti no neatkarīgā learning | 12 |

| Frozen calendar partition | Observations | Independent fixtures |
|---|---:|---:|
| TRAIN | 1 804 | 560 |
| CALIBRATION_FIT | **163** | **163** |
| VALIDATION_EVALUATION | 0 | 0 |
| SEALED_HOLDOUT | 0 | 0 |
| PURGED | 759 | 297 |
| EXCLUDED | 22 | 20 |

Dataset fingerprint `6069d8be9aa24a8cb783085f45c78078d5dfb4ff6278f2f03b7f8792f82fb0a8`. Canonical calendar partitioni nav jāsajauc ar evidence failā atsevišķi marķēto veco rolling projection. Starp četriem research partitioniem fixture pārklāšanās=0.

## AI_PERFORMANCE

**SMALL_GITHUB_FIX.** Papildināts esošais authoritative snapshot, ko izmanto PREMATCH status/why-no-picks, observer un cycle health: calibration bias, frozen data-quality segmenti, EV zīme un policy cohorts. Pilnie segmenti paliek evidence, kompaktais scheduled output ietver totals/bias un pilnā snapshot fingerprint. Jaunie lauki production parādīsies tikai pēc atsevišķas operatora release sagatavošanas/uzlikšanas.

Authoritative skaitīšana: tikai **SENT receipt**, viena hipotētiska vienība uz likmi. Average/median odds — publicētām likmēm. ROI denominator — visas settled likmes, ieskaitot VOID; hit rate — WON/(WON+LOST), izslēdzot partial VOID. Probability metrics — derīgi frozen SINGLE p un binary outcomes. Neapstiprināta piegāde netiek izlikta par apstiprinātu publikāciju.

| SINGLE | Visa saglabātā vēsture | Aktuālais ≥1.50 periods |
|---|---:|---:|
| Published | 389 | 140 |
| Settled | 366 | 118 |
| WON | 196 | 70 |
| LOST | 170 | 48 |
| VOID | 0 | 0 |
| Pending | 23 | 22 |
| Hit rate | 53.55% | 59.32% |
| Average odds | 2.344679 | 1.575429 |
| Median odds | 1.53 | 1.55 |
| Flat P/L | −37.61 | −6.97 |
| Flat ROI | −10.28% | −5.91% |
| Probability sample | 363 | 118 |
| Brier | 0.224320 | 0.241777 |
| Log loss | 0.639579 | 0.677240 |
| ECE | 0.078261 | 0.038015 |
| Calibration bias mean(p−y) | +0.070158 | +0.019870 |

Trīs legacy SINGLE trūkst frozen probability. Pozitīvs bias nozīmē pārvērtējumu. Šie ir aprakstoši raw ensemble rezultāti, ne pierādīta modeļa kalibrācija. Negatīvs ROI neizraisa threshold tuning.

| COMBO | Visa vēsture | DC agreement periods | Tirgus periods |
|---|---:|---:|---:|
| Published | 171 | 5 | 26 |
| Settled | 158 | 4 | 18 |
| WON | 61 | 2 | 5 |
| LOST | 97 | 2 | 13 |
| VOID / partial VOID | 0 / 0 | 0 / 0 | 0 / 0 |
| Pending | 13 | 1 | 8 |
| Flat P/L | −7.756958 | +2.955644 | −3.878929 |
| Flat ROI | −4.91% | +73.89% | −21.55% |

Visa COMBO vēstures average combined odds=**10.195883**, median=2.570944; vidējo spēcīgi ietekmē vecās politikas. Atsevišķo periodu pilnie odds un metric fields ir `performance.json`. DC periods ir tikai četras settled likmes; early loss un pending atšķirības neļauj salīdzināt atlases kvalitāti pēc šiem ROI.

**NO_CHANGE.** Privātā ≥1.70 / p70–80% līnija tiek skaitīta atsevišķi: **1 published, 1 settled, 1 WON, 0 LOST, 0 pending; odds 1.70; P/L +0.70**. BIT–Chengdu Rongcheng II, UNDER2.5, frozen p≈71.78%. Tā bija dabiska publikācija un settlement, ne šī darba test send. Viena uzvara nav kvalitātes pierādījums. Atsevišķa evidence: `private_performance.json`.

**NO_CHANGE.** Pilni SINGLE/COMBO segmenti pēc odds, p, tirgus, līgas, lead-time, odds age, disagreement, EV un frozen quality ir `performance.json`. Grupu salīdzinošs attēlojums ar ≥30 settled ir aprakstošs, ne statistiskas nozīmības tests.

**NO_CHANGE — model/market disagreement.** Pēdējie 12 cikli: **7 458 kandidātu ieraksti / 141 unikāla spēle**; severe contradiction=509, material signal disagreement=2 354, ensemble-market divergence=384. Iemesls vienā kandidātā skaitīts tikai vienreiz, bet spēle/tirgus atkārtojas ciklos.

| Tirgus | Candidate rows | Severe contradiction | Material disagreement |
|---|---:|---:|---:|
| HOME_WIN | 732 | 162 | 415 |
| DRAW | 732 | 150 | 582 |
| AWAY_WIN | 732 | 95 | 558 |
| BTTS_NO | 692 | 24 | 165 |
| BTTS_YES | 692 | 24 | 74 |

407/509 severe gadījumu ir 1X2. Augstākie league skaiti: UEFA Nations League 112/924, EFL Trophy 104/1089, UEFA U21 Qualification 82/715, League Two 64/411 kandidāti. No 384 divergence gadījumiem 262 ir DRAW. Tas pamato turpmāku diagnostiku šajos segmentos, ne threshold maiņu.

Freshness 0.5–1h: severe 27/716; 1–4h: 482/6742. Lielāks absolūtais vecāko datu skaits lielā mērā atspoguļo sample sadalījumu; cēloniska saistība nav pierādīta. Lead-time un p/odds segmenti ir evidence. Candidate timing aprēķins izmanto vēlāko no frozen cycle start un paša quote retrieval; tas ir skaidri marķēts evaluation-time tuvinājums.

## CALIBRATION_READINESS

**BLOCKED_NEEDS_MORE_EVIDENCE — NOT READY: 163/300 neatkarīgi piemēri.** Trūkst 137, un frozen CALIBRATION_FIT logs vēl ir atvērts līdz `2026-10-10T00:00:00Z` (03:00 Riga). Nākamā atļautā darbība ir dabiskā datu uzkrāšana. Fit tikai pēc esošo sample un loga slēgšanas nosacījumu izpildes.

Jauns fit, training vai calibration artifact **nav izveidots**. Esošo post-hoc calibration artifacts skaits=0. VALIDATION sākuma robeža ir 11.10. plkst. 03:00 Riga, SEALED_HOLDOUT — 19.10. plkst. 03:00 Riga; neviena nav izmantota fit. Esošie astoņi vēsturiskie CALIBRATED_ENSEMBLE modeļi nav jaunā frozen calibration procesa artefakti.

Kad gatavs, saglabājas plāns salīdzināt identity, Platt, temperature un tikai pietiekama sample gadījumā isotonic ar Brier/logloss/ECE/MCE/bins/bias/extremes un immutable generation/dataset/partition/time/schema provenance. Readiness nav mīkstināta.

## DIXON_COLES

**SMALL_GITHUB_FIX.** Papildināts jau reviewed comparator, ne DC algoritms. Sešas metodes vērtētas uz **vienām un tām pašām 9 atrisinātām spēlēm divos kickoff datumos**. 30 eligible 1X2 forecast families; pārējie resolved/pending un izslēgšanas skaiti ir `dixon_coles_paired.json`. Nelietots nekohērents champion vektors, nepieejams comparator vai cits fixture sample, lai aizpildītu tabulu.

| Metode | Brier (3 klašu summa) | Log loss | RPS | ECE |
|---|---:|---:|---:|---:|
| Champion | 0.601781 | 0.994813 | 0.176619 | 0.191196 |
| Multiplicative market | 0.700593 | 1.128149 | 0.211500 | 0.253751 |
| Shin | 0.707023 | 1.133630 | 0.213633 | 0.230191 |
| Power | 0.711104 | 1.138464 | 0.214685 | 0.232240 |
| OO-EPC | 0.712345 | 1.138003 | 0.215438 | 0.233484 |
| Dixon–Coles | 0.693128 | 1.126230 | 0.203468 | 0.171959 |

Paired deltas definētas kā DC−baseline; negatīvs ir labāk:

| Baseline | ΔBrier | ΔLog loss | ΔRPS | ΔECE |
|---|---:|---:|---:|---:|
| Champion | +0.091347 | +0.131417 | +0.026850 | −0.019236 |
| Multiplicative market | −0.007465 | −0.001919 | −0.008032 | −0.081792 |

**BLOCKED_NEEDS_MORE_EVIDENCE.** DC šajā mazajā paraugā ir sliktāks par champion un tikai nedaudz labāks par multiplicative market pēc proper scores. Stabils incremental contribution nav pierādīts. Confidence intervals netiek izlikti par ticamiem pie 9 spēlēm/2 datumiem; implementētais date-cluster bootstrap prasa ≥30/7. ECE ir nelineārs un katrā resample tiek pārrēķināts. League/competition/date/lead-time/partition sample un deltas ir saglabāti.

Optimālais forward DC weight=**nav novērtēts**, nevis 0. Fit logs atvērts, sample<300, nav unseen validation. Fiksētais 0.5 pool ir tikai diagnostika. Nav jauna dynamic attack/defence modeļa, DC aktivācijas, papildu publication integrācijas vai promotion. Esošā operatora agrāk autorizētā COMBO DC experiment līnija šajā uzdevumā nav mainīta.

## DATA_QUALITY

**NO_CHANGE — DATA_QUALITY_LIMITATION.** Pēdējā 12:30 Riga broad sweep: 84/162 stale=**51.85%**, 38/162 missing=**23.46%**, 29 current un 11 insufficient comparable bookmakers. Denominator ir odds scope, ne 208 visas discovered spēles. Precīzo final-review overrides un broad-sweep skaitītājus nedrīkst saskaitīt kopā.

Astoņos ciklos bija 177 dažādas odds-scope spēles; 115 vismaz vienreiz stale (**64.97%**), 48 vismaz vienreiz nebija pilnā provider sweep. Tie nav 115 zaudējumi vai independent calibration piemēri.

| Riga cikls | Odds scope | Stale | Missing |
|---|---:|---:|---:|
| 09:00 | 171 | 97 | 42 |
| 09:30 | 171 | 48 | 42 |
| 10:00 | 170 | 23 | 42 |
| 10:30 | 167 | 23 | 42 |
| 11:00 | 169 | 10 | 43 |
| 11:30 | 168 | 0 | 43 |
| 12:00 | 162 | 0 | 38 |
| 12:30 | 162 | 84 | 38 |

Visos astoņos ciklos 15/15 datuma lapu sweep bija pilns, bez partial page. Šajā posmā **120 date-page calls + 131 exact-odds calls**, 888 kopējie dabiskie discovery calls. Tie nav aģenta pieprasījumi. Tracked-only refresh apakškopā 81/97 AVAILABLE=**83.51%**, 16 WAITING; tā nav visu 131 exact calls success metrika, jo final/priority refresh ir atsevišķi.

Piegādātāja root snapshot timestamp noveco pāri esošajai 3 h 30 min robežai. Piemēram, 12:00 snapshot vecums≈181min, bet 12:30≈212min. Atbilde tika saņemta no jauna; atkārtota HTTP izsaukšana pati par sevi nepadarītu provider timestamp svaigu. Kvotas nebija izsmeltas un datuma lapas netika izlaistas. Tāpēc nav pamata akli palielināt calls vai mainīt freshness limitu.

| Līga | Fixture-cycle observations | Stale |
|---|---:|---:|
| UEFA U21 Qualification | 168 | 103 |
| EFL Trophy | 152 | 53 |
| Non League Premier — Northern | 80 | 20 |
| Friendlies | 116 | 11 |

Pārsvarā stale bija >90min pirms kickoff: 279/1288 fixture-cycle observations; 45–90 min logā 6/37; 25–45 min 0/15. Missing tajos pašos logos 304, 18, 8. Pilns league/competition/provider sadalījums ir evidence. Provider ir API-Football; trūkstošai fixture atbildei nav iespējams godīgi izveidot bookmaker/market coverage denominator. Nepamatots refresh targeting labojums nav ieviests.

**SMALL_GITHUB_FIX — PROVIDER_ZERO_PROBABILITY.** 12 ciklos 89 invalid incidents no 19 spēlēm: 51 AWAY_WIN un 38 HOME_WIN. Visos raw provider value ir `0%`. Saglabā fixture/market/source fingerprint, raw/normalized/ensemble vērtības, downstream rejection un evaluation timestamp (skaidri marķēts, ne izgudrots provider timestamp). Jauns iemesls tikai ar pierādītu API cēloni; nezināmas nulles paliek generic invalid. Clamp nav veikts.

## RUNTIME

**NO_CHANGE.** Pēdējās 24 h: 28 persisted health cikli, 1999 discovery calls, 10 490 markets, 97 klasiskie READY, 42 publicētās likmes counter (41 public + 1 private). Visi 28 ir DEGRADED, bet `failure=None`; visiem quota status ir `REDUCED_TO_PRESERVE_QUOTA`. Šī etiķete šeit nozīmē apzinātu budžeta samazināšanu, ne quota exhaustion vai model crash. UTC dienas lokālajā ledger līdz cutoff: 1521 quota claim; tas nav jāpielīdzina provider kopējai dienas bilancei.

Pārskatītajos discovery/settlement/observer/forward žurnālos nav atrasts database locked, quota contention retry/exhausted, protected settlement reserve atteikums, FileNotFoundError vai service failed. Settlement bija viens `DISCOVERY_ACTIVE` koordinācijas skip; tas atbilst guard, ne DB lock pierādījumam. 180 s guard un settlement reserve maršruts saglabāti.

**NO_CHANGE / BLOCKED_NEEDS_MORE_EVIDENCE — queue.** Jaunā release astoņos dabiskajos ciklos 30 review attempts, max 9 vienā ciklā; same-cycle duplicates=0, nepieļautu laika logu attempts=0, APIcalls≤effective ceiling. 24 public SINGLE, 9 COMBO un 1 private SINGLE dabiskās publikācijas; jaunajam ≥1.50 periodam fixture duplicates nav. Vecajā vēsturē 10 atkārtotas fixture publikācijas bija 21.09.–01.10. dažādos tirgos; tās nav jaunā queue regresija un nav pārrakstītas.

Visos astoņos ciklos final_review_candidate_count=0 un queue pending list tukšs. Tātad exact-review ceļš strādā, bet pending-deadline prioritāte un least-recently-reviewed tie pie pārslogotas rindas **vēl nav pilnībā pierādīti dabiskajā plūsmā**. Divu batchu≤5 ierobežojums, pending prioritāte un invalid/same-cycle izslēgšana iztur offline reāla runner/fake-provider testus. Jauna queue kļūda nav atrasta; queue kods nav mainīts.

**NO_CHANGE.** Pēdējās 24 h: 12 publication cycles COMPLETED un 16 NOT_ATTEMPTED; 41 public delivery ar receipt, jauns transport failure/pretransport delivery rejection/unresolved=0. Aggregate mismatch nav novērots. Private policy noraidījumi ietver 11 stale decision evidence un vienu already-claimed; COMBO lanes 1262 repeated candidate blocks uz already-claimed fixtures. Tie rāda gate darbību, ne nosūtītus dublikātus. Rejection populācijas ir atkārtoti kandidāti.

**OPERATOR_ACTION_REQUIRED.** Saglabāts vecs COMBO delivery-unknown ieraksts no **05.10.12:01:59 Riga**: transport attempted, TIMEOUT, receipt nav, unknown marker ir. Prediction suffix `e1f7df2f…`; pilns ID ir `unresolved_delivery.json`. Tas ir ārpus 24 h jaunās kļūdas loga. Operatoram jāpārbauda oriģinālā COMBO saruna un jāveic atsevišķi reviewed reconciliation. Neizdzēst claim, nesūtīt testu un neveikt automātisku resend.

**NO_CHANGE.** Piecas vecākas pending likmes (>6h pēc pēdējā kickoff) saistītas ar provider POSTPONED/PST pierādījumiem. Jaunākais settlement diagnostics satur 6 unresolved fixture references (viena fixture atkārtojas divos produktos). Kickoff age nav izmērīts settlement kavējums kopš piegādātājs paziņojis gala rezultātu. Esošie settlement noteikumi paliek spēkā.

ADMIN autorepair timer inactive/disabled, worker inactive/MainPID0. Root-only ADMIN incident DB šajā darbā nav nolasīta; konkrēta ADMIN incident closure nav apgalvota. Production konfigurācija nav labota vai restartēta.

## GOVERNANCE

**NO_CHANGE — NOT_ELIGIBLE.**

| Ieraksti | Skaits |
|---|---:|
| Learning cycles | 3 |
| Training runs | 133 |
| Model artifacts | 59 |
| Validation results | 0 |
| Holdout results | 0 |
| Governance shadow runs/predictions/settlements | 0 / 0 / 0 |
| Candidate comparisons | 0 |
| Promotion gates | 0 |
| Jaunas promotion recommendations | 0 |
| Activation events | 1 bootstrap |
| Rollback events | 0 |
| Post-hoc calibration artifacts | 0 |

Skaiti pirms/pēc darba sakrīt. Training runs/artifacts ir vēsturiskie, ne šajā darbā trenēti modeļi. Research forward ieraksti netiek pieskaitīti governance shadow run. VALIDATION=0 un HOLDOUT=0 obligāti bloķē promotion. Netika patērēts holdout, aktivizēta kalibrācija, izveidots jauns classifier, ieslēgts auto training/promotion vai mainīts champion.

## ACTIONS

| Klasifikācija | Darbība / statuss |
|---|---|
| SMALL_GITHUB_FIX | Provider-zero reason/provenance, authoritative performance papildinājumi un esošā paired DC comparator paplašinājums sagatavoti reviewed branch. |
| NO_CHANGE | Champion, odds floors, publication thresholds, selection, bankroll/staking, DC solver, today-only, Reply results un early COMBO settlement saglabāti. |
| BLOCKED_NEEDS_MORE_EVIDENCE | Calibration 163/300 un vēl atvērts logs; turpināt dabisko vākšanu. |
| BLOCKED_NEEDS_MORE_EVIDENCE | Queue saturated pending/tie situācija nav novērota; nelabot jau strādājošu queue bez incidenta. |
| NO_CHANGE | Stale/missing current quotes: upstream snapshot/coverage ierobežojums; nepievienot calls vai nemīkstināt freshness. |
| BLOCKED_NEEDS_MORE_EVIDENCE | DC 9 paired fixtures / 2 dates: turpināt shadow, neveidot dynamic modeli un nepromovēt. |
| OPERATOR_ACTION_REQUIRED | Pārbaudīt 05.10. COMBO timeout oriģinālajā sarunā un saskaņot delivery evidence; bez resend. |
| OPERATOR_ACTION_REQUIRED | Ja vēlas jaunās observability izmaiņas scheduled production izvadē, atsevišķi sagatavot/review operatora immutable release. Šis darbs to nedeployo. |

**Pārbaudes:** 475 PASS divās galīgajās grupās: 342 root/integration (37.33 s) + 133 adaptive (13.93 s). Izolētais copied-application `-I -B` research/resource smoke PASS, tīkla connect bloķēts. Sākotnējās test-harness problēmas novērstas: fake capability response/league, jauktas test kolekcijas fixture scope un observer testa pieņēmums par insertion order pie vienāda timestamp. Pēdējais tests tagad izgūst precīzo immutable record pēc digest; production observer algoritms netika mainīts.

**Noslēgums:** source commit `c5fec8c52625e3fc2742265ad75fad82e59a3911`; šis handoff un sanitizētā evidence tiek saglabāti atsevišķā commit. GitHub push un darba koka gala statuss tiek pārbaudīts pēc commit un norādīts pavadošajā atbildē. Production branch netiek pārrakstīts; sākotnējās 220 dirty takas saglabātas. **Deployments 0; manual cycles 0; aģenta provider calls 0; aģenta Telegram sends 0; LIVE DISABLED; Official pilnīgi neskarts.** Dabisko timer darbību skaitļi reportā ir novērojumi, ne aģenta izsaukumi. Liels jauns modeļa izstrādes uzdevums nav izveidots.
