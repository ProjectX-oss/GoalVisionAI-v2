# ADMIN worker startup compatibility — 2026-10-01

Status: PASS (regression); NEEDS_MORE_EVIDENCE (production incident attribution).
Branch: fix/admin-worker-startup-20261001. Base: 160bb67.
Changed: app/admin_autorepair/worker.py; tests/admin_autorepair/test_worker.py.

The deployed unit has RestrictSUIDSGID=yes. Job creation requested mkdir
mode 02770, which explicitly requests a forbidden special permission bit.
Use 0770 and the managed parent group instead. Keep all systemd restrictions.
Existing job directories still cannot be overwritten or rerun.

Validation: 104 tests passed in tests/admin_autorepair, including a simulated
RestrictSUIDSGID denial. The test follows an isolated fake Codex job through
startup, clone and completion. No production Codex job was started.
Recent readable journal records are IDLE; they do not establish the original
incident's syscall or demonstrate successful production repair.

No deployment or service restart. Operator deployment and an actual job's
lifecycle evidence remain required. Rollback: use the previous pinned release.
