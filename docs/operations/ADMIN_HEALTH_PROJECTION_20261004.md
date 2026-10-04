# ADMIN bounded health projection — 2026-10-04

## Why

The operator's recent incident export accounts for 36 MONITORING_COVERAGE_DEGRADED messages on the health source. The installed adapter reproduces 18 oversized discovery records; these align with failure/recovery pairs. Removing PERFORMANCE alone still leaves large selection review/blocker diagnostics in publication. The separate 12 overnight settlement quota failures are a different, diagnosed issue and are not changed here. The previous stdout-rotation repair is retained.

## Change and evidence

For oversized valid JSON only, remove the existing root PERFORMANCE plus exactly four reviewed publication diagnostics: publication_blockers, publication_reviews, single_publication_blockers and single_publication_reviews. None is consumed by completed_health/compact. Preserve every delivery row, failure/code/status field, publication counter and unknown field. Raw producer records are untouched. Unknown/required oversize, malformed documents, page backlog and unavailable sources still fail closed. Raw 4 MiB, projected 128 KiB, 128-row and SQL deadline bounds are unchanged.

Offline tests: 351 passed and 79 subtests passed. Coverage includes full-report event equivalence across healthy, failure, uncertain/confirmed delivery, pre-transport rejection, malformed/overflow delivery lists, namespace isolation and unchanged producer bytes. Package guards reject modified PREMATCH/research routes, protected timers, enabled Codex, missing import proof and foreign monitor routes. Existing apply/replay/rollback/failure-restoration tests pass with the new monitor-only wrapper.

Read-only source capture and disposable replay cover 19 discovery plus 19 observer reports from October 3. All 228 events exactly equal the full-document rule output. Oversized discovery errors decrease from 18 to zero; the largest source document is 849,109 bytes and the largest projected discovery report is 10,013 bytes. Both captured source content and disposable producer bytes remain unchanged. No Store ingest, real monitor scan, provider request or Telegram send occurs. Reproduction script: operations/admin-autorepair/replay_health_projection.py, taking the reviewed source/assembled runtime root as its sole argument. Evidence: docs/evidence/admin_health_projection_20261004/verification.json.

## Installation boundary

Only goalvision-admin-alerts service routing and its timer are controlled. Stop its timer, drain the existing oneshot, stage an immutable release, switch the exact override and restore prior timer state. Do not manually start a monitor service. The wrapper requires ADMIN Codex disabled in configuration, marker, timer and service state. PREMATCH, weekly, worker and both research service routes/timer states are guarded against drift. Config, source databases, incidents, receipts and history are not edited. Rollback restores the previous monitor route and preserves history. Root-only guards are deferred to operator apply.

The package includes a complete assembled runtime import proof without source fallback or network capability. All source and helper files must match a Git commit before packaging; the operator wrapper pins metadata and updater, which verify helper and overlay/base hashes.

```bash
sudo python3 ~/goalvision-operations/admin-health-projection.py --apply
```

Rollback if required:

```bash
sudo python3 ~/goalvision-operations/admin-health-projection.py --apply --rollback
```

Deployment remains operator-only. After apply, review the installed hashes/routes and the next natural monitor health polling cycle; no test message or forced cycle.

## COMBO question

The new constrained Dixon–Coles and conservative COMBO ranking exist only in the separately deployed forward shadow comparison. Its first successful natural invocation completed at 09:12 Riga on October 4. Published COMBO selection has not been switched to this model, and improved real predictive performance has not been demonstrated yet. Retain SINGLE >=1.50, COMBO legs >=1.30, no extra total-odds floor, today-only, independent bot/statistics, replies, early loss/remaining-leg tracking, disabled LIVE/ADMIN Codex and unchanged champion.

## Prepared package readback

Source commit 99e40ac01110b6dbc54036f46696df4e5228c738. Package /home/arvis/goalvision-operations/admin-health-projection-99e40ac-20261004. All 29 checksums pass. The complete assembled runtime imports in isolated Python with six app modules and no source fallback; the real-report replay under /usr/bin/python3 exactly matches the tested source replay. Read-only wrapper preflight passes. The intended target is absent and the installed monitor still uses admin-rotation-alerts-6a37787-20261002. Protected routes/timers/champion match preparation; ADMIN Codex remains disabled. Root-only configuration/marker guards and first natural post-install health scan remain pending operator apply. No push or deployment. See package_readback.json next to verification.json.
