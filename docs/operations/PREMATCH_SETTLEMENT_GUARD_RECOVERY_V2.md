# Settlement guard recovery v2 — 2026-09-29

Prepared from exact commit `9ff50c2380280c8343833bd08658600e64937d83`.
Preparation only: no production inspection, preflight, recovery, control, API,
Telegram or business database access; no push.

## Root cause and exact change

The operator reported `UNIT_PROPERTY_DRIFT_ExecCondition`. Production
`systemctl show` omitted all five empty `ExecCondition`, `ExecStartPre`,
`ExecStartPost`, `ExecStop`, and `ExecStopPost` properties. Unit/drop-in contents
otherwise matched the predecessor. These facts were supplied by the operator;
this task did not inspect production.

Commit `9ff50c2` required every stable property to be present, inadvertently
removing the predecessor's empty-string fallback. The sole executable-code
change restricts presence enforcement to the existing dependency allowlist:

```python
require((key not in DEPENDENCY_KEYS or key in props) and
        property_equal(key, props.get(key, ''), value), 'UNIT_PROPERTY_DRIFT_'+key)
```

`After`, `Before`, `Requires`, `Wants`, `OnFailure`, and `OnSuccess` still require
presence and exact token-set equality. Reordering, whitespace and identical
duplicates pass; missing, added, changed and substring tokens fail. Missing
properties fail even when the dependency set is pinned empty.

For every other stable property, `props.get(key, '') == expected` is exact.
An omitted property passes only when expected is empty. Present nonempty drift,
including whitespace, fails. Absent or empty actual values fail when expected is
nonempty. No new normalization was added.

## Preserved recovery contract

All [recovery-v1 invariants](PREMATCH_SETTLEMENT_GUARD_RECOVERY.md#recovery-invariants)
remain in place. In particular:

- Only predecessor manifest `c50abe7fc9f7f44a3c05d12fbc81fb41cf53be847d17a09b5f316f0ac85bcfb5`
  in phase `installing`, exact original argv, and no existing completion/recovery fields.
- Exact predecessor runtime/drop-in hashes and loaded wrapper ExecStart;
  `NeedDaemonReload=no`; settlement `inactive/dead`; all five timers `active/waiting`.
- Complete unit/drop-in, environment, calendar, ownership and security pins,
  ADMIN sender disabled, and exact installed stagger-v4 receipt.
- Read-only preflight with no lock creation; finalization reruns full preflight
  under the existing exclusive lock and atomically replaces only the receipt.
- No recovery daemon-reload, worker/timer control, runtime/drop-in rewrite,
  API, Telegram or business database access.
- Exact original receipt text/hash, manifest and argv provenance; the schema
  remains `settlement-guard-installing-recovery-v1`. The package name changes,
  while the receipt format stays unchanged.
- Rollback preserves provenance and restores the exact original application argv,
  including its existing retry behavior after reload failure.

Baseline, runtime, evidence helpers, schedule proof and vendor files are byte-identical
to `9ff50c2`. All executable recovery/rollback code outside the expression above is
unchanged. Forward production validation remains pending.

## Offline validation

| Suite | Result |
| --- | --- |
| Recovery | 33 passed |
| Settlement runtime guard | 38 passed |
| Timer-stagger regressions | 61 passed |
| Total | **132 passed** |

```bash
python3 -B -m unittest discover -s tests/operations -p test_settlement_guard_recovery.py
python3 -B -m unittest discover -s tests/operations -p test_settlement_runtime_guard.py
python3 -B -m unittest discover -s tests/operations -p test_prematch_timer_stagger.py
python3 -B -m unittest discover -s tests/operations -p test_settlement_guard_recovery.py -k production_show_fixture
```

The last command separately reruns one of the 33 recovery tests. Its synthetic
`systemctl show` stdout omits all five empty Exec properties entirely and exercises
the real `Host.show` parser. It reproduced `UNIT_PROPERTY_DRIFT_ExecCondition` before
the fix and passes afterward. Preflight creates no lock or writes; fixture
finalization changes only the temporary transaction receipt. Subprocesses are
stubbed to allow only `systemctl show`; sockets and SQLite access are blocked.

New regressions cover each omitted empty Exec property, each unexpected nonempty
Exec property, absent/empty semantics across all other stable pins, and missing
dependencies pinned both empty and nonempty. All existing dependency permutation,
missing/added/changed/substring and recovery-invariant tests pass unchanged.
`evidence/recovery-validation.json` records results and source hashes.

## New package and trusted hashes

Package: `/home/arvis/goalvision-operations/prematch-settlement-guard-recovery-v2-20260929`

Archive: `/home/arvis/goalvision-operations/prematch-settlement-guard-recovery-v2-20260929.tar.gz`

Archive SHA256: `db5d6aedc9b37b047032909aa08d8bababb57cb5789b0994e41905854eea4dba`

SHA256SUMS SHA256: `b32966e45f178e0f74ff005b25adbe684933bf372b62c4da16cd4b22a32c7cc7`

The package contains 13 checksummed files plus SHA256SUMS. The previous recovery-v1
package, archive and checksum sidecar are preserved. Keep recovery-v2 for subsequent
status, evidence and rollback after finalization with its manifest.

## Exact operator commands — prepared, not executed on production

Verify the archive before extraction, then verify the extracted package. Use the
new directory; never extract over a previous package. Do not use `install` for
this interrupted transaction.

```bash
cd /home/arvis/goalvision-operations &&
printf '%s\n' 'db5d6aedc9b37b047032909aa08d8bababb57cb5789b0994e41905854eea4dba  prematch-settlement-guard-recovery-v2-20260929.tar.gz' | /usr/bin/sha256sum --check --strict -

cd /home/arvis/goalvision-operations/prematch-settlement-guard-recovery-v2-20260929 &&
printf '%s\n' 'b32966e45f178e0f74ff005b25adbe684933bf372b62c4da16cd4b22a32c7cc7  SHA256SUMS' | /usr/bin/sha256sum --check --strict - &&
/usr/bin/sha256sum --check --strict SHA256SUMS
```

Read-only recovery preflight:

```bash
sudo /usr/bin/python3 -I -B /home/arvis/goalvision-operations/prematch-settlement-guard-recovery-v2-20260929/control.py recovery-preflight --manifest-sha256 b32966e45f178e0f74ff005b25adbe684933bf372b62c4da16cd4b22a32c7cc7
```

Expected: `verdict=PASS`, `phase=installing`, predecessor and new recovery manifests.
Investigate any refusal; do not bypass pins or edit receipts.

After reviewing the verified package and a passing preflight, explicit finalization:

```bash
sudo /usr/bin/python3 -I -B /home/arvis/goalvision-operations/prematch-settlement-guard-recovery-v2-20260929/control.py recover-installing --manifest-sha256 b32966e45f178e0f74ff005b25adbe684933bf372b62c4da16cd4b22a32c7cc7
```

Expected: `phase=installed`, original manifest/argv retained and explicit recovery
provenance. Full preflight runs again under the lock.

Post-recovery status:

```bash
sudo /usr/bin/python3 -I -B /home/arvis/goalvision-operations/prematch-settlement-guard-recovery-v2-20260929/control.py status --manifest-sha256 b32966e45f178e0f74ff005b25adbe684933bf372b62c4da16cd4b22a32c7cc7
```

Expected: `pins=PASS`, `phase=installed`, original manifest and recovery provenance.
Preparation stops here; none of these production actions was executed.
