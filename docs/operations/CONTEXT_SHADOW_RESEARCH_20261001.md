# xG and dynamic-strength shadow comparators — 2026-10-01

Engineering status: PASS. Publication/promotion eligibility: false. No deployment or provider calls.

## xG foundation

shadow_research.xg requires CURRENT_XG_CONTEXT_V1: current fixture/team/league identity and at least three resolved, genuine expected_goals observations for the home team's home venue and away team's away venue. Each sample binds /fixtures/statistics, source fingerprint, league/team/fixture, played_at and availability before capture. Current context must be at most six hours old; samples older than 180 days are excluded. Missing xG, duplicates, future availability and provider prediction goal bounds fail closed.

Research goal rates are geometric means of attack xG and opposing defence xG in the matching venues. This is a declared baseline choice, not a fitted or calibrated production model. Independent Poisson distributions produce HOME/DRAW/AWAY, totals 1.5/2.5/3.5 and BTTS. Rate domain is 0.05–8; out-of-domain rates are rejected. Truncation mass is reported and must be <=1e-10. No arbitrary probability clamp.

xG sources may overlap CURRENT_MATCH_INTELLIGENCE. Independence is not asserted merely because the code is a separate module.

Real input audit: analysis.db contains 423 CMI snapshots, latest 2026-09-15 14:30:41 UTC; the latest 25 have no xG fields. Fresh genuine xG is unavailable. Runtime status BLOCKED: NO_FRESH_GENUINE_XG_CONTEXT. No surrogate was manufactured. See xg_input_readiness.json.

## Dynamic team strength foundation

dynamic_strength.update implements Glickman's Glicko-2 rating/RD/volatility equations. The official worked example is a regression test (1464.06 rating, 151.52 RD, approximately 0.059996 volatility).

Football adaptation is explicitly research-only:
- one league namespace; eight prior matches required for each team;
- daily kickoff groups update simultaneously; every source result must already be available at capture;
- inactivity inflates RD, attenuating uncertain rating differences;
- tau=0.5, initial 1500/RD350/volatility0.06;
- fixed 35-point home advantage (zero when known neutral);
- separate uncalibrated Davidson-style draw link, using only the captured league results and a 20-match, 25% prior;
- no margin-of-victory adjustment yet; no historical odds.
This shares RESULT_HISTORY_MODEL_CONTEXT with existing result-history models and cannot claim an additional independent publication family.

shadow_inputs.current_results_context validates fingerprints and freshness of existing /fixtures(results) FT cache entries. Conflicting scores, future results or unknown history block the capture. It performs no network operations.

## Actual current-data probe

A read-only probe of 1,650 upcoming fixtures produced 562 current PREMATCH dynamic-strength captures, 768 insufficient-team-history blocks and 320 unavailable-current-cache blocks. These are forward predictions, not resolved accuracy evidence. No learning row, publication ledger or champion registry was written.

dynamic_strength_current_probe.json contains per-fixture status/probabilities. dynamic_strength_forward_captures.json.gz losslessly retains every full source context and capture fingerprint for later settlement comparisons. Source timing is frozen in each capture. Source cache history is incomplete and results were first known no later than their recorded retrieval; no earlier availability is invented.

## Paired forward metrics and execution

Both models use the same immutable capture schema. forward_metrics validates capture integrity, deduplicates the first model/fixture capture, and joins only later source-bound resolved scores. It reports per-market Brier/log loss/ECE/MCE/reliability and exact matched comparisons against frozen champion, current-market or xG references: Brier/log-loss delta and mean absolute disagreement. Incremental information remains NEEDS_MORE_EVIDENCE until enough paired forward outcomes exist.

Explicit offline CLI:
python -m app.adaptive_lab.shadow_cli capture --method xg --input context-envelope.json --journal research-only.db
python -m app.adaptive_lab.shadow_cli capture --method dynamic-strength --input context-envelope.json --journal research-only.db
python -m app.adaptive_lab.shadow_cli metrics --journal research-only.db --results resolved-results.json

The envelope has context and optional references. Tests document exact input fields. Capture uses the actual current clock; it does not backdate forward evidence. Metrics opens the journal read-only. No provider, Telegram, selection, training or promotion capability exists in this CLI. These comparators are not wired into publication. Routine source collection/settlement integration requires a separately reviewed operator-approved runtime release; the current implementation is callable research infrastructure.

Changed files: shadow_research.py, dynamic_strength.py, shadow_inputs.py, shadow_cli.py, test_context_shadow_research.py and the evidence files above.

Tests cover Poisson identities and tails, source/chronology/duplicate checks, exact Glicko worked example, order invariance, idle uncertainty, draw probability, paired comparisons, immutable evidence, cache corruption and CLI capture/read-only metrics.

References:
- Glickman (2022), official algorithm and example: https://www.glicko.net/glicko/glicko2.pdf
- Dixon & Coles (1997), Poisson football modelling context: https://doi.org/10.1111/1467-9876.00065 . This implementation does not reproduce their fitted model or use their historical odds.
