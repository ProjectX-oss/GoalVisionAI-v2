# Compact PREMATCH output upgrade — 2026-09-26

Status: **COMPACT_OUTPUT_UPGRADE_READY_FOR_REVIEW**. Prepared only; no deployment,
manual provider cycle, Telegram call, publication enablement or history audit.

## Reviewed change

Application branch: `codex/prematch-compact-operator-output`.
Application commit: `4fd68bd9a71958152a91a6ca51cbc23ef96da47b`, based on
`a7cb28ba5fcd87ada8ed8f4e78a18e0cec6021f2`.
Application tree: `d4774b75452014d1a79274c60b4327e937159e2f`.

Operations branch: `codex/prematch-compact-output-upgrade`, based on
`730c27737355030240559c2b55127d7d81c8bfa5`. Its only helper change makes
`previous_protected_stdout=true` preserve the installed protected stdout sink when
recognizing the prior release or recovering to it. The old manifest default stays
compatible. Existing lock, drain, gates, rollback journal and timer restoration
behavior remain intact. Operations tests exercise both prior configurations.

The application adds a pure stdout projection for `controlled-cycle` and
`rehearse`: `goalvision-lab-v2-operator-cycle-v1`. Delivery evidence is retained
without a record limit, including acknowledgement without receipt, timeout without
unknown-marker persistence, partial batch success and cycle-persistence failure.
Immutable stores, delivery code, policies, model logic, statistics and settlements
are unchanged. See `app/lab_v2_shadow/README.md` in the application release for the
schema and evidence inspection instructions.

## Validation

- **380 application tests passed**, zero failures/errors/skips: compact output,
  delivery accounting, probability/publication hardening, Lab V2 shadow/global/
  prematch/hardening/throughput, combo/integrity and PREMATCH V2 enablement.
- **90 upgrade/rollout tests passed**, zero failures/errors/skips. The final run
  imported the new application while exercising the updated operations helper.
- Tests used disposable stores and fake transports; a seccomp launcher denied
  network syscalls, including in child processes.
- A synthetic CLI cycle with **2,500 fixtures and 600 candidates** emitted
  **936 UTF-8 bytes including newline**. Its full report was **13,731,974 bytes**.
  Candidate/fixture growth does not grow stdout beyond numeric counter widths.
- Real runner persistence and candidate reconstruction, append-only protection,
  unchanged `summary`, redaction, night pause and terminal-error exit tested.
- Read-only package validation passed against the installed configuration, pinned
  host/interpreter files and both clean releases. All five relevant module imports
  resolve to the proposed release with network denied.
- No historical/model audit was repeated. Historical integrity results in the
  task request are the previously reviewed baseline, not a new measurement.

## Package and installed configuration

Package:
`/home/arvis/goalvision-operations/prematch-compact-output-upgrade-v1-20260926`

Proposed isolated release:
`/home/arvis/GoalVisionAI-prematch-release-compact-output-4fd68bd-20260926`

Current release remains:
`/home/arvis/GoalVisionAI-prematch-release-reviewed-hardening-a7cb28b-20260925`

Manifest SHA-256:
`a17e98a88215342f2f15642b9f414e20da8a13bbe4eb47c7ee03901bf86a21e9`

The package contains the pinned manifest, helper, unchanged installer primitives,
before/proposed drop-ins, configuration diff, normal stdout sample, size result,
JUnit results, import verification and installed-state snapshot. `SHA256SUMS`
checks every package artifact. Release files and package are read-only by file
permissions; this is not a root-only filesystem immutability claim.

The proposed drop-ins change only the four service `EnvironmentFile` paths.
`new_picks=false`, `observe=true`, `labels=true`; all commands, cadence, quota,
settlement reserve and timer configuration remain byte-identical. The existing
protected stdout sink remains `/var/log/goalvision-prematch/discovery-output.log`
(root:arvis 0640, parent 0750); rotation bytes remain identical. No log was read,
truncated, rotated or replaced by this task. Existing environment credentials were
only fingerprint-checked, never printed or changed.

## Prepared command — NOT EXECUTED

```bash
sudo /home/arvis/GoalVisionAI/.venv/bin/python /home/arvis/goalvision-operations/prematch-compact-output-upgrade-v1-20260926/upgrade_prematch_reviewed.py /home/arvis/goalvision-operations/prematch-compact-output-upgrade-v1-20260926/manifest.json upgrade --sha256 a17e98a88215342f2f15642b9f414e20da8a13bbe4eb47c7ee03901bf86a21e9
```

The read-only `check` action was executed successfully. Do not use first-install
`apply`. Installation must be separately authorized; this package never enables
new-pick publication. After an authorized upgrade, inspect the next scheduled
no-send cycle's schema and delivery flags. A scheduled tick on this proposed
release has not occurred.

For a failed upgrade, use this same command with `recover` replacing `upgrade`
after reviewing the failure. Recovery retains the previous no-send release,
observation/label state and protected stdout sink. If automatic recovery cannot
finish, the existing gates and journal stay in place; never delete the journal,
claims or receipts to retry. The previous release's output will again be verbose.
