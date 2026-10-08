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

## Active conservative COMBO experiment authorized 2026-10-04

The user explicitly requested real Lab COMBO publications from the improved
selection immediately for personal evaluation. This supersedes the preceding
shadow-only COMBO selection restriction after operator activation; it does not
promote a champion or change SINGLE/Official/LIVE. Use the conservative minimum
of verified constrained Dixon–Coles, existing ensemble and current multiplicative
de-vig scores for COMBO ranking. Treat the score as uncalibrated and the experiment
as unproven. Preserve current quality, identity, chronology, today-only, 1.30 leg
floor and correlation checks; SINGLE stays >=1.50 and no combined floor is added.
Unavailable inputs skip COMBO rather than forcing picks or silently falling back.
Keep separate immutable test statistics, old results and all settlement/reply
behavior. Deployment remains an explicit operator action; ADMIN Codex and LIVE
remain disabled. See docs/operations/PREMATCH_COMBO_CONSERVATIVE_20261004.md.

## Parallel visible market COMBO experiment authorized 2026-10-04

The user requested a second visible COMBO selection for personal evaluation,
with every leg >=1.30. Retain the active DC lane with first choice, and add at
most one disjoint three-leg market-consensus coupon per natural cycle. Use
already captured complete current quotes from at least two distinct bookmakers;
rank by the lower of median multiplicative and median power de-vig estimates.
This is an uncalibrated experimental score, not proven predictive improvement.
Preserve existing quality/correlation/today-only guards, exact leg floor,
SINGLE >=1.50, separate frozen statistics and early-loss/reply settlement.
No extra combined floor, new provider calls, champion/Official/LIVE change,
automatic deployment or promotion. ADMIN Codex remains disabled. The new
flag-off rollback pauses only new market-lane publications and retains readers.
See docs/operations/PREMATCH_COMBO_MARKET_PARALLEL_20261004.md.

## Private Lab SINGLE filter authorized 2026-10-04

The user requested a private Lab-bot selection with current decimal odds >=1.70
and the previously specified model probability 70–80%, inclusive and unrounded.
Prepare a separate prospective private ledger/statistics cohort. Search the full
natural evaluated candidate pool, keep existing quality/freshness/replay,
independent-model, severe-disagreement and Riga today-only gates, and publish at
most one new private fixture per natural cycle. No forced picks or probability
inflation. Verify the already confirmed private COMBO owner through a fresh Lab
bot START before operator activation. Private results use original-message Replies.
Existing Lab SINGLE 1.50 / COMBO legs 1.30, both COMBO lanes, learning/champion,
Official, LIVE and ADMIN restrictions remain unchanged. No automatic deployment.


## COMBO Double replacement authorized 2026-10-06

The user explicitly requested replacing new COMBO Tirgus tests publications with
exactly TWO legs, each with current decimal odds >=1.70 and the retained model
probability in [0.70, 0.80], inclusive and without display rounding. Declare
`LAB_COMBO_DOUBLE_170_P70_80_20261006_V1`, cohort `COMBO_DOUBLE_20261006_V1`.
This authorization applies only to the replacement lane; DC COMBO and public/private
SINGLE policies remain unchanged. At most one Double per natural discovery cycle.

The Double uses the existing frozen model/ensemble estimate, without DC agreement,
multiple-bookmaker consensus ranking or confidence/edge/agreement quality cutoffs.
Severe model/market or intelligence disagreement is retained as diagnostic evidence
rather than a Double publication veto. Do not bypass data integrity: require actual
non-market model evidence, exact probability replay, valid current quote provenance,
upcoming permitted fixture/time window, fresh completed final review, distinct
fixtures/teams, cross-COMBO exposure/duplicate checks, and bound original-message
result delivery. Do not clamp/inflate probabilities, fabricate review approval,
force picks or increase API budgets. Other unrecognized/data-quality failures remain
blocking. These are uncalibrated experimental probabilities, not proven win rates.

Retire new market-lane claims at explicit operator activation. Preserve all historical
market/DC triples, immutable results/statistics, early loss and remaining-leg tracking.
New two-leg statistics are a separate prospective cohort. Existing COMBO bot/private
recipient remains. No additional combined floor, bankroll/staking change, champion
change, Official/LIVE/ADMIN change, automatic deployment/promotion, provider call,
Telegram test send or historical bookmaker odds acquisition is authorized.


## Lab evening LIVE confirmation authorized 2026-10-07

The user reconfirmed that the already deployed LIVE Lab discovery stays enabled
from 18:00 inclusive until 23:00 exclusive Europe/Riga. PREMATCH/SINGLE/COMBO
discovery stays 10:00–18:00 Riga; pending-result checks continue outside discovery
windows. This supersedes the generic LIVE DISABLED wording in the later audit
request. Official and ADMIN Codex remain unchanged. Retain all installed model,
publication, freshness and shared-quota gates. No new deployment, automatic
training/promotion/rollback or Telegram test is authorized by this confirmation.


## LIVE quote age diagnostic policy authorized 2026-10-08

The user explicitly requested removal of LIVE coefficient freshness as a selection
blocker. For the operator-enabled API-Football Lab feed, quote origin/retrieval age
becomes diagnostic-only with no maximum age veto. This supersedes the LIVE
20-second quote-age gate; preserve original timestamps and prospective V2 policy
identity. Retain final exact refresh, state/event freshness, score/minute match,
valid temporal provenance, active-market, EV, uncertainty, divergence and duplicate
checks. PREMATCH/COMBO, champion, Official, schedule and quota ceilings are unchanged.
Deployment remains an explicit operator action. See
docs/operations/LIVE_QUOTE_AGE_DIAGNOSTIC_20261008.md.
