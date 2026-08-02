# Forward-Test Governance

This manual-only foundation evaluates immutable, settled LAB forward-test evidence. It never fetches provider data, sends Telegram, changes Official state, trains, recalibrates, activates, rolls back, or schedules work.

Policy v1 uses explicit UTC cutoffs, Riga calendar weeks, lifetime and rolling 7/20/50-observation windows, rolling 7/30-day windows, and model, calibration, market, competition, and bookmaker scopes. Maturity progresses through `NO_EVIDENCE`, `GOVERNANCE_SAMPLE_INSUFFICIENT`, `WARM_UP`, `MONITORING`, `REVIEWABLE`, and `POLICY_MINIMUM_MET`. Early results must remain insufficient even when they happen to win.

The decision engine combines predictive, calibration, input, completeness, odds, explanation, lifecycle, incident, and scope evidence. Warnings require consecutive evaluations, blocking requires consecutive severe evaluations (except integrity-critical failures), and recovery requires sustained clear evidence. Acknowledgement records operator awareness but cannot repair a mathematical failure.

LAB publication fails closed without recent governance evidence. A blocked market, competition, bookmaker, model generation, or calibration artifact is excluded without silently changing model logic. The observation-time snapshot preserves exactly what governance state was known at decision time.

Inspect manually with `python -m app.forward_test_governance inspect-governance --database <path>`. After any future Pro activation, first collect genuine observations through the reviewed forward-test workflow, settle results, then run an explicit evaluation; Pro activation itself must not trigger governance or publication.

Governance thresholds are risk controls, not proof of accuracy or long-term profitability. A winning prediction can still be invalid because its data, odds, provenance, explanation, or applicable scope failed policy.
