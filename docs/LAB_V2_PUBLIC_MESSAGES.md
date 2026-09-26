# Lab V2 public Telegram presentation

Only new labelled V2 single previews use `LAB_V2_PUBLIC_MESSAGE_V2`.
Latvian market and predictive-family labels live in
`app/lab_v2_shadow/public_presentation.py`. All eleven current markets are
supported. Unknown predictive identifiers display “Modeļa signāls”; current
market consensus is excluded from the predictive signal list. The original
identifiers, origin, policy, model and quote evidence remain internal.

## Frozen statistics

`public_single_snapshot` reuses `single_cohorts` without changing its formulas
or eligibility. Only confirmed Lab receipts for labelled V2 singles qualify.
Unlabelled history, unpublished candidates, combos, Official and LIVE are excluded.
“Likmes” is the settled count. Hit rate is WON / (WON + LOST); VOID is excluded.
P/L uses existing validated 1u settlement accounting. ROI divides by all settled
singles, including VOID. Empty denominators display “—”. Units are hypothetical
flat-stake accounting, not cash profit.

New predictions freeze the snapshot in `public_presentation.statistics` within
the immutable prediction document before rendering its preview. The pending
prediction is not a settled result. Result previews freeze the same cohort
snapshot in their existing `statistics` document after settlement acceptance,
including the new result. The existing interrupted-settlement recovery path does
the same if no preview exists. Once a preview exists it is never regenerated.
Snapshots retain the cutoff, totals and cohort records for internal audit.
Duplicate confirmed economic selections retain the existing fail-closed behavior.

## Compatibility

Predictions without `public_presentation` retain the accepted historical renderer
for exact replay and send-time equality checks. Existing prediction/result previews
remain byte-identical. Newly created result previews for old labelled predictions
use the new public wording. Prediction IDs, publication keys, linkage, claims,
receipts, fingerprints, reconciliation and plain-text parse mode are unchanged.
No schema migration, backfill, historical edit or combo-accounting change occurs.
Combo messages use independent existing helpers, which already omit references
and technical signals; no combo change is needed.

The prediction selector, probability estimates, severe-disagreement gate,
accounting formulas, odds rules, scheduling, API quota and compact stdout are
unchanged. No algorithm changed, so model backtesting is outside this change.

## Validation

`tests/test_lab_v2_public_presentation.py` covers market/signal wording, complete
prediction/result strings, zero denominators, cohort exclusions and formulas,
accepted-result inclusion, interrupted-preview recovery, frozen snapshots,
old-renderer byte equality, claims/receipts and fake transport delivery. Directly
affected delivery, publication, Lab V2, combo and compact-output suites run with
network syscalls denied and disposable stores. Upgrade tests use fake systemd
and disposable paths. Test counts and commands are recorded in the upgrade package.
