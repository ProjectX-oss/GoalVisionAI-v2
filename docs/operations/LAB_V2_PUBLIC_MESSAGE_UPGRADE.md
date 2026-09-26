# Lab V2 public message upgrade — 2026-09-26

Prepared for review only. No deployment, timer stop, provider request, Telegram
message, live discovery cycle, sudo, push or merge was performed.

Application branch: `codex/lab-v2-public-message` (accepted base `4fd68bd`).
Operations branch: `codex/lab-v2-public-message-upgrade` (base `9b74345`).
The exact commits and application tree are in the versioned package's
`SOURCE_REVIEW.json`.

Package: `/home/arvis/goalvision-operations/lab-v2-public-message-upgrade-v1-20260926`.
Proposed isolated release:
`/home/arvis/GoalVisionAI-prematch-release-public-message-v2-20260926`.
Current/recovery release:
`/home/arvis/GoalVisionAI-prematch-release-compact-output-4fd68bd-20260926`.

## Scope and compatibility

Only new labelled V2 single messages use the new Latvian formatter and frozen
confirmed-publication statistics. Historical previews, exact replay, receipts,
claims and internal linkage remain unchanged. Settlement P/L comes from the
accepted `unit_result`; cohort formulas are reused. All eleven current markets
remain supported. Combo statistics remain separate. No database migration,
policy/model change or algorithm backtest is needed. See the application's
`docs/LAB_V2_PUBLIC_MESSAGES.md` for the snapshot and compatibility contract.

The operations helper accepts publication-enabled installed state only when the
pinned manifest sets `preserve_new_picks=true`. Upgrade carries the actual
publication, observation and label state forward. The package binds the exact
installed `true/true/true` drop-ins. Normal recovery retains these capabilities;
failed/interrupted upgrade recovery restores the journal's exact prior bytes.
Existing disable controls remain monotonic, and old manifests retain their
publication-disabled contract.

The existing lock, timer pause, start gates, drain, atomic switch, restoration and
recovery journal remain in use. These mechanisms run only during a future
operator-authorized installation. No first-install `apply` is used. After a
successful upgrade the next scheduled tick imports the new release automatically.

## Configuration and validation

The exact diff is `PROPOSED_CONFIGURATION.diff`: only four `EnvironmentFile`
paths change. `new_picks=true`, `observe=true`, `labels=true`; discovery command,
quotas, timer cadence, settlement and protected stdout remain unchanged.
Credentials are fingerprint-checked without printing or copying their contents.

- 407 application tests passed (27 new presentation tests plus 380 directly
  affected regressions), zero failures/errors/skips.
- 114 operations/rollout tests passed, zero failures/errors/skips, including
  enabled publication, old disabled states, failures at switch/reload/timer
  restoration, interrupted recovery, locking, gates, drift and protected output.
- Tests used disposable stores, fake transports and fake systemd. The offline
  launcher denied network syscalls, inherited by subprocesses.
- Package validation is read-only. Exact outcome is in `PACKAGE_VERIFICATION.json`.
  It checks installed configuration, clean application identity, both release
  contents, interpreter pins and protected output metadata.
- `SAMPLE_MESSAGES.md` contains generated synthetic prediction/WON/LOST/VOID text.
  The samples are illustrative, not production statistics.

## Operator commands

`COMMANDS.md` contains the exact manifest SHA-256, read-only check, one-line
upgrade and recovery commands. Upgrade/recovery commands are prepared but were
not executed. Run the check again immediately before any authorized installation;
configuration or package drift must be reviewed before proceeding.

If recovery cannot finish, retain the start gates and journal and use the pinned
`recover` command after resolving the reported failure. Never delete claims,
receipts, previews or the transaction journal to retry. Recovery restores the
compact-output release and its exact original `true/true/true` capabilities.
