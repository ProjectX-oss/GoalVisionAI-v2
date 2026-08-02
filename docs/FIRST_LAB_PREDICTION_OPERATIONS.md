# First LAB Prediction Operations Runbook

Before any future manual LAB send, a current governance evaluation is mandatory. Publication review fails closed when the evaluation is missing or stale, the system is paused, or the selected market, competition, bookmaker, model generation, calibration artifact, input drift, or explanation drift is blocked. Persist the observation-time governance snapshot so later settlements cannot rewrite decision-time eligibility.

The optional local review surface is documented in
`docs/LAB_OPERATOR_CONSOLE.md`. Start it read-only on `127.0.0.1`; it does not
replace or schedule any existing readiness, discovery, review, sender, result
or settlement gate.

This runbook is for the first seven days after API-Football Pro is activated
manually. Nothing here schedules work, sends Telegram automatically, publishes
Official content, or places a bet. TheStatsAPI remains paused. No historical
odds purchase is required.

## Day 0

1. Activate the API-Football plan manually. Keep the existing key unless the
   provider requires a change, and confirm `.env` remains ignored.
2. Run the offline secret-safe inspection:
   `python -m app.current_odds_forward_test pro-readiness --output human`.
3. Run exactly one bounded verification:
   `python -m app.current_odds_forward_test pro-readiness --network-verify --output human`.
   Require `PRO_PLAN_READY`; inspect daily and minute quota and the 12-call
   minimum. No secret may appear.
4. Explicitly refresh an expired six-hour capability cache by running one dry
   run. Do not repeatedly delete or refresh a valid cache.
5. Run once against an isolated forward-test database:
   `python -m app.current_odds_forward_test first-lab-dry-run --database var/first_lab_forward_test.db --max-candidates 50 --max-calls 40 --daily-reserve 20 --output human`.
6. Inspect the run, observation, markets, calibration quality, distribution
   shift, audit and preview. Do not send anything until publication review and
   a separate human decision are complete.

## Daily workflow (days 1–7)

Run bounded discovery once, or at a deliberately controlled manual interval;
never loop across future windows. Inspect skipped candidates and remaining
quota. A fixture must be chosen from pre-inference facts, both current-season
team baselines must be complete, and exact-fixture odds must still be within the
15-minute freshness boundary when inference and review occur.

Inspect the selected observation and run:
`publication-review --database <db> --observation-id <id>`. A passing report is
necessary but does not send. At most one suitable LAB prediction may later be
authorized manually through the hardened Real Match Lab sender, using the exact
analysis ID, observation ID, message fingerprint, review fingerprint, Lab
destination and `SEND_TO_GOALVISION_AI_LAB` confirmation.

After full time, use `fetch-forward-test-result`; if the provider is unavailable,
use the existing versioned `record-forward-test-result --input <json>` fallback.
Inspect the immutable result, settle once, generate `result-message-preview`,
and inspect `forward-test-statistics`. Preserve losses, blocked analyses,
no-selections and unpublished observations.

## Quota and expected blockers

Keep the configured daily reserve and allow the provider's minute window to
recover without retry loops. A valid capability cache lasts six hours; team
history is scoped and fresh for 15 minutes within one explicit run. Never reuse
stale odds.

- `NO_ELIGIBLE_CURRENT_FIXTURE`: stop; inspect skip reasons and try only at the
  next planned manual interval.
- `CURRENT_ODDS_UNAVAILABLE`: do not infer or substitute historical odds.
- `CALIBRATION_QUALITY_BLOCKED`: retain the internal diagnostic preview only.
- `DISTRIBUTION_SHIFT_BLOCKED`: retain evidence, do not publish.
- `QUOTA_INSUFFICIENT`: stop before discovery and preserve the reserve.

## Incidents and stop conditions

Stop on provider outage, ambiguous or exhausted quota, stale odds, model
resolver failure, database integrity failure, result-source conflict, or
settlement conflict. Never overwrite immutable evidence. If Telegram delivery
is uncertain, do not retry: inspect delivery state and reconcile the channel
manually. If result sources disagree, preserve both external facts outside the
database, investigate, and append nothing until one final source is justified.

Stop the first-week program if secrets appear in output, foreign-key checks
fail, source database hashes change unexpectedly, Official or bankroll tables
change, any scheduler is enabled, or any destination differs from the exact Lab
channel and bot.
# Reasoning publication prerequisite

Every new Lab candidate must have an immutable reasoning record and passed audit
before publication review. The review binds the exact public reasoning to the
candidate message fingerprint. A preview created before reasoning is internal
diagnostic evidence and cannot be authorized for send.
