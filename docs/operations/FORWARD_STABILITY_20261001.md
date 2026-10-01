# PREMATCH observer / deployed combo verification — 2026-10-01

Status: PASS (isolated lock regression); NEEDS_MORE_EVIDENCE (deployed fix).
Base: c490866. No deployment, provider calls, Telegram sends or champion edits.

ReadOnlyLedger previously kept BEGIN open until the whole observer completed.
In rollback-journal mode its first read prevented ledger writers from committing.
Use SQLite online backup into a private in-memory consistent snapshot, with a
5-second acquisition deadline and 256 MiB size limit. Close the source before
observer processing. The snapshot remains query-only and verifies fingerprints.
No source journal mode or schema changes.

Changed: app/adaptive_lab/observations.py;
tests/adaptive_lab/test_source_snapshot.py.
Validation: 3 tests pass: writer commits while snapshot remains stable,
source-size failure releases resources, corrupted fingerprints fail closed.

The first deployed accuracy COMBO cycle finished successfully at
2026-10-01T13:05:11.466745Z. singles_sent=0, combos_sent=0,
COMBO_NO_CURRENT_CANDIDATES, eligible_fixture_count=0, prepared_count=0.
This is not evidence of a complete delivery/settlement lifecycle.

Its rehearsal started 13:00:02Z: 32 odds page calls, 506 fixtures with complete
coverage, 1159 incomplete, 290 stale, 216 without current odds; zero candidates.
Do not fabricate publication using expired prior singles.
Operator deployment and subsequent natural-cycle evidence remain separate.

## Later live CPU incident (unresolved)

The 14:00 UTC discovery process (PID 1562506) was still running at 14:17 UTC,
after its last provider response at 14:04:53 UTC, with 87.3% lifetime CPU.
This is an observed CPU interval, not proof of a SQLite lock.

A no-send replay of the exact 2,106 current candidates against an empty in-memory
ledger and no optional context observer took 3.869 profiled seconds, producing
118 eligible fixtures and three accuracy triples. It does not reproduce the
live ledger, context or adaptive state; it cannot establish the live root cause.

Reading the live Python stack with py-spy was denied by the OS ptrace policy.
No elevated retry, process signal, restart or production edit was attempted.
New append-only phase start/end markers identify ADAPTIVE_SHADOW and
PUBLICATION_PREPARATION in the next approved release. Failure markers retain
status only, not exception text. Runtime root cause remains NEEDS_MORE_EVIDENCE.

This incident needs an operator-authorized live stack capture with the required
OS privilege before declaring end-to-end runtime stability PASS. It does not
authorize deployment or relaxing freshness/publication gates.
