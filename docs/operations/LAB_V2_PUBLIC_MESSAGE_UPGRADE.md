# Public message upgrade: corrected operations lineage

Status: **PUBLIC_MESSAGE_V2_UPGRADE_READY_FOR_REVIEW**. Preparation only.

## Sources and package

- Operations branch: `codex/lab-v2-public-message-upgrade-v2`.
- Operations parent: `ac2ffec3dd7fed0ca596a384a6096cf9fa90350a`.
- Application remains `23e57e9c48f321b8ee5f67bd536fbb2b264f6cb0`.
- Package: `/home/arvis/goalvision-operations/lab-v2-public-message-upgrade-v2-20260926`.
- Exact operations commit, manifest digest, commands and local verification are
  recorded in `SOURCE_REVIEW.json`, `COMMANDS.md` and `PACKAGE_VERIFICATION.json`.

This branch starts directly from the accepted production operations lineage.
It replaces the divergent `29c04bf` preparation. No application files change.
The package inherits the accepted re-enablement manifest's fingerprints and
configuration contracts, then pins this helper and the accepted presentation
release. It checks installed bytes against the known send-enabled rendering;
unknown drift cannot become a new baseline.

## Recovery contract

| Operation | Successful target | Failure recovery target |
| --- | --- | --- |
| Formatter `upgrade` | New release, existing send/observe/labels capabilities | Exact pre-upgrade bytes, including send=true |
| `disable-new-picks` | Same upgraded release, send=false; observation/labels preserved | Explicit journaled no-send target |
| `recover` with journal | Recorded recovery target | Same recorded recovery target |
| `recover` without journal | Previous compatible release, current capabilities | Exact prior bytes |

The kill switch remains monotonic, idempotent and independent of delivery/history
clearance. Its journal retains actual `before` bytes for evidence and distinct
`recovery` bytes for safe restoration. A disable journal that would restore
send=true is rejected. Never remove the journal or gates to force a retry.

If automatic recovery fails, retain the journal and gates. A final timer-stop
attempt handles partially successful timer restoration, and gate installation is
attempted even if that stop fails. Explicit recovery retries toward the journal's
safe target after the underlying fault is resolved. Permanent filesystem or
systemd failures may prevent a gate write or timer stop; the other fence remains,
and the helper never restores send=true for a disable action or starts timers
against send=true during disable recovery.

An interrupted gate write/cleanup can leave systemd's loaded gate list different
from disk. Recovery accepts only the owned drop-in with or without its known
gate, re-establishes gates, drains, then validates. Unknown gate bytes, unrelated
drop-ins, mixed unknown release bytes and mismatched manifests still fail closed.

Old packages retain their prior state-recognition contract. Send-enabled previous
release recognition requires the literal boolean `preserve_new_picks=true` in the
pinned formatter manifest. The accepted compact-only enablement action and its
fresh history checks are retained; this formatter package cannot enable picks.

## Configuration and protections

`PROPOSED_CONFIGURATION.diff` changes exactly four `EnvironmentFile` references
from the compact package environment to this package's environment. Discovery
keeps `--send`, `--max-calls 400`, `--settlement-reserve 100`, observation arguments,
labels and protected append stdout. Before and after capabilities are
`new_picks=true, observe=true, labels=true`.

The installer lock, exact configuration checks, service drain, start gates,
fsynced journal, prior active timer restoration, protected stdout and log rotation
remain. No service/application/manual discovery cycle is invoked. Existing
receipts, claims, previews, settlement records and database history are untouched.
There is no prediction algorithm or policy change requiring a new backtest.

## Verification

- 236 operations/history/rollout tests pass, including the accepted lineage tests.
- 407 application regressions pass at exact `23e57e9`, including all 27 public
  presentation cases and delivery/history regressions.
- Upgrade and disable failures are injected at timer stop, gate write, drain,
  drop-in write, verification, reload, gate cleanup and timer restoration.
- Automatic disable recovery failures retain the safe journal; explicit recovery
  produces no-send. Tests cover partial timer start, persistent faults, unknown
  recovery drop-ins, unsafe legacy journals, old packages, locking and no cycles.
- Tests use disposable stores and fake systemd. Inherited seccomp rules deny
  network syscalls. JUnit evidence and test commands are packaged.

## Operator use

`COMMANDS.md` contains the read-only check and the prepared upgrade, emergency
disable and recovery commands with the exact manifest SHA-256. Mutating commands
were **not executed**. The new package's disable command applies after upgrade;
before upgrade, use the accepted `lab-new-pick-reenable-v1-20260926` controls.
A pending journal requires its matching package's `recover` action.

Run the read-only check again before an authorized installation. Keep the earlier
pinned packages/releases because the manifest verifies their reviewed bytes.
No deployment, sudo, real timer stop, provider request, Telegram message, manual
cycle, push or merge was performed. No main-workspace user edits were changed.
