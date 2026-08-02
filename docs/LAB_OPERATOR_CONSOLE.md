# GoalVision AI Lab Operator Console

## Boundary

The console is a local, manual review surface over existing immutable Lab and
forward-test evidence. It is not a production website. It has no cloud hosting,
remote assets, analytics, telemetry, external fonts, scheduler, startup action,
automatic discovery, inference, result capture, settlement, report publication,
or Telegram send.

The implementation uses Python's standard-library HTTP server and server-side
HTML templates. This avoids a new dependency and build pipeline. Templates
receive typed presentation models; they never query SQLite.

## Launch

Read-only is the default:

```text
python -m app.lab_operator_console run --database var/first_lab_forward_test.db --host 127.0.0.1 --port 8765
```

Explicitly enable confirmed local actions:

```text
python -m app.lab_operator_console run --database var/first_lab_forward_test.db --host 127.0.0.1 --port 8765 --enable-actions --operator <operator-id>
```

Validate without starting a server:

```text
python -m app.lab_operator_console config-check --database var/first_lab_forward_test.db --output json
```

The database must exist below an allowed root. The only supported host is
`127.0.0.1`; `localhost`, `0.0.0.0`, LAN and public interfaces fail closed.
Ports below 1024 and above 65535 are rejected. Do not reverse proxy, tunnel,
expose, or deploy this console.

## Sessions and actions

A random 32-byte session secret is created in memory by default. It is never
printed or persisted; sessions become invalid on restart. The cookie is
HttpOnly, SameSite=Strict and expires after one hour. POST forms use
session/action/time-bound HMAC CSRF tokens. Browser storage is not used.

Every state change is POST-only and requires explicit action-enabled mode, an
operator identifier, CSRF and exact confirmation text. Schema v39 stores a
sanitized append-only request/event chain with provider/Telegram call counts
and fingerprints. GET requests never write evidence. Arbitrary SQL, shell,
Python, endpoints, provider URLs, chat IDs, tokens and credentials are rejected.

Provider readiness and discovery types are bounded to one and forty calls, but
this foundation deliberately has no injected provider executor: they stop as
audited `BLOCKED` with zero calls. The fake Lab-send action is demo/test only and
never constructs a Telegram transport. Real sends remain exclusively behind
the existing hardened sender and its independent confirmation contract.

## Pages

Overview, Readiness, Discovery, Candidates, Fixtures/Baselines, Odds,
Analyses/Market Comparison, Observations, LAB Previews, Publication Reviews,
Send Readiness, Results, Settlements, Monitoring, Reports, Unresolved,
Incidents, Health and Operator Actions are server-rendered from typed read
models. Correct-score and combo predictions are never rendered.

The Reports page exposes separately confirmed weekly, cumulative, exact
reproduction, comparison and export actions. Export destinations are safe
directory names resolved beneath an operator-configured allowed root;
arbitrary paths and overwrite are rejected. These actions never publish.

Monitoring retains `HYPOTHETICAL_FLAT_STAKE` and sample warnings. Opening any
page makes zero provider calls. Result and settlement pages never mutate merely
because they were viewed.

## Fictional demo

```text
python -m app.lab_operator_console demo --database var/lab_operator_console_demo.db --no-serve --output json
```

Remove `--no-serve` to inspect locally. Every page is labelled `CONTROLLED
FICTIONAL DEMO DATA`. Six unique fixtures cover win, loss, void, no-selection,
calibration blocker and shift blocker; passed/blocked reviews; conflict
incidents; weekly/cumulative reports; and unresolved work. The demo performs
zero network, Telegram, delivery, Official, bankroll, statistics, activation or
scheduling changes. Never use it as genuine evidence.

## Shutdown, backups and limitations

Stop with Ctrl+C. Copy and hash the isolated database only while writers are
stopped. Afterward run foreign-key/health checks and hash it again. Do not commit
`.env`, cookies, demo databases or temporary exports.

Localhost and CSRF are not multi-user authentication. There is no TLS, role
system or public hardening. Public exposure is rejected rather than documented.

## After API-Football Pro activation

On or after 2026-08-10, run the existing one-call readiness verification with
explicit confirmation and inspect persisted evidence. Then use the established
bounded discovery service, inspect current-season baselines and exact current
odds, and run the existing dry-run pipeline. Create/review one genuine Lab
observation only if every gate passes. Keep the console read-only for review.
Publication, result and settlement remain separate explicit operations.
# Reasoning integration

The read-only `Reasoning` page shows immutable public and operator explanations,
feature/group evidence, all market explanations and audit status. With actions
explicitly enabled, `CREATE_REASONING` remains a confirmed, zero-network,
zero-Telegram action. See `LAB_PREDICTION_REASONING.md`.
