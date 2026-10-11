# LIVE research result-source review — 2026-10-11

Status: SMALL_GITHUB_FIX; research quality remains BLOCKED_NEEDS_MORE_EVIDENCE.

The isolated hardening audit previously sourced labels only from PREMATCH SINGLE
and canonical results. It omitted already verified LIVE settlements. The new
adapter runs after all forecasts and nominations are frozen. It verifies the
candidate/publication/settlement identity, a confirmed SENT receipt, fixture,
market, odds, source fingerprint, full-time score, terminal status, outcome and
prepared/sent/retrieved/settled chronology. Future, VOID, malformed, conflicting
and COMBO-sourced labels fail closed. Result disagreements pass through the
existing fixture conflict exclusion. No common learning/result source was changed.

At the 2026-10-11 11:05:21.700896 UTC cutoff, 2934 retained candidate versions
cover 139 fixtures. Context V2 can forecast 173 versions; the fixed first
fixture/market sample has seven resolved market rows on ONE independent fixture.
Baseline Brier/log loss/ECE: 0.238913 / 0.667160 / 0.109406.
V2 Brier/log loss/ECE: 0.231174 / 0.651001 / 0.164923.
These dependent rows cannot support an improvement claim or confidence interval.
Red-card effects and xG coefficients remain unfitted. No model weights were invented.

The 32 synthetic adapter cases include the actual persisted `sent_at_utc` receipt
schema, chronology, missing provenance, inconsistent outcome, VOID, conflicting
scores and COMBO exclusion. Focused plus adjacent/Official regression passed
180 tests and 46 subtests with real socket transport denied. A first draft
adapter produced zero matched real rows because it omitted `sent_at_utc`; the
persisted-schema regression and reviewed adapter now cover that actual schema.

No LIVE production code, selectors, thresholds, Official files, immutable inputs,
champion state or PREMATCH learning tables were changed. No deployment, real
provider request, Telegram send or worker invocation occurred.
