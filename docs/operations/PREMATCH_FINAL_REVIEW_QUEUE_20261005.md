# PREMATCH final-review queue repair — 2026-10-05

Status: OFFLINE_VERIFIED; operator deployment pending.

## Why this change is needed

Read-only review of the 2026-10-04 natural cycles identified three private SINGLE
numeric matches that never received an exact fixture/current-odds review:
Las Palmas–Valladolid (1569956 / UNDER_2_5), Colchagua–Provincial Osorno
(1600716 / BTTS_NO), and Atletico Avila–Dinamo de Puerto La Cruz
(1635939 / BTTS_NO). Colchagua additionally had stale broad quotes from 19:00 Riga.

The first batch admitted only the highest resource class, including 23:00 Riga
kickoffs that publication does not allow. The second five-slot shortlist was
truncated before already attempted fixtures and disallowed kickoffs were skipped.
Lower-priority pending matches could expire without a review despite unused quota.
At 22:00 Riga the recorded shortlist contained five 23:00 kickoffs, while Atletico
Avila started at 22:30. That natural cycle used 84 of its effective 300-call ceiling.
The affected fixtures have no retained enrichment_service phase=review records.

These facts do not establish that the bets would have passed a fresh review or won.
The numerical model/market contradiction controls are separate and unchanged.

## Changes

Only application file app/lab_v2_shadow/runner.py changes.

- Admit mandatory reviews only for publishable, same-Riga-day PREMATCH fixtures
  inside the existing greater-than-10 through 75-minute review window.
- Prioritize retained pending fixtures, then kickoff deadline, least recent
  review at tied deadlines, existing resource class, and stable fixture ID.
- Use the existing two batches of at most five fixtures. Exclude every earlier
  same-cycle attempt before taking the second batch, including failed attempts.
- Retain provider-wrapper retry limits and existing cycle/minute/daily budgets,
  the settlement reserve, and the 180-second settlement/discovery guard.
- Retain optional early-match context collection when no final review is due.
- Persist explicit due/selected/attempted/pending fixture IDs. Distinguish quota
  pending from shortlist capacity pending; do not label an unattempted review
  as completed or attempted.

No prediction formula, score ranking, model/champion, probability threshold,
odds floor, freshness limit, publication volume cap, or timer schedule changes.
A scheduling repair can make more existing candidates reach their required
checks, but it neither guarantees publication nor manufactures a qualifying pick.

Existing Lab SINGLE >=1.50, COMBO legs >=1.30 in both lanes, private SINGLE
>=1.70 / 70–80%, today-only 09:00–23:00 Riga (23:00 excluded), Reply results,
early COMBO loss, remaining-leg tracking, period history and quota reserve remain.
Official is untouched. LIVE and ADMIN Codex remain disabled. No historical odds.

## Validation

- Original-code regression: 5 failed as expected, each reproducing an operational
  defect (pending priority, reused shortlist slots, cutoff, failed-attempt capacity,
  and false attempted status under insufficient budget).
- Initial affected-path matrix: 208 passed.
- Final focused matrix with real socket connections denied: 338 passed in 47.97s.
  Includes the new queue and operator tests, existing discovery/tracking,
  private SINGLE, COMBO market/aggregate, and settlement Reply regressions.
- Fixture, price, quote provenance, prediction and publication gates remain real
  in existing adjacent tests. New end-to-end scheduling tests use the actual
  runner and disposable repositories with synthetic provider responses.
- Restart/tie fairness, 10/75-minute boundaries, invalid PREMATCH status, two-batch
  capacity, failed exact quotes, low budget, and optional early context covered.
- Independent in-memory queue replay over retained incident snapshots places
  Las Palmas third in the 19:00 first batch, Colchagua tenth at 21:30 (second batch
  conditional on budget), and Atletico Avila first at 22:00.
  This is a scheduling replay, not a full provider-cycle or prediction replay.
  Current tracked snapshots inform replay priority; no forecast or fresh quote
  is invented. See incident_queue_replay.json for the exact scope.
- git diff --check passed. The deployed application baseline and full file-set
  equality are enforced again by the operator package builder.

No real provider requests, Telegram sends, manual production cycles or deployments
were performed. Synthetic call counts in tests do not represent provider traffic.

## Operator procedure

The builder pins the source commit, one-file overlay, exact installed baseline
application and environment, all four PREMATCH command/routes, current protected
ADMIN/research/weekly routes, and required JSON runtime resources. Default
validation is read-only. The package import smoke forbids network and checkout
fallback. Apply requires root, an inactive/disabled ADMIN Codex worker, exact
hashes, a serialized lock, timer pause and bounded service drain. Running workers
are never killed and no service is manually started.

After the reviewed package is prepared:

    python3 ~/goalvision-operations/final-review-queue.py
    sudo python3 ~/goalvision-operations/final-review-queue.py --apply

A busy-worker timeout is a safe refusal: retry after the natural cycle finishes.
No rollback operation is prepared or authorized. Interrupted installation restores
the prior route/timer state; it does not roll back a model or rewrite evidence.

After operator apply, verify the next natural discovery cycle's queue evidence,
exact reviews, service status and retained policy flags. Do not force a cycle,
provider call or Telegram test. New successful publication is not an acceptance
requirement: stale quotes and failed quality checks must still block.

## Provenance

Base branch: fix/combo-aggregate-20261004
Base commit: cf6aaf441914000382bb11dfed50d20d583c4037
Installed base: /opt/goalvision-prematch-combo-aggregate-cb6b7c6-20261004
Installed monitor preserved: admin-mixed-delivery-ab327dd-20261004
Work branch: fix/final-review-queue-20261005

Package and exact source commit: docs/evidence/final_review_queue_20261005/package.json
Focused verification: docs/evidence/final_review_queue_20261005/verification.json

## Prepared package readback

Source commit: 76d96c1a374a35a2d8d7cd059d0363ac095be3eb
Package: /home/arvis/goalvision-operations/final-review-queue-76d96c1-20261005
Target: /opt/goalvision-prematch-final-review-queue-76d96c1-20261005

Read-only operator preflight: PASS, current_mode=BASE.
Checksums: 3/3 PASS. Complete application manifest: 852 .py/.json files.
Isolated release import/queue smoke: 549 modules PASS; independently assembled
second copy produced the identical manifest and smoke evidence.
Required reviewed_competitions.json and frozen calendar plan are included.

Working release remains the COMBO aggregate baseline; deployment is pending.
ADMIN Codex systemd timer is inactive/disabled; worker inactive with MainPID=0.
Bootstrap champion generation remains unchanged; live publication count is zero.
