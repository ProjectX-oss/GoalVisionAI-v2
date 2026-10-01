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
