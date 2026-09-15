# LAB V2 broad-coverage path

This package is the isolated Lab-only V2 selection path. It consumes only
current/upcoming fixture data, completed football results/goals, current
API-Football predictions and current bookmaker quotes captured during the
run. The default `rehearse` command never constructs Telegram transport. The
separate `controlled-cycle --send` boundary can publish only final-reviewed
READY evidence through the existing exactly-once Lab ledger and settlement.

It never retrieves historical bookmaker odds, cannot address Official, cannot
mutate Official state and never installs or starts a timer by itself.

```bash
PYTHONPATH=. python -m app.lab_v2_shadow audit
PYTHONPATH=. python -m app.lab_v2_shadow rehearse --max-calls 100 --daily-reserve 1500
PYTHONPATH=. python -m app.lab_v2_shadow controlled-cycle --send --max-calls 100 --daily-reserve 1500
```

The launch runbook and safety report are
`docs/LAB_V2_BROAD_COVERAGE_LAUNCH.md`. The Phase 1 baseline remains in
`docs/LAB_V2_PHASE1_PI_COVERAGE_SHADOW.md`.
