# PREMATCH settlement: early COMBO loss and unresolved-result diagnostics

Date: 2026-10-02. Branch: fix/prematch-settlement-20261002.
Status: implementation and offline validation PASS. Operator deployment and natural-cycle evidence remain pending.

## Problem and behavior

Two published COMBOs were economically lost but remained PENDING because the old aggregator required all three fixtures to finish. The result service itself was healthy, and existing settled-result deliveries had valid receipts.

The operator-enabled flag GOALVISION_LAB_EARLY_COMBO_LOSS=1 now permits a single immutable LOST/-1u settlement after a bound losing leg has confirmed FT/AET/PEN regulation-time scores, a source fingerprint and valid chronology. Unknown legs remain explicitly waiting; no result or effective final odds are invented. Full three-leg outcomes retain the existing format and VOID/partial-VOID rules.

The financial settlement is written once. Its immutable preview and existing claim/receipt mechanism prevent a second result send. Remaining fixtures continue to receive scheduled checks when due. When all legs have results, a separate combo_result_detail is appended. This is audit detail, never a second financial settlement or model-learning observation. The early settlement and combo_analytics record describe evidence known at the decision time; the later detail holds any subsequently observed VOID legs and final effective odds. Historical preview bytes remain frozen.

All four PREMATCH readers receive compatible code together: discovery, observer, settlement and research. This is required because adaptive combo_record reproduces settlement evidence. Official, LIVE, ADMIN and weekly configuration remain unchanged; ADMIN Codex stays disabled.

## Diagnostic evidence

Natural result sweeps append bounded settlement_diagnostic documents and include the same summary in the run record. Each record has fixture ID, frozen/current provider kickoff, observed time, allowlisted provider status, schedule_changed and a typed unresolved reason. Reasons distinguish postponement, not-started, future/rescheduled kickoff, missing score, malformed/ambiguous response, request failure and exhausted call budget.

At most 100 diagnostic rows are persisted per sweep, with a total/truncation marker. No raw provider error, exception message, response body or credential is retained. Diagnostics add no provider calls. The existing 20-call result ceiling, quota guards and 90-minute relevance boundary are preserved. String/integer fixture IDs share the same per-sweep cache.

A provider kickoff in the future or malformed provider date cannot produce settlement. The original frozen prediction is never overwritten. The Dayrout–Ismaily schedule discrepancy will receive provider-level diagnostics from its next naturally scheduled response; this work did not request a manual provider refresh or assign an invented outcome.

## Verification

206 tests PASS with network socket connects disabled. Covered scopes:

- early loss with future legs; delayed win/VOID completion; immutable accounting and preview;
- crash after leg, settlement or preview persistence; restart recovery;
- exactly-once accepted delivery and no automatic retry after ambiguous timeout;
- bound fixture/market/odds/probability-independent result proof and chronology;
- all 27 three-leg WON/LOST/VOID combinations;
- postponed/nonterminal/malformed/missing-score responses; rescheduled dates;
- shared provider cache, call budget, bounded diagnostics and credential redaction;
- exact CLI flag composition (1 enables, 0/invalid disables);
- COMBO remains excluded from model-learning observations;
- observer performance, existing single/combo publication and today-scope regressions;
- operator upgrade, compatible rollback, mixed timer state preservation, busy drain refusal,
  write/reload/timer failure recovery, package/source/environment tamper and symlink rejection;
- ADMIN disabled guard and protected routes.

The explicit adaptive test-fixture plugin is loaded for the combined pytest slice. The first combined run exposed a fixture-registration issue (202 tests passed, one missing fixture); no application assertion failed there. The final correctly registered slice passed all 206.

A separate read-only arithmetic replay against retained real ledger evidence reproduced all 21 complete settlements byte-for-byte. It identified exactly two new early-loss decisions, messages 309 and 301, each -1u with two pending legs. No source ledger was modified. This supports the implementation against the observed incident; real scheduled publication remains pending deployment.

Test files in the final slice: tests/test_lab_combo_early_loss.py, tests/test_lab_combo.py, tests/test_lab_experimental_selection.py, tests/adaptive_lab/test_no_combo_learning.py, tests/test_prematch_settlement_upgrade.py, tests/adaptive_lab/test_performance_snapshot.py, tests/test_lab_accuracy_combo.py, tests/test_lab_today_scope.py, tests/test_prematch_v2_enablement.py.

## Changed files

- app/lab_combo/settlement.py: economic decision and compatible outstanding-leg detection; malformed result handling.
- app/lab_combo/service.py: opt-in early settlement, continued detail collection, proof-bound delivery and diagnostics.
- app/lab_combo/presentation.py: truthful pending-leg result message.
- app/lab_combo/result_diagnostics.py: allowlisted bounded unresolved-result evidence.
- app/lab_combo/cli.py: explicit flag and remaining-leg scheduling relevance.
- app/adaptive_lab/metrics.py: reproduce both complete and early financial outcomes.
- tests/test_lab_combo_early_loss.py; tests/test_prematch_settlement_upgrade.py.
- operations/prematch-settlement/update.py; operations/prematch-settlement/build.py.
- TASKS.md; this report; docs/evidence/prematch_settlement_fix_20261002/verification.json.

## Operator package and rollback

Base: /opt/goalvision-prematch-quality-3ad346b-20261001. Package creation compares the entire source application with the exact base plus six reviewed Python files (806 modules after adding diagnostics). The updater pins source/overlay hashes, environment, configured commands and protected routes. It pauses only the four affected timers, lets running one-shot services drain for up to 45 seconds, never kills a service, changes the four environment routes, then restores each prior timer state. Failure restores previous routes and timers. No manual service cycle or test send is part of deployment.

Read-only plan:

    python3 ~/goalvision-operations/settlement-fix.py

Operator installation (separate authorization):

    sudo python3 ~/goalvision-operations/settlement-fix.py --apply

Expected success marker: PREMATCH_SETTLEMENT_DEPLOYED.

Compatible rollback:

    sudo python3 ~/goalvision-operations/settlement-fix.py --apply --rollback

Rollback disables new early-loss decisions while retaining the compatible readers, diagnostics and completion of existing early-loss leg audits. It intentionally does not route back to the old binary, which cannot reproduce the new immutable settlement shape. Accounting and previously accepted deliveries are never deleted or reversed. The same --apply command can explicitly re-enable early decisions.

After operator installation, inspect the next successful natural settlement and observer cycles. The two known losses should each enter financial statistics once and receive at most one accepted result notification; the other legs remain audited until completion. Provider-derived unresolved evidence should explain Dayrout status/date without extra manual requests. Champion/promotion, learning datasets/holdout and selection thresholds are outside this change.

No deployment, timer control, manual research/discovery/settlement cycle, provider request, Telegram send, model training, promotion or Official mutation was executed during implementation.
