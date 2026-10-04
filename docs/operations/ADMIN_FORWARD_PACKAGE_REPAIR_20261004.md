# 2026-10-04 ADMIN investigation and forward package repair

## Confirmed failure

The deployed 1183e35 forward shadow service failed at import on every recorded scheduled start. The initial journal window shows 23 failures from 2026-10-03 21:12:34 through 2026-10-04 08:12:34 Riga. No forward records/latest.json were created. The package omitted app/lab_v2_shadow/reviewed_competitions.json, required through COMBO publication-policy imports. The repository checkout has the file; tests in that checkout and matching hashes against an incomplete manifest did not establish packaged runtime readiness. The earlier deployed readback was therefore insufficient as a readiness check.

The repair includes that exact committed resource in the manifest, creates a new immutable forward release and checks imports directly from the assembled package using isolated Python, no source-checkout fallback, no worker main, no source DB access and blocked network connections. Existing 842 application/plan files are unchanged; this is packaging-only. No forecasts are backfilled, no quality/selection/champion change.

## ADMIN attribution remains open

The current ADMIN monitor allowlist contains PREMATCH discovery, settlement, observer, daily learning and weekly statistics. It does not contain the new forward service. Therefore the confirmed forward failure cannot be assumed to explain the user's ADMIN messages. The private ADMIN DB/report require sudo, which is unavailable unattended. Prepared a bounded, sanitized query-only export for the operator; it makes no monitor scan, acknowledgements, incident edits or sends. Latest observer journal output is valid and recognized by the installed monitor parser. The full DB observer document is larger than the journal output; a suspected journal-size cause was disproved and no monitor code was changed.

PREMATCH service last exits were successful; no unresolved ledger claims without receipts were found. Late discovery health records report reduced allocation to preserve API quota. Old V1 research remains active and has existing resolved evidence; its data is preserved. ADMIN Codex remains disabled. This does not prove that every historic ADMIN alert was false or recovered.

## Verification and operator steps

109 offline tests pass, including reproduction of the missing-resource import, fixed isolated imports, tampered-resource rejection, reviewed old/new unit acceptance, unrelated-route preservation and sanitized ADMIN export immutability/secret filtering. No application algorithm changed.

Repair only the forward shadow release:

```bash
sudo python3 ~/goalvision-operations/dixon-coles-forward-r2.py --apply
```

The updater pauses/drains only goalvision-dixon-coles-forward.timer/service, retains its state, repoints its exact unit to the repaired immutable release and resumes natural scheduling. No manual cycle, provider call or Telegram send. The original broken release is retained for evidence; rollback is pause-only with the same command plus --rollback.

Export the actual recent ADMIN incidents:

```bash
bash ~/goalvision-operations/admin-check-20261004.sh
```

It prompts for sudo if needed and saves a user-readable sanitized report. Send the printed ADMIN_DIAGNOSTIC_SAVED line for follow-up. Current warning diagnosis remains pending that report; do not silence or invalidate alerts without evidence.
