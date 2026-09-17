# AGENTS.md

# GoalVision AI

Version: 1.0

This document is the highest-level engineering guide for every AI agent,
developer and contributor working on GoalVision AI.

Every implementation must follow this document.

If there is any conflict between implementation and this document,
this document always wins.

---

# 1. PROJECT VISION

GoalVision AI is not just a Telegram bot.

GoalVision AI is a long-term AI-powered football analytics platform.

Our mission is to create the most transparent football prediction platform
using AI, statistics and disciplined bankroll management.

The project must always prioritize:

1. Accuracy
2. Transparency
3. Stability
4. Trust
5. Long-term profitability

Never optimize for hype.

Always optimize for long-term quality.

---

# 2. PRODUCT PHILOSOPHY

GoalVision AI never guarantees profit.

GoalVision AI never guarantees winning bets.

GoalVision AI never manipulates statistics.

GoalVision AI never hides losing predictions.

Every prediction becomes public history.

Trust is more important than short-term performance.

---

# 3. OFFICIAL PRODUCTS

GoalVision AI consists of independent products.

## Official

Main Telegram channel.

Contains only official predictions.

Official bankroll.

Official statistics.

---

## LIVE

Independent Telegram channel.

Publishes only high-confidence live value bets.

Uses:

- Lineups
- Live match statistics
- Match events
- Momentum
- AI evaluation

Every live prediction must include reasoning.

---

## High Risk

Independent Telegram channel.

Own bankroll.

Own statistics.

Experimental strategy.

Never affects Official statistics.

---

## Combo

Independent Telegram channel.

Own bankroll.

Own statistics.

Combination bets only.

Contains Weekly Mega Combo.

---

## Lab

Testing environment.

New AI models.

Backtesting.

Experimental algorithms.

Never affects Official statistics.

---

## Admin

Private channel.

System notifications.

Errors.

Deployment logs.

Bank alerts.

Server status.

---

## Test

Development environment.

Every new feature must be tested here first.

---

# 4. PREDICTION POLICY

Official channel publishes:

Single Bets only.

Minimum odds:

1.60

Exception:

If no qualifying single exists,

one Combo Bet

Maximum selections:

2

Minimum combined odds:

2.00

---

Weekly Mega Combo

Allowed.

Entertainment only.

Minimum odds:

10+

Tracked separately.

Never affects Official bankroll.

---

Never publish:

Correct Score predictions.

Guaranteed bets.

Impossible claims.

---

# 5. TRANSPARENCY

Always publish:

Winner

Probability

Confidence

Reasoning

After every match:

WON

LOST

Weekly:

Bank

Wins

Losses

Strike Rate

Monthly:

Bank report

Performance report

Never delete losing predictions.

Never modify historical results.

---

# 6. BANK MANAGEMENT

Every product has its own bankroll.

Official

High Risk

Combo

LIVE (future)

Never mix bankrolls.

Never mix statistics.

---

# 7. AI PRINCIPLES

Every new feature must improve:

Prediction quality

OR

Explainability

Otherwise reject it.

Every algorithm change must be backtested.

Never deploy untested prediction logic.

---

# 8. ENGINEERING PRINCIPLES

Priority order:

1 Stability

2 Accuracy

3 Readability

4 Performance

5 New Features

Never sacrifice stability for speed.

---

# 9. ARCHITECTURE

Keep modules independent.

Prediction Engine must never depend on Telegram.

Telegram must never contain prediction logic.

Database must never contain business logic.

Business logic belongs only inside services.

Keep prediction pipeline deterministic.

Same input must always produce same prediction.

---

# 10. CODING RULES

Avoid duplicated code.

Avoid global mutable state.

Avoid circular imports.

Use dependency injection.

Keep functions small.

Prefer composition over inheritance.

Document public APIs.

Type hints everywhere.

---

# 11. API RULES

Football API failures must never crash GoalVision AI.

Retry when reasonable.

Use caching.

Respect rate limits.

Never expose secrets.

Never commit:

.env

API keys

Bot tokens

Database files

Logs

---

# 12. TESTING

Every important feature requires:

Unit tests

Integration tests

Regression tests

Backtesting

No production deployment without testing.

---

# 13. CODEX AUTHORITY

Codex MAY:

Write code

Refactor

Optimize

Write tests

Write documentation

Improve architecture

---

Codex MUST NOT:

Change prediction philosophy

Change bankroll rules

Change publication rules

Change confidence thresholds

Change odds policy

Deploy production

Delete historical statistics

Without explicit user approval.

---

# 14. LONG TERM ROADMAP

GoalVision AI will evolve into:

Telegram Platform

Website

Dashboard

REST API

Mobile App

Analytics Platform

Partner Integrations

Official APIs

Everything must be built with scalability in mind.

---

# 15. DEVELOPMENT WORKFLOW

Always:

Read AGENTS.md

Read PRODUCT_RULES.md

Read ROADMAP.md

Read TASKS.md

Understand existing architecture.

Implement.

Test.

Document.

Commit.

Never skip documentation.

---

# 16. FINAL RULE

If there are multiple possible implementations,

always choose the solution that makes GoalVision AI

more maintainable,

more scalable,

more transparent,

and easier to optimize in the future.

GoalVision AI is a long-term product.

Every decision must support that vision.
