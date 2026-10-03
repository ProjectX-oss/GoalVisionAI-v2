## 2026-10-03 — Dixon–Coles automation preparation, normal priority

- [x] Verify actual SINGLE 1.50 release, 818 hashes, timer grid and unchanged protected champion/LIVE/ADMIN state.
- [x] Separate :10:30/:40:30 research worker with busy/slot/lock guards, CPU/memory/deadline limits, isolated writes and no network.
- [x] Reuse capture/evaluate logic; first forecasts retained, duplicate-safe cycles, results still evaluated after the frozen capture window or a capture-input failure.
- [x] Operator-only pinned package builder/updater; SQLite consistent seed backup; pause rollback preserves all research; existing production routes/timers untouched.
- [x] 104 offline tests passed (45 automation/installer checks); systemd unit verification PASS; frozen plans and all non-research application files unchanged.
- [x] Source commit e5b02e4; pinned operator package built; 831 checksums and read-only preflight PASS. Research service/timer remain not installed.
- [x] Operator activated e5b02e4; independent release/unit/resource/seed/route/champion readback PASS. All 10 original research records retained; timer active/enabled.
- [x] First natural timer run 19:10:30–19:10:36 Riga completed, exit 0; 13 research records verified and original 10 preserved. No new forecast: one fixture/two families explicitly unavailable (FIT_DID_NOT_CONVERGE). One original fixture remains pending.
- [x] Reproduce both fit failures offline: 43 results/11 teams, line search stalls at fixed rate ceiling 8.0 in iterations 50/52; no policy/code change, no DB writes or new forecasts. Diagnostic report: docs/evidence/dixon_coles_automation_20261003/FIT_DIAGNOSIS_20261003.md.
- [x] Second natural cycle 19:40 succeeds and adds fixture 1498855 TOTAL_3_5; two pending fixtures/five families/11 market comparisons, all prior evidence retained.
- [ ] Prepare a separately declared constrained-optimizer research candidate with bounded deterministic tests; keep current experiment immutable.
- [ ] Review genuine resolved/cross-day quality evidence and ongoing coverage; no automatic promotion.
- Runbook: docs/operations/DIXON_COLES_AUTOMATION_20261003.md.
- Evidence: docs/evidence/dixon_coles_automation_20261003/verification.json.
- No deployment, manual production cycle, provider/Telegram request or automatic promotion during preparation.

## 2026-10-03 — Dixon–Coles isolated research, normal priority

- [x] User approved the next research comparison without maximum priority; existing Lab publication remains active.
- [x] Freeze prospective plan before fitting (3de240d), preserve calendar plan/reserved and consumed holdouts.
- [x] Standard-library joint Dixon–Coles fit, JSON artifacts, tail-safe probabilities and explicit unavailable outcomes.
- [x] Bounded query-only natural-input adapters, separate append-only store and manual paired capture/evaluate CLI.
- [x] Final offline matrix: 249 passed; deterministic 30-fixture synthetic held-out replay; three genuine cached-result league fits converged.
- [x] First genuine prospective evidence: fixture 1641278, four families/nine paired markets captured at 17:09 Riga; result pending.
- [x] Production release/routes/818 hashes/ADMIN guard and protected champion/model counts unchanged; no deployment, timer, provider call or Telegram request.
- [x] Verify first natural SINGLE 1.50 publications from the 16:30/17:00 cycles; six confirmed receipts and separate V4 statistics.
- [ ] Genuine resolved/cross-day comparison and coverage review. No automatic research job installed; scheduling is a separate reviewed operator task.
- Report: docs/research/DIXON_COLES_RESEARCH_20261003.md.
- Commands: app/dixon_coles_research/README.md.
- Research-only; no claim of improved win rate or model/selection activation.

## 2026-10-03 — SINGLE 1.50 with normal Lab publication

- [x] User explicitly approved SINGLE >=1.50 and continued actual publication to the existing Lab conversation; COMBO legs remain >=1.30.
- [x] Verify deployed 2436d39 reply release, repo instructions and protected routes/champion/disabled ADMIN.
- [x] Versioned V4 policy, exact pre-ranking/preclaim floor, unchanged quality/today-only/COMBO selection, Lab message minimum and separate immutable 1.50 cohort statistics.
- [x] Preserve old open bets, frozen previews, Reply text/photos and economic claim terminality; compatible rollback retains 1.50 result readers.
- [x] Update de-vig provenance to the actual SINGLE policy; no research selection or champion change.
- [x] Offline matrix: 883 passed, one inherited inapplicable installer case skipped; full 818-file exact-base parity PASS.
- [x] GitHub/forum source review compared against existing capabilities; document Dixon–Coles/uncertainty/confirmed-XI options and source/license limits. No external installation or model change.
- [x] Source/evidence committed as e1263e7; pinned exact-base operator package built, eight checksums and read-only BASE preflight PASS. Operator apply remains pending.
- [x] Operator deployed e1263e7 at 16:04 Riga; independent 818-file release/flags/four routes/timers/disabled ADMIN/protected champion readback PASS. Evidence: docs/evidence/single_150_20261003/deployed_readback.json.
- [x] First natural 1.50 publication verified: 16:30/17:00 cycles, six confirmed SINGLE receipts, all odds >=1.50 and V4 statistics. Evidence: docs/evidence/single_150_20261003/natural_publications.json. No manual cycles/provider calls/test sends.
- Runbook: docs/operations/PREMATCH_SINGLE_150_20261003.md.
- Research: docs/research/CURRENT_DATA_QUALITY_OPTIONS_20261003.md.
- Official/weekly unchanged; LIVE and ADMIN Codex disabled; no automatic deployment/promotion or historical bookmaker odds.

## 2026-10-03 — SINGLE/COMBO result replies to the original prediction

- [x] User requested WIN/LOST as Reply to the original bet; inspect existing confirmed message IDs and deployed COMBO routing.
- [x] Lab-only text/photo replies for SINGLE, old Lab COMBO and new private COMBO; frozen same-chat receipt binding, strict parent validation and no extra fallback send.
- [x] Retain terminal claims, early COMBO loss/remaining-leg details, immutable results/statistics and both 1.30 floors.
- [x] Offline matrix: 744 passed, one inherited inapplicable installer case skipped; 818-file exact-base parity PASS.
- [x] Review exact 9a3b198-base operator updater; rollback disables reply attachment only, preserving COMBO routing and all current policies.
- [x] Source commit 2436d39; pinned package built, five checksum entries and read-only exact-base preflight PASS.
- [x] Operator deployed 2436d39 at 14:57 Riga; full release/routes/timers/disabled ADMIN readback PASS. Natural 15:05 SINGLE LOST reply confirmed (result 616 -> original 582), immutable evidence verified.
- [ ] First natural COMBO result reply. No manual cycle or test send.
- Report: docs/operations/PREMATCH_SETTLEMENT_REPLIES_20261003.md.
- Official/champion unchanged; LIVE and ADMIN Codex remain disabled. SINGLE 1.50 stays pending.

## 2026-10-03 — Separate COMBO Telegram bot and prospective statistics

- [x] User identified @GoalVision_AI_Combo_Bot, deferred the channel and requested system connection.
- [x] Read-only natural 13:00 floor proof: 3 SINGLE + 3 COMBO, all nine legs >=1.30; today-only and receipt fingerprints verified.
- [x] Dedicated bot/configuration/recipient contract; private START challenge verification and hidden credential enrollment.
- [x] Original-route settlement, independent prospective COMBO statistics, unchanged economic claims and compatible pause rollback.
- [x] Offline matrix: 622 passed, one inherited inapplicable case skipped; 817-file exact-base parity PASS.
- [x] Source commit 9a3b198; pinned operator package built, checksums and read-only exact-base preflight PASS; enrollment/apply pending.
- [x] Operator enrolled the private recipient and deployed 9a3b198 at 13:51 Riga; independent release/configuration/four routes/timers/disabled ADMIN readback PASS.
- [ ] First qualifying natural COMBO-bot prediction/result; next discovery 14:00 Riga and observer 14:08. No manual cycle/test send.
- Report: docs/operations/PREMATCH_COMBO_BOT_20261003.md.
- SINGLE remains >=1.30; COMBO legs >=1.30. SINGLE 1.50 and channel/weekly COMBO delivery remain later work.
- Official/champion unchanged; LIVE and ADMIN Codex disabled; no automatic deployment or test send.

## 2026-10-03 — Planned SINGLE 1.50 test and separate COMBO Telegram stream

- [x] Record the user's future SINGLE >=1.50 test and proposed COMBO bot/channel separation with a new COMBO statistics period.
- [x] Inspect existing shared destination, receipt validation and all-time statistics boundaries; document safe cutover and old-bet continuity.
- [x] Verify natural 13:00 publication and 13:08 observer evidence for the installed 1.30 policy.
- [ ] Implement versioned SINGLE >=1.50 independently of COMBO legs >=1.30; no additional combined-odds minimum.
- [ ] Establish the exact COMBO destination and publishing bot; implement product-specific prediction/result routing and immutable period membership.
- [ ] Preserve prior history and original-route settlement, prevent cross-channel duplicates, and test compatible rollback with open bets.
- [ ] Offline tests/evidence/commit, then reviewed exact-base operator package; no automatic deployment or promotion.
- Plan: docs/operations/PREMATCH_SINGLE_150_COMBO_SPLIT_PLAN_20261003.md.
- Documentation only: installed policy/routes unchanged; Official unchanged; LIVE/ADMIN Codex disabled.

## 2026-10-03 — COMBO installer after calibration deployment

- [x] Verify calibration observer c4daf63 is installed; the rejected ff55669 COMBO attempt created no release or overrides.
- [x] Retain exact-route guards and pin both installed source/environment contracts; runtime application files remain identical.
- [x] Mixed-source apply/rollback/failure recovery and drift rejection: 157 installer tests passed, one inapplicable inherited case skipped; network disabled.
- [x] Prepare a distinct R2 pinned entry point; preserve earlier packages and wrappers unchanged.
- [x] Commit e355b51; R2 package prepared with 15 checksum entries and read-only preflight PASS for both installed sources.
- [x] Operator deployed R2 e355b51 at 12:39 Riga; independent release/flags/four routes/timers/disabled ADMIN readback PASS.
- [x] Natural 12:38 readiness observer succeeded on the previously installed calibration release; immutable report verified.
- [x] Post-R2 natural 13:00 discovery: 3 SINGLE + 3 COMBO, all nine legs >=1.30; 13:08 observer report verified. No manual cycles/provider calls/test sends.
- Report: docs/operations/PREMATCH_COMBO_LEG_FLOOR_R2_20261003.md.

## 2026-10-03 — COMBO per-leg minimum 1.30

- [x] Apply the user's clarified rule: each COMBO selection >=1.30, not an aggregate 1.30 threshold.
- [x] Exact pre-ranking filter, qualifying alternative-market selection, versioned identity/metadata and preclaim delivery guard across current/legacy Lab paths.
- [x] Preserve SINGLE >=1.30, all quality/chronology/correlation checks, published history, early settlement and remaining-leg tracking.
- [x] Persist bounded floor diagnostics in full and compact cycle evidence; retain old-policy reader/rollback compatibility.
- [x] Offline integration matrix: 1,147 passed, one inherited inapplicable single-route installer case skipped.
- [x] Source parity: 13 overlays reproduce the installed base plus the candidate; previously approved readiness files remain byte-identical.
- [x] Combine pending approved readiness integration and leg floor into one reviewed operator package implementation.
- [x] Source commit ff55669; pinned package prepared, 15 checksums and read-only preflight PASS; installed mode remains BASE.
- [x] Operator applied R2 e355b51 after calibration deployment; see latest readback above.
- [x] Post-R2 natural discovery evidence recorded in docs/evidence/combo_bot_20261003/natural_floor_readback.json.
- Report: docs/operations/PREMATCH_COMBO_LEG_FLOOR_20261003.md.
- Official unchanged; LIVE/ADMIN Codex disabled; champion unchanged.

## 2026-10-03 — Optional calibration readiness in PREMATCH observer

- [x] Read current de-vig routes and disabled ADMIN Codex; preserve existing frozen calendar plan.
- [x] Add bounded query-only readiness and fixture lifecycle progress to the existing observer behind an explicit flag.
- [x] Keep canonical/SINGLE economic dedup, no COMBO learning inflation, strict cohort/holdout/chronology guards, sanitized optional failure.
- [x] Offline regressions: 876 passed, one inapplicable multi-route case skipped; installed ADMIN output contract PASS.
- [x] Query-only evidence: TRAIN 1,804 / 560 fixtures; FIT 312 opportunities / 101 upcoming fixtures, zero eligible resolved. No training/holdout/champion change.
- [x] Prepare reviewed observer-only operator implementation with full application and plan hashes, atomic recovery and compatible flag rollback.
- [x] Commit c4daf63; package checksums and read-only installer preflight PASS, current mode BASE.
- [x] Operator installed calibration observer c4daf63; source/flag/route readback PASS on 2026-10-03.
- [x] Natural readiness observer at 12:38 Riga: success, report retained; FIT still data/window BLOCKED, no training or promotion.
- [ ] Natural calendar evidence, then separately reviewed offline calibration/evaluation if all gates pass.
- Report: docs/operations/CALIBRATION_OBSERVER_20261003.md.
- SINGLE >=1.30; COMBO no floor; today-only/early COMBO settlement retained. Official unchanged; LIVE/ADMIN Codex disabled.

## 2026-10-02 — Fixed-calendar calibration research candidate

- [x] Add opt-in immutable 14/7/7/7-day research schedule with 24-hour gaps and exact model/policy cohort.
- [x] Preserve prior sealed/consumed holdout, fixture grouping, chronology and independent sample minima.
- [x] Add query-only audit CLI; synthetic fitter integration and 654 tests + 42 subtests PASS.
- [x] Read-only real comparison: TRAIN 1,804 / 560 fixtures; fitting/evaluation/holdout remain future and BLOCKED. Reserve all 156 old holdout fixtures.
- [x] Commit prospective plan before fitting starts; independent replay and unchanged runtime/champion evidence retained.
- [ ] Collect natural evidence for the frozen plan, then offline calibration/holdout/shadow evaluation if all readiness gates pass.
- [ ] Any scheduled-research integration or deployment requires separate review; no automatic promotion.
- Report: docs/operations/CALIBRATION_CALENDAR_RESEARCH_20261002.md.

## 2026-10-02 — Calibration readiness and chronological window bottleneck

- [x] Read-only installed-code projection: 2,293 eligible observations / 773 fixtures; VALIDATION 0 after the retained 24-hour embargo.
- [x] Confirm existing Platt/temperature/isotonic research implementation; no fitting or sealed holdout evaluation invoked.
- [x] Diagnose all 155 provisional validation fixtures excluded by label-availability timing; preserve current champion and production state.
- [x] Isolated calendar-window candidate, immutable prospective plan and clustered-date/late-settlement/leakage regressions; no runtime wiring or deployment.
- [ ] Genuine independent calibration/evaluation and later shadow evidence once data readiness passes; promotion remains separately approved.
- Report: docs/operations/CALIBRATION_READINESS_20261002.md.

## 2026-10-02 — Current-odds de-vig research integration

- [x] Read handoff/instructions; verify actual f81aa2c routes, flags and disabled ADMIN Codex.
- [x] Isolated V2 current-quote captures with exact provenance, optional failure isolation and no added provider calls.
- [x] Existing observer result join, paired/common cohorts, missingness, policy/market segments and bounded stdout.
- [x] 879 affected regressions and final 312-test slice (47 de-vig), network disabled; counts overlap.
- [x] Exact-base operator package from commit 83958d1 prepared; read-only validation and nine checksum entries PASS; no deployment.
- [x] Operator deployed de-vig release 83958d1; independent readback PASS at 14:16 Riga.
- [x] Natural deployment verification PASS: 13 discovery + 13 observer cycles; 1,459 capture replays verified; 18 settled unique fixtures at 20:38.
- [ ] Broader genuine forward outcomes and cross-day/family stability; no comparator superiority or promotion approval.
- Report: docs/operations/PREMATCH_DEVIG_INTEGRATION_20261002.md.
- SINGLE >=1.30, COMBO no floor, today-only and early settlement retained. Official unchanged; LIVE/ADMIN Codex disabled.

## 2026-10-02 — Segmented forward selection quality

- [x] Reconcile 165 SINGLE / 53 COMBO publications; separate policy cohorts and partial maturity.
- [x] Paired old-ensemble vs frozen market probability comparison; analyze negative EV without cross-policy causal claims.
- [x] Full market/odds/probability/league/timing/disagreement evidence saved; no threshold changes.
- [x] Current-odds de-vig research wiring completed in the latest entry; genuine validation/calibration readiness remains pending.
- [ ] Evaluate V2/V3 cohorts once results are available; no resolved V2/V3 tickets at 12:50 Riga.
- Report: docs/operations/PREMATCH_SEGMENTED_QUALITY_20261002.md.

## 2026-10-02 — Natural SINGLE-floor and settlement audit

- [x] Actual 12:00 publication, today scope, SINGLE floor and COMBO independence PASS.
- [x] All 131 SINGLE and 23 COMBO settlements reconcile with observer and settlement totals.
- [x] All result receipts present; no duplicate message IDs or unreceipted claims.
- [x] Dayrout fixture identified as rescheduled to today 15:30 Riga (provider NS).
- [x] Segmented forward quality review: policy/market/odds/EV/timing/league and paired market baseline reconciled.
- [ ] Resolved V2/V3 outcomes and dataset/calibration readiness; comparator wiring completed in the latest entry.
- Report: docs/operations/PREMATCH_FLOOR_NATURAL_AUDIT_20261002.md.

## 2026-10-02 — SINGLE-floor installer after settlement deployment

- [x] Verify installed settlement source, enabled early-loss flag and failed-upgrade non-mutation.
- [x] Pin the new base, preserve settlement behavior on rollback, reject mixed/old routes.
- [x] 126 focused offline tests PASS; application source unchanged.
- [x] Operator deployed f81aa2c at 11:54 Riga; full release/configuration/timer readback PASS.
- [x] Natural settlement service exited successfully at 11:55:38 Riga.
- [x] 12:00 discovery: three SINGLE >=1.30 and three COMBO, including a 1.17 leg; six receipts verified.
- Deployment report: docs/operations/PREMATCH_SINGLE_FLOOR_DEPLOYED_20261002.md.
- Report: docs/operations/PREMATCH_SINGLE_FLOOR_COMPAT_20261002.md.

## 2026-10-02 — PREMATCH SINGLE minimum 1.30; COMBO without minimum

- [x] User-authorized inclusive SINGLE floor at preparation and delivery.
- [x] Independent COMBO candidate pool, including legs below 1.30.
- [x] Historical previews, claims and low-odds settlement preserved.
- [x] Offline boundary, complete-cycle, settlement and operator rollback tests.
- [x] Combined operator package includes the pending settlement correction.
- [x] Operator deployment and configuration readback PASS (f81aa2c).
- [x] 12:00 discovery: three SINGLE >=1.30 and three COMBO, including a 1.17 leg; six receipts verified.
- Report: docs/operations/PREMATCH_SINGLE_FLOOR_20261002.md.

## 2026-10-02 — PREMATCH early COMBO loss and result diagnostics

- [x] Financial LOST once after confirmed losing leg; outstanding leg audit continues.
- [x] Compatible adaptive readers, immutable late detail and bounded unresolved-result evidence.
- [x] 206 network-disabled tests; exact replay of 21 historical COMBO settlements and two known losses.
- [x] Four-route operator upgrade and compatible flag-off rollback prepared.
- [x] Operator deployed settlement 04a0751 on 2026-10-02; release hashes and four routes verified.
- [x] 12:08 observer and 12:25 settlement independently reconciled; two early losses recorded/delivered once.
- [ ] Remaining future legs of early financial losses: natural full-detail completion.
- Report: docs/operations/PREMATCH_SETTLEMENT_FIX_20261002.md.

## 2026-10-01 — Integrēts PREMATCH quality release

- [x] Savienot TODAY_RIGA/CPU pamatu ar performance, timing, no-floor un evidence gates.
- [x] COMBO learning izolācija, observer snapshot un dataset/calibration preflight.
- [x] Tikai manuāla champion promotion ar pilnu evidence.
- [x] 1475 tests + 34 subtests; 41 integration corrections; 74 stdout/performance; 17 installer (pārklājas).
- [x] Read-only dati: TRAIN 583 / VALIDATION 10 / HOLDOUT 345 / PURGED 865; BLOCKED, bez treniņa.
- [x] Īsa operatora pakotne ar četru PREMATCH maršrutu rollback un aizsargātiem ADMIN/weekly.
- [x] Operators izvietoja 3ad346b 22:13 Riga; 805 moduļi, 4 route/timer un champion pārbaude PASS.
- [ ] Dabisko discovery/observer/research ciklu verification pēc 22:13 deployment.
- [ ] De-vig/xG/dynamic-strength pieslēgšana atsevišķā research posmā.
- Runbook: docs/operations/PREMATCH_QUALITY_20261001.md.

## 2026-10-01 — PREMATCH Lab Riga same-day scope

- [x] Reproduce both screenshot cases against the deployed hour-only gate.
- [x] Audit the three-day window and future fixtures restored from earlier cycles.
- [x] Filter provider/restored fixtures to today in Riga before analysis work.
- [x] Require same-day SINGLE/COMBO kickoffs at preparation and delivery.
- [x] Preserve published history and later-day settlements.
- [x] Add bounded day-scope diagnostics and 525 passing adjacent regressions.
- [x] Prepare discovery-only hash-pinned upgrade/rollback on the active CPU-fixed base.
- [x] Operator deployment f5d7968; release hashes, TODAY_RIGA environment and routes PASS.
- [x] Natural 21:00/21:30 cycles PASS: 6 SINGLE + 2 COMBO; all eight receipts and 12 kickoff entries verified for today in Riga.
- Runbook: docs/operations/PREMATCH_TODAY_SCOPE_20261001.md.

## 2026-10-01 — Explicit Lab accuracy COMBO option

- Confirmed 9 SINGLE receipts, 8 non-positive EV selections and the legacy COMBO policy mismatch.
- Added opt-in accuracy triples from the current approved SINGLE pool, immutable leg evidence,
  fail-closed delivery review, diagnostic reasons, no repeated combo fixtures and legacy default.
- Added offline full-cycle delivery, settlement and deployment/rollback regression coverage.
- Prepared discovery-only immutable package; no real provider calls, manual Telegram sends,
  source-ledger mutations, service controls or production activation performed.
- Policy activation pending explicit approval under AGENTS.md section 13.
- Runbook: docs/operations/LAB_ACCURACY_COMBO_20261001.md.

## 2026-10-01 — Protect current-odds page budget

- [x] Trace three-page starvation to the priority analysis reservation.
- [x] Protect up to 32 page attempts inside the existing adaptive cycle cap.
- [x] Verify three-day sweep, restart gaps, low quota and unrelated delivery gates.
- [x] Prepare discovery-only immutable upgrade with tested rollback and drain refusal.
- [x] Network-blocked regression: 286 passed; no manual provider or Telegram calls.
- [ ] Operator installation and naturally scheduled runtime verification.
- Runbook: `docs/operations/PREMATCH_ODDS_PAGE_BUDGET_20261001.md`.
- Ledger read-lock contention and AutoRepair startup remain separate known issues.

## 2026-09-27 — PREMATCH shared quota lock hardening

- [x] Audit the exact failed invocation and every shared-audit writer boundary.
- [x] Move history/compute outside writer locks with atomic validated append batches.
- [x] Add bounded cancellable local quota retries before any HTTP/count increment.
- [x] Verify real SQLite contention, quota limits, rollback, and focused regressions offline.
- [x] Rehearse host readability/configuration read-only; prepare inert upgrade/rollback payloads.
- [ ] Obtain protected exact systemd lifecycle/exit and independent ADMIN disabled readback.
- Report: `docs/operations/PREMATCH_QUOTA_LOCK_HARDENING.md`.
- No deployment, production service controls, real API calls or Telegram sends.

# TASKS.md

## 2026-09-26 — Professional Lab V2 public messages

- [x] Add versioned Latvian presentation for new labelled single previews.
- [x] Freeze existing confirmed labelled-single cohort statistics for predictions/results.
- [x] Preserve historical bytes, internal linkage, claims, receipts and plain-text delivery.
- [x] Cover wording, accounting, replay and directly affected regressions offline.
- Documentation: `docs/LAB_V2_PUBLIC_MESSAGES.md`.
- No model/policy/schema change, deployment, timer stop, live cycle or Telegram send.


## 2026-09-26 — Compact PREMATCH operator stdout

- [x] Add versioned bounded controlled-cycle/rehearse output without altering persisted evidence.
- [x] Retain all delivery reconciliation facts, including emergency persistence failures.
- [x] Add large synthetic cycle, immutable inspection, redaction and exit regressions.
- [x] Recheck focused delivery, statistics, settlement and discovery behavior offline.
- No policy/model changes, migrations, deployment or publication enablement.


## 2026-09-23 — PREMATCH adaptive shadow chronology hardening

- Audit the complete incoming/canonical/governance shadow path on exact `50a73ce`.
- Diagnose and skip expired immutable canonical PREMATCH records before governance,
  retaining structured, idempotent evidence and processing later candidates.
- Reject future incoming preparation before canonical substitution can hide it;
  future frozen preparation and unrelated integrity errors remain fail-closed.
- Preserve the invalid-baseline hotfix, canonical identities/history and governance.
- Add focused synthetic chronology, continuation, replay and integrity regressions.
- Audit and validation record: `docs/PREMATCH_SHADOW_HARDENING_2026-09-23.md`.
- No deployment, production-state changes, external API calls or Telegram sends.

## Final LAB launch readiness foundation (2026-08-02)

- [x] Add independent governance policy review and append-only operator approval/revocation.
- [x] Add one-use, expiring first-LAB launch authorization bound to exact destination and model evidence.
- [x] Add final readiness, inert Pro preflight, SQLite backup/verification/restore rehearsal, launch execution stages, post-run audit, and post-match review boundaries.
- [x] Extend the local operator console with schema-42 launch governance pages and confirmed POST actions.
- [x] Add the 39-check controlled fictional final-launch rehearsal and operator checklist.

## Forward-test model governance foundation (2026-08-02)

- [x] Add centralized, versioned, conservative governance policy and deterministic settled-evidence windows.
- [x] Add predictive, calibration, feature/input, completeness, odds, market, competition, bookmaker, explanation, and generation governance.
- [x] Add append-only schema v41 evaluations, windows, scopes, decisions, transitions, recommendations, reproductions, observation snapshots, and events.
- [x] Add fail-closed LAB publication integration, deduplicated incidents, manual recommendations, reports, reproduction, CLI, console panels/actions, and controlled fictional rehearsal.
- [x] Keep genuine provider access, Telegram, Official state, training, recalibration, model activation/rollback, scheduling, bets, and bookmaker transactions disabled.

## Prediction explainability and reasoning quality foundation (2026-08-02)

- [x] Add exact deterministic live-78 multinomial score/probability attribution
  with explicit bucket-derived totals and no fabricated direct contribution.
- [x] Add a reviewed 78-feature catalog, grouped material evidence, risks,
  missing-data, calibration, shift, confidence and counterfactual disclosures.
- [x] Add schema v40 immutable reasoning, normalized contribution and strict
  audit evidence with replay/conflict and foreign-key protection.
- [x] Bind Lab publication review to the exact reasoning, passed audit and
  composite message fingerprint; keep pre-reasoning previews diagnostic-only.
- [x] Add offline CLI, operator-console, monitoring and reporting integration.
- [x] Complete a controlled fictional rehearsal with exact reproduction and
  zero provider, Telegram, delivery, Official, bankroll, statistics, scheduler
  or production activity.
- [x] Document policy, audit, operator use and limitations.

## Local Lab operator console foundation (2026-08-02)

- [x] Add a standard-library, server-rendered local console with no new runtime
  dependency, CDN, telemetry, remote font, or asset build pipeline.
- [x] Enforce `127.0.0.1`, read-only default operation, allowed database roots,
  signed ephemeral sessions, SameSite/HttpOnly cookies and action-bound CSRF.
- [x] Add typed presentation services for the complete Lab workflow, monitoring,
  reports, unresolved work, incidents, health and operator action history.
- [x] Add schema v39 append-only console actions/events and fictional demo
  manifests with replay, conflict, foreign-key and immutability protection.
- [x] Centralize confirmed POST-only actions and retain zero automatic provider,
  inference, Telegram, scheduler, publication or startup work.
- [x] Add a deterministic fictional demo and document local-only operation.

## Forward-test monitoring and weekly reporting foundation (2026-08-01)

- [x] Add a centralized, immutable monitoring policy with conservative sample,
  freshness, anomaly, calibration and segmentation thresholds.
- [x] Add schema v38 append-only snapshots, reports, lifecycle audits,
  incidents, acknowledgement events and export manifests.
- [x] Add deterministic cumulative and Riga-week reports with Decimal-only
  predictive, calibration and hypothetical flat-stake metrics.
- [x] Include wins, losses, voids, pending results, blocked analyses,
  no-selections, unpublished observations and explicit sample warnings.
- [x] Add lifecycle and data-quality findings with identifiers and provenance,
  unresolved work queues, offline health inspection and incident recording.
- [x] Add deterministic JSON, Markdown, Telegram-preview and nine-file CSV
  export bundles with exact report reproduction and overwrite protection.
- [x] Keep generation manual-only with zero networking, Telegram transport,
  scheduler, Official state or bankroll mutation.
- [x] Document the operator runbook and controlled rehearsal evidence.

## First LAB prediction operational readiness (2026-08-01)

- [x] Add offline and one-call network `pro-readiness` diagnosis with typed,
  secret-free plan, capability and quota outcomes.
- [x] Add explicit bounded `first-lab-dry-run` orchestration through live-78
  analysis, observation and Lab preview, always stopping before Telegram.
- [x] Add schema v37 append-only run stages, publication reviews and result
  previews with replay/conflict and foreign-key protection.
- [x] Harden the operator sender with exact observation, message and passing
  review linkage while retaining the Lab environment/chat/bot/confirmation locks.
- [x] Complete result fetch/manual fallback, settlement preview and transparent
  statistics operations without Official or bankroll mutation.
- [x] Rehearse the full flow offline with controlled evidence; create no genuine
  observation, delivery record, publication, schedule, or production activation.
- [x] Document first-week operation and the manual post-2026-08-10 Pro checklist.

## API-Football discovery request efficiency (2026-08-01)

- [x] Trace shared fixture-list, team-history, optional-data, odds, retry and
  cache costs for every deeply considered candidate.
- [x] Reject explicit fixture/odds coverage failures from the fixture-list and
  cached league-season metadata before detailed calls.
- [x] Add a sanitized, fingerprinted six-hour competition capability cache and
  context-bound 15-minute team/standings reuse without startup networking.
- [x] Plan the full remaining mandatory cost before starting a candidate and
  short-circuit immediately when the first required team baseline is blocked.
- [x] Preserve required-before-optional ordering and query exact fixture odds
  only after both current-season team baselines are available.
- [x] Run the optimized bounded discovery: 967 fixtures, 620 prefiltered,
  seven planned, six deeply called, zero odds, terminal
  `DISCOVERY_QUOTA_INSUFFICIENT`.
- [x] Prove the configured free plan rejects 2026 team history and therefore
  cannot support a genuine current-season forward observation without a plan
  change; no data was fabricated or mixed across seasons.

## Adaptive API-Football fixture discovery (2026-08-01)

- [x] Prove the original zero result was a rejected unfiltered `from`/`to`
  request whose HTTP-200 provider errors were discarded.
- [x] Preserve sanitized query, errors, result count, paging and exact quota
  headers and distinguish provider validation errors from empty schedules.
- [x] Correct daily versus per-minute quota meanings and enforce request,
  candidate and reserve ceilings across real HTTP attempts and retries.
- [x] Resolve reviewed competition IDs and provider-current season chronology;
  reject stale current flags whose season end has passed.
- [x] Replace the invalid range boundary with staged UTC date discovery,
  deterministic priority/all-supported fallbacks and explicit senior-fixture
  exclusions.
- [x] Enforce baseline-before-odds, one odds request per fixture, exact identity,
  current timestamp provenance, supported markets and 15-minute freshness.
- [x] Keep discovery and every inspection command inference- and Telegram-free.

## API-Football configuration and first current discovery (2026-08-01)

- [x] Reuse the canonical `FOOTBALL_API_KEY` from the project `.env` lazily.
- [x] Fail closed on conflicting process and `.env` canonical values.
- [x] Add secret-safe explicit authentication, plan and quota diagnosis.
- [x] Add deterministic discovery ceilings of 50 candidates and 50 API calls.
- [x] Run the first bounded discovery: authenticated, active plan, one API call,
  zero provider fixtures in the 2026-08-01 through 2026-08-08 UTC window,
  terminal result `NO_ELIGIBLE_CURRENT_FIXTURE`.
- [x] Keep odds retrieval, inference, Telegram, publication, bankroll, startup,
  scheduling, TheStatsAPI and historical-odds probing at zero for that result.

# GoalVision AI Development Tasks

Version 1.0

Tasks are always completed from top to bottom.

No task may be skipped unless explicitly approved.

---

# CURRENT ODDS CAPTURE AND FORWARD-TEST FOUNDATION

Status:

COMPLETED — READY FOR FIRST OPERATOR-SUPPLIED GENUINE FIXTURE

- [x] Introduce the isolated `FORWARD_TEST_REAL_TIME` evidence tier without
  reclassifying historical or legacy Real Match Lab evidence.
- [x] Add API-Football-assisted and versioned manual current-odds modes with
  exact GoalVision-vs-provider timestamp semantics and all 11 single markets.
- [x] Enforce source selection, capture, sealing, inference, and kickoff order;
  reject stale, replaced, post-inference, post-kickoff, and incomplete quotes.
- [x] Add schema v36 append-only odds, observation, result, settlement, and
  event chains linked to immutable Real Match Lab analyses.
- [x] Retain completed, no-selection, blocked, losing, unpublished, and pending
  observations with separate mathematical, actionable, Lab, and Official states.
- [x] Add deterministic result capture and statistical-only settlement without
  a stake, bookmaker transaction, or production bankroll entry.
- [x] Add transparent predictive, calibration, selection, distribution, data
  quality, simulated-risk, sample-maturity, and read-only integrity reporting.
- [x] Keep Telegram sends, delivery records, Official publication/statistics,
  production activation, scheduling, and startup execution at zero.
- [x] Export sanitized canonical evidence at
  `docs/rehearsals/current_odds_forward_test_foundation_2026-08-01.json`.

Next: select one genuine upcoming fixture, predeclare one source/bookmaker,
capture current odds before inference using the versioned template, seal them in
an isolated schema-v36 database, run Real Match Lab analysis, and explicitly
create the first forward-test observation. No send is authorized.

---

# HISTORICAL ODDS PROVIDER COVERAGE PROBE

Status:

COMPLETED — PROVIDER CREDENTIAL NOT CONFIGURED

- [x] Add a provider-neutral, credential-ready acquisition boundary and a
  concrete TheStatsAPI adapter without import-time or startup networking.
- [x] Load `GOALVISION_THESTATSAPI_API_KEY` only for explicit provider commands;
  redact credentials from endpoints, receipts, errors, evidence, and output.
- [x] Bound sampling to ten fixtures, 25 requests, six stratified VALIDATION/TEST
  periods, finite timeouts, and at most two transient-only retries.
- [x] Preserve real opening and last-seen capture timestamps and reject missing
  timestamps as coverage proof instead of inventing them.
- [x] Add deterministic 626-fixture request, quota, storage, and resume planning;
  keep bulk export behind five independent fail-closed authorization gates.
- [x] Record TheStatsAPI as `REVIEW_REQUIRED`; advertised capabilities are not
  treated as verified coverage and storage/redistribution remain unresolved.
- [x] Produce sanitized evidence at
  `docs/rehearsals/historical_odds_provider_coverage_probe_2026-08-01.json` with
  zero network, Telegram, Official, bankroll, production, or raw-data changes.

Historical paid acquisition is paused. Keep this foundation dormant and
inspectable; do not configure or probe TheStatsAPI. Current forward testing is
the active evidence strategy. No publication or activation is authorized.

---

# EXTENDED REVIEWED HISTORICAL ODDS COVERAGE FOUNDATION

Status:

COMPLETED WITH REVIEWED TEST-ODDS COVERAGE UNAVAILABLE

- [x] Derive and persist the unchanged split acquisition window: 1,459 TRAIN,
  313 VALIDATION, and 313 TEST examples with indivisible equal-kickoff groups.
- [x] Review The Odds API paid archive, Sportmonks Premium Odds Feed, and
  Betfair Historical Data using official public documentation only.
- [x] Record all three sources as `ACCESS_UNAVAILABLE`; no authorized API key,
  subscription export, eligible exchange archive, or operator-supplied raw file
  is present.
- [x] Add schema v35 versioned immutable source reviews, acquisition windows,
  and partition coverage reports without mutating schema-v34 evidence.
- [x] Extend offline parsing and normalization across 1X2, totals 1.5/2.5/3.5,
  and BTTS, with multi-snapshot replay and content-conflict rejection.
- [x] Preserve the primary Pinnacle 24-hour policy and add an explicit reviewed
  bookmaker-set policy that is unusable unless historical comparison capability
  was declared before evaluation.
- [x] Keep TEST backtesting, comparison, shadow, staging activation, and Lab
  rehearsal blocked; perform zero Telegram, Official, bankroll, production,
  scheduler, or startup mutations.
- [x] Export canonical evidence at
  `docs/rehearsals/live_78_extended_test_odds_coverage_2026-08-01.json`.

Next: provide an operator-approved licensed archive or authorized API credential
covering 2023-05-13 through 2025-05-17, plus a separately reserved post-TEST
shadow window. Then import once under a predeclared quote policy and rerun every
quality, integrity, comparison, shadow, and audit gate. Lab publication remains
separately unauthorized.

---

# REVIEWED HISTORICAL PRE-KICKOFF ODDS AND BETTING EVIDENCE FOUNDATION

Status:

COMPLETED WITH GENUINE TEST-ODDS BLOCKER

- [x] Add typed append-only odds source reviews, manifests, hashes, event links,
  normalized quotes, quote selections, coverage, integrity, evidence, shadow,
  and audit records in schema v34.
- [x] Review The Odds API public sample, BALLDONTLIE, and the
  DataHub/football-data.co.uk mirror without bypassing access controls.
- [x] Import 591 genuine timestamped 1X2 quotes from 18 October 2022 Bundesliga
  events and link all events deterministically to reviewed OpenLigaDB matches.
- [x] Enforce a fixed Pinnacle 24-hour cutoff with no best-price hindsight.
- [x] Report complete source, bookmaker, market, season, capture-window, and
  TRAIN/VALIDATION/TEST coverage without hiding missing TEST coverage.
- [x] Preserve VALIDATION-only calibration and reject odds as labels.
- [x] Keep TEST betting metrics unavailable because the sample has zero TEST
  quotes; do not substitute synthetic or untimestamped closing odds.
- [x] Persist `INSUFFICIENT_BETTING_EVIDENCE`, shadow insufficiency, blocked
  audit, and no staging activation.
- [x] Export canonical sanitized evidence with zero Telegram, Official,
  production activation, bankroll/statistics, and scheduling mutations.

Next: obtain an authorized timestamped odds archive covering the immutable
2024/25 TEST window and a distinct post-TEST shadow window, then rerun all
calibration, betting, risk, stability, comparison, shadow, and audit gates.
No genuine Lab publication may be considered before those gates pass and
separate publication authorization is granted.

---

# REVIEWED REAL HISTORICAL DATA FOUNDATION

Status:

COMPLETED WITH HONEST PROMOTION BLOCKERS

- [x] Add typed append-only source review, manifests, file hashes, and evidence tiers.
- [x] Review OpenLigaDB ODbL usage for controlled internal derived-data research.
- [x] Import 2,142 genuine completed Bundesliga matches from seven seasons.
- [x] Build 2,085 exact live-78 examples with explicit missingness and coverage.
- [x] Pass a dedicated leakage audit before training.
- [x] Create an atomic chronological 1,459/313/313 TRAIN/VALIDATION/TEST split.
- [x] Train and VALIDATION-calibrate two compatible reviewed-real candidates.
- [x] Complete TEST-only predictive evaluation and calibration-quality review.
- [x] Keep betting evidence unavailable because genuine pre-kickoff odds are absent.
- [x] Persist insufficient comparison/shadow evidence and block staging activation.
- [x] Export sanitized canonical evidence with zero Telegram or Official mutations.

Next: lawfully acquire immutable pre-kickoff odds with event and capture-time
provenance, then rerun betting/risk evidence and calibration-quality review. Do
not consider a genuine Lab publication until the complete independent audit passes
and separate publication authorization is granted.

---

# CALIBRATION QUALITY AND EXTREME PROBABILITY REVIEW

Status:

COMPLETED

- [x] Reproduce and trace the exact Aberdeen `UNDER_2_5 = 0.999` path.
- [x] Persist per-target support, reliability, scoring, adjustment, and
  reconciliation evidence without mutating calibration artifacts.
- [x] Compare all 78 live inputs with TRAIN, VALIDATION, and TEST distributions.
- [x] Separate mathematical rank, calibration actionability, preview, and send
  eligibility.
- [x] Keep controlled-synthetic calibration send-ineligible and Official
  fail-closed.
- [x] Add deterministic operator inspection and sanitized evidence export.
- [x] Replay all 11 Aberdeen markets with zero Telegram or Official mutations.

---

# CALIBRATION EVIDENCE AND MARKET FRESHNESS SEPARATION

Status:

COMPLETED

- [x] Trace the original 7,200-second fit-age implementation and its history.
- [x] Separate immutable calibration evidence time from artifact creation time.
- [x] Add typed integrity, evidence, review, and Lab actionability statuses.
- [x] Keep odds, feature, and lineup freshness independent and fail-closed.
- [x] Keep controlled synthetic calibration evidence Lab/staging-only and
  Official fail-closed.
- [x] Preserve legacy inspection without fabricating or mutating timestamps.
- [x] Reproduce the original two-hour failure with deterministic regression
  coverage and complete the controlled audit/dry-run evidence workflow.

---

# RECENT LIVE-78 CALIBRATION CHAMPION FOUNDATION

Status:

COMPLETED

- [x] Recover the expected Real Match Lab commit onto a development branch.
- [x] Preserve all unrelated working-tree and operational artifacts.
- [x] Document the exact runtime calibration freshness timestamp semantics.
- [x] Add an injected recent controlled chronology without changing defaults.
- [x] Preserve TRAIN-only preprocessing, VALIDATION-only calibration, and
  TEST-only backtesting through the existing domain services.
- [x] Add a fail-closed live-78 active-champion freshness report.
- [x] Complete and retain the controlled chain, audit, staging activation,
  rollback/reactivation, Real Match Lab rehearsal, and canonical evidence.
- [x] Complete focused and full verification and commit the reviewed changes.

The source mode is explicitly
`CONTROLLED_SYNTHETIC_RECENT_CALIBRATION_REHEARSAL`; its performance is not a
claim of real predictive quality. Production activation and every publication,
Telegram, scheduler, and Official bankroll/statistics path remain unauthorized.

---

# LIVE FEATURE CONTRACT-COMPATIBLE MODEL FOUNDATION

Status:

COMPLETED

- [x] Expose the live 78-position model-input schema as the single authority.
- [x] Build leakage-safe historical rows in the exact live contract.
- [x] Preserve unavailable optional fields as explicit missing values.
- [x] Parameterize training, calibration, inference, and backtesting contracts.
- [x] Keep legacy 145-position artifacts distinct and incompatible.
- [x] Run compatible train, calibration, TEST backtest, comparison, promotion,
  shadow, staging activation, resolver, and Real Match Lab dry-run flows.
- [x] Preserve zero Telegram sends and zero Official publications.

Next: validate the foundation on a reviewed external historical dataset with
explicit venue-neutrality and richer pre-kickoff availability provenance.

---

# PRIORITY 1

## Stabilize Current Project

Status:

COMPLETED

Tasks

- [x] Complete Feature migration.
- [x] Fix TeamStrength migration.
- [x] Remove remaining runtime errors.
- [x] Verify project starts successfully.
- [x] Verify prediction pipeline.
- [x] Verify Telegram publishing without contacting the live channel.
- [x] Verify database initialization.
- [x] Verify repository layer.

Definition of Done

Project starts without exceptions.

---

# PRIORITY 2

## Prediction Engine

Status

TODO

Tasks

Improve rating calculation.

- [x] Complete deterministic Official Prediction Selection Engine foundation.
- [x] Complete Official Selection-to-Risk and Candidate Preparation integration.
- [x] Complete Registered Candidate-to-Quality Gate and Official Publication Pipeline integration.
- [x] Complete controlled manual end-to-end fixtures, operational CLI, diagnostics, recovery analysis, and operator runbook.

Review feature weights.

Review confidence thresholds.

Improve probability calculation.

Improve prediction explainability.

Definition of Done

Prediction engine stable.

---

# PRIORITY 3

## Feature System

Status

TODO

Tasks

Review every feature.

Remove duplicate calculations.

Normalize feature values.

Improve FeatureBuilder.

Improve TeamStrengthEngine.

Definition of Done

Feature system fully documented.

---

# PRIORITY 4

## Data Collection

Status

TODO

Tasks

Improve Football API caching.

Improve Standings collector.

Improve Match collector.

Improve History loading.

- [x] Complete the deterministic append-only Historical Match Data Import foundation.

Improve retry logic.

Definition of Done

Stable data collection.

---

# PRIORITY 5

## Telegram

Status

TODO

Tasks

Improve formatting.

Improve readability.

Improve notifications.

Improve weekly reports.

Improve monthly reports.

Improve result publishing.

Definition of Done

Professional Telegram output.

---

# PRIORITY 6

## Bank Manager

Status

TODO

Tasks

Public bankroll.

Weekly statistics.

Monthly statistics.

Bank growth.

Bank history.

Definition of Done

Automatic bankroll management.

---

# PRIORITY 7

## Backtesting

Status

IN PROGRESS

Tasks

- [x] Deterministic historical evaluation foundation.

- [x] Accuracy and hit rate.

- [x] ROI and profit/loss metrics.

- [x] Win rate.

- [x] League reports.

Definition of Done

Reliable backtesting.

---

# PRIORITY 8

## Optimization

Status

TODO

Tasks

Performance.

Database.

Caching.

Async.

Logging.

Imports.

Architecture cleanup.

Definition of Done

Production-ready performance.

---

# PRIORITY 9

## Testing

Status

TODO

Tasks

Unit Tests.

Integration Tests.

Regression Tests.

Performance Tests.

Definition of Done

Stable release.

---

# PRIORITY 10

## Version 1.0 Release

Status

TODO

Checklist

Production deployment.

Telegram running.

Public bankroll.

Automatic results.

Weekly reports.

Monthly reports.

Monitoring.

Definition of Done

GoalVision AI Version 1.0 released.

---

# COMPLETED TASKS

Move completed work here.

Never delete completed tasks.

Only append.

## 2026-07-31 - Recently Calibrated Live-78 Staging Champion

- Recovered preserved commit `27fb6a2` onto
  `goalvision/live-78-fresh-calibration` without touching unrelated work.
- Added an injected controlled chronology and produced immutable live-78 model
  and calibration artifacts through the real TRAIN, VALIDATION, and TEST
  services; the runtime freshness reference is the persisted calibration fit
  timestamp and remained fresh without timestamp mutation or policy changes.
- Completed compatible backtests, promotion, settled Shadow evidence,
  independent audit, manual staging activation/rollback, resolver and freshness
  inspection, and a deterministic all-11-market Real Match Lab rehearsal.
- Retained canonical non-production evidence at
  `docs/rehearsals/live_78_recent_calibration_champion_2026-07-31.json` with
  zero Telegram calls, sends, deliveries, Official publications, bankroll or
  statistics changes, production activation, scheduling, or startup execution.

## 2026-07-12 - Stabilize Current Project

- Completed the Feature and TeamStrength migration.
- Fixed model and feature imports.
- Removed obsolete bot startup code and unused AI initialization.
- Added safe football API failure handling and guaranteed client cleanup.
- Verified the prediction pipeline, Telegram service boundary, database initialization, and team repository with automated tests.
- Verified `python -m app.main` starts and exits without an unhandled exception when no match data is available.

## 2026-07-12 - League Strength Engine

- Added a centralized, normalized league-rating table.
- Added a validated League Strength Engine with injected ratings and unknown-league fallback.
- Injected the engine into the prediction pipeline without changing prediction outcomes.
- Added unit coverage for lookup, validation, fallback, dependency injection, and outcome isolation.

## 2026-07-12 - H2H Engine

- Added a typed H2H Engine with injected historical fixture data.
- Added finished-match, team-pair, duplicate, and maximum-history filtering.
- Added recency weighting and configurable insufficient-history confidence handling.
- Injected the engine into the prediction pipeline without changing prediction outcomes.
- Added unit coverage for empty, single, multiple, recent, duplicate, and normalized histories.

## 2026-07-12 - Rest Days Engine

- Added a typed Rest Days Engine using only finished-fixture timestamps.
- Added configurable rest capping and normalized home-versus-away comparison.
- Injected the engine into the prediction pipeline without changing prediction outcomes.
- Added unit coverage for missing, equal, advantaged, capped, unfinished, and normalized histories.

## 2026-07-13 - AI Quality Score Framework

- Added deterministic, typed supporting-data quality scoring from 0 to 100.
- Centralized and validated signal weights, critical signals, and penalties.
- Added completeness, consistency, warnings, and explanation-ready reason codes.
- Injected the framework into the prediction pipeline without changing predictions or publication.
- Added unit coverage for complete, empty, partial, conflicting, critical-missing, invalid, deterministic, and isolated behavior.

## 2026-07-13 - AI Quality Score Pipeline Integration

- Added typed prediction assessments containing predictions, quality results, team contexts, signals, reason codes, and supporting metadata.
- Built real quality signals from team form, standings, configured league ratings, cached H2H/rest history, venue history, attack, and defense data.
- Preserved missing data explicitly and added deterministic component-conflict measurement.
- Reused the existing prediction method so assessments do not duplicate or alter prediction calculations.
- Added integration coverage for complete, partial, missing, deterministic, isolated, and Telegram-neutral behavior.

## 2026-07-13 - Deterministic Prediction Explanations

- Added typed deterministic explanations to every prediction assessment.
- Added concise positive factors, risks, missing-data labels, reason codes, and supporting metrics.
- Derived explanations only from predictions, quality results, team contexts, league configuration, and typed H2H/rest history.
- Preserved a single prediction and quality-score calculation per assessment.
- Added coverage for home/away advantages, conflicts, missing and neutral data, determinism, factual isolation, and prediction isolation.

## 2026-07-13 - Telegram Prediction Presentation Framework

- Added typed compact prediction, detailed explanation, result, and inline-action presentation models.
- Added deterministic Telegram-safe HTML formatters with complete text escaping.
- Kept compact posts separate from concise “Why this pick?” analysis.
- Kept AI Quality Score display configurable and disabled by default pending calibration.
- Added unit coverage for home/away picks, optional odds and quality, details, risks, escaping, determinism, and network isolation.

## 2026-07-13 - Telegram Prediction Interaction Framework

- Added typed interaction actions for deterministic explanation retrieval plus future statistics and bankroll placeholders.
- Added versioned, validated callback identifiers with no secrets or raw explanation data and an enforced Telegram size limit.
- Added a dependency-injected assessment/explanation lookup boundary with expiry and missing-data handling.
- Added idempotent duplicate handling that reuses the first formatted explanation response.
- Kept production Telegram sending unchanged and added isolated callback coverage without network access.

## 2026-07-13 - Prediction Result Resolution Framework

- Added typed published-prediction, fixture-result, resolution, status, reason-code, and audit models.
- Added deterministic Match Winner settlement for home, away, and draw picks through a centralized extensible rule registry.
- Added configurable handling for pending, cancelled, postponed, abandoned, finished, and unsupported fixture statuses.
- Added a dependency-injected repository boundary with terminal-result idempotency and immutable prior settlements.
- Kept result publishing, bankroll settlement, live API access, and database schemas unchanged.

## 2026-07-13 - Persistent Prediction Result Storage

- Added an additive, versioned SQLite migration for published predictions and terminal settlement audit data.
- Added persistent pending-prediction loading, idempotent publication writes, immutable result settlement, and result-history retrieval.
- Stored prediction identity, fixture, market, pick, optional odds and stake, timestamps, final score, status, reason codes, and settlement rule version.
- Preserved existing database tables and data while reusing the project Database abstraction.
- Kept Telegram result publishing, bankroll settlement, prediction policy, and application startup behavior unchanged.

## 2026-07-14 - Official Bankroll Settlement Framework

- Added a Decimal-based Official bankroll account starting at EUR 10,000.
- Added explicit STANDARD, STRONG, and ELITE stake tiers at 1%, 2%, and 3%, with separate 3-, 4-, and 5-star public metadata.
- Added deterministic WON, LOST, VOID, PENDING, and UNRESOLVED settlement handling with immutable audit transactions.
- Added dependency-injected bankroll repositories, atomic idempotency, snapshots, and strict product separation.
- Kept Telegram, prediction policy, database schemas, and automatic tier selection unchanged.

## 2026-07-14 - Persistent Official Bankroll Storage

- Added additive SQLite account and immutable transaction migrations without altering existing result history.
- Initialized the Official EUR 10,000 account exactly once and preserved its balance and settled prediction IDs across restarts.
- Added Decimal-safe persistent account loading, atomic idempotent transaction storage, and chronologically ordered history retrieval.
- Integrated explicit-tier bankroll settlement with existing typed prediction resolution results.
- Kept Telegram, automatic jobs, prediction policy, other product bankrolls, and automatic tier selection disabled.

## 2026-07-14 - Automatic Prediction Settlement Orchestration

- Added one deterministic application service for pending prediction loading, deduplicated fixture retrieval, result persistence, and Official bankroll settlement.
- Added typed settlement candidates, batch requests, per-prediction outcomes, reports, and failure reason codes.
- Enforced result-first persistence boundaries and restart-safe bankroll recovery for partial failures.
- Added per-fixture failure isolation, duplicate handling, aggregate audit counts, timestamps, and rule versions.
- Kept scheduling, Telegram publishing, live API coupling, prediction policy, and non-Official bankrolls disabled.

## 2026-07-14 - Official Telegram Result Publication Framework

- Added deterministic WON, LOST, and VOID Official result messages using the existing presentation layer.
- Added persistent, restart-safe publication audit state with atomic delivery claims, retryable confirmed failures, and duplicate prevention.
- Included optional league/team context, final score, odds, public stake stars, Decimal stake and profit/loss values, and updated Official bankroll.
- Kept internal stake percentages, AI Quality Score, other product channels, recurring scheduling, and live Telegram wiring disabled.
- Added isolated SQLite and fake-Telegram coverage for formatting, escaping, retries, database failures, idempotency, and mixed batches.

## 2026-07-15 - Backtesting Engine Foundation

- Added an isolated, typed `app/backtesting` package for deterministic historical evaluation.
- Added immutable one-unit evaluation records with Decimal probabilities, odds, profit/loss, results, and WON/LOST/VOID outcomes.
- Added leakage validation that rejects feature or odds timestamps newer than the prediction timestamp.
- Added deterministic hit rate, ROI, profit, odds, drawdown, Brier Score, Log Loss, CLV, and probability metrics.
- Added pluggable walk-forward window and evaluator interfaces without model training or optimization.
- Added edge-case and repeatability coverage without changing production prediction, publication, settlement, scheduling, or database behavior.

## 2026-07-15 - Probability Calibration Engine Foundation

- Added isolated immutable calibration observations with explicit binary outcomes and VOID rejection.
- Added deterministic equal-width and explicit-boundary binning with retained empty bins.
- Added Decimal Brier Score, Log Loss, ECE, MCE, bin reports, and raw-versus-calibrated comparisons.
- Added a fully functional Identity calibrator plus honest Platt and Isotonic fitting interfaces that do not fabricate fitted behaviour.
- Added immutable fit metadata, model/competition/market/odds-band scopes, minimum-sample fallback, and actual-scope reporting.
- Added strict prediction/outcome cutoff, target-isolation, duplicate-timestamp, scope, and model-version protections.
- Kept live prediction generation, Telegram publication, scheduling, bankrolls, and database schemas unchanged.

## 2026-07-15 - Publication Quality Gate Foundation

- Added an isolated deterministic decision pipeline returning APPROVED, REJECTED, or REVIEW_REQUIRED with ordered audit checks and reason codes.
- Encoded configurable Official single-bet, minimum-odds, correct-score, timing, evidence, calibration, value, conflict, uncertainty, exposure, and duplicate policies.
- Represented the reviewed two-selection combo exception without creating or publishing combo bets.
- Added typed calibration metadata consumption, unrounded Decimal expected-value calculation, minimum-sample enforcement, and raw-probability opt-in controls.
- Added explicit evidence states, per-category evidence policy, deterministic decision precedence, and normalized Official duplicate identities.
- Kept prediction generation, Telegram publication, bankroll settlement, scheduling, all product channels, and database schemas unchanged.

## 2026-07-15 - Publication Quality Gate Shadow Evaluation Foundation

- Added immutable shadow requests, snapshots, decisions, safe errors, settlement facts, and deterministic comparison reports.
- Added migration v4 with isolated shadow evaluation and error audit tables plus prediction, fixture, date, status, publication, policy, and stage lookup support.
- Added insert-once persistence keyed by prediction, policy version, and evaluation stage while allowing INITIAL_CANDIDATE, PRE_PUBLICATION, and FINAL_PRE_KICKOFF observations.
- Added disabled-by-default runtime observation immediately after prediction assessment without using the shadow result to alter sorting or publication behaviour.
- Added explicit missing-data adaptation for currently unavailable odds, calibration, lineup, injury, consensus, exposure, and sample-size facts.
- Added idempotent authoritative WON, LOST, and VOID settlement enrichment without bankroll or publication side effects.
- Added descriptive and clearly labelled hypothetical one-unit comparison reports using only evaluation-time offered odds.
- Kept Quality Gate enforcement, Telegram publication decisions, scheduling, betting, bankroll mutation, settlement polling, and all non-Official products disabled.

## 2026-07-16 - Odds Observation and CLV Tracking Foundation

- Added an isolated immutable `app/odds` domain for typed sources, markets, selections, observations, snapshots, consensus, movement, closing odds, CLV, and safe ingestion errors.
- Added deterministic normalization and validation for Decimal odds, exchange commission, source/fixture/market/selection identities, timezone-aware cutoffs, source status, and kickoff policy.
- Added migration v5 with lossless Decimal text storage, insert-once observations, source metadata, separate closing-odds records, deterministic uniqueness constraints, and indexed lookup paths.
- Added deterministic opening/latest queries, consensus and complete-market no-vig calculations, model-versus-market disagreement, odds movement, closing fallback selection, and the established `publication_odds / closing_odds - 1` CLV formula.
- Added provider contracts plus Static and Null providers, idempotent batch ingestion, backtesting conversion with leakage checks, and a shadow-only odds enrichment adapter that never uses future observations.
- Kept live odds network access, Telegram publication, Quality Gate enforcement, betting, bankroll mutation, scheduling, and all non-Official product behavior disabled.

## 2026-07-16 - Team Availability Evidence Foundation

- Added an isolated immutable `app/team_availability` domain for player availability, injuries, suspensions, predicted and confirmed lineups, substitutes, formations, evidence state, conflicts, and safe ingestion audit data.
- Added migration v6 with separate availability-source, player-observation, lineup-observation, and lineup-player tables using insert-once uniqueness and deterministic fixture/team/player/time lookups.
- Added deterministic freshness, lineup-confirmation, snapshot, conflict-preservation, Quality Gate mapping, shadow enrichment, backtesting leakage, and no-op player-impact foundations.
- Added Static, Null, and honest existing-football-API adapters; the current API surface does not expose lineup, injury, suspension, player, coach, or squad evidence and therefore produces no fabricated records.
- Added disabled-by-default one-shot runtime ingestion without scheduling, network activation, Telegram publication, bankroll mutation, betting, or Quality Gate enforcement.

## 2026-07-16 - Opponent-Adjusted Form and xG Evidence Foundation

- Added an isolated immutable `app/form_features` domain for normalized completed-match observations, raw and venue form, deterministic recency weighting, transparent opponent adjustment, conflicts, evidence status, and safe ingestion reports.
- Added migration v7 with insert-once historical match observations, lossless Decimal text fields, fixture/team/competition indexes, restart persistence, and no changes to migrations v1-v6.
- Added deterministic on-demand snapshots for wins/draws/losses, points, goals, clean sheets, failed-to-score counts, goal rates, venue splits, weighted form, opponent-adjusted attack/defense, freshness, completeness, exclusions, and result/goal-rate divergence.
- Added strict no-fake-xG contracts: the existing finished-fixtures provider supplies goals but no genuine xG, shots, cards, penalties, possession, event timing, or player data, so those fields remain explicitly missing.
- Added provider, ingestion, Quality Gate context, shadow enrichment, walk-forward backtesting, disabled-by-default runtime, Null-provider, and prediction-isolation foundations without enabling publication, betting, bankroll mutation, scheduling, or non-Official products.

## 2026-07-16 - Production Calibration Fitting

- Added deterministic Platt fitting using clipped logit inputs, damped Newton/IRLS optimization, L2 regularization, explicit convergence rules, immutable coefficients, diagnostics, and typed unsupported-fit failures.
- Added deterministic Isotonic fitting using grouped Pool Adjacent Violators regression with weighted blocks and right-continuous piecewise-constant prediction and extrapolation.
- Added scope-aware sample and class-balance policies, explicit broader-scope and Identity fallback audit trails, fitted walk-forward target outputs, and conservative validation-window method selection.
- Added stable versioned JSON-safe calibrator serialization with lossless Decimal strings, strict malformed/version rejection, and safe positive-infinite Log Loss representation.
- Kept calibration fitting isolated from live prediction generation, Quality Gate enforcement, Telegram, bankrolls, scheduling, betting, and non-Official products.

## 2026-07-16 - Calibration Registry and Model Monitoring Foundation

- Added an immutable calibration artifact registry using the existing safe versioned calibrator JSON contract, deterministic artifact identity, idempotent equivalent-artifact registration, and audited explicit status transitions.
- Added migration v8 with isolated calibration artifact, status-history, model-monitoring run, and alert tables using lossless Decimal text, deterministic JSON, insert-once constraints, immutable triggers, and indexed scope/status/time queries.
- Added deterministic fixed-count, interval, rolling, and explicit monitoring windows driven only by caller-supplied timestamps.
- Added model performance reports by reusing the existing backtesting and calibration metric services for hit rate, ROI, profit, drawdown, Brier Score, Log Loss, ECE, MCE, and CLV.
- Added conservative threshold-based drift findings, fixed-bin PSI with explicit epsilon smoothing, existing reliability-bin drift, insufficient-sample protection, persisted one-shot monitoring runs, and idempotent alerts.
- Added authoritative Official, settled Quality Gate Shadow, and backtesting monitoring adapters with deterministic Shadow-stage selection and Official-to-Shadow-to-backtesting deduplication priority.
- Kept calibrator activation, automatic promotion or retirement, live prediction changes, Quality Gate enforcement, Telegram alerts/publication, bankroll mutation, betting, scheduling, and non-Official products disabled.

## 2026-07-16 - Risk, Stake Recommendation, and Exposure Assessment Foundation

- Added an isolated immutable `app/risk_management` domain that consumes supplied bankroll and exposure snapshots and returns structured ELIGIBLE, REDUCED_STAKE, REVIEW_REQUIRED, or INELIGIBLE audit decisions.
- Added a transparent Official-only default stake policy using unrounded Decimal 1%, 2%, and 3% internal bands, final EUR-cent quantization, configurable EV/evidence requirements, and public 1-to-3-star mapping without Telegram formatting.
- Added exact drawdown states at 5%, 10%, and 15%, conservative loss-streak caps, explicit no-martingale behaviour, and deterministic reduction-only precedence.
- Added typed single, daily, competition, fixture, team, market, correlated-group, and unsettled exposure evaluation without reserving or mutating exposure.
- Added Quality Gate consumption, special combo-exception representation, explicit product-policy separation, and historical Shadow recommendation adapters that reject missing or future bankroll snapshots.
- Added deterministic flat-unit, fixed-1%, fixed-2%, and recommended-policy backtesting comparison with ROI, drawdown, losing streak, volatility proxy, stake concentration, skips, and stake/drawdown segmentation.
- Kept automatic staking, bankroll mutation, exposure reservation, Quality Gate enforcement, Telegram changes, scheduling, betting, and all non-Official product activation disabled.

## 2026-07-20 - Probability Calibration Post-Prediction Engine

- Added the isolated deterministic `app/probability_calibration` package as a post-prediction transformation boundary without changing prediction generation.
- Added configuration-selected Identity, Platt Scaling, and Isotonic Regression by composing the existing production calibration fitters.
- Added strict model-version and historical-cutoff validation, monotonic-order enforcement, and `[0.001, 0.999]` output clamping.
- Added immutable reports containing raw and calibrated probabilities, delta, method, Brier Score, Log Loss, ECE, MCE, reliability bins, confidence histograms, timestamp, and model version.
- Added migration v9 with lossless Decimal text storage and database-enforced append-only calibration run history.
- Kept prediction selection, Telegram publication, bankroll, risk management, scheduling, external APIs, and all product policies unchanged.

## 2026-07-20 - Official Publication Quality Gate

- Added the isolated deterministic `app/publication_quality_gate` package for fully prepared Official candidates immediately before publication eligibility.
- Added immutable configurable checks for calibrated probability, Official odds, supplied/recomputed EV, confidence, calibration quality, model health, freshness, supported market semantics, optional lineup/injury evidence, risk, exposure, bankroll scope, and duplicate publication state.
- Added fixed REJECTED, REVIEW_REQUIRED, APPROVED precedence with ordered internal reason codes, explanations, normalized input snapshots, and deterministic SHA-256 fingerprints.
- Added migration v10 with database-enforced append-only Official Quality Gate evaluation history and idempotent identical-candidate persistence.
- Added a fail-closed eligibility wrapper that persists evaluations before forwarding only APPROVED candidates to an injected atomic publisher while leaving claim and retry ownership unchanged.
- Kept prediction generation, market selection, bankroll balances, stake calculation, settlement, result publication, Telegram formatting, scheduling, external APIs, and non-Official products unchanged.

## 2026-07-20 - Official Prediction Candidate Assembly and Publication Orchestration

- Added the isolated deterministic `app/official_prediction_orchestration` application boundary for complete supplied Official facts.
- Added strict model, match, market, calibration, health, risk, exposure, bankroll, and publication-state identity validation with deterministic newest-record selection.
- Added Decimal EV verification that preserves the upstream supplied value and canonical versioned candidate fingerprints over every material selected fact.
- Added persisted gate-before-publisher sequencing, typed dry-run and disabled-publisher outcomes, safe retryable/indeterminate delivery mapping, and identical-input idempotency.
- Added migration v11 with append-only immutable Official orchestration history and safe Quality Gate foreign-key linkage.
- Added a production service factory without scheduling, startup publication, fake production data, direct Telegram calls, bankroll mutation, or non-Official product changes.

## 2026-07-20 - Official Prediction Message Assembly and Atomic Publisher Adapter

- Added the isolated `app/official_prediction_publication` package for deterministic Telegram HTML assembly from approved orchestration and supplied public facts only.
- Added supported Official match-winner, double-chance, totals, and both-teams-to-score formatting; calibrated-only public probability; strict HTML escaping; approved reasoning limits; responsible-betting language; and fail-closed exact-score, unsafe-language, and unsupported-market rejection.
- Added exact 1%, 2%, and 3% public stake-star mapping with conservative lower-band mapping for reduced stakes and rejection of zero or ineligible recommendations.
- Added immutable publication payloads and canonical SHA-256 message fingerprints that exclude raw probability, internal expected value, stake percentage, exposure, calibration metrics, internal audit content, destination identifiers, and credentials.
- Added migration v12 with append-only immutable Official prediction publication events and atomic claim/send/finalize sequencing that distinguishes confirmed retryable failures from indeterminate delivery outcomes.
- Added a concrete publisher adapter and production composition path that reuse the existing Telegram sender and settlement-facing published-prediction writer without changing prediction generation, selection, bankroll, risk, exposure, settlement, result publication, scheduling, or non-Official products.

## 2026-07-20 - Official Prediction Run Coordinator and Manual Batch Boundary

- Added the isolated `app/official_prediction_run_coordinator` application layer over the existing single-prediction orchestration callable.
- Added injected persisted-candidate discovery, explicit Official-only state classification, deterministic kickoff/creation/prediction ordering, bounded lookahead and batch limits, immutable-fingerprint rejection freshness, and dry-run-only force review without bypassing the Quality Gate.
- Added centralized confirmed-failure retry limits and cooldowns while permanently blocking automatic published, active-claim, indeterminate, expired, malformed, non-Official, and unchanged rejected/review-required candidates.
- Added sequential failure-isolated batch execution, exact orchestration outcome mapping, validated immutable counters, safe stop-after-failure policy, structured status-only logging, and no hidden time, randomness, fetching, or startup execution.
- Added canonical SHA-256 run idempotency, existing-terminal result reuse, incomplete-run replay blocking, and migration v13 with append-only immutable run start/terminal events and ordered item outcomes.
- Added `build_official_prediction_run_coordinator(...)` and the explicit dry-run-default `run_official_prediction_batch(...)` manual callable without scheduling, provider ingestion, real credential construction, or changes to prediction, bankroll, risk, publication, settlement, or non-Official product logic.

## 2026-07-21 - Official Prediction Candidate Ingestion and READY Registry

- Added the isolated `app/official_prediction_candidate_registry` boundary for complete supplied pre-match Official facts without prediction, calibration, EV, risk, exposure, bankroll, Quality Gate, message, or publication calculations.
- Added strict Official-only market, identity, Decimal, timestamp, scope, live/accumulator, and structured reasoning validation with deterministic Unicode, whitespace, identifier, market, selection, line, Decimal, timestamp, and reasoning normalization.
- Added canonical logical-identity and material-content SHA-256 fingerprints; source events remain provenance, registration time remains audit-only, and identical content is idempotent across ingestion attempts.
- Added append-only READY, SUPERSEDED, WITHDRAWN, and INVALIDATED lifecycle history with transaction-safe version allocation, concurrent ingestion protection, explicit withdrawal/invalidation, published-state protection, and no hard deletion or historical reactivation.
- Added migration v14 with immutable Official candidate version and lifecycle-event tables, unique content and logical-version identities, deterministic snapshots, foreign keys, discovery indexes, and update/delete prevention triggers.
- Added a registry-backed coordinator source and injected assembly-context port that preserve registry traceability while leaving calibration, model-health, risk, exposure, bankroll, Quality Gate, atomic publication, and retry selection in the existing orchestration stack.
- Added `build_official_prediction_candidate_registry(...)`, `build_registry_candidate_source(...)`, and the explicit `register_official_prediction_candidate(...)` callable without automatic ingestion, scheduling, external providers, or startup execution.

## 2026-07-21 - Pre-Match Data Snapshot and Feature Store Foundation

- Added isolated `app/match_data_snapshot` and `app/feature_store` packages for supplied pre-match provenance and deterministic model-ready features without provider, prediction, candidate, or publication coupling.
- Added strict partial-data-preserving validation and normalization for identity, timing, status, form, venue splits, season aggregates, head-to-head, availability, context, and optional odds using Unicode, UTC, and lossless Decimal contracts.
- Added logical match identity and complete material-content SHA-256 fingerprints, idempotent identical registration, sequential immutable versions, and append-only ACTIVE, SUPERSEDED, WITHDRAWN, and INVALIDATED history.
- Added the centralized 78-feature `official_prematch_features_v1` registry, Decimal-only final quantization, explicit zero-denominator/missingness rules, completeness/sample/evidence indicators, and odds/future-data leakage protection.
- Added deterministic feature fingerprints and append-only feature-set history linked to source snapshots, plus explicit historical replay without enabling inactive snapshots by default.
- Added migration v15 with immutable `match_data_snapshot_versions`, `match_data_snapshot_lifecycle_events`, and `match_feature_sets` tables, safe indexes, unique identities, foreign keys, and update/delete triggers.
- Added `build_match_data_snapshot_service(...)`, `register_match_data_snapshot(...)`, `build_feature_store_service(...)`, and `generate_match_feature_set(...)` without external fetching, automatic ingestion, scheduling, prediction generation, training, live processing, or startup execution.

## 2026-07-21 - Prediction Model Input Builder

- Added isolated `app/model_input_builder` as the deterministic bridge from persisted Feature Store output to future machine-learning engines, without implementing or invoking inference or prediction logic.
- Added immutable `goalvision_model_input_v1` with fixed registry-derived 78-feature ordering, typed per-position metadata, explicit compatibility, source snapshot/feature provenance, and no dictionary-dependent ordering.
- Added strict persisted-provenance and canonical Feature Store fingerprint verification, schema/compatibility enforcement, duplicate/unknown/order checks, type and finite-Decimal validation, and fail-closed required recent-form baselines.
- Added missing-value preservation with an ordered boolean mask, ordered missing-feature list, and deterministic available-position completeness score; no zero or learned imputation is performed.
- Added canonical model-input SHA-256 identity over schema, compatibility, ordered names/typed values, missingness, and source feature fingerprint while excluding execution time.
- Added migration v16 with immutable append-only `model_input_vectors`, unique identities, deterministic serialization, Feature Store foreign-key linkage, indexes, and update/delete triggers.
- Added `build_model_input_builder(...)` and `generate_model_input(...)` without training, inference, probability calibration, odds, market, candidate registry, Quality Gate, bankroll, Telegram, scheduling, or live coupling.

## 2026-07-21 - Official Selection-to-Risk and Candidate Preparation

- Added isolated `app/official_candidate_preparation` to re-verify one persisted selected decision and value assessment, consume explicit immutable Official EUR bankroll/exposure facts, and call the existing risk service exactly once.
- Added explicit pre-publication-gate risk phase semantics without claiming Quality Gate approval or changing existing post-gate behavior, stake thresholds, exposure limits, bankroll logic, or selection policy.
- Registered candidates only for exact `ELIGIBLE` or `REDUCED_STAKE` outcomes; persisted `REVIEW_REQUIRED` and `INELIGIBLE` as typed no-registration decisions without a Candidate Registry call.
- Preserved selection, model, calibration, value, risk, stake, bankroll, and exposure provenance while leaving candidate identity, versioning, lifecycle, and publication protection under Candidate Registry authority.
- Added migration v21 with immutable append-only preparation execution/risk snapshot tables, structured candidate provenance, deterministic fingerprints, query indexes, foreign keys, and update/delete triggers.
- Added production composition, explicit callable, read-only downstream Quality Gate handoff, idempotent terminal replay, conflict handling, recovery-safe registry interaction, and comprehensive integration/migration/regression tests.

---

# NEXT PRIORITIES

- [x] Probability Calibration Engine foundation.
- [x] Publication Quality Gate foundation.
- [x] Quality Gate shadow-mode persistence foundation.
- [x] Safe disabled-by-default runtime observation.
- [x] Shadow settlement enrichment foundation.
- [x] Shadow comparison reporting foundation.
- [x] Odds domain foundation.
- [x] Odds persistence foundation.
- [x] CLV calculation foundation.
- [x] Consensus and disagreement foundation.
- [x] Shadow odds-enrichment adapter.
- [x] Provider adapter contracts.
- [x] Team availability domain foundation.
- [x] Lineup and injury persistence.
- [x] Deterministic availability snapshots.
- [x] Quality Gate availability adapter.
- [x] Shadow availability enrichment.
- [x] Team availability provider adapter contracts.
- [x] Opponent-adjusted form foundation.
- [x] Historical match normalization and persistence.
- [x] Deterministic form snapshots.
- [x] Venue and recency weighting.
- [x] Genuine xG evidence contracts and no-fake-xG policy.
- [x] Quality Gate form adapter.
- [x] Shadow form enrichment.
- [x] Backtesting form adapter.
- [x] Production Platt fitting.
- [x] Production Isotonic fitting.
- [x] Deterministic calibrator serialization.
- [x] Walk-forward fitted calibration.
- [x] Calibration method comparison and conservative selection.
- [x] Calibration artifact registry foundation.
- [x] Immutable artifact status history.
- [x] Deterministic model performance reports.
- [x] Drift detection foundation.
- [x] Persisted monitoring runs and alerts.
- [x] Shadow/backtesting monitoring adapters.
- [x] Risk assessment domain foundation.
- [x] Official stake recommendation foundation.
- [x] Drawdown and loss-streak guards.
- [x] Exposure limit evaluation.
- [x] Public stake-star mapping.
- [x] Shadow risk recommendation adapter.
- [x] Risk-policy backtesting comparison.
- [x] Immutable model comparison and promotion-recommendation foundation.
- [x] Immutable pre-match match-data snapshots.
- [x] Versioned deterministic feature-store foundation.
- [x] Versioned prediction model-input builder.
- [x] Deterministic prediction inference engine foundation.
- [x] Calibrated market probability assembly foundation.
- [x] Market probability and value assessment foundation.
- Lineup Impact Engine.
- Richer provider-backed Opponent Adjusted xG.

---

# DISCOVERED TASKS

If new work is discovered during development,

add it here.

Do not interrupt higher priority work.

Review after completing the current priority.

- Collect a sufficient settled Quality Gate shadow sample before threshold or enforcement decisions.
- Calibrate Quality Gate thresholds from settled shadow observations.
- Integrate the Quality Gate with prediction selection only after shadow-mode review and explicit production-enforcement approval.
- Integrate approved Quality Gate decisions with Official Telegram publication only after explicit product review.
- Add a persistent active-publication duplicate checker adapter.
- Integrate exposure inputs with the Official bankroll without allowing the gate to mutate balances.
- Integrate a reviewed official odds provider only when genuine licensed/provider data is available.
- Add scheduled odds ingestion only after operational review.
- Automate opening/reference/publication/pre-kickoff/closing role assignment after the observation foundation is proven.
- Add CLV reporting to Official weekly statistics after publication and closing roles are reliably populated.
- Add real-time lineup refresh near kickoff only after a genuine provider endpoint and operational schedule are reviewed.
- Build a calibrated player-strength and lineup-impact model only after reliable minutes, starts, ratings, or internal player-strength inputs exist.
- Integrate a richer licensed event/xG provider only when genuine xG, shots, cards, penalties, possession, and event timing are available.
- Add scheduled historical-form ingestion only after operational review.
- Integrate a reviewed real pre-match model artifact without implicit loading.
- Build calibrated market prediction assembly after inference and calibration evidence is approved.
- Add group-aware calibration only under a new reviewed policy/schema version.

- Gather a sufficient settled Shadow sample before monitoring threshold decisions.
- Statistically tune drift thresholds after sufficient historical evidence exists.
- Add scheduled monitoring execution only after operational review.
- Add Telegram/Admin monitoring alert presentation only after product review.
- Define an automatic artifact promotion policy only after offline and Shadow evidence is sufficient.
- Activate reviewed calibration artifacts in prediction runtime only after explicit approval.
- Persist Shadow risk audit records only after a reviewed persistence consumer exists.
- Integrate authoritative historical bankroll snapshots before historical risk reporting.
- Statistically validate stake and exposure thresholds on separate evaluation samples.
- Integrate exposure with bankroll reservations only after explicit operational review.
- Keep production Quality Gate enforcement disabled pending settled Shadow evidence.
- Build the Publication Quality Gate after calibration is production-proven.
- Add CLV reporting to weekly statistics without changing prediction selection policy.
- Build a reviewed Lineup Impact Engine.
- Build Opponent Adjusted xG as an isolated, backtested feature.
- Replace goals-only form inputs with genuine provider xG only after a reviewed richer provider integration.

- Calibrate Quality Score weights through backtesting.
- Integrate Quality Score into Telegram display only after calibration and product review.
- Consider publication-threshold integration only after calibration proves an explicit threshold improves quality.
- Add expandable deterministic analysis to Telegram only after product review.
- Consider an optional LLM wording layer only after deterministic explanations are proven reliable; it must never alter prediction facts.
- Integrate presentation actions with Telegram interactions only after product review.
- Keep AI Quality Score display blocked until backtest calibration is complete.
- Integrate WON/LOST/VOID result presentation with result publishing in a future task.
- Wire the prediction interaction handler into production Telegram callbacks after product review.
- Implement the future statistics button data lookup and presentation.
- Implement the future bankroll button data lookup and presentation.
- Integrate result-resolution persistence with the production database in a future task.
- Integrate WON/LOST/VOID presentation with Telegram publishing in a future task.
- Integrate resolved results with the correct product bankroll only in a future reviewed task.
- Wire persistent WON/LOST/VOID history into Telegram result publication in a future task.
- Apply resolved outcomes to the correct product bankroll only in a future reviewed task.
- Build weekly statistics from persistent result history in a future task.
- Add persistent database storage for Official bankroll accounts and transactions.
- Add Telegram presentation for Official bankroll snapshots and stake-star ratings.
- Build weekly Official statistics from immutable bankroll transaction history.
- Backtest automatic stake-tier selection before connecting tiers to prediction confidence or AI Quality Score.
- Build separate reviewed bankroll systems for High Risk and Combo without mixing Official history.
- Orchestrate automatic result-to-bankroll settlement only after the explicit workflow is reviewed.
- Add coordinated Telegram result and Official bankroll messages in a future task.
- Build weekly Official statistics from persistent bankroll and result history.
- Calibrate automatic stake-tier selection through backtesting before enabling it.
- Schedule recurring settlement execution only after operational review.
- Publish coordinated Telegram WON/LOST and bankroll messages in a future task.
- Generate weekly Official statistics from settlement reports and persistent histories.
- Add operational settlement monitoring, retry metrics, and alerts.
- Coordinate scheduled settlement and result publication only after operational review.
- Generate weekly Official reports from immutable result and bankroll histories.
- Send publication failures and stuck-delivery claims to the Admin channel in a future task.
- Integrate the operations CLI with application-owned staging/production Telegram credential resolution only after deployment-specific controls are reviewed.
- Keep automatic Official discovery, scheduling, provider ingestion, bankroll/exposure retrieval, and startup execution disabled until separately approved.

## 2026-07-22 - Historical Match Data Import Foundation

- Added the strict `goalvision_historical_dataset_v1` supplied-dataset boundary.
- Added deterministic Unicode/team identity and UTC normalization with
  fail-closed score, result, statistics, lineup, duplicate, and kickoff checks.
- Added canonical SHA-256 identities for dataset content, provider/natural match
  identity, normalized match content, statistics, and lineups.
- Added migration v23 with atomic append-only import, match-version, statistics,
  and lineup persistence plus update/delete rejection triggers.
- Added exact replay idempotency, cross-version match reuse, immutable correction
  versions, conflict detection, and full transaction rollback.
- Kept live fetching, scheduling, provider polling, feature generation, model
  training, prediction, backtesting, publication, Telegram, and startup imports
  outside this foundation.

## 2026-07-22 - Historical Training Dataset Builder Foundation

- Added the immutable `historical_training_features_v1` and
  `historical_training_labels_v1` contracts over explicitly selected imports.
- Added strict source-kickoff-before-target enforcement, independent leakage
  inspection, fixed Decimal-safe feature ordering, masks, provenance, and
  deterministic labels without correct-score output.
- Added centralized last-3/5/10, venue, season, head-to-head, rest/congestion,
  and prior-statistics projection with no target-match or future information.
- Added migration v24 with atomic append-only builds, examples, source linkages,
  exclusions, foreign keys, uniqueness, indexes, and update/delete guards.
- Added immutable request/example/dataset fingerprints, replay idempotency,
  request conflict handling, bounded streaming, and read-only inspection.
- Kept splitting, training, calibration fitting, backtesting, model comparison,
  promotion, shadow evaluation, fetching, scheduling, prediction, publication,
  and Telegram activity outside this foundation.

## 2026-07-22 - Historical Dataset Split Foundation

- Added typed explicit-boundary, ratio-by-chronology, and bounded expanding-
  window split strategies over one immutable verified training dataset.
- Added strict partition chronology, indivisible equal-kickoff groups,
  deterministic ordering, explicit buffer exclusions, and no randomization.
- Added immutable per-fold assignments, achieved counts/ratios, all-11-label
  reporting, bounded partition streaming, and independent integrity inspection.
- Added canonical request, assignment, fold, and complete split SHA-256
  identities with exact replay idempotency and immutable request conflicts.
- Added migration v25 with atomic append-only split, fold, and assignment
  persistence, foreign keys, uniqueness, indexes, and update/delete guards.
- Kept model training, hyperparameter tuning, calibration fitting, inference,
  backtesting, model comparison/promotion, shadow evaluation, fetching,
  scheduling, publication, and Telegram outside this foundation.

## 2026-07-22 - Historical Model Training Foundation

- Added the explicit TRAIN-only `MULTI_TARGET_LOGISTIC_REGRESSION_V1` baseline
  over verified immutable split folds and the exact 145-feature schema.
- Added deterministic TRAIN-fitted median imputation and standard scaling,
  evaluation-only VALIDATION handling, strict TEST isolation, class-support and
  convergence rejection, and canonical raw 11-target probability validation.
- Added safe executable-free JSON-compatible artifacts with ordered parameters,
  convergence evidence, compatibility metadata, complete source provenance,
  descriptive TRAIN/VALIDATION metrics, and read-only inference reproduction.
- Added request, preprocessing, estimator, artifact, and run SHA-256 identities,
  exact replay idempotency, immutable request conflicts, and atomic persistence.
- Added migration v26 with six append-only training/artifact/target/
  preprocessing/example/metric tables, foreign keys, uniqueness, indexes, and
  twelve update/delete guards.
- Kept calibration fitting, backtesting, model comparison/promotion, shadow
  evaluation, live inference wiring, fetching, scheduling, publication, and
  Telegram outside this foundation.

## 2026-07-22 - Historical Probability Calibration Fitting Foundation

- Added explicit VALIDATION-only fitting over one verified training run, model
  artifact, split, and fold; TRAIN is not refitted and TEST is never loaded.
- Reused the runtime identity, Platt, and isotonic fitters with strict support,
  convergence, schema, version, and provenance validation.
- Added seven fitted calibrators, four derived complements, lower-bounded result
  simplex reconciliation, decreasing totals PAVA, and the canonical bounded
  11-target output contract.
- Added per-target and multiclass metrics, deterministic reliability bins,
  diagnostics, and read-only reproduction and compatibility inspection.
- Added migration v27 with six atomic append-only run/artifact/target/
  prediction/metric/reliability tables and twelve mutation guards.
- Added deterministic fingerprints, exact replay idempotency, immutable request
  conflicts, and a deliberately inactive runtime compatibility adapter.
- Kept runtime activation, TEST evaluation, backtesting, model promotion, shadow
  evaluation, fetching, scheduling, publication, and Telegram outside scope.

## 2026-07-23 - Historical Backtesting Foundation

- Added the deterministic TEST-only `app/historical_backtesting` boundary over
  one verified split fold, persisted model artifact, compatible persisted
  calibration artifact set, and explicit immutable supplied odds.
- Reproduced canonical raw and calibrated 11-target probabilities without
  training or recalibration; verified the complete upstream fingerprint,
  chronology, exclusivity, schema, and temporal-leakage chain.
- Added Decimal-safe value assessment for every supported Official market,
  version-pinned single-market selection, isolated EUR 1%/2%/3% stakes,
  equal-kickoff decision freezing, immutable-score settlement, and a complete
  bankroll/drawdown ledger.
- Added TEST-wide predictive metrics, reliability bins, betting and risk
  metrics, competition/season/market/bucket/month reports, optional decision-
  isolated CLV, and explicit exclusions and rejection evidence.
- Added migration v28 with ten atomic append-only backtest tables, deterministic
  request-to-ledger SHA-256 identities, exact replay idempotency, conflicts,
  bounded event streaming, and read-only reproduction and inspection helpers.
- Kept model comparison, promotion, shadow evaluation, production activation,
  live inference wiring, external odds access, scheduling, publication, and
  Telegram outside scope.

## 2026-07-23 - Model Comparison and Promotion Foundation

- Added the Lab-only `app/model_comparison_promotion` boundary over explicit
  immutable champion and challenger model, calibration, and completed TEST
  backtest identities and fingerprints.
- Added exact shared, intersection, and policy-normalized scope modes with
  strict policy/schema/currency compatibility, minimum evidence thresholds,
  and persisted non-overlap exclusions.
- Added direction-aware predictive, calibration, betting, and risk deltas;
  grouped market/competition/season/month/bucket/stake stability; deterministic
  paired bootstrap intervals; effect sizes; and uncertainty classifications.
- Added mandatory source, scope, predictive, calibration, betting, risk,
  stability, concentration, and evidence gates plus one centralized bounded
  weighted score and deterministic multi-challenger tie-break.
- Added migration v29 with ten atomic append-only comparison, candidate,
  evidence, metric, stability, statistical, gate, score, recommendation, and
  exclusion tables plus immutable-history triggers and indexed queries.
- Added canonical request/source/metric/stability/statistical/evaluation/run
  SHA-256 identities, exact request replay idempotency, conflict detection,
  bounded event streaming, and read-only inspection/reproduction helpers.
- Kept model activation, production configuration, shadow evaluation, live
  inference wiring, training, calibration fitting, backtest execution, external
  odds retrieval, scheduling, publication, and Telegram intentionally deferred.

## 2026-07-23 - Shadow Evaluation Foundation

- Added the Lab-only `app/shadow_evaluation` boundary for one explicit promoted
  challenger beside the authoritative champion on the exact same immutable
  pre-match feature input and supplied odds.
- Re-verified promotion gates, model/calibration linkage, schema, provenance,
  chronology, odds fingerprints, and the canonical 11-target contract.
- Added independent Decimal value assessment and hypothetical single selection,
  disagreement evidence, later one-unit settlement, metrics, aggregates, and
  read-only reproduction/export.
- Added migration v30 with ten atomic append-only tables, fingerprints,
  idempotent replay, conflicts, indexes, and immutable triggers.
- Kept observation disabled and fail-open to the unchanged champion; activation,
  Quality Gate, publication, Telegram, staking, exposure, bankroll, fetching,
  and scheduling remain outside this foundation.

## 2026-07-23 - Controlled Model Activation and Rollback Foundation

- Added isolated `app/model_activation` with conservative centralized
  eligibility over final promotion approval, runtime artifacts, exact settled
  shadow evidence, completeness, agreement, predictive/calibration/betting
  degradation, and drawdown deterioration.
- Added two-stage manual activation and rollback plans; preparation never
  changes runtime state, while execution revalidates state and appends one
  atomic champion generation and registry event.
- Added an append-only champion ledger, explicit manual bootstrap, rollback to
  compatible history as a new generation, and a read-only fail-closed resolver
  that remains disconnected from production.
- Added migration v31 with ten append-only request, plan, validation, generation,
  event, execution, and evidence-link tables plus fingerprints, idempotency,
  conflict protection, indexes, foreign keys, and mutation guards.
- Kept automatic promotion, startup/scheduled activation, automatic rollback,
  inference switching, Telegram, betting, bankroll, and upstream evidence
  mutation explicitly disabled.

## 2026-07-24 - Manual Lab Telegram Connection Test

- Added one isolated manual command for a single fixed Lab connection message.
- Reused the existing Telegram service with bounded per-call timeouts and a
  receipt that confirms the accepted destination and message identifier.
- Hard-locked the command to Lab channel `-1003510920417`, rejected Official
  destinations, and kept automatic Lab publication disabled.
- Kept Official publication, model activation, bankroll, statistics,
  settlement, scheduling, and application startup behavior unchanged.

## 2026-07-24 - Manual Model Operations CLI and Runbook

- Added an isolated manual CLI for one-time champion bootstrap, two-stage
  activation and rollback, champion/audit inspection, generation listing, and
  fail-closed state diagnostics.
- Reused the v31 activation service, runtime resolver, artifact repositories,
  settled Shadow evidence, promotion recommendations, and append-only registry
  without duplicating domain decisions or adding a migration.
- Required explicit database, environment, scope, immutable references,
  fingerprints, operator reasons, incident references, and exact execution
  confirmation phrases.
- Added deterministic versioned JSON, secret-redacted human output, typed
  failures, non-zero failure exits, read-only inspection connections, bounded
  SQLite waits, and recovery guidance that never edits append-only rows.
- Added the complete model operations runbook and a Lab preview formatter that
  never sends Telegram.
- Kept runtime inference integration, automatic activation/rollback,
  scheduling, startup execution, Telegram, Official publication, bankroll,
  settlements, and prediction behavior unchanged.

## 2026-07-25 - Controlled Staging Model Operations Rehearsal

- Added the explicit `STAGING`-only
  `app/staging_model_operations_rehearsal` boundary over the existing audited
  model-operations CLI, resolver, append-only registry, activation, and
  rollback services.
- Added read-only real-chain inventory with explicit deterministic fictional
  fallback, source/backup SHA-256 verification, collision-safe disposable
  paths, immutable evidence output, and secret/path redaction.
- Added mandatory independent pre-bootstrap, pre-execution, and final audits
  without weakening the complete activation audit or its readiness policy.
- Exercised bootstrap, plan preparation, activation, resolver transition,
  rollback, human/JSON diagnostics, exact replay, changed-request conflict,
  confirmation rejection, and injected atomic failure/retry recovery.
- Retained the successful controlled run as JSON and Markdown evidence and
  documented the reviewed operator procedure.
- Kept production activation, runtime inference, Official publication,
  Telegram, bankroll, settlements, statistics, scheduling, workers, and
  startup behavior unchanged.

## 2026-07-28 - Controlled REAL_ONLY Staging Artifact Chain

- Replaced staging fixture fallback with a mandatory deterministic
  `REAL_ONLY` chain built through the real historical import, training dataset,
  chronological split, model training, calibration, TEST backtesting,
  comparison/promotion, Shadow evaluation, and settlement services.
- Used only `CONTROLLED_SYNTHETIC_STAGING_SOURCE` for generated historical
  labels and preserved full persisted provenance from source matches through
  activation evidence.
- Kept the caller-supplied database read-only, retained matching before/after
  and backup SHA-256 fingerprints, and confined all mutations to ignored
  staging databases.
- Completed the audited bootstrap, activation, resolver transition, rollback,
  replay/conflict rejection, confirmation rejection, and atomic failure/retry
  rehearsal with final audit status `AUDIT_PASSED`.
- Added regression coverage for sparse odds ranking and restored Decimal
  stability concentrations discovered by the genuine service-scale chain.
- Kept production activation, runtime inference, Official publication,
  Telegram, bankroll, scheduling, workers, and startup behavior unchanged.

## 2026-07-30 - Controlled Manual Real Match Analysis to Lab

- Added isolated `app/real_match_lab_analysis` with a versioned one-match JSON
  contract, immutable typed outcomes, deterministic Lab-only single-market
  policy, traceable reasoning, Telegram-safe HTML, human/JSON operator output,
  and complete inspection commands.
- Composed the real immutable match snapshot, Feature Store, model-input,
  controlled champion resolver, inference, calibration, and market-value
  boundaries without adding a parallel prediction engine.
- Added migration v32 with append-only analysis, market evaluation, stage event,
  and exactly-once Lab delivery tables, deterministic SHA-256 identities,
  foreign keys, indexes, and UPDATE/DELETE guards.
- Hard-locked the only explicit send command to `LAB`, chat
  `-1003510920417`, bot `@GoalVision_AI_Lab_Bot`, and exact confirmation
  `SEND_TO_GOALVISION_AI_LAB`; dry-run, validation, diagnostics, imports, and
  startup remain network-inert.
- Documented the current fail-closed incompatibility between the activated
  145-position historical artifact schema and the live 78-position Feature
  Store contract. No remapping, placeholder inference, or fictional
  probabilities were introduced.
- Deferred automatic discovery, external API integration, collection,
  scheduling, background work, automatic sends, settlement, Official
  publication, production wiring, High Risk, Combo, Live, AutoTrader, and web
  dashboard work.

## Lab V2 throughput, classification and current odds (2026-09-17)

- Add versioned, country-guarded provider league registry and auditable fingerprints.
- Replace fixed discovery ceiling with bounded adaptive quota and durable page accounting.
- Preserve retriable current-odds states and serve due exact reviews before broad scans.
- Add independent single-model Experimental evidence and explicit readiness lanes.
- Freeze full ready-candidate evidence; retain terminal markets and append-only protection.
- Verify focused, regression, full-suite, schema, replay and bounded no-send paths.
- See `docs/LAB_V2_THROUGHPUT_HARDENING.md` and the external throughput review report.

## Lab V2 discovery timer wiring

- Point the discovery service at the accepted throughput worktree using Python safe-path mode.
- Raise only the obsolete operator cap from 100 to the existing bounded 400 maximum.
- Verify five focused tests, import resolution and systemd dry validation.
- Installed unit update remains blocked by unavailable passwordless sudo; keep discovery disabled/inactive.
- See the wiring check in `docs/LAB_V2_THROUGHPUT_HARDENING.md`.

## Adaptive Lab forward learning and LIVE foundation (2026-09-18)

- Add isolated append-only PREMATCH/LIVE learning evidence, strict publication/result linkage, combo deduplication, metrics and symmetric diagnostics.
- Add bounded reviewed JSON model registry/search, chronological embargoed splits, sealed holdout, future shadow, independent LAB generations and rollback.
- Add separate regulation-time LIVE single engine, current in-play odds adapter, final refresh, Lab-only durable delivery and settlement.
- Add explicit opt-in runtime composition, read-only operator views, shared per-attempt quota governance and synthetic forward rehearsal.
- Preserve accepted live checkout, installed units, credentials, source ledgers and Official state. No deployment or timer enablement.
- Operator architecture, provenance gaps, limits and future Test deployment procedure: `docs/runbooks/adaptive_lab_live.md`.

## 2026-09-20 — PREMATCH production-lineage integration

- Port PREMATCH light safety onto exact ce028907, preserving production adaptive capabilities.
- Pace daytime discovery with 100 result calls reserved; analyze missing-odds fixtures locally.
- Preserve exact refresh, publication isolation and Official policy; prioritize reviewed major competitions.
- Integrate canonical non-public evidence into existing adaptive settlement/learning with deduplication.
- Add deterministic 958-fixture incident regression; see docs/LAB_V2_PREMATCH_SIMPLIFICATION.md.
- No deployment or production state changes.

## 2026-09-25 — PREMATCH V2 reviewed competition regulation registry foundation

- Added dormant V2-only immutable reviewed-source contracts, bounded retained
  content, explicit authority hierarchy, exact/declared season scope and strict
  review-before-cutoff resolution.
- Added explicit isolated SQLite initialization, append-only import, integrity
  verification, offline operator CLI and a decision-bound Phase B FormatEvidence
  bridge without runtime wiring or feature/model changes.
- Added synthetic conflict, timing, immutability, tampering, IFAB, AET/PEN,
  historical snapshot and zero-additional-provider-request regressions.
- No real entries added; accepted audit remains NO_ACCEPTABLE_EXISTING_PROOF.
  Phase E remains unauthorized. Next: manually review one genuine authoritative
  document and exact provider-ID mapping in an isolated Test registry.
- Report: `docs/audits/PREMATCH_FOOTBALL_CONTEXT_V2_REGULATION_REGISTRY_REPORT.md`.

## 2026-09-25 — PREMATCH V2 authoritative incorporated-law evidence

- Added a mandatory fingerprinted incorporation relationship inside a versioned
  immutable competition review, with independently reviewed base-law provenance.
- Added exact-scope, strict as-of, conflict-aware offline resolution and complete
  chain FormatEvidence proof hashing without attributing law duration to organizer text.
- Preserved old registry records/schema, IFAB-alone rejection, append-only import,
  runtime isolation, V1/V2/model semantics and provider request parity.
- Added synthetic chain, immutability, replay, timing, conflict, CLI, AET/PEN and
  snapshot regressions; no real evidence imported and UCL 2026/27 stays unverified.
- Phase E remains unauthorized. Next: operator review/import of a complete genuine
  mapping + competition incorporation + base-law chain in an isolated Test registry.
- Report: `docs/audits/PREMATCH_FOOTBALL_CONTEXT_V2_INCORPORATED_LAW_REPORT.md`.


## 2026-09-25 — Deployed PREMATCH audit and gated V2 enablement

- Audited actual 363f567 runtime, timers, immutable SQLite snapshots and fixed 24h/7d windows; preserved deployed probability/chronology fixes.
- Bounded lock-held quota/learning reads, fixed cooldown diagnostics and atomic cross-version economic publication claims; guarded result sends with confirmed receipts.
- Added opt-in existing-loop Football Context observation and truthful existing-selector attribution, offline verified context links and separate forward singles statistics in existing settlement/weekly paths.
- Offline affected-path regression: 1,287 passed and 42 subtests; deployed isolated baseline: 764 passed and 8 subtests. No operational training or synthetic live sends.
- Prepared service-specific reversible rollout; installation blocked by unavailable sudo. No production unit/release/champion changes.
- Full evidence and remaining limitations: docs/operations/PREMATCH_FULL_AUDIT_V2_ENABLEMENT.md.

## 2026-09-25 — PREMATCH installer-only rollout hardening

- Preserve the completed audit and exact tested application tree from `e120f1b`.
- Make disable controls monotonic/idempotent with exact current-state validation.
- Serialize installer actions; gate new starts, drain, then fence rollback with
  a decisive ledger check that conservatively refuses unresolved labelled sends.
- Add focused disposable regressions and rerun only installer and directly
  related publication/settlement tests; prepare a distinct clean release/package.
- Old `prematch-v2-release-e120f1b` package MUST NOT be applied.
- Report: `docs/operations/PREMATCH_INSTALLER_HARDENING_2026-09-25.md`.
- Installation BLOCKED pending review/operator execution; no deployment/push/merge.
