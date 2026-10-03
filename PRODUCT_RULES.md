# PRODUCT_RULES.md

# GoalVision AI Product Rules

Version: 1.0

This document defines the business rules of GoalVision AI.

These rules override implementation decisions.

If code conflicts with this document, the code must be changed.

---

# 1. PRODUCT MISSION

GoalVision AI exists to provide transparent, data-driven football predictions.

Primary goals:

- Transparency
- Long-term profitability
- Consistency
- Explainability
- Trust

The project must never prioritize marketing over prediction quality.

---

# 2. CORE PRINCIPLES

Always:

- Publish transparent statistics.
- Publish winning and losing predictions.
- Keep historical results.
- Keep public bankroll.
- Use disciplined bankroll management.
- Improve models through data.

Never:

- Delete losing predictions.
- Manipulate historical statistics.
- Claim guaranteed profits.
- Publish misleading information.

---

# 3. OFFICIAL CHANNEL

Official Telegram is the primary public product.

It publishes:

- Match Winner
- Win Probability
- Confidence
- Odds
- AI reasoning

Official channel uses:

Single Bets only.

Minimum odds:

1.60

Exception:

If no qualifying single bet exists,

one Combo Bet

Maximum selections:

2

Minimum combined odds:

2.00

Correct Score predictions are never published.

---

# 4. LIVE CHANNEL

GoalVision AI LIVE is independent.

Publishes only high-confidence LIVE value bets.

AI evaluates:

- Starting lineups
- Match momentum
- Shots
- Possession
- Dangerous attacks
- Red cards
- Injuries
- Live odds

Every LIVE prediction must include reasoning.

---

# 5. HIGH RISK CHANNEL

Independent bankroll.

Independent statistics.

Experimental prediction strategy.

Never mixed with Official statistics.

---

# 6. COMBO CHANNEL

Independent bankroll.

Independent statistics.

Publishes:

Daily Combo

Weekend Combo

Live Combo

Weekly Mega Combo

Weekly Mega Combo:

Minimum odds:

10.00+

Entertainment only.

Never included in Official statistics.

---

# 7. LAB

Testing only.

Experimental AI.

Backtesting.

Model comparison.

Never affects Official statistics.

## PREMATCH result replies authorized 2026-10-03

After explicit operator activation, unsent SINGLE and COMBO result notifications
reply to their original confirmed prediction message in its existing destination.
This includes text/photo results, voids and early COMBO loss. Retain the original
bot/recipient/period, immutable settlements and statistics, and terminal delivery
claims. If Telegram no longer has the original message, allow standalone delivery
within the same request; never issue a second fallback send. Do not replay prior
results. This presentation change does not change selection, odds floors or
Official/LIVE behavior.

## PREMATCH Lab policy update authorized 2026-10-02

For the separately approved operator release, new PREMATCH Lab SINGLE bets require
current decimal odds >= 1.30 (inclusive, without display rounding). COMBOs have no
economic odds floor, either per leg or on the combined odds; odds must remain valid
and all existing quality, freshness, independence and correlation checks still apply.
The SINGLE floor applies before market ranking and again before a new delivery claim.
Already published bets retain their immutable history, settlement and statistics.
Official and LIVE rules are unaffected. Deployment remains an explicit operator action.

## PREMATCH Lab policy update authorized 2026-10-03

The user superseded the preceding COMBO no-floor rule: every newly selected
PREMATCH Lab COMBO leg must have current decimal odds >= 1.30, inclusive and
without display rounding. Apply this before per-fixture ranking and again before
a new delivery claim. There is no additional combined-odds minimum. SINGLE
remains >= 1.30. Existing quality, freshness, independence/correlation, today-only
and early settlement/remaining-leg tracking rules remain in force. Already
published low-odds bets retain settlement, result notifications and history.
Official is unchanged; LIVE and ADMIN Codex remain disabled. Deployment remains
an explicit operator action.




## PREMATCH SINGLE 1.50 experiment authorized 2026-10-03

The user approved activating new PREMATCH Lab SINGLE selection with current odds
>=1.50, inclusive without display rounding, and normal publication into the
existing Lab conversation. This supersedes the earlier future-only 1.50 note
after operator activation. COMBO legs remain >=1.30; no combined-odds floor.
Maintain independent immutable policy statistics for comparison, preserve all
prior history/open-bet settlement, and retain today-only and Reply results.
Compatible rollback returns new SINGLE selection to 1.30 while retaining 1.50
cohort/result readers. Official, LIVE and ADMIN Codex behavior is unchanged.

## Future PREMATCH test direction recorded 2026-10-03

The user requested a later PREMATCH SINGLE minimum-odds test at 1.50 and proposed
moving COMBO predictions/results to a separate COMBO Telegram destination with
a new prospective statistics period. This records future work, not a change to
the installed policy. COMBO legs remain >=1.30 with no combined-odds floor.
Keep historical results and old open bets in their original publication and
statistics context; never erase past losses or reset learning evidence.
See docs/operations/PREMATCH_SINGLE_150_COMBO_SPLIT_PLAN_20261003.md for scope,
source findings, cutover requirements and offline acceptance coverage.


## COMBO bot connection authorized 2026-10-03

Use @GoalVision_AI_Combo_Bot for new COMBO predictions/results after explicit
operator enrollment and deployment. The channel is deferred; initial private
recipient must be verified through a unique START challenge and operator confirmation.
Start a prospective COMBO statistics period without deleting prior results.
Keep pre-cutover settlement in the original destination and period. Pause rollback
must retain readers/credentials for already published COMBO bets. SINGLE remains
>=1.30 in this change; the future SINGLE 1.50 test remains separate.

---

# 8. PREDICTIONS

Every prediction must include:

League

Teams

Market

Odds

Probability

Confidence

Reasoning

Timestamp

Never publish incomplete predictions.

---

# 9. CONFIDENCE

Confidence levels:

LOW

MEDIUM

HIGH

ELITE

LOW predictions are never published.

---

# 10. RESULTS

After every finished match:

Publish:

WON

LOST

Void (if applicable)

Historical results are permanent.

---

# 11. BANKROLL

Official bankroll starts from fixed starting value.

Every published prediction updates bankroll.

Every channel owns its own bankroll.

Official

LIVE

High Risk

Combo

Never combine bankrolls.

---

# 12. WEEKLY REPORT

Every week publish:

Total Bets

Wins

Losses

Strike Rate

Current Bank

Weekly Profit/Loss

Best Pick

Worst Pick

---

# 13. MONTHLY REPORT

Every month publish:

Total Bets

Wins

Losses

Strike Rate

Bank Growth

Profit/Loss

Largest Winning Streak

Largest Losing Streak

---

# 14. PREDICTION QUALITY

Every prediction should maximize:

Expected Value

Probability

Long-term profitability

Never chase unrealistic odds.

---

# 15. MODEL IMPROVEMENTS

Before deployment:

Backtest.

Compare.

Measure.

Deploy only if quality improves.

---

# 16. BACKTESTING

Every important AI change requires:

Historical evaluation

Sample size

Accuracy

Win Rate

ROI

Backtest results must be stored.

---

# 17. PUBLIC TRANSPARENCY

Always visible:

Bank

Statistics

Prediction history

Never hide failures.

Transparency is mandatory.

---

# 18. MONETIZATION

GoalVision AI launches fully free.

Primary long-term monetization:

Licensed advertising.

Licensed partner programs.

The prediction engine must remain independent.

Partners must never influence prediction decisions.

---

# 19. LONG-TERM PRODUCT

GoalVision AI will evolve into:

Telegram Platform

Website

Analytics Dashboard

REST API

Mobile Application

Partner Integrations

GoalVision AutoTrader (separate project)

---

# 20. FINAL RULE

Whenever there is uncertainty,

choose the solution that improves:

Prediction quality

Transparency

Maintainability

Scalability

Long-term trust

These principles are permanent.
## Dixon–Coles research authorized 2026-10-03

Implement the planned isolated comparison at normal priority using existing
chronological football results and current quote evidence. Preserve all frozen
calendar/holdout boundaries. Manual research capture/evaluation may write only
the dedicated research store. This does not authorize selection/champion changes,
production deployment, new provider requests, Telegram sends or automatic jobs.
SINGLE >=1.50 and COMBO legs >=1.30 keep their installed publication routes.

## Dixon–Coles automation preparation authorized 2026-10-03

The user approved preparing a separately scheduled, resource-bounded research
capture/evaluation job at normal priority. Operator installation remains separate;
preparation does not activate the timer or run production cycles. Existing cached
results/current quotes only, dedicated append-only state, frozen plan/holdouts,
no provider/Telegram calls and no selection/champion or publication changes.
Preserve the first prospective research records across installation and rollback.

## Constrained Dixon–Coles calculation improvement authorized 2026-10-03

The user approved continuing calculation improvements at normal priority.
Develop and test an explicitly separate constrained-solver research candidate
with existing cached chronological results; preserve the deployed model/plan,
selection and champion. Development replays are not prospective forecasts.
No deployment, provider requests, Telegram sends, historical bookmaker odds
or automatic promotion. A later forward comparison needs its own declaration.

## Forward solver and COMBO selection preparation authorized 2026-10-03

The user requested installation preparation for the improved calculation and COMBO selection improvements. Prepare a separate prospective constrained-model and paired COMBO shadow comparison at normal priority; preserve actual selection/champion and existing research. New declaration precedes prospective capture and excludes development fixtures. Operator activation is separate; no automatic deployment or promotion.
