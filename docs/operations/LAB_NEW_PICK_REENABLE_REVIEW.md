# Controlled LAB new-pick re-enablement — 2026-09-26

Status: **LAB_NEW_PICK_REENABLE_READY_FOR_REVIEW**. Preparation only.

## Scope and provenance

- Branch: `codex/lab-new-pick-reenable`.
- Accepted operations parent: `9b74345e7cd76f3566485baaafb41676fba8b1c4`.
- Accepted application, unchanged: `4fd68bd9a71958152a91a6ca51cbc23ef96da47b`.
- Package: `/home/arvis/goalvision-operations/lab-new-pick-reenable-v1-20260926`.
- Manifest SHA-256: `31b4c2fab50b866d9db1ba59350cc6ca965afb71caa768602aee6a63ba57d7c1`.
- Final operations commit is recorded in the package's `SOURCE_REVIEW.json`.

The worktree is based on the accepted operations commit. The existing main
workspace and installed application were not edited. The new manifest inherits
all 3,625 host and 1,158 prior payload fingerprints unchanged, adds four package
runtime files, and replaces expected drop-in digests with digests computed from
the accepted compact/no-send rendering. Actual installed bytes were checked
against that rendering; drift was not incorporated into the baseline. The
manifest also pins the application/operations identities and history paths.

## Proposed configuration

The sole content change is in
`/etc/systemd/system/goalvision-lab-v2-discover.service.d/90-reviewed-prematch-v2.conf`:
insert `--send` immediately after `controlled-cycle` in `ExecStart`.

The complete literal diff is [LAB_NEW_PICK_REENABLE_PROPOSED_CONFIGURATION.diff](LAB_NEW_PICK_REENABLE_PROPOSED_CONFIGURATION.diff).
Package `.before` and `.proposed` files contain all four service drop-ins.

All four service release environments stay byte-identical. The settlement,
observer and weekly drop-ins stay byte-identical. Discovery keeps max-calls 400,
settlement-reserve 100, observation, labels, football-context root and registry,
and protected append stdout. Base units, timers/cadence, credentials, model,
thresholds, severe-disagreement publication policy, log rotation, database
history, Official and LIVE are unchanged. No release is deployed by this action.

## Operator action and safeguards

`enable-new-picks` requires the exact accepted compact application and recognized
no-send/observe/labels configuration. It rejects an existing recovery journal,
unknown or mixed drop-ins, disabled observation or labels, missing protected
stdout, and any reviewed file, metadata, effective command/environment or
configuration-directory drift. Existing unloaded-drop-in inspection remains.

The shared installer lock, prior active timer capture/pause/restoration, all four
service start gates, service drain, byte checks, fsynced recovery journal and
fail-closed recovery remain. Protected stdout/rotation are verified read-only;
this package does not create, truncate, rotate or replace them.

A fresh bounded history check runs before any timer/configuration mutation and
again after all four services drain, immediately before writing the configuration.
It uses SQLite `mode=ro`, `query_only`, separate read transactions, three-second
connection waits and a 15-second SQL progress deadline per database. There are
no application imports, provider calls, reconciliation or database writes.

The check counts all durable publication/economic claims without receipts,
unknown outcomes, invalid receipts, and PREMATCH weekly unknown/unreceipted
claims. It inspects the latest 200 persisted publication-cycle reports and up to
200 complete records from the current protected stdout file, with a 64 MiB bound
per source. Explicit unknown/failed delivery, unresolved transport evidence and
acknowledgement without persisted receipt block enablement. Missing, malformed,
partial, oversized or timed-out evidence fails closed. These are bounded current
checks; they do not claim to audit every historical JSON document or rotated log.

For this one-time action, **any pending published single/combo settlement blocks
enablement**, including legacy combo receipt identities. This conservative gate
ensures no pending settlement can conceal an integrity blocker. It changes no
settlement logic. The stored review is evidence only; it never replaces the two
fresh checks during a future authorized action. Separate database snapshots are
not a simultaneous cross-database snapshot; the second check runs behind the
existing systemd fences. Those fences do not authorize concurrent manual publishers.

Failed enablement restores the exact journaled compact/no-send configuration,
with observation and labels true. The package refuses journal-free `recover`
and `upgrade`; it cannot select an older release as a default rollback target.
If recovery fails, gates and the journal remain, and paused timers stay paused.
Run the same pinned helper with `recover` only after reviewing that failure.
Never remove claims, receipts, gates or the journal to force a retry.

`disable-new-picks` is the immediate operator kill switch. It retains observation
and labels, works without delivery/history clearance, and is idempotent. Its
journal records both the actual prior bytes and an explicit no-send recovery
target, so a failed disable cannot recover back to `--send`. It shares the same
lock and safe drain; it does not interrupt a running publication mid-transport.
A pending transaction still requires the existing reviewed recovery procedure.

The helper starts only previously active timers; it never starts a service or
runs an application cycle. An authorized enablement takes effect at the next
scheduled discovery tick after timer restoration. No post-enable scheduled tick
has been performed or verified by this preparation task.

## Evidence and validation

- **168 operations/history tests passed**, zero failures, errors or skips.
- **380 accepted-application regression tests passed**, zero failures, errors or skips.
- Tests ran with network syscalls denied by inherited seccomp rules; systemd
  administration used fakes and databases were disposable.
- Tests cover exact no-send/send bytes, unchanged compatible service settings,
  drift before mutation, both history-check boundaries, claim/unknown/acknowledgement
  and settlement blockers, SQL timeout and evidence bounds, protected stdout,
  failure recovery, monotonic/idempotent disable, concurrent CLI lock rejection,
  retained recovery fences and the absence of manual service/application starts.
- Read-only host verification passed: compact release, no-send, observe=true,
  labels=true, no journal, protected stdout, 1,162 payload hashes, 3,625 host
  hashes and 288 configuration-directory inventories.
- Fresh bounded current history review found **zero in every blocker category**.
  Timestamp and inspected record counts are in `CURRENT_HISTORY_REVIEW.json`.
- No prediction algorithm changed; the exact accepted application and its model
  remain pinned. No new model training or backtest was needed for this operator
  control; its 380 offline application regressions were rerun.

The package includes the manifest, helper/primitives/history reader, before/after
bytes, exact diff, JUnit evidence, tests, review, source provenance and `SHA256SUMS`.
It depends on the existing accepted release/environment and earlier pinned package
files referenced by the manifest; those paths must be retained. Package files are
made read-only by file permissions, with no root-only immutability claim.

## Proposed enable command — NOT EXECUTED

```bash
sudo /home/arvis/GoalVisionAI/.venv/bin/python -B /home/arvis/goalvision-operations/lab-new-pick-reenable-v1-20260926/upgrade_prematch_reviewed.py /home/arvis/goalvision-operations/lab-new-pick-reenable-v1-20260926/manifest.json enable-new-picks --sha256 31b4c2fab50b866d9db1ba59350cc6ca965afb71caa768602aee6a63ba57d7c1
```

## Emergency disable command — NOT EXECUTED

```bash
sudo /home/arvis/GoalVisionAI/.venv/bin/python -B /home/arvis/goalvision-operations/lab-new-pick-reenable-v1-20260926/upgrade_prematch_reviewed.py /home/arvis/goalvision-operations/lab-new-pick-reenable-v1-20260926/manifest.json disable-new-picks --sha256 31b4c2fab50b866d9db1ba59350cc6ca965afb71caa768602aee6a63ba57d7c1
```

No sudo command, deployment, enablement, Telegram message, provider call, manual
discovery cycle, merge or push was executed. Only read-only installed-state/history
inspection and local source/package/test/documentation work were performed.
