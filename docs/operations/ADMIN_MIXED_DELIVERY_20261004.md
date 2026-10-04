# ADMIN mixed delivery classification — 2026-10-04

## Confirmed behavior

Persisted PREMATCH publication reports from 19:30 and 20:00 Riga contain three
confirmed SENT/RECEIPT_PERSISTED SINGLE deliveries and one COMBO rejected before
transport. All three send attempts have receipts. The installed monitor nevertheless
emits aggregate DELIVERY_FAILURE because its earlier suppression covers only
all-rejected batches. This is a classification defect, alongside the real COMBO
arithmetic defect repaired separately.

The forwarded incident 4f3832ebaf241e92b8d3ad51 is exactly the mapped identity of
aggregate UNKNOWN delivery failures after the retained bd52a22acbc330714271ae9a
pre-transport tombstone. Root-owned incident storage was not accessible to arvis:
its current count/state/outbox are not claimed as independently inspected.

## Change and proof

Recognize a bounded terminal batch only when every item is either a strict
confirmed receipt or a proven pre-transport rejection, identities are unique,
all explicit counters match confirmed sends, and no failure/uncertainty remains.
Emit healthy evidence only for the aggregate UNKNOWN transport incident. Keep
individual delivery uncertainty, persistence faults and integrity incidents.
Do not delete, invalidate or rewrite historical incident/notification records.
Normal subsequent scans may recover the mapped incident from new healthy
publication evidence; no manual scan/send is performed.

- Monitor suite: 323 passed, 79 subtests passed in 18.97s.
- Operator/helper/retirement regressions: 56 passed in 1.47s.
- Read-only replay of actual 19:30/20:00 reports changes one false aggregate
  failure per report to zero; all three actual sends stay counted.
- Synthetic recovery proves the mapped incident recovers while the old
  invalidation tombstone and evidence remain intact.
- Network connections denied in test and replay processes.

## Operator sequence

Apply the separate COMBO arithmetic repair first:

    python3 ~/goalvision-operations/combo-aggregate.py
    sudo python3 ~/goalvision-operations/combo-aggregate.py --apply

Then install this monitor-only release:

    python3 ~/goalvision-operations/admin-mixed-delivery.py
    sudo python3 ~/goalvision-operations/admin-mixed-delivery.py --apply

The monitor package accepts its exact captured protected routes or the explicitly
pinned cb6b7c6 COMBO repair routes. The latter additionally verifies every .py/.json
application hash and release environment hash. Other route/timer drift is rejected.
The route transaction independently retains protected PREMATCH/research/worker/weekly
configuration and timer state. ADMIN Codex must remain disabled before and after.
No automatic rollback interface is provided.

Evidence: docs/evidence/admin_mixed_delivery_20261004/verification.json.
No agent deployment, provider call, Telegram send, manual cycle/monitor scan,
model change, LIVE activation or Official modification. Natural live recovery
and forward COMBO delivery remain pending operator apply and qualifying evidence.

## Exact prepared package

Source commit: ab327dddd08ef731571a981b4cb77a4db1cc05fe

19 base source files verified; only app/admin_alerts/rules.py changes. Isolated six-module import smoke passed without network or scans. Package checksums and read-only preflight passed. Prepared target: /opt/goalvision-admin-alerts-releases/admin-mixed-delivery-ab327dd-20261004. No deployment performed.

## Operator deployment verified — 2026-10-04 21:09 Riga

The operator installed this pinned monitor release after COMBO aggregate cb6b7c6.
Independent read-only checks pass for the 19-file monitor manifest and the
approved 852-file PREMATCH release/routes. The monitor's natural 21:08:20 Riga
start completed with exit status zero. ADMIN Codex remains inactive/disabled.

Incident recovery is still unconfirmed: arvis cannot read the root-owned incident
store, and the first post-deployment discovery is scheduled for 21:30 Riga.
No manual scan or send was run. Consolidated deployment evidence is on reviewed
branch fix/combo-aggregate-20261004 at
docs/evidence/combo_aggregate_20261004/deployed_readback.json.
