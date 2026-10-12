# DC forward verification recovery — 2026-10-12

Status: source regression PASS; operator package built and read-only preflight PASS (BASE). Production deployment NONE.

Operator package details, full regression matrix and command: `GOALVISION_LEARNING_DIAGNOSTICS_20261012.md`, sections 14–17. Exact installed application plus the one-file overlay passed 97 offline tests; installer guards passed 16 tests.

The separate forward service still uses `/opt/goalvision-dixon-coles-forward-ebd0924-20261004/application`, CPUQuota=25%, TimeoutStartSec=50. The 08:43 Riga invocation timed out. Its next 09:12:30 invocation completed at 09:13:17, using about 11.98 CPU seconds. A successful retry does not remove the narrow wall-clock margin.

Offline profiling of the 09:25:49 Riga snapshot identified duplicate full numerical artifact verification: the forward evaluate pre-loop verifies each artifact, then forecast reproduction verifies it again in predict. With 537 forecast families and 537 referenced artifacts, numerical certificates were recomputed 1,074 times.

The small service-only change validates reproduced forecasts inside the existing predict path once, explicitly forwarding consumed/reserved training-fixture exclusions. Future and reserved forecasts, which the scorer skips, retain their original explicit full validation. Model equations, prices, scores, timestamps, cohort, calendar, confidence criteria, quotas, resource limits and timer schedule are unchanged. Invalid hashes and resealed invalid numerical parameters still fail for resolved, pending, future and reserved records.

Same complete report before/after: exact equality, fingerprint `631c33656ec9efe45b3885f9d12370e59e8d4234d2a490c08aea34ccb219ccb1`.
Unprofiled evaluation: 8.6173 seconds before, 5.8798 seconds after, about 31.8% less elapsed time in this detached run. This is not a guarantee against future growth, external contention or systemd timeouts.

Focused/adjacent numerical, forward, original research and worker tests: 173 passed, zero failed; 15 new lifecycle/corruption/exclusion/equality cases included. All tests deny outbound sockets. Additional comparison/calendar/LIVE/COMBO regressions are recorded in the final diagnostic report.

Changed application file: `app/dixon_coles_forward/service.py` only. Its pre-patch hash exactly matched the installed file (`30c079aebe047c37f12cdf6090ecb802d983de34842138949959bcc9ace62ce2`). Tests: `tests/test_dixon_coles_forward_verification.py`.

No source database mutation, fit, publication, provider request, Telegram send, model activation, production install or timer change was performed. The operator package must copy the exact installed application and overlay this one file, preserving the separate forward database and all other service routes.
