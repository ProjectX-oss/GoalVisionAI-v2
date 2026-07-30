# Real Match Analysis to GoalVision AI Lab Runbook

## Purpose and safety boundary

This runbook covers one manually supplied upcoming football match. The feature
is experimental and isolated from Official publication, Official statistics,
Official bankroll, production activation, startup, scheduling, workers, live
betting, High Risk, Combo, and AutoTrader.

Dry-run commands never construct a Telegram transport and cannot send. Only the
explicit `send` command may call Telegram. Development and verification must use
a fake transport and must never use real credentials.

Hard-coded destination:

- Channel: 🧪 GoalVision AI Lab
- Chat ID: `-1003510920417`
- Bot: `@GoalVision_AI_Lab_Bot`
- Confirmation: `SEND_TO_GOALVISION_AI_LAB`

## Prerequisites

Use an operator-created database copy at the latest migration level. Never use
`data/goalvision.db` for rehearsal. The database must contain one verified,
controlled `OFFICIAL_GLOBAL` champion generation whose model artifact accepts
the live `goalvision_model_input_v1` / `official_prediction_model_input_v1`
contract and whose linked calibration artifact set passes the controlled
resolver's fingerprint checks.

At the current repository state, the trained artifacts use the separate
145-position historical schema. That is not compatible with the 78-position
live Feature Store schema. Analysis therefore fails closed until a reviewed
live-compatible champion is trained, compared, shadowed, and activated. Do not
work around this check.

## Input JSON

The top-level schema is `goalvision-real-match-lab-input-v1`. It contains:

- request, operator, `LAB` environment, and `OFFICIAL_GLOBAL` model scope;
- match/provider/event/snapshot identities;
- competition, season, teams, and UTC kickoff;
- collection and source-update timestamps;
- mandatory home and away recent-form records;
- optional venue, season, head-to-head, lineup, availability, injury,
  suspension, and match-context facts;
- one immutable price per supported single market;
- optional operator notes.

Supported markets are HOME_WIN, DRAW, AWAY_WIN, OVER/UNDER 1.5, 2.5, and 3.5,
and BTTS YES/NO. Correct score and combos are rejected.

All timestamps must include an offset. Kickoff must be future, evidence cannot
be future, and odds must precede kickoff and collection. Inputs are immutable:
reusing a request ID with different content is a conflict.

## Commands

Validate without opening a database:

```text
python -m app.real_match_lab_analysis validate-input --input path/to/match.json
```

Create the persisted dry-run:

```text
python -m app.real_match_lab_analysis analyze --database path/to/lab-copy.db --input path/to/match.json --output human
python -m app.real_match_lab_analysis analyze --database path/to/lab-copy.db --input path/to/match.json --output json
```

Inspect:

```text
python -m app.real_match_lab_analysis inspect --database path/to/lab-copy.db --analysis-id <id>
python -m app.real_match_lab_analysis preview --database path/to/lab-copy.db --analysis-id <id>
python -m app.real_match_lab_analysis inspect-markets --database path/to/lab-copy.db --analysis-id <id>
python -m app.real_match_lab_analysis events --database path/to/lab-copy.db --analysis-id <id>
python -m app.real_match_lab_analysis eligible --database path/to/lab-copy.db --analysis-id <id>
python -m app.real_match_lab_analysis delivery --database path/to/lab-copy.db --analysis-id <id>
python -m app.real_match_lab_analysis diagnose --database path/to/lab-copy.db --env-file .env
```

The preview reports the exact destination, model/calibration identifiers and
fingerprints, feature and model-input fingerprints, raw and calibrated
probabilities, fair/bookmaker odds, implied probability, edge, EV, freshness,
lineup status, selection/rejection reasons, and message fingerprint.

## Lab policy

The policy considers only supplied supported singles, requires valid actionable
odds and positive EV, ranks deterministically by calibrated probability, EV,
canonical market order, and assessment identity, and selects at most one. It
never creates a combo or stake. Official minimum odds and Quality Gate outcomes
are reported separately and are never weakened. A Lab candidate can remain
experimental when Official rejects it.

Reasons are deterministic facts from supplied data and computed features. No
generative model creates narrative reasoning.

## Explicit manual send

Set only the Lab-specific environment values:

```text
GOALVISION_LAB_TELEGRAM_BOT_TOKEN=<secret>
GOALVISION_LAB_TELEGRAM_CHAT_ID=-1003510920417
GOALVISION_LAB_TELEGRAM_BOT_USERNAME=@GoalVision_AI_Lab_Bot
```

Then, after reviewing the exact preview:

```text
python -m app.real_match_lab_analysis send --database path/to/lab-copy.db --analysis-id <id> --confirmation "SEND_TO_GOALVISION_AI_LAB"
```

Missing, partial, lower-case, or whitespace-modified confirmation is rejected.
Destination and bot overrides do not exist. The token is never printed.

## Exactly-once and failure recovery

A send first appends `CLAIMED`, performs at most one bounded Telegram call, then
appends `SENT`, `FAILED`, or `INDETERMINATE`. `SENT`, active `CLAIMED`, and
`INDETERMINATE` block another send. A confirmed `FAILED` outcome may be retried
as a new attempt. If Telegram accepted the message but terminal persistence
fails, the durable claim remains and automatic retry is forbidden. Inspect the
delivery history and reconcile manually with Telegram before any further work.

All analysis, evaluation, stage, and delivery records are append-only with
UPDATE/DELETE guards, foreign keys, deterministic IDs, and SHA-256 fingerprints.

## Verification

Before a separately authorized real send:

1. Use a database copy and record its hash.
2. Run `diagnose`; require schema 32, exact Lab destination/bot, and no secrets
   in output.
3. Run validation and analysis. Confirm delivery history is empty.
4. Inspect every market and provenance fingerprint.
5. Query Official publication, bankroll, and model-generation counts before and
   after the dry-run; they must be unchanged.
6. Confirm `data/goalvision.db` hash is unchanged.
7. Only then seek separate authorization for a real send.

## Limitations and deferred work

Manual facts can be incomplete or transcribed incorrectly; provenance and
freshness validation cannot prove source truth. This feature does not discover
upcoming fixtures, call a sports API, collect recurring data, schedule analysis,
send automatically, settle results, publish Official predictions, activate
production, or provide a dashboard. The next prerequisite is a reviewed
live-Feature-Store-compatible champion artifact and calibration chain.
