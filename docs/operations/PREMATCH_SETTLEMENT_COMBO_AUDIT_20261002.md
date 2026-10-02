# PREMATCH Lab settlement and COMBO reconciliation — 2026-10-02

Scope: read-only audit requested at 08:37 Europe/Riga. All values below refer to the inspected ledger and the 08:35 settlement / 08:38 observer snapshots. No runtime code, source ledger, timer, policy, provider-call schedule, or Telegram message was changed.

## Verdict

- PASS: settlement runtime is completing normally; all persisted public results have valid Telegram receipts.
- PASS: independent score/outcome, odds-product, unit P/L and count reconciliation; latest cycle, observer and frozen latest COMBO result message agree.
- NEEDS_MORE_EVIDENCE: provider-level explanation for one unresolved SINGLE with an outdated frozen kickoff.
- Confirmed reporting limitation: two COMBOs with a confirmed losing leg remain pending until all three leg results exist. Current statistics therefore lag already-known economic outcomes.

## Delivery and liveness

The service last inspected started at 08:35:00 Riga and finished at 08:35:30, exit 0, MainPID 0. Its timer is active. There are 63 persisted settlement runs since the quality deployment; maximum completion-to-completion interval is 10.15 minutes. Inactive between one-shot timer executions is normal.

All 130 settled SINGLEs and all 21 settled COMBOs have valid SENT receipts for the Lab destination. There are no claims without receipts, no missing result receipts, and no duplicated Telegram message IDs within the 327 publication/result receipts. Receipts establish Telegram acceptance; this audit did not independently read back channel contents or check subsequent deletion.

A historical 30.6-minute result-delivery delay on September 23 is already resolved. The larger pre-deployment execution gap does not represent a current hung process.

## Independent accounting

| Population | Published | Settled | Won | Lost | Void | Pending | Flat P/L | ROI on settled |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| All published Lab SINGLEs | 144 | 130 | 40 | 90 | 0 | 14 | -27.72u | -21.32% |
| All published Lab COMBOs | 32 | 21 | 2 | 19 | 0 | 11 | -4.588824u | -21.85% |

These are cumulative Lab populations, including earlier policies. They are not exclusively the latest discovery cycle or the new accuracy policy. The accuracy-COMBO cohort alone has 13 publications, 2 formal settlements (1 WON, 1 LOST), 11 pending and +0.984100u formally settled P/L.

The audit independently recalculated each of 130 SINGLE and 21 COMBO outcomes from retained regulation-time scores; all 63 settled COMBO leg outcomes and all 32 published combined-odds products agree. Calculated unit returns agree with all immutable settlements. It compared the resulting counts and P/L with the natural settlement cycle and observer. This validates internal evidence consistency, not an independent re-fetch of every match score.

The latest COMBO result receipt is message 342, 2026-10-01 23:55:33 Riga. Its frozen text shows W2/L19, -4.59u, -21.9%, correctly rounded from the same formal ledger totals. Historical Telegram messages are frozen snapshots rather than continuously updated dashboards.

## Known lost COMBOs still pending

| Publication message | Confirmed losing leg | Retained score | Market | Result observed Riga |
|---|---|---|---|---|
| 309 | Germany – Serbia | 2:0 | OVER_2_5 | October 1 23:45 |
| 301 | British Virgin Islands – Montserrat | 0:2 | OVER_2_5 | October 2 00:55 |

`app/lab_combo/service.py:check_results` only appends settlement when `len(results) == 3`. `app/lab_combo/settlement.py:aggregate` also requires the complete immutable three-leg set. Both pending combos contain future legs, so execution follows the current complete-set rule; it is not a stalled worker.

With the two already-known losses included analytically, the all-time COMBO figures would be 23 decided, 2 WON, 21 LOST, 9 still undecided, -6.588824u and -28.65% ROI. These are an audit projection, not newly committed settlements. The accuracy cohort would have 4 decided (1 WON, 3 LOST), 9 undecided, -1.015900u and -25.3975% ROI.

Recommended follow-up: expose known terminal loss promptly and continue resolving remaining legs for audit detail, with one-time accounting/delivery and unchanged historical evidence. Do not mark future legs as played or generate invented scores. The current audit does not alter settlement or publication semantics.

## Unresolved fixtures

Of the 14 pending SINGLEs, 13 had future frozen kickoffs at inspection. The remaining one is Dayrout – Ismaily SC, provider fixture 1594851, OVER_1_5, frozen kickoff October 1 15:30 Riga. The scheduled 08:35 sweep queried that fixture successfully at the HTTP layer and retained no settlement. There are zero past-kickoff unresolved COMBO legs; all pending COMBO legs lacking results are future fixtures under their frozen schedules.

Fresh public corroboration lists Dayrout – Ismaily for October 2, while some older pages and the frozen prediction retain October 1. This supports a schedule discrepancy, but does not establish the current API-Football status or authorize rewriting frozen evidence:

- Winwin, Dayrout–Ismaily, October 2: https://www.winwin.com/كرة-قدم/مباراة/ديروط-ضد-الإسماعيلي-2026-10-02
- Youm7, October 2 07:30 local report listing the fixture among today's six matches: https://www.youm7.com/story/2026/10/2/6-مباريات-في-استكمال-الجولة-السابعة-من-دوري-المحترفين/7564281

The settlement client does not persist a sanitized reason/status payload for unresolved results in this path. An HTTP 200 cannot distinguish NS/PST, missing fulltime scores, or another nonterminal/malformed response. Recommended follow-up: retain bounded structured unresolved-result evidence during natural sweeps, including current provider kickoff/status and schedule drift, without additional manual provider calls or invented VOID/LOST decisions.

## Changes and verification

Only this report and `docs/evidence/prematch_settlement_20261002/reconciliation.json` are added. Verification was an independent read-only Python/Decimal reconciliation, receipt joins, actual persisted cycle/observer inspection and bounded service/journal reads. No new regression tests were needed for these documentation-only changes. No application tests, model training, manual cycle, manual provider call, Telegram send, deployment or promotion were run.
