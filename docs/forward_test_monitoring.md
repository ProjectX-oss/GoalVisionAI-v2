# Forward-Test Monitoring and Weekly Reporting

The local console integrates these reports through typed read services. It
computes page views with `persist=False`; report persistence is possible only
through an explicitly enabled, confirmed POST action. See
`docs/LAB_OPERATOR_CONSOLE.md`.

## Scope and safety boundary

This foundation observes the isolated `FORWARD_TEST_REAL_TIME` evidence chain.
It never discovers fixtures, calls a provider, runs inference, sends Telegram
messages, schedules work, records bookmaker transactions, changes model
activation, or writes Official statistics or bankroll state. Reports describe
LAB forward testing. Betting values are labelled `HYPOTHETICAL_FLAT_STAKE`.

All commands are explicit and manual:

```text
python -m app.forward_test_monitoring --database <isolated.db> health --cutoff <UTC>
python -m app.forward_test_monitoring --database <isolated.db> snapshot --cutoff <UTC>
python -m app.forward_test_monitoring --database <isolated.db> audit <observation-id> --cutoff <UTC> --persist
python -m app.forward_test_monitoring --database <isolated.db> weekly-report --cutoff <UTC> --output markdown
python -m app.forward_test_monitoring --database <isolated.db> cumulative-report --cutoff <UTC>
python -m app.forward_test_monitoring --database <isolated.db> unresolved --cutoff <UTC>
python -m app.forward_test_monitoring --database <isolated.db> incidents --cutoff <UTC>
python -m app.forward_test_monitoring --database <isolated.db> reproduce <report-id>
python -m app.forward_test_monitoring --database <isolated.db> export <report-id> --output <directory>
```

Export refuses a non-empty destination unless `--overwrite` is explicit.
`--output telegram` renders a preview; it cannot send.

## Reporting contract

Policy `goalvision-forward-test-monitoring/1.0.0` uses Europe/Riga weeks from
Monday 00:00 local time to the next Monday (exclusive). Internally all cutoffs
and evidence timestamps are UTC. A cutoff includes only source events whose
relevant timestamp is at or before the cutoff. A frozen snapshot lists every
source fingerprint and the source-set fingerprint. Exact request replay is
idempotent; changed content is rejected.

Sample states are operational warnings, not significance claims:

| Settled sample | State |
|---:|---|
| 0 | `NO_SAMPLE` |
| 1–29 | `FORWARD_TEST_SAMPLE_INSUFFICIENT` |
| 30–99 | `EARLY_SAMPLE` |
| 100–199 | `MONITORING_SAMPLE` |
| 200–299 | `REVIEWABLE_SAMPLE` |
| 300+ | `POLICY_MINIMUM_MET` |

Per-market and per-competition interpretation requires 30 records;
calibration interpretation requires 100 and each probability bin requires 20.
These thresholds do not prove profitability. Closing-line value remains
unavailable until an immutable, correctly timed closing quote exists.

## Lifecycle and gap analysis

The existing chain already provided provider readiness, discovery, candidate
filters, baseline collection, current-odds capture and sealing, Real Match Lab
inference, calibration-quality/distribution-shift evidence, observation,
preview/review, optional Lab delivery, result capture and settlement. Schema
v36 protects odds, observations, results, settlements and events; v37 protects
operator runs, publication reviews and result previews.

The legacy aggregate statistics remain compatible, but had these reporting
gaps: hard-coded sample thresholds; floating-point log loss; publication always
reported as zero; no frozen cutoff/source set; no exact report reproduction;
no weekly boundary; limited bookmaker/model/calibration segmentation; no
incident workflow; and no deterministic Markdown, Telegram-preview or CSV
bundle. The new package adds those capabilities without replacing the working
capture or settlement services.

Each observation audit defines 35 checks covering identity and time ordering,
odds freshness and exact price, canonical single markets, feature/model/
calibration/shift provenance, probability contracts, Lab-only delivery review,
result identity/timing, deterministic settlement, duplicates/orphans, and the
Official isolation boundary. Findings are `WARNING`, `BLOCKING`, or `CORRUPT`;
evidence is never silently repaired.

## Weekly operator checklist

1. Work on a copied or isolated database and record its hash before generation.
2. Run `health`; stop on `FORWARD_TEST_CORRUPT`.
3. Run `unresolved` and obtain missing genuine results or settlements through
   the separately authorized operator workflow.
4. Persist lifecycle audits for every observation in the week. Investigate all
   blocking/corrupt findings; acknowledgement does not alter the evidence.
5. Generate the weekly report at the declared cutoff, then the cumulative
   report at the same cutoff.
6. Run `reproduce` for both report IDs and require exact fingerprint matches.
7. Export to a new directory. Review JSON, Markdown, all CSV files and the
   Telegram preview. The preview is not authorization to send.
8. Compare week-over-week counts cautiously and retain every loss, void,
   blocked/no-selection and unpublished observation.
9. Record database/export hashes and archive the isolated evidence.

## Incident response

Run `incidents` to append deterministic records for quality findings. Use
`acknowledge` with a real operator identity and reason; use `--resolved` only
after the external problem is actually resolved. Acknowledgements and
resolutions are append-only events. They never rewrite or waive a finding.

Escalate fixture/result/settlement identity conflicts, non-Lab publication,
message fingerprint mismatch, invalid probabilities, Official boundary
violations, or failed foreign keys immediately. Do not publish, delete, repair,
or backfill evidence silently.

## First genuine week

After API-Football Pro is activated on or after 2026-08-10, rerun the existing
secret-safe readiness check. Use only compatible current-season baselines and
genuine current odds. Do not substitute older history. For every genuine
observation record the selected source/bookmaker before capture, seal before
inference, keep the Lab review explicit, capture the final result after
completion, settle deterministically, then follow the weekly checklist above.
# Explainability monitoring

Reports now include reasoning volume, audit outcomes/pass rate, public factor
counts, missing/calibration/shift disclosure rates, explanation stability and
top supporting/opposing groups. These are transparency diagnostics; explanation
frequency does not prove causation, predictive quality or profitability.
