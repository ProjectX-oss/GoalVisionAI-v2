# API-Football Pro Activation Checklist

Use on or after 2026-08-10.

1. Activate API-Football Pro manually; Codex must not purchase it.
2. Keep the API key unchanged unless required by the provider.
3. Confirm `.env` is ignored and contains no staged changes.
4. Run `pro-readiness --network-verify --output human`.
5. Require the typed outcome `PRO_PLAN_READY`.
6. Inspect daily and per-minute quota; preserve the configured daily reserve.
7. Allow an expired capability cache to refresh, or explicitly run one bounded
   refresh; never reuse stale capability claims.
8. Run `first-lab-dry-run` once against the isolated database.
9. Inspect every market, model/calibration provenance, calibration quality,
   distribution shift, odds timestamp, preview, observation audit and run stages.
10. Send nothing until `publication-review` passes and the operator makes a
    separate explicit manual decision.
11. Preserve the evidence export and before/after database hashes.

TheStatsAPI remains paused. Do not scrape Flashscore, buy historical odds,
schedule the workflow, publish to Official, or treat early results as evidence
of profitability.
