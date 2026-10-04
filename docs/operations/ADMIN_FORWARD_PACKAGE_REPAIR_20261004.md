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

## Prepared artifact readback

Repair source: ebd09247ad34a578b330b79a02a17e87fb2b8628. Package: /home/arvis/goalvision-operations/dixon-coles-forward-ebd0924-20261004. All 845 checksums match (843 application/resource files); isolated package smoke imports 513 app modules, preserves the declared forward plan and never invokes the worker. Read-only preflight passes; the privileged ADMIN configuration guard remains deferred to operator apply.

Diagnostic builder source: 18cf39cccc5d3e31bfdd400f03fd2e12dfcf7599. Package: /home/arvis/goalvision-operations/admin-diagnostic-18cf39c-20261004. The shell entry point checks the exact diagnostic source hash inside isolated Python before execution. Shell syntax, Git/source equality, isolated help and deliberate pin rejection pass without reading the private DB.

At 08:57 Riga the old forward service is still failed (last exit 08:42:35); its timer remains scheduled. The repaired release is not installed. Original research retains all 62 captured records, forward state remains empty, and protected champion/training/LIVE counts match before inspection. ADMIN Codex timer is inactive/disabled; the monitor last exit is successful. Raw private ADMIN incidents and first repaired natural cycle remain pending. Evidence: docs/evidence/forward_package_repair_20261004/package_readback.json. No push or deployment.

## Operator deployment and actual ADMIN diagnosis (09:14 Riga)

The operator exported recent ADMIN incidents and applied the pinned repair. Independent readback matches all 843 installed application/resource files and both exact systemd units. The first natural forward invocation aab3d483627946e4810dc123d2d8bc5e ran at 09:12 Riga, completed at 09:12:41 and exited successfully at 09:12:42. It created 21 immutable research records, including 5 forecast families, with 7 unavailable model outputs explicitly marked TEAM_CAPACITY. COMBO has only one eligible fixture and produces no combination. Verdict remains NEEDS_MORE_EVIDENCE. No provider request, Telegram send, model promotion or published-selection change. All 62 pre-inspection original V1 records remain; V1 now has 80 records from natural scheduling.

The sanitized export accounts for 50 receipt-persisted ADMIN deliveries over the preceding 24 hours:

- 36 notifications on the health monitoring-coverage incident, last recovered at 18:10 Riga on October 3. Direct read-only replay of the installed health adapter returns exactly 18 OVERSIZED_RECORD events for the same window. These are discovery cycle_health records, not observer journal output: removing root PERFORMANCE still leaves 155,242 to 599,574 bytes in these 18 records, mainly publication details. This is consistent with 18 failure/recovery pairs. The export keeps latest incident evidence, not the complete occurrence history; no historical per-occurrence reason was invented. Other coverage errors were not returned by the replay.
- 12 separate SERVICE_FAILURE notifications for settlement invocations from 01:05 through 02:55 Riga on October 4. Every matching ledger run contains FootballQuotaError at SETTLEMENT with zero API calls and no Telegram send. October 3 UTC has 7,414 local claims out of 7,500, leaving 86. The initial STATUS call requires a 100-call reserve, while SETTLEMENT can use that reserve; consequently a new settlement cycle cannot reach its own reserved calls. An isolated disposable replay reproduces PROTECTED_QUOTA_RESERVE for STATUS at 86 headroom and permits SETTLEMENT, while zero provider allowance remains blocked. Successful settlement resumed naturally at 03:05:56 Riga after the UTC reset; 37 subsequent successful runs were observed through 09:06. Historic failed invocations remain OPEN in ADMIN history; a newer successful invocation is not retroactively proof that those invocations succeeded.
- Two notifications for one DELIVERY_UNCERTAIN incident, now RECOVERED. Current bounded ledger inspection finds no claim without its corresponding receipt. This does not claim that no temporary uncertainty occurred.

The acknowledged stdout-rotation incident sent zero messages in this window. Its prior repair is not repeated. ADMIN monitor currently completes successfully and ADMIN Codex remains inactive/disabled. The larger list of old OPEN incidents is retained history, not 177 newly sent alerts.

### Next bounded repair scope

1. ADMIN monitor: project only the health and publication fields actually consumed by completed_health/compact before applying the size bound, retaining failure codes, all delivery evidence and explicit malformed/overflow diagnostics. Preserve raw producer records, occurrence history, sent receipts and the existing worker/weekly/PREMATCH routes. Prove event equivalence against full valid reports and fail-closed behavior for malformed/oversized required evidence.
2. Settlement: allow its initial status request to use settlement quota authority, retaining provider/day/minute limits and discovery protections. Distinguish verified quota deferral from unexpected service failure so exhausted budget does not produce one generic crash alert per timer tick. Preserve honest pending settlement tracking, early COMBO loss, result replies, destination/statistics periods, today-only selection and odds floors. No provider calls or manual production cycle during tests; fake transports and disposable quota boundaries only.

These two repairs are diagnosed follow-up work, not implemented or deployed by this verification. Audit evidence: docs/evidence/forward_package_repair_20261004/admin_diagnosis_and_deployed_readback.json. No application changes or automatic deployment occurred in this follow-up.
