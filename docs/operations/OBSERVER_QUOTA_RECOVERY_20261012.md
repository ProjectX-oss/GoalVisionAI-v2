# Observer and quota recovery — 2026-10-12

Status: PASS_READY_FOR_OPERATOR after source regressions; exact assembled-package verification is recorded below after build. No agent deployment.

## Confirmed defects

1. ADMIN rejected complete PREMATCH observer output because it required LIVE=DISABLED. The installed producer now correctly reports LIVE=NOT_EVALUATED with LIVE_SCOPE=PREMATCH_OBSERVER. The user's incident 8c440c57f2857c55f96954b8 belongs to invocation a54d7838f7c44048b1ed2ae95e2b8b99, which exited 0 and emitted a complete 11,562-byte result. Since 2026-10-11 05:00 UTC, 22 of 49 observer documents were rejected solely for this field. The fix recognizes the scoped new pair and legacy format; other final-output and exact-invocation safeguards remain.

2. Quota claim reads used N+1 SQL lookups. The retained 20:42 Riga snapshot contained 5,160 same-day claims: old read/verification 0.699543 seconds, one batch read/verification 0.042594 seconds, identical documents/order/fingerprints (SQL fetch 0.007896 seconds). The old path alone can consume the entire 0.5-second contention retry window. Journal evidence includes seven PREMATCH discovery and 31 LIVE invocations with actual contention exhaustion; late LIVE failures occur at RESERVE_COMMIT on attempt one after about 0.6–1.6 seconds. Exact historical lock owners are not established; this optimization does not guarantee elimination of permanent external locks.

The patch is confined to two application files:
- app/admin_alerts/output_contracts.py, ADMIN only.
- app/adaptive_lab/repository.py, PREMATCH and LIVE: quota_since only.

No threshold, quota ceiling, retry window, final-review reserve, model, source probability, champion, calendar, staking or settlement change. Same source fingerprint validation and optimistic revision guard; cursor exhausted before Python decoding. Actual LIVE timer was active/enabled at audit; the installer preserves its state and does not enable it.

## Evidence and tests

- ADMIN focused/adjacent suite: 539 tests, 93 subtests passed, network denied.
- Exact reported journal invocation: offline final-output recognition and recovery proof PASS. No production incident write or monitor scan.
- Quota focused/adjacent suite: 99 passed; corruption, chronology/order, empty/midnight/day/minute accounting, SQLite contention, cancellation, no HTTP before durable reservation, final-review and settlement-reserve regression coverage.
- Installer: 23 passed, including hashes, base/overlay/configuration drift, real-transport exclusion by fake controls, active/inactive timer preservation, busy service drain, idempotence, disabled Codex guard and partial failure without rollback.
- Initial installer regression expected the old automatic restoration behavior. Its expectation was updated to the explicitly required pause-for-operator behavior; final suite passed. This was a test adjustment to the intentional operator recovery contract.
- An earlier alternative ADMIN-only package implementation was discarded before commit/build in favor of the existing combined installer.

The agent cannot read root-private ADMIN incident storage directly. The journal confirms this defect and real quota faults, but does not prove that every private ADMIN incident has been enumerated. Previous notifications and immutable audit data remain untouched.

## Reviewed source commits

- ADMIN: 772b7a3, branch fix/admin-observer-contract-20261012.
- Reader: ba96299, branch fix/quota-batch-reader-20261012.
- Combined operator package: branch fix/observer-quota-recovery-20261012; source and final verification commits recorded after build.

## Exact installed bases

- PREMATCH: /opt/goalvision-prematch-recovery-380bcf7-20261011
- LIVE: /opt/goalvision-live-quota-reader-3d4f5c5-20261010
- ADMIN: /opt/goalvision-admin-alerts-releases/admin-quota-correlation-9e321c3-20261010

Targets:
- /opt/goalvision-prematch-quota-batch-20261012
- /opt/goalvision-live-quota-batch-20261012
- /opt/goalvision-admin-alerts-releases/admin-observer-contract-20261012

The builder demands that each patch parent exactly matches its installed base file. All other application files/assets are copied byte-for-byte. Existing ADMIN quota correlation and the October 11 PREMATCH/COMBO/calendar fixes are retained.

## Operator application

The single pinned entry point will be:

```bash
sudo /usr/bin/python3 -I /home/arvis/goalvision-operations/observer-quota-recovery-20261012.py --apply
```

Default invocation without --apply is read-only. Application acquires existing deployment locks, checks package/base hashes and all GoalVision unit configuration, stages three immutable releases, briefly pauses affected timers, waits up to 180 seconds for active services to finish naturally, switches only their release references and restores the same timer activity. It does not start any worker service or test Telegram/API transport. No schedule/enablement change.

If failure occurs before route writes, timer activity is restored. After any route write, affected timers remain paused for operator review and a journal is written under /var/lib/goalvision-operator-recovery; **no automatic rollback**. Do not blindly restart a partial installation. Successful repeated application is idempotent.

Expected success marker: OBSERVER_QUOTA_RECOVERY_DEPLOYED.

Existing natural ADMIN scans revisit unresolved output incidents (bounded two per scan), allowing exact matching journal proof to recover them while preserving sent messages and other incidents. Recovery is not asserted before installation and natural verification.

## Acceptance boundary

Production deployment by the agent = NONE.
Telegram sends = 0. Additional provider calls = 0.
Official changes = NONE. Model activation = NONE.
PREMATCH champion remains generation-aa7e535b86267741aabc967e8044de2ab94a4334b1520a829414dd55ebc7371a.
Full runtime resolution remains pending operator installation and subsequent natural cycles.

## Final package verification

**PASS_READY_FOR_OPERATOR.**

- Package source commit: 3c83f7e3d76d26622bf2e7a69c974f648da30667.
- ADMIN source: 772b7a310dbdaf6cae86792108c4d6b42930e1af.
- Reader source: ba96299dfa68524d330df7babb3bd4cf96c4e903.
- Package: /home/arvis/goalvision-operations/observer-quota-recovery-20261012.
- Metadata SHA256: aeee9d4a1300247bae57999baeb6477de3807efeca4fd493bac960e9f7d0e9f2.
- Pinned entry SHA256: 2ca8054bc7a4cd13198dc0cea7c912cdd61c8078c0de810cab83d2aac0c41aaf.
- Exact assembled PREMATCH: **34 tests passed**.
- Exact assembled LIVE: **54 tests passed**, including mandatory final refresh, fake-provider HTTP failures, exhaustion and reserve behavior.
- Exact assembled ADMIN: **13 tests passed**, plus explicit new-format/invalid-scope/API-call guard checks.
- Every assembled release imported its own application, with no checkout fallback and zero network attempts.
- Default pinned entry preflight: **PASS, mode=BASE**. Root-only disabled-Codex/config checks remain enforced by --apply. The agent did not invoke sudo or --apply.
- Production readback: champion unchanged, only the existing one bootstrap activation.
- Initial package build attempted a LIVE-only final-review test against the PREMATCH release's older unused LIVE module. The harness now runs that test only on the actual LIVE package; both relevant quota reader suites still run on PREMATCH and LIVE. No unrelated LIVE application files were added to PREMATCH. Corrected complete build passed.

Changed source/test/document paths:
- ADMIN branch: app/admin_alerts/output_contracts.py; tests/admin_alerts/test_quality_compatibility.py; tests/admin_alerts/test_observer_scope.py; docs/operations/ADMIN_OBSERVER_CONTRACT_20261012.md.
- Reader branch: app/adaptive_lab/repository.py; tests/adaptive_lab/test_quota_batch_reader.py; docs/operations/QUOTA_BATCH_READER_20261012.md.
- Package branch: operations/quota-admin-repair/{update.py,build.py,smoke.py,operator_wrapper.py}; tests/test_quota_admin_repair_operations.py; TASKS.md; this report; docs/evidence/observer_quota_recovery_20261012/package.json.

Installation remains required to affect production. Real permanent lock contention can still fail closed; assess future natural cycles before declaring every quota incident resolved.
