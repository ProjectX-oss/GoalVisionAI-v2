# Active conservative COMBO Lab experiment — 2026-10-04

The user explicitly requested that the improved COMBO selection be used for
actual Lab publications immediately so they can evaluate it personally. This
supersedes shadow-only authorization for this COMBO experiment only. Preparation
does not install it: operator activation remains separate. No quality improvement,
profitability or champion promotion is inferred from this authorization.

## Selection and provenance

The opt-in GOALVISION_COMBO_CONSERVATIVE_AGREEMENT=1 replaces the previous
COMBO rank with LAB_COMBO_CONSERVATIVE_AGREEMENT_V1. It retains the existing
current-quote, accuracy, severe contradiction, identity, today-only Riga, 55%
ensemble minimum, 1.30 per-leg floor, distinct-fixture/team and durable claim
gates. There is no extra combined-odds minimum and no forced triple.

Each eligible market receives three paired values:
- Constrained Dixon–Coles probability from a verified cached forward artifact.
- Existing unchanged ensemble probability for that current candidate.
- Multiplicative de-vig probability from the prospectively defined lowest-ID
  available complete bookmaker, exactly the reference rule used by shadow.

The minimum of the three values is a ranking score, not a calibrated probability.
Choose one market per fixture and up to three disjoint triples by product of
scores, with deterministic existing tie breaks. The existing ensemble joint
estimate remains explicitly separate from the conservative ranking score.

The adapter reads the research database in SQLite query-only mode, verifies
model hashes, protocol, numerical certificate, training chronology and exclusions,
then evaluates verified parameters for the current candidate. It never fits a
model, obtains provider data, or alters research records. The original research
purpose/selection_effect fields remain immutable. New publication authority and
model/quote bindings live in separate frozen COMBO policy evidence.

Current complete bookmaker quotes are read from existing consensus records and
reproduced, with exact selected-quote binding and delivery-time freshness checks.
Model age is limited to 24 hours; forecast and kickoff must stay in the original
declared forward window ending 2026-10-19 UTC. Excluded development/holdout and
target-in-training fixtures remain blocked. Missing, invalid, expired or
unavailable inputs skip the candidate. No fallback silently restores old ranking.

The reader has a 10-second preparation budget, two-MiB input-document bounds,
600 eligible-candidate capacity and 60 eligible-fixture combination bound.
Exhausting a budget/capacity discards the COMBO pool; SINGLE continues unchanged.
Publication does no model fitting. Offline work runs at nice 10; installed
research jobs keep CPU=25%, nice=10, budget=45s and their current schedules.

## Delivery, statistics and history

The existing enrolled @GoalVision_AI_Combo_Bot private route is reused without
credential or recipient changes. New predictions show “COMBO DC tests” and
carry immutable COMBO_AGREEMENT_20261004_V1 membership. Result statistics filter
confirmed original publication membership, not the current flag or settlement
date. Previous selections retain their prior cohort; all-time totals retain the
union and all historical losses. No historical record is reset or relabeled.

The new evidence is reproduced before a new durable delivery claim. Old
prepared selections cannot slip through while the new mode is active. Existing
economic claims prevent policy changes from republishing the same fixtures.
Frozen prediction identities bind current quotes and the source model/consensus;
replaying the same input does not renew frozen review timestamps.

Result Reply for text/photos, early COMBO loss, remaining-leg tracking, old
open-bet settlement, private routing and result deduplication remain active.
Compatible rollback turns only this ranking flag off, restoring previous new-pick
selection while retaining all new cohort, evidence and settlement readers.

SINGLE remains >=1.50 in its existing Lab route and 1.50 cohort. Champion,
Official, LIVE, ADMIN Codex, weekly and both research services are unchanged.
LIVE and ADMIN Codex remain disabled.

## Verification and limitation

Network-denied synthetic tests exercise real numerical artifacts, alternate
market selection, source integrity, unavailable inputs, exact floors, duplicate
claims, tampering, rollback, old/new cohorts, text/photo replies, early loss and
remaining-leg completion. Installer rehearsals cover active-service drain,
partial failures, timer restoration, immutable manifests and exact protected
routes. The complete assembled release must pass isolated imports and load all
JSON resources without falling back to a checkout.

A read-only development replay of the stored 10:00 Riga pool used 786 candidate
documents in temporary ledgers. Previous ranking had 47 eligible fixtures and
prepared three triples; the new ranking had only one eligible fixture and
prepared none. Both retained the same three SINGLE selections. No production
claim/receipt was created, and prior claims were intentionally not applied to
this selection comparison. This measures coverage, not betting performance.

There is insufficient prospective evidence to establish improved win rate or
ROI. No historical bookmaker odds were invented. The user-authorized experiment
may publish no COMBO until three fully evidenced fixtures are available.
See docs/evidence/combo_conservative_20261004/ for exact tests, source references,
protected-state readback and package verification.

## Operator activation order

The previously prepared monitor repair pins current PREMATCH routes. Apply it
first, while those routes still match its reviewed preparation state:

    sudo python3 ~/goalvision-operations/admin-health-projection.py --apply
    sudo python3 ~/goalvision-operations/combo-conservative.py --apply

The COMBO package accepts only the exact reviewed pre/post monitor route for
read-only preflight, and requires the repaired monitor before any apply mutation.
It then switches only the four existing PREMATCH release environment routes,
draining active oneshots through a temporary timer pause and restoring prior
timer states. It never starts a manual cycle or sends a test message.

Read-only preflight:

    python3 ~/goalvision-operations/combo-conservative.py

Compatible rollback:

    sudo python3 ~/goalvision-operations/combo-conservative.py --apply --rollback

No automatic deployment, Git push, champion promotion, provider request,
Telegram test send, or production learning cycle was performed.

## Prepared release evidence

Implementation commit: 222f20c. Package source: 6784969b14d5d5c17f4cdd09b5009114d83b9b9b.

Pinned package: /home/arvis/goalvision-operations/combo-conservative-6784969-20261004.
All 35 checksum entries passed; isolated package smoke imported 542 app modules
and verified the plan, solver protocol and competition registry. Offline regression:
528 passed. Both monitor and COMBO operator preflights exited 0 in read-only mode.
The COMBO preflight reports BASE and requires the prepared monitor repair first.
Root-owned disabled-Codex files are rechecked by operator sudo apply. Neither
release target is installed at this checkpoint. No services were switched.
