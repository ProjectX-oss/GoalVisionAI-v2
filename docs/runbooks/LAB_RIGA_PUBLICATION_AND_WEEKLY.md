# Riga publication window and weekly Lab results

These are Lab product rules, not model features. They affect new PREMATCH single and combo publications only. Official is untouched and LIVE remains disabled. They become active only when the reviewed release is deployed; unchanged baseline production does not inherit them from this checkout.

## Publication cutoff

`ZoneInfo("Europe/Riga")` supplies the DST-safe clock. New betting publications require a decision time >=09:00 and <23:00. Outside that window return `LAB_PUBLICATION_WINDOW_CLOSED`. Selection/leg kickoffs outside the same local 09:00–23:00 horizon return `FIXTURE_AFTER_LAB_CUTOFF`, including next-day 00:30 or 03:00 kickoffs. A 22:59 kickoff remains eligible subject to all existing requirements. Naive timestamps are rejected.

Policy `LAB_RIGA_PUBLICATION_V2` supersedes the midnight reopening rule. Status exposes the window, OPEN/CLOSED, NEXT OPEN and NEXT CLOSE as timezone-aware timestamps. NEXT OPEN/CLOSE are the next transitions strictly after the status timestamp; during an open window NEXT OPEN is tomorrow at 09:00. Discovery, settlement, learning, shadow and monitoring continue overnight. Weekly statistics remain Sunday 22:30 Europe/Riga. This change is not deployed by the implementation task.

The rule is checked before preparation and again in both Lab new-prediction send paths. The send-boundary check occurs after durable claim acquisition and directly before invoking the transport. A claim that crosses the boundary is retained with an immutable cutoff diagnostic and no publication receipt. It cannot become a published W/L observation. An already-dispatched request cannot be recalled if Telegram completes delivery after the boundary: the controlled time is the publication decision/dispatch, as requested.

Discovery remains scheduled. Fixtures receive publication-blocker metadata; dedicated near-kickoff and tracked exact-odds enrichment for categorically blocked opportunities is skipped. Ordinary bounded discovery/research may still collect useful evidence. Candidate probabilities, training thresholds and stakes do not change. Learning features do not include the cutoff flag. Shadow opportunities may still be evaluated. Settlement processing and settlement notifications are not blocked at night.

## Weekly schedule and source of truth

`goalvision-lab-weekly-stats.timer` uses:

```ini
OnCalendar=Sun *-*-* 22:30:00 Europe/Riga
Persistent=true
AccuracySec=1s
```

The service uses the reviewed release `PYTHONPATH`, existing interpreter/runtime, and dedicated adaptive audit DB. It never creates an API-Football client or calls provider endpoints. It validates the existing Lab destination/bot identity; there is no configurable new group and no Official/LIVE reporting.

Publication receipts determine cohort membership, not prediction creation or settlement date. Only positive message-ID receipts with SENT/true and the existing Lab chat are counted. Records with unprovable publication timestamps are explicitly diagnosed rather than assigned a fabricated week. Source access uses the existing read-only/query-only ledger and a consistent read transaction.

The frozen report covers Monday 00:00 through Sunday 22:30, Europe/Riga. UTC conversion happens after constructing local calendar boundaries, including 167/169-hour DST weeks. Persistent catch-up selects the latest due Sunday, retains that exact cutoff and does not silently change the original reporting period. Missed older weeks are available to historical queries; the worker does not spam a backlog.

SINGLE uses only single publication receipts and single settlements. COMBO uses only combo receipts and combo settlements. Combo legs never inflate SINGLE counts. A result available after the as-of cutoff remains pending in the frozen message. A historical `statistics(..., week_start=original_monday, as_of=later_time)` query includes the later result in its original publication week. It also includes publications later that Sunday before Monday if querying the completed calendar week. Sent messages are never edited.

W/L/V, settled, pending, flat-unit PnL/ROI and average settled captured odds are separate per product. Hit rate excludes full voids and pending; combo hit rate includes a partial-void winning settlement, matching existing combo semantics. `PARTIAL_VOID` is the source settlement status for partial-void wins; `partial_void_count` additionally includes losing combos with a void leg. The message explains the difference. ROI denominator is settled flat-unit bets, including full voids; pending stakes do not depress ROI. No combined hit rate is produced.

## Delivery semantics

Schema 4 adds immutable `weekly_reports`, `weekly_claims`, `weekly_receipts`, and `weekly_delivery_unknown` with foreign-key parent links and update/delete guards. Identity contains product, week start, fixed Sunday cutoff, timezone and report version. The report text and counts freeze before transport. A transaction durably claims before sending; two processes/restarts cannot both claim. Confirmed delivery is never repeated. A timeout, ambiguous exception, invalid receipt or crash after claim requires reconciliation and is never blindly resent. This is exactly-once protection, not a promise of exactly-once delivery across an uncertain external network.

Configuration failure before claim is retryable after repair. Re-running after a confirmed receipt returns ALREADY_SENT without constructing Telegram transport. An unresolved claim returns an explicit reconciliation status. Do not delete claims, reset guards or automatically resend to resolve ambiguity. No live Telegram tests are permitted during implementation.

## Operator checks and deployment

```bash
cd /home/arvis/GoalVisionAI
# PYTHONPATH must point at the reviewed release, as in the main cutover runbook.
/home/arvis/GoalVisionAI/.venv/bin/python -P -m app.adaptive_lab.prematch status --database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db --json
/home/arvis/GoalVisionAI/.venv/bin/python -P -m app.adaptive_lab.weekly_cli --database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db
```

Without `--send`, weekly CLI is a current-week-to-date preview: no Telegram configuration read, no transport, no report claim or DB creation. Status includes PUBLICATION WINDOW, NEXT CUTOFF, weekly last confirmed send, next Riga schedule and current-week separate product metrics. Source read-only queries remain available independently of the publication window.

Use `PREMATCH_ADAPTIVE_CUTOVER.md` for the complete conditional deployment, now including the weekly service/timer and no-send preview. Required active timers after successful cutover: discovery, combo settlement, adaptive observer, adaptive learning, weekly stats. LIVE remains absent/disabled. Privileged installation is not implied by committing templates.

The current cutoff is never applied retroactively to weekly cohorts: a genuinely published historical night bet remains a real bet and its loss remains counted. A previous-week publication settling this week stays in the previous publication week, not this week's W/L.
