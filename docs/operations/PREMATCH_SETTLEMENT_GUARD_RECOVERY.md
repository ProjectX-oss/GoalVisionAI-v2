# Settlement guard interrupted-install recovery — 2026-09-29

Prepared from `ec0fa32789476d5fad497c05cbf93e3c78e09d18`.
**Production commands executed: zero. Package preparation only; no push.**

## Root cause and scope

The operator verified an interrupted receipt with phase `installing` and manifest
`c50abe7fc9f7f44a3c05d12fbc81fb41cf53be847d17a09b5f316f0ac85bcfb5`.
The loaded wrapper, installed runtime/drop-in hashes, inactive/dead settlement,
and `NeedDaemonReload=no` were exact. `After` contained exactly the pinned members
in a different order following daemon-reload. Raw string comparison raised
`UNIT_PROPERTY_DRIFT_After`, preventing normal completion and rollback/status.
These are operator-supplied production facts, not a new host inspection here.

The fix compares exactly these six dependency properties as
`set(actual.split()) == set(expected.split())`:
`After`, `Before`, `Requires`, `Wants`, `OnFailure`, `OnSuccess`.
Only order, whitespace between members, and repeated identical members are ignored.
Tokens remain case-sensitive and exact; no substring, prefix, glob, alias, unit-name,
or path normalization occurs. Missing, additional, or changed members fail.
A missing property fails even for an empty pinned value.

No additional property is normalized. Existing DropInPaths inventory comparison
retains its existing set behavior and exact file hashes. ExecStart, EnvironmentFiles,
Environment hash, calendars, unit/drop-in hashes, sandbox/security properties,
package hashes, timer settings, ADMIN protection and stagger-v4 protection retain
their existing checks. Baseline, runtime, evidence reader and vendor helpers are
byte-identical to the predecessor. All application, publication, model, quota,
Telegram, bankroll and statistics code is unchanged.

## Recovery invariants

`recovery-preflight` is read-only, including no creation of a lock file.
`recover-installing` acquires the existing nonblocking exclusive transaction lock,
reruns the entire preflight, and then atomically replaces only transaction metadata.
It requires:

1. Exactly the predecessor manifest above; phase exactly `installing`; the exact
   original application argv; no previous `installed_at` or recovery fields.
2. An externally pinned new package manifest and exact file inventory/hashes.
   Recovery additionally requires the unchanged predecessor baseline SHA256
   `f78123f84c612e58d3d47cd1897d9afdaa0a058b805d22bc7abc6c223544374e`.
3. Exact installed routing at
   `/etc/systemd/system/goalvision-lab-combo-settle.service.d/99-goalvision-settlement-guard.conf`:
   `c78ae7eb2347d049d2b9c763d4f77316b91a566de1eaa9f642c6754db6e36d51`.
4. Exact installed runtime at `/opt/goalvision-settlement-guard-v1/runtime_guard.py`:
   `4ab82ae534403e2a3d8f7e1b589220b555b8f3cfac63bb7c878337eea53ea5ff`.
5. Exactly one loaded ExecStart with executable `/usr/bin/python3` and argv
   `/usr/bin/python3 -I -S /opt/goalvision-settlement-guard-v1/runtime_guard.py`.
   Extra argv, different executable paths, additional command entries, or ignored
   errors fail. `NeedDaemonReload=no`; settlement exactly `inactive/dead`.
6. Complete existing production inspection with **no pending-install exemptions**:
   timezone/localtime, all ten pinned unit/drop-in files, loaded and unloaded drop-in
   inventory, loaded unit identity/settings, service environment/sandbox and exact
   calendars, environment-file hashes, installed artifact inventory and ownership.
   All five timers must additionally be `active/waiting` during recovery.
7. ADMIN `sender.enabled` exactly false and stagger receipt exactly `installed`
   with manifest `61f3a3263cab3bf25fd064071ae8744190f6effa0f8c984f5d1aae2c3b2ba598`.
8. Root-owned receipt/state and artifacts without group/world write permission;
   no symlink paths. Loaded recovery state is checked again after inspection,
   and receipt text must still match the initial read.

Recovery performs no daemon-reload, start, stop, restart, kill, enable, disable,
rearm, runtime/drop-in rewrite, API call, Telegram send, or business DB access.
Only the existing lock and atomic receipt replacement are written. Reads are
observations; the transaction lock does not prevent naturally scheduled activation.
A refused state check requires another operator preflight when normal idle state
is available; do not change timers or workers to create it.

## Manifest and receipt lineage

The top-level `manifest` remains the **old** digest; `original_argv` is unchanged.
Recovery sets `phase=installed` and records a `recovery` object containing:

- Schema `settlement-guard-installing-recovery-v1`.
- The **new** recovery package manifest and UTC recovery time.
- The complete original receipt text and its SHA256.

`installed_at` is explicitly the recovery time. Evidence defaults to that time
and refuses earlier windows, avoiding claims about unverified pre-recovery cycles.
Normal status exposes the preserved manifest and recovery provenance. Normal
status/evidence/rollback accept the old manifest only with valid provenance bound
to this exact new package. An unrelated digest, absent/tampered provenance, or
changed original argv fails. Other predecessor manifests are never admitted.

Re-running recovery after completion refuses; use status. A recovered transaction
cannot be overwritten by reinstalling it. Future rollback retains recovery
provenance through `rolling_back` and `rolled_back`, including retries after an
interrupted reload. Keep this new package for all subsequent operations. The old
package remains preserved and still contains the ordering bug.

## Review and test evidence

Local code review covered every mutation path, exact dependency allowlist,
predecessor authorization, fail-closed production pins, receipt provenance,
package checks, and rollback continuity. This was a local implementation review,
not an independent operator approval or production validation.

| Suite | Result |
| --- | --- |
| `test_settlement_guard_recovery.py` | 27 passed |
| `test_settlement_runtime_guard.py` | 38 passed |
| `test_prematch_timer_stagger.py` | 61 passed |
| Total | **126 passed** |

Commands from the source checkout:

```bash
python3 -B -m unittest discover -s tests/operations -p test_settlement_guard_recovery.py
python3 -B -m unittest discover -s tests/operations -p test_settlement_runtime_guard.py
python3 -B -m unittest discover -s tests/operations -p test_prematch_timer_stagger.py
```

Recovery regressions test permutations and missing/added/changed/substring members
for all six properties, empty/missing properties, exact unrelated pins, all recovery
refusals, read-only preflight, exclusive-lock contention, atomic failure/retry,
and receipt/state changes during inspection. The real Host adapter rehearsal allows
only `/usr/bin/systemctl show`; socket, DB and other subprocess effects are blocked.
All mutations occur in temporary fixtures.

The CLI lifecycle rehearsal covers preflight → recovery → status → evidence →
rollback → status, retaining the original manifest and argv. The evidence dispatch
uses a stub; the existing 38-test guard suite covers the real evidence summarizer.
Future scheduled production evidence is still pending. Successful rollback and
an injected reload-failure/retry both restore this exact argv:

```text
/home/arvis/GoalVisionAI/.venv/bin/python -P -m app.lab_combo settle --send --adaptive-database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db
```

`evidence/recovery-validation.json` contains results and test/control source hashes.
The earlier `evidence/validation.json` is preserved as historical predecessor evidence.

## Changed files

- `operations/prematch-settlement-guard/control.py`: comparison and recovery lifecycle.
- `tests/operations/test_settlement_guard_recovery.py`: 27 focused offline tests.
- `operations/prematch-settlement-guard/README.md`: recovery contract and usage.
- `operations/prematch-settlement-guard/SHA256SUMS`: new package manifest.
- `operations/prematch-settlement-guard/evidence/recovery-validation.json`: new validation record.
- `docs/operations/PREMATCH_SETTLEMENT_GUARD_RECOVERY.md`: this handoff.
- `docs/operations/PREMATCH_DISCOVERY_PRIORITY_SETTLEMENT_GUARD.md`: incident handoff pointer.
- `TASKS.md`: completion record.

## New package and trusted checksums

Extracted package:
`/home/arvis/goalvision-operations/prematch-settlement-guard-recovery-v1-20260929`

Archive:
`/home/arvis/goalvision-operations/prematch-settlement-guard-recovery-v1-20260929.tar.gz`

Archive SHA256:
`a1092abaa99890f9b728fbaa37bd86ecd80bb89934a49e80bd8a8e972f189007`

SHA256SUMS SHA256 (the new `--manifest-sha256`):
`ea44324c43b81954d33a99a286f4aa2ad8084e8d73f87d2337b44079f36639a6`

The package has 13 checksummed files plus SHA256SUMS. The original standalone v1
package and its manifest have not been changed.

## Exact operator commands — prepared, not executed

Use the new extracted package at the path above on the VPS. If transferring the
archive, verify its hash before extracting it into that new directory. Never
extract it over the predecessor package. The commands below do not run the runtime
wrapper directly. Do not use `install` for this interrupted transaction.

### Archive and extracted-package verification

```bash
cd /home/arvis/goalvision-operations &&
printf '%s\n' 'a1092abaa99890f9b728fbaa37bd86ecd80bb89934a49e80bd8a8e972f189007  prematch-settlement-guard-recovery-v1-20260929.tar.gz' | /usr/bin/sha256sum --check --strict -

cd /home/arvis/goalvision-operations/prematch-settlement-guard-recovery-v1-20260929 &&
printf '%s\n' 'ea44324c43b81954d33a99a286f4aa2ad8084e8d73f87d2337b44079f36639a6  SHA256SUMS' | /usr/bin/sha256sum --check --strict - &&
/usr/bin/sha256sum --check --strict SHA256SUMS
```

### Read-only recovery preflight

```bash
sudo /usr/bin/python3 -I -B /home/arvis/goalvision-operations/prematch-settlement-guard-recovery-v1-20260929/control.py recovery-preflight --manifest-sha256 ea44324c43b81954d33a99a286f4aa2ad8084e8d73f87d2337b44079f36639a6
```

Expected: `verdict=PASS`, `phase=installing`, old predecessor and new recovery
manifest shown. A refusal must be investigated; do not edit receipts or bypass pins.

### Explicit recovery/finalization

Only after reviewing the verified package and passing preflight:

```bash
sudo /usr/bin/python3 -I -B /home/arvis/goalvision-operations/prematch-settlement-guard-recovery-v1-20260929/control.py recover-installing --manifest-sha256 ea44324c43b81954d33a99a286f4aa2ad8084e8d73f87d2337b44079f36639a6
```

Expected: `phase=installed`, original `manifest` retained, explicit `recovery`
provenance present. This reruns preflight under the lock; it does not consume or
trust a stale preflight result.

### Post-recovery status

```bash
sudo /usr/bin/python3 -I -B /home/arvis/goalvision-operations/prematch-settlement-guard-recovery-v1-20260929/control.py status --manifest-sha256 ea44324c43b81954d33a99a286f4aa2ad8084e8d73f87d2337b44079f36639a6
```

Expected: `pins=PASS`, `phase=installed`, original manifest and recovery provenance.

### Later scheduled evidence

After normal scheduling supplies sufficient cycles:

```bash
sudo /usr/bin/python3 -I -B /home/arvis/goalvision-operations/prematch-settlement-guard-recovery-v1-20260929/control.py evidence --manifest-sha256 ea44324c43b81954d33a99a286f4aa2ad8084e8d73f87d2337b44079f36639a6
```

The existing minimum remains 2 discovery, 3 executed settlement, and 2 observer
cycles. Deferrals do not count as executions; early evidence may be incomplete.

### Future rollback, only if separately chosen by the operator

```bash
sudo /usr/bin/python3 -I -B /home/arvis/goalvision-operations/prematch-settlement-guard-recovery-v1-20260929/control.py rollback --manifest-sha256 ea44324c43b81954d33a99a286f4aa2ad8084e8d73f87d2337b44079f36639a6
```

Rollback retains the existing idle/safe-window and exact ownership/pin checks,
removes only owned routing/runtime, daemon-reloads, and verifies the original argv.
It does not control workers or timers. This command is not part of finalization.

Preparation stops here. No production preflight, recovery, status, evidence or
rollback command was executed in this task.
