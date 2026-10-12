# Quota batch reader — 2026-10-12

The 2026-10-11 journal contains 7 PREMATCH discovery and 31 LIVE invocations with QUOTA_DB_CONTENTION_EXHAUSTED. These are real reservation failures, distinct from ADMIN's observer-format false positives. Late LIVE failures are at RESERVE_COMMIT on attempt 1 after approximately 0.6–1.6 seconds; the unchanged retry window is 0.5 seconds.

On the retained 20:42 Riga snapshot with 5,160 same-day claims, existing quota_since took 0.699543 seconds. One SELECT of encoded documents/fingerprints followed by verification after cursor exhaustion took 0.042594 seconds (SQL fetch: 0.007896 seconds), with exactly equal output. The N+1 reader consumes the retry budget before contention recovery. This measurement identifies a latency defect, not every historical lock owner; permanent external locks still fail closed.

The fix changes only quota_since in app/adaptive_lab/repository.py: one ordered query replaces per-ID lookups; all document fingerprints remain verified. The cursor closes before hashing. Explicit caller transactions remain owned by the caller. Existing indexes, table contents, immutable triggers, optimistic revision checks, quotas, retry window, reservation policy, final review, provider transport and model calculations are unchanged.

Verification: 99 focused/adjacent tests passed, including retained reader locks, real SQLite contention, no HTTP on exhausted reservation, async cancellation, midnight/day/minute accounting, final-review reserve, settlement preflight, dataset integrity and new single-query/ordering/corruption/concurrent-commit checks. Real transport denied. Installation and natural-cycle confirmation remain operator tasks; do not claim all contention eliminated before deployed observation.
