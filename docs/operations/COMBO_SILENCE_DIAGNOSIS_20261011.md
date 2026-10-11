# COMBO silence — 2026-10-11 follow-up

**SMALL_GITHUB_FIX; OPERATOR_APPROVAL_REQUIRED for installation.**

Checked at **2026-10-11 15:11:59 Europe/Riga**. This supplements the recovery report; its earlier audit snapshot is retained.

## Authoritative runtime findings

- Last confirmed COMBO prediction receipt: **2026-10-09 17:06:36 Riga**, `COMBO_DOUBLE_20261006_V1`. Silence is approximately 46 hours.
- All six completed publication cycles today through 15:09 Riga report `COMBO_AGREEMENT_BUDGET_EXHAUSTED` for DC Agreement.
- The Double lane reports `INSUFFICIENT_INDEPENDENT_DOUBLE_LEGS`; the 14:09 cycle has zero eligible fixtures. Retained probability 70–80%, odds >=1.70 and final-review/data-integrity requirements remain unchanged.
- SINGLE delivery continues: 15 confirmed SINGLE publications in the five cycles through 14:09 Riga. This count excludes the later 15:09 cycle.
- PREMATCH discovery timer is active/enabled. LIVE evening timer is also active/enabled, retaining the separately documented Watch desired-state mismatch.
- Installed PREMATCH `combo_agreement_sources.py` still matches the pre-fix source. This task did not deploy anything.

## Root cause

The DC reader starts its 10-second wall-clock deadline in its constructor. CLI constructs it before shared candidate review, SINGLE preparation and public-statistics computation. Those unrelated steps therefore consume the DC reader allowance before the first DC input is evaluated.

The 11:00 UTC rehearsal retains 1,103 candidates. On an isolated ledger copy taken before its 11:09 publication preparation, the original implementation reaches its first DC score after **10.3412 seconds** and immediately rejects it. Profiling attributes most preparation time to repeated ledger reads and fingerprint verification, including three SINGLE presentation-statistics snapshots. These integrity checks were retained.

The production preparation phase lasted 12.0284 seconds; the preceding four phases lasted 10.9591–11.8955 seconds. Runtime phase evidence and offline reproduction support the same budget ownership defect. Profiling adds overhead and is not used as production latency evidence.

## Minimal source fix

Start the one-shot DC deadline at the first call to `Inputs.score`. Keep the existing **10-second** DC allowance, shared across all subsequent candidates. Do not reset it per candidate. Existing SQL interruption and post-model/post-evidence deadline checks remain. Timeout still discards the complete partial COMBO pool.

This changes which work consumes the DC reader allowance. Total publication preparation can consequently last longer than the old prematurely exhausted path; no overall preparation deadline or provider quota is increased. No model equation, publication threshold, odds policy, selection ranking, receipt, settlement, Official file, timer or provider request path changes.

## Offline evidence

The same retained candidate report and detached ledger were replayed with network connections denied. No worker, Telegram transport or provider was executed. Both runs use the same frozen selection clock, 2026-10-11T11:08:48.950973+00:00.

| Result | Original source | Fixed source |
|---|---:|---:|
| Retained candidates | 1,103 | 1,103 |
| DC input evaluations | 1, rejected immediately | 124 |
| Successful DC scores | 0 | 35 |
| Eligible distinct DC fixtures | 0 | 22 |
| Prepared DC COMBO previews | 0 | 3 |
| Double eligible fixtures | 0 | 0 |
| Actual sends | 0 | 0 |

Fixed DC scoring elapsed approximately **2.0511 seconds** from first to last score, within its unchanged allowance. Overall fixed replay preparation took 14.4873 seconds.

SINGLE prediction fingerprints, SINGLE settlements, COMBO settlements, receipts and claims are identical across the two detached replay ledgers. Historical production evidence was read only.

Limitations: this is a development replay, not prospective prediction-quality evidence and not proof of three missed or deliverable production coupons. The football-context observer was omitted; retained consensus and the read-only research store are accessed under existing as-of guards. Model availability and source integrity remain fail-closed. No historical bookmaker odds were acquired. Future real publication still requires all existing final delivery gates and a separately authorized installation.

Private evidence is retained under `/home/arvis/goalvision-research/combo-silence-20261011/`. Raw candidate/ledger documents and recipient information are not committed.

## Verification

- Focused: **36 passed**.
- Adjacent: **327 passed, 39 subtests passed**, including the focused tests; do not add the two totals.
- Adjacent coverage includes DC Agreement, parallel market compatibility, Double, recipient routing, early loss/VOID behavior, PREMATCH publication, DC chronology, SINGLE presentation and Official publication.
- Four new regression cases cover delay before the first DC score, a non-renewable shared deadline, slow model verification and slow evidence calculation. Existing partial-pool timeout, no selection and duplicate-delivery coverage remains.
- Adjacent tests explicitly deny socket connections; fake transports only.
- `git diff --check`: PASS.
- Tooling notes: an initial adjacent command referenced a nonexistent test filename and collected no tests; the corrected command passed. The initial unprofiled diagnostic wrote its complete result before an unused profiler formatter failed; the fixed replay removes that formatter and completed successfully. These are harness errors, not omitted failing application tests.

## Operator action

No installation was performed. Review this source delta together with the already prepared calendar-reader/health changes and the pinned installed PREMATCH base. Preserve existing flags, quotas, thresholds, champion and settlement.

After separate deployment authorization, include only the reviewed DC reader change in an appropriate PREMATCH release and perform offline smoke tests before installation. Observe a natural scheduled cycle afterwards. Do not launch a worker, send a test message, replay old coupons, force picks, or relax Double requirements to end the silence.

A working DC lane does not establish calibrated joint probabilities or profitability. COMBO quality remains `INSUFFICIENT_EVIDENCE`.

Production deployment = **NONE**; Telegram sends by this task = **0**; extra provider calls = **0**; Official changes = **NONE**; model activation = **NONE**.
