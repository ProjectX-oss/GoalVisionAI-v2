# PREMATCH ADMIN alerts v1.1 — output contracts and exact recovery

**Status: ADMIN_ALERTS_V1_1_BLOCKED.** The ADMIN code, tests and upgrade package are prepared. Required live ADMIN database/configuration and historical manager evidence could not be read. No installation, push, merge, Telegram send or PREMATCH control operation occurred.

Branch: `codex/prematch-admin-alerts-v1-1`, based on `7acdec28bb759ab89c6f0a913d0856fbe8c885c8`.

## Findings for the two requested invocations

The installed settlement unit has **`StandardOutput=null`, `StandardError=journal`**. The installed `app/lab_combo/cli.py:266` writes its final result with `print(canonical_json(value))`. Thus its normal final JSON goes to discarded stdout. This is an invalid journal-output assumption in ADMIN v1, not evidence of a failed settlement. No producer changes are needed or included.

The loaded unit has `NeedDaemonReload=no`. Its unit/drop-in hashes match the v1 baseline captured before these invocations. This establishes the configuration explanation. It does not reconstruct historical systemd exit status or prove that a particular execution reached the final print.

| Invocation | Sanitized finding | Readable journal evidence (UTC, 2026-09-27) | Incident assessment |
|---|---|---|---|
| `98ef19a6d7cd463a8f03842c5decd889` | `OUTPUT_CONTRACT_NOT_APPLICABLE` | Six entries, 06:50:13.239648–06:50:23.786218; no JSON object | `7f2cfe2a621b163f2367ac94`: unsupported output-contract alert; historical execution/association unresolved; retain OPEN |
| `7e9844d0c9a54464a4fde8bd7ce6417e` | `OUTPUT_CONTRACT_NOT_APPLICABLE` | Six entries, 07:00:09.183144–07:00:35.479641; no JSON object | `d9f68a79d28d17a4bcb88d10`: unsupported output-contract alert; historical execution/association unresolved; retain OPEN |

For **each** invocation:

- All six readable entries carry the exact trusted `_SYSTEMD_INVOCATION_ID` and matching unit. None contains final structured JSON. Final stdout emission itself is not observable through the configured sink.
- Historical `Result`, `ExecMainStatus`, start and exit timestamps are **UNKNOWN**. Exact manager-field queries returned no readable manager records. Current `systemctl show` describes a newer invocation and was not attributed to either historical execution.
- The live ADMIN journal cursor and incident evidence are **UNKNOWN** to this investigation: `/var/lib/goalvision-admin-alerts` is mode 0700 owned by its dedicated account. The live configuration is also unreadable. `sudo -n` required a password. No permission changes or credential access were attempted.
- Output arriving after the 180-second grace is **NOT PROVEN**. There is no final-output timestamp to compare. Existing output that ADMIN failed to associate is also **NOT PROVEN**.
- The contract defect explains why v1 can produce a false alert for this service. Neither incident is certified as a valid producer failure or as an exactly recovered false positive. Both remain **unresolved**, with their existing history intact.

Investigation read six entries per invocation with a 100-entry cap. The single later rehearsal read the same six per invocation with a 94-entry cap. No other invocations' journal records were inspected. Raw messages, provider payloads and secrets were neither printed nor committed. Sanitized cursor references are in [the evidence summary](PREMATCH_ADMIN_ALERTS_V1_1_EVIDENCE.json).

## Old defect and v1.1 behavior

V1 treated every completed non-discovery oneshot as requiring journal JSON. Any JSON dictionary counted as output, and `outputs[unit]` retained only one invocation. The absence branch opened invocation-specific `MISSING_OUTPUT`, but there was no corresponding healthy event. A newer successful invocation could replace the remembered output without resolving the earlier incident.

[Output contracts](../../app/admin_alerts/output_contracts.py) now have an explicit version, source and association policy for all five services:

| Service | Contract version/source | Evidence accepted |
|---|---|---|
| `goalvision-lab-v2-discover.service` | 1 / `COMPACT_STDOUT` | Recognized operator-cycle schema and timestamp; `TIME_WINDOW_ONLY` |
| `goalvision-lab-combo-settle.service` | 1 / `NONE` | No verifiable per-invocation output artifact; stdout is discarded |
| `goalvision-adaptive-learning-observer.service` | 1 / `STRUCTURED_JOURNAL_JSON` | Final PREMATCH observer document with timestamp, linkage/state/metrics and inert-worker fields |
| `goalvision-adaptive-learning.service` | 1 / `STRUCTURED_JOURNAL_JSON` | Final eligibility shape or an allowlisted research outcome |
| `goalvision-lab-weekly-stats.service` | 1 / `STRUCTURED_JOURNAL_JSON` | Allowlisted final status and boolean `sent` |

Health, ledger and weekly persisted evidence continue their existing independent checks. Their records are not promoted into exact systemd invocation proof. `NONE` affects only new output-absence alerts; systemd failure, timeout, timer and existing diagnostic rules remain enabled.

Journal recovery requires the final document, matching `_SYSTEMD_UNIT` and trusted `_SYSTEMD_INVOCATION_ID`. Arbitrary diagnostic JSON and manager-only invocation fields cannot satisfy this contract. Loaded stdout routing must also be `journal` before opening a new journal-output absence incident; unknown routing produces a coverage warning.

Recovery uses `MISSING_OUTPUT healthy=True` with the **same service, object ID and invocation**. Incident signature version remains 1, so existing incident IDs survive. The recovery observation uses the time proof was acquired; its facts retain the original journal timestamp/cursor. This permits a historical output timestamp to recover an incident opened later when that output was missed.

- Stream delivery emits recovery even after grace, after restart, or after systemd has moved to a newer invocation.
- A bounded exact lookup revisits two unresolved incidents per scan, round-robin, up to 100 records and the existing byte/deadline bound per invocation. It does not advance the main journal cursor. Output outside the retained/bounded journal window stays unproven.
- A bounded cache keeps 32 proven invocations per service. Cursor loss retains verified proofs. The old v1 `outputs` mapping is not accepted as final-output proof.
- Recovered invocation tombstones prevent stale absence checks from reopening the same terminal invocation. A different invocation cannot recover it.
- Existing `Store.ingest` and `Store.enqueue` semantics are reused. An unsent OPEN incident recovered by exact evidence leaves its attempts=0 PENDING outbox entry `SUPERSEDED`, with no recovery notification. Enabling a fake sender later sends neither stale fault nor unnecessary recovery.
- Discovery retains conservative absence detection. Its incident facts explicitly say `ASSOCIATION_UNKNOWN`; its contract says `TIME_WINDOW_ONLY`. No exact recovery is fabricated from compact stdout, time proximity or a later discovery cycle.
- Existing settlement incidents are not deleted, rewritten or automatically recovered because their contract is now `NONE`. The two real IDs appear only in this handoff/evidence, not in monitor logic.

## Validation

**86 ADMIN tests passed: 72 previous ADMIN tests plus 14 focused output/upgrade regressions.** The final complete ADMIN run used a `socket.socket.connect` guard that rejects real networking. Transports are fake. No API-Football or Telegram calls occurred. No historical/model suite was run.

Coverage includes completion/grace/open, exact late output/recovery, outbox superseding, enabled fake sender sending nothing stale, another invocation remaining separate, `NONE`, genuine service failures, replay idempotence, persisted state across restart, historical lookup behind the cursor, cursor-loss proof retention, discovery uncertainty, final-document shape validation, unchanged producer fixtures, and no producer DB sidecars. Upgrade tests exercise real atomic directory exchange in temporary directories, rollback, failure after exchange, preserved database/configuration/PREMATCH bytes, package tampering, enabled-sender rejection and loaded-drift rejection.

Reproduce the focused and previous ADMIN tests:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/admin_alerts -p 'test_*.py' -q
```

`git diff --check` passed. Changed application modules are confined to `app/admin_alerts`; all other changes are ADMIN operations scripts, ADMIN tests and documentation.

## One bounded real-host rehearsal

At **2026-09-27 07:20:40 UTC**, one scan ran under a 45-second outer timeout with isolated state at `/home/arvis/goalvision-operations/prematch-admin-alerts-v1-1-rehearsal`. The scan took **0.0372 seconds**, read 2,853 compact stdout bytes and consumed journal evidence scoped to the two requested historical invocations. Sender was explicitly disabled, `no_send=True`, and both socket connection and Telegram construction were blocked. **Network attempts: 0; football API calls: 0; Telegram sends: 0.**

Because the installed ADMIN database was unreadable, the isolated incident/outbox state was **reconstructed from the user's supplied observations**, using normal Store ingestion. It was not a copy of the live database. This reproduced the two supplied incident IDs without hard-coding them in monitor logic. Both remained OPEN/PENDING/attempts=0. The rehearsal cannot verify live cursor preservation or live incident transitions.

Health and weekly evidence were readable; the bounded ledger review reported `UNRESOLVED_SCAN_IN_PROGRESS`. The isolated report was `DEGRADED`; this does not contradict the user's live v1 `AVAILABLE` observation. No claim is made that the isolated state is equivalent to installed history.

**1,586 protected PREMATCH file hashes were identical before/after**, covering the original 17 protected configuration/unit/manifest files and Python files in both configured releases. Installed ADMIN package file hashes were also unchanged. Producer databases used the existing read-only/query-only adapters. Volatile producer database/log contents are not claimed to be frozen while PREMATCH continues to run.

The local full rehearsal evidence and its checksum are referenced by [the committed evidence summary](PREMATCH_ADMIN_ALERTS_V1_1_EVIDENCE.json). The original local report had an overbroad statement about WAL refusal; the summary explicitly corrects it because no such refusal was observed. It retains the original report hash.

After this single host scan, a healthy event for restored journal routing and upgrade durability checks were added and verified offline. No second host monitor scan was run. The final software has not received a complete privileged-state rehearsal.

## ADMIN-only upgrade package — prepared, not deployed

Reviewed directory: `/home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-1-review`

Archive: `/home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-1-review.tar.gz`

Archive SHA256: `710522294fd86d5513206c9dcfbe03a307a8d1aaa4adcc20d096508b019d8fed`

`SHA256SUMS` SHA256: `3d29fde0539516a480d1afbb417c3e79f8952e3222eae85007a2c3845b960ffb`

[Payload checksums](PREMATCH_ADMIN_ALERTS_V1_1_PACKAGE_SHA256SUMS.txt). The unsuffixed and `-final` intermediate v1.1 directories are superseded; use only `-review` above.

The package's payload hashes, all installed v1 manifest hashes, protected configuration hashes, ADMIN unit hashes and loaded service/timer drift checks passed. The complete read-only `check` command returned **BLOCKED** because the current account cannot read the live configuration and prove its sender is disabled. No upgrade or rollback command was executed against installed files.

### Upgrade guarantees and limitations

- Only `goalvision-admin-alerts.timer` and `goalvision-admin-alerts.service` are stopped. PREMATCH units are never controlled. ADMIN's prior timer activity is recorded and restored.
- Sender must be explicitly `false` in the existing live configuration before upgrade/rollback and immediately around replacement. The configuration is never replaced; no token file is read or copied.
- `/var/lib/goalvision-admin-alerts/admin.sqlite` is never opened by the upgrader, replaced, restored, migrated or cleared. Incident/outbox history and cursors remain in place. Only ADMIN lock files are opened there.
- Installed v1 hashes and immutable PREMATCH/ADMIN unit baselines are verified before staging. Target and backup manifests are rechecked under the ADMIN scan lock immediately before exchange.
- The complete new ADMIN directory is staged and fsynced. Linux `renameat2(RENAME_EXCHANGE)` atomically exchanges it with `/opt/goalvision-admin-alerts`. The old tree remains at `/opt/goalvision-admin-alerts-v1-rollback`; transaction metadata remains in `/opt/goalvision-admin-alerts-v1-1-transaction.json`.
- A failure after exchange attempts to restore the old tree and leaves ADMIN stopped. The rollback command verifies both trees and the unchanged disabled configuration before restoring the original timer state. Interrupted staging before a transaction is saved leaves the installed tree untouched and requires inspection of the stage before another upgrade attempt. State is never wiped to retry.
- Unit files are unchanged. There is **no daemon-reload** in either operation. Both operations review loaded service/timer drift and refuse unexpected ADMIN drop-ins. Any future unit change/reload requires a new drift review outside this package.
- Rollback exchanges ADMIN code only and retains all current database history, including legitimate recoveries. V1's old output assumptions return on rollback; do not interpret its later absence alerts as new producer failures.

### Exact one-line operator commands

These are handoff commands for a later authorized operator session. They were **not executed for upgrade/rollback**. Complete the missing read-only evidence review first; do not enable the sender. Each command pins the manifest hash, validates payload files, then invokes the action. `check` performs no file replacement or unit control.

Check:

```sh
cd /home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-1-review && printf '%s  SHA256SUMS\n' '3d29fde0539516a480d1afbb417c3e79f8952e3222eae85007a2c3845b960ffb' | sha256sum -c - && sha256sum --quiet -c SHA256SUMS && sudo /usr/bin/python3 -I ./upgrade_v1_1.py check
```

Upgrade:

```sh
cd /home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-1-review && printf '%s  SHA256SUMS\n' '3d29fde0539516a480d1afbb417c3e79f8952e3222eae85007a2c3845b960ffb' | sha256sum -c - && sha256sum --quiet -c SHA256SUMS && sudo /usr/bin/python3 -I ./upgrade_v1_1.py upgrade
```

Rollback:

```sh
cd /home/arvis/goalvision-operations/prematch-admin-alerts-upgrade-v1-1-review && printf '%s  SHA256SUMS\n' '3d29fde0539516a480d1afbb417c3e79f8952e3222eae85007a2c3845b960ffb' | sha256sum -c - && sha256sum --quiet -c SHA256SUMS && sudo /usr/bin/python3 -I ./upgrade_v1_1.py rollback
```

## What blocks READY

An existing authorized read-only access method is needed for the installed ADMIN configuration/database and exact historical manager evidence. No password or token should be supplied in chat. The missing evidence is: live `sender.enabled=false`, actual incident/outbox/cursor snapshots, and historical Result/status/timestamps if retained. Retention or missing manager records must be reported as unknown if they cannot be proven. The prepared package already refuses upgrade without the disabled-sender check.

The user reported that the installed sender is disabled. This task did not write its configuration or operate its units. Independent proof is available for the isolated disabled sender and zero attempted sends; independent verification of the live setting is still missing. PREMATCH, Lab, Official and LIVE application/operational configuration were not changed.
