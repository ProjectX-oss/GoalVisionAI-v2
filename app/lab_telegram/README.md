# Manual Lab Telegram test

This package contains one inert operator command:

```bash
python -m app.lab_telegram.cli send-test
```

It reads the Lab token and destination from `.env`, requires the exact Lab
channel `-1003510920417`, rejects known or configured Official destinations,
uses bounded Telegram timeouts, and sends the fixed technical test message at
most once. `GOALVISION_LAB_TELEGRAM_ENABLED` controls no behavior here because
this is an explicit manual operation.

The package has no import from application startup, scheduling, prediction,
publication, statistics, settlement, model activation, or bankroll code.

Manual model operations remain a separate no-send boundary. Their optional Lab
adapter formats preview text only and never calls this sender. Any future
technical publication must continue to use only `@GoalVision_AI_Lab_Bot` and
channel `-1003510920417`; model operations must never publish activation,
rollback, bootstrap, diagnostics, or audit data automatically.
