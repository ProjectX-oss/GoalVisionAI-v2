# COMBO aggregate arithmetic repair — 2026-10-04

## Confirmed incident

The operator forwarded DELIVERY_FAILURE incident 4f3832ebaf241e92b8d3ad51.
The 20:00 Riga natural cycle has three confirmed persisted SINGLE receipts.
Its market COMBO was rejected before any claim or Telegram transport. The
20:30 cycle repeated the same kind of COMBO evidence rejection. Private 1.70
selection had no qualifying pick and was not the source of this fault.

Direct read-only reproduction at the frozen creation time raises
COMBO_MARKET_AGGREGATE_MISMATCH. The persisted score ends in 4764; the same
leg scores multiplied in stored publication-key order end in 4765. Difference:
1E-28. Decimal multiplication with fixed precision is order-sensitive.

## Change

Persist the aggregate rank score in the same frozen leg order used by review.
Ranking, chosen fixtures/markets, candidate evidence, exact identity validation,
all odds/probability floors and publication gates are unchanged. Both scored
COMBO lanes share the corrected preparation. No epsilon tolerance, probability
clamp, rewritten old prediction, forced pick or resend is introduced. Existing
invalid immutable prepared records remain rejected; fresh current-quote records
use the fix after operator deployment.

## Verification

- Red regression: 12 failures reproduce the exact arithmetic mismatch across
  both lanes and all six input permutations; one varied-market test passed.
- Focused public/private/COMBO/reply/accounting matrix: 197 passed in 10.92s.
- Operator exact-base/hash/symlink/timer/drain/rollback-rejection checks:
  18 passed in 0.34s.
- Network connects denied in test processes; only fake transports.
- Evidence: docs/evidence/combo_aggregate_20261004/verification.json.

## Operator installation

Prepare the pinned immutable package from the reviewed commit. It replaces only
app/lab_v2_shadow/accuracy_combo.py over the installed private SINGLE release.
All private/public flags, routes, reply settlement, 180-second guard, research,
champion and statistics remain intact. Default entry point is read-only:

    python3 ~/goalvision-operations/combo-aggregate.py
    sudo python3 ~/goalvision-operations/combo-aggregate.py --apply

No automatic rollback is provided. Failed installation restores only its own
in-progress route transaction. Existing pending/confirmed predictions are never
replayed or edited. Run no manual cycle or Telegram test. Validate the next
natural discovery result after explicit operator apply.

## Monitor follow-up

A separate monitor-only correction is required: mixed confirmed deliveries and
proven pre-transport rejections currently fall through to a generic UNKNOWN
delivery failure. Retain genuine transport uncertainty and integrity incidents.
Root-owned incident storage could not be read as arvis; this report does not
claim to have modified or closed the live incident.

Agent production deployment, provider calls, Telegram sends, training, promotion,
rollback, LIVE activation and Official changes: zero.

## Exact prepared package

Source commit: cb6b7c605c70360031b84cc754b4bc9913536f54

852 application files verified; only accuracy_combo.py differs from the installed private release. Isolated 549-module import/resource smoke passed with source-checkout fallback and sockets denied. All package hashes and read-only BASE route checks passed.

Separate monitor repair prepared at source ab327dddd08ef731571a981b4cb77a4db1cc05fe. Apply COMBO first, then admin-mixed-delivery.py; the monitor installer verifies the pinned new PREMATCH manifest. No deployment performed.

## Operator deployment verified — 2026-10-04 21:09 Riga

The operator installed COMBO source cb6b7c605c70360031b84cc754b4bc9913536f54
at approximately 21:07:03 Riga, then ADMIN source
ab327dddd08ef731571a981b4cb77a4db1cc05fe at approximately 21:07:41.
Read-only inspection verifies all 852 PREMATCH files and environment bytes,
all four PREMATCH routes, all 19 monitor source files and manifest, and the
monitor preflight's exact approved PREMATCH release/hash checks.

The new monitor completed its natural 21:08:20 start with exit status zero.
PREMATCH discovery's latest completed run predates deployment; its next timer
start is 21:30 Riga. The first corrected natural COMBO selection/publication
remains unobserved. The root-owned incident state was not directly accessible;
successful monitor startup does not prove that incident 4f3832ebaf241e92b8d3ad51
has recovered.

Champion/protected model counts remain unchanged; ADMIN Codex is inactive/disabled
and live publication count remains zero. No agent deployment, manual cycle,
provider request, Telegram send, training, promotion, rollback or Official change.
No tests rerun for this documentation-only deployment readback.

Evidence: docs/evidence/combo_aggregate_20261004/deployed_readback.json.
