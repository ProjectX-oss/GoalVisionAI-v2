# PREMATCH installer hardening — 2026-09-25

Installation status: **BLOCKED pending review/operator execution**.
The old `/home/arvis/goalvision-operations/prematch-v2-release-e120f1b`
package **MUST NOT be applied**. Its installer has both independently reproduced
defects. The old package is retained unchanged for comparison, not reused.

Base branch: `codex/prematch-full-audit-v2-enablement`.
Documentation base: `2c08974a180bf891233d91858545d2e91426c29d`.
Preserved tested application: `e120f1b81f37c8774291e82c952378ce467fb139`.
Reproduced installer blob: `bceafa342d3672080fb35f370d2322cb00658ade`.
This focused commit changes only installer, tests and documentation. The `app/`
tree remains byte-identical to the tested application. The completed audit is
preserved; this is not a repeat application audit or an algorithm change.

## Corrected controls

The installer recognizes exact rendered command states before changing anything.
Unexpected command, quota, environment, base-unit, effective-fragment or drop-in
drift is refused, including drift found after draining. The release must be clean,
the installer must match its committed release copy, and the environment must
match both its hash and the exact pinned release path. The rollback ledger must
match discovery's effective working directory and ledger argument/default.

`disable-new-picks` removes only `--send`, preserving the current observation and
label controls. `disable-data-labels` removes observation arguments and
`--label-v2-selections`, preserving the current publication control. Either order
ends with all three disabled. Repeated operations are idempotent. Previously
recognized no-send/no-label states also stay disabled. Settlement, observer and
weekly service drop-ins are untouched by either disable action.

## Rollback ordering and evidence

1. Acquire the fixed host-wide nonblocking `flock` at
   `/run/lock/goalvision-prematch-v2-installer.lock`. All new installer actions use
   this same lock regardless of manifest/package path. Never unlink its inode.
2. Validate configuration and record timer states. Pause only previously active
   timers for the four reviewed services; verify the relevant triggers paused.
3. For rollback only, install temporary runtime drop-ins named
   `91-prematch-installer-quiesce.conf` for those services. Their
   `ConditionPathExists=!/run/lock/goalvision-prematch-v2-installer.lock` condition
   skips new starts while existing processes finish. Reload and verify these exact
   gates are loaded. No service is stopped, restarted, killed or frozen.
4. Drain relevant services (up to 30 minutes). Revalidate release/configuration.
   Acquire a SQLite `BEGIN IMMEDIATE` writer reservation on the existing ledger
   in `mode=rw`; inability to open/lock/query it refuses rollback.
5. Under that reservation, perform the decisive compatibility query, then recheck
   service idleness immediately before changing release configuration. Any labelled
   single with a receipt, durable claim, unknown delivery or economic claim refuses
   rollback. A claim without a receipt is potentially delivered, including a claim
   whose transport outcome was lost. Conservative refusal also applies to unusual
   receipt shapes and blocked claims; absence of a successful receipt is not proof
   of no publication. Unclaimed prepared records and ordinary legacy receipts do
   not alone prohibit rollback.
6. Hold the writer reservation through configuration changes, verification,
   daemon reload, removal of temporary gates and any configuration recovery. The
   unchanged reviewed sender commits a durable ledger claim before transport, so a
   competing publisher cannot newly claim a labelled send during this interval.
   A pre-existing labelled claim makes rollback refuse before mutation. This uses
   the existing publication protocol; no application/deployment framework is added.
7. On handled refusal/failure, retain or restore original compatible release
   drop-ins and remove this operation's temporary gates. Restore exactly the
   previously active timers. Release the installer lock after recovery.

No ledger document is inserted, updated or deleted by the guard; its reservation
ends with rollback. A rollback failure after release-file mutation restores the
original files under the same writer reservation. Unrelated services/timers,
learning service, champion, settlement evidence and statistics are preserved.

Scope: the start gates cover the reviewed systemd services; the database fence
covers cooperating senders using the reviewed ledger claim protocol. Do not run
manual discovery, an obsolete installer, or alternate publishers during operator
execution. An uncatchable process/host failure can leave timers paused or temporary
gates present; the next invocation refuses that drift. Inspect service idleness and
retained configuration before operator recovery. Never delete claims/receipts to
force a rollback. A refusal after labelled publication requires compatible code;
use the disable controls to stop prospective work.

## Focused deterministic validation

Final checks run after the last installer/test/documentation change:

```bash
/home/arvis/GoalVisionAI/.venv/bin/python docs/operations/offline_test_runner.py /home/arvis/GoalVisionAI/.venv/bin/python -m pytest -q tests/test_prematch_v2_rollout.py
/home/arvis/GoalVisionAI/.venv/bin/python docs/operations/offline_test_runner.py /home/arvis/GoalVisionAI/.venv/bin/python -m pytest -q tests/test_prematch_v2_enablement.py tests/test_lab_combo.py
```

Recorded handoff results: **42 installer tests passed**; **43 directly
related publication/settlement tests passed**. Exact final output is retained in
`/home/arvis/goalvision-operations/prematch-installer-hardening-20260925-v2/`.
The existing offline launcher denies network syscalls, inherited by subprocesses.
Installer tests use disposable paths, fake systemctl/systemd-analyze/git responses,
synthetic SQLite evidence and a separate process to test lock contention.

Regressions cover both disable orders and repeats, monotonic capabilities, receipt
arrival during drain, uncertain sends, successful drained rollback, lock/query/
verification/reload/drain/start-gate failures, configuration recovery while the
writer fence remains held, timer restoration, competing installer invocation,
blocked concurrent claims, drift refusal and unrelated service/evidence preservation.
Existing lifecycle tests cover publication claims, ambiguous delivery, receipt-bound
settlement and cohort accounting. No unrelated historical/ML suites were rerun.

## Replacement package and operator command

New versioned package:
`/home/arvis/goalvision-operations/prematch-v2-installer-v2-20260925`.
New clean detached release:
`/home/arvis/GoalVisionAI-prematch-release-installer-v2-20260925`.
The package's `manifest.json` pins the full focused commit containing this report;
`PACKAGE_VERIFICATION.json` records that commit and exact artifact hashes after
preparation. The versioned directory is created exclusively, never overwritten.

[The committed secret-free review record](PREMATCH_INSTALLER_V2_PACKAGE_REVIEW.json)
retains every manifest field except the containing commit's self-reference, the
source manifest hash, installer hash, full environment text, all four drop-in
previews and their hashes. Compare its fields with the actual manifest, whose
exact SHA-256 is also retained in the external verification report and operator
summary. Original services, quota arguments, discovery command, observation
arguments, ledger path and installed fingerprints are copied unchanged from the
old local manifest. Only the release/package identity and environment binding
change. Historical import/observation reports are not relabelled as new evidence.

After review, the operator command is:

```bash
sudo /home/arvis/GoalVisionAI/.venv/bin/python /home/arvis/goalvision-operations/prematch-v2-installer-v2-20260925/install_prematch_v2.py /home/arvis/goalvision-operations/prematch-v2-installer-v2-20260925/manifest.json apply
```

This command was **not executed**. Use the same package/manifest with
`disable-new-picks`, `disable-data-labels` or `rollback` when appropriate. The new
package is not an in-place replacement for an already installed old package:
its exact environment/command validation will refuse that mismatch for review.

Stable operator summary:
`/home/arvis/goalvision-operations/PREMATCH_V2_OPERATOR_SUMMARY.md`.
Package report: the new package's `PACKAGE_VERIFICATION.json`.
No sudo command, real systemd mutation, live discovery, provider request, Telegram
message, deployment, merge or push was performed. Models, thresholds, quotas,
Official, LIVE and historical statistics remain unchanged.
