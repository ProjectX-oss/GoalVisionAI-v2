# PREMATCH SINGLE minimum 1.50 — 2026-10-03

The user explicitly authorized a 1.50 SINGLE experiment with actual predictions
published into the existing Lab conversation. This is not a shadow-only selection
change. COMBO legs remain >=1.30, with their existing private COMBO bot and no
additional combined-odds minimum.

## Selection and delivery

GOALVISION_LAB_SINGLE_MIN_ODDS_150=1 takes precedence over the retained 1.30 flag.
Both flags accept only exact 0/1. The existing default behavior is unchanged when
the new flag is absent. Exact Decimal odds are checked before per-fixture ranking
and again before a new SINGLE claim. 1.499999… is rejected, exact 1.50 accepted.
A lower-probability qualifying alternative market can replace a sub-1.50 market
for the same fixture. The independently filtered COMBO candidate pool stays intact.

Newly prepared SINGLEs retain a distinct immutable policy:
LAB_SINGLE_ACCURACY_FIRST_PER_FIXTURE_V4_MIN_ODDS_150.
Frozen metadata, IDs, preview and delivery-review readers recognize the new
policy while preserving prior versions. Existing economic claims prevent a
policy change from authorizing duplicate bets. Current odds freshness, quality,
probability minimum 55%, correlation, today-only Europe/Riga and review rules
remain unchanged. EV remains diagnostic under the existing approved Lab policy.

SINGLE predictions continue through the ordinary publication path to the
existing Lab destination. Prediction text shows the 1.50 minimum. COMBO routing,
Reply results, result photos, early loss and remaining-leg tracking are retained.
The de-vig capture records the actual active SINGLE policy/minimum instead of
mislabeling the new period as 1.30; its sampling/selection effect remains unchanged.

## Transparent policy statistics and open bets

New 1.50 predictions/results display explicitly labelled SINGLE 1.50 test
statistics. Membership follows the immutable prediction policy and a confirmed
original Lab receipt, not the current flag or settlement date. W/L/VOID, pending,
flat-unit P/L and ROI retain the existing accounting formulas. Only confirmed
1.50-policy publications enter this public test cohort.

The read-only SINGLE cohort report adds mutually exclusive policy totals for
comparison; the existing all-time union and historical segments remain available.
No past losses, predictions, messages, evidence or training samples are reset.
Old frozen previews retain their exact text. Old open bets still settle and
announce in their original destination, with Reply to the original message.

Compatible rollback restores new SINGLE selection to 1.30 but retains the
current readers and all 1.50 cohort membership. A later 1.50 result therefore
remains in the 1.50 statistics even after rollback. Already attempted messages
are never resent.

## Verification

883 offline tests passed; one inherited inapplicable installer case skipped.
The targeted 1.50 suite contributes 30 tests to that matrix.

Coverage includes exact boundaries without rounding, alternative-market ranking,
COMBO 1.30 independence/private routing, ordinary fake-transport Lab delivery,
complete controlled-cycle fake publication, frozen-contract rejection, invalid
flags, versioned identities with shared economic claims, as-of/PENDING/VOID
accounting, old/new policy cohorts, old-bet settlement, text/photo replies,
rollback readers and the current de-vig provenance. Installer regressions cover
the exact installed base, active-service drain, partial recovery, timer state
restoration, missing configuration, hash/source drift and protected routes.

The entire candidate matches the deployed 818-file application/plan manifest
plus exactly six reviewed runtime overlay changes. No module outside that overlay
is changed. The frozen calendar plan and champion/model counts remain unchanged.
Tests deny network access; controlled cycles use fake providers/transports only.
No manual production cycle, provider call or Telegram test send was performed.

## Operator package

The exact installed base is:
 /opt/goalvision-prematch-settlement-replies-2436d39-20261003

After preparing the pinned package:

    python3 ~/goalvision-operations/single-floor-150.py
    sudo python3 ~/goalvision-operations/single-floor-150.py --apply

The operator's sudo password is required; unattended sudo is unavailable.
Apply verifies source/environment/package hashes, current four service routes,
existing COMBO enrollment, Reply support and disabled ADMIN Codex. It drains
only the existing affected services through a temporary timer pause and restores
prior timer states. It never starts a manual cycle or synthetic Telegram send.

Compatible rollback:

    sudo python3 ~/goalvision-operations/single-floor-150.py --apply --rollback

Rollback switches off the new 1.50 flag only. The 1.30 SINGLE flag, COMBO per-leg
1.30, separate COMBO route/period, settlement Reply, today-only, early settlement,
de-vig research and calibration readiness stay enabled.

Official and weekly routes remain unchanged. LIVE and ADMIN Codex remain disabled.
No automatic champion promotion, git push or historical bookmaker-odds work.
Operator installed the release at 16:04 Riga; independent deployment readback
passed. The first qualifying natural 1.50 publications were independently verified
in the 16:30 and 17:00 Riga cycles; see the natural receipt evidence below.

Evidence: docs/evidence/single_150_20261003/.
Related source review: docs/research/CURRENT_DATA_QUALITY_OPTIONS_20261003.md.

## Prepared package evidence

Source commit: e1263e7f3e5aeb3291cc2e506d1115020fc27cac

Pinned package: /home/arvis/goalvision-operations/single-floor-150-e1263e7-20261003

All eight package checksum entries passed. Read-only operator preflight exited 0:

```text
SINGLE_150_PLAN_VALIDATED=/opt/goalvision-prematch-single-floor-150-e1263e7-20261003
current_mode=BASE; ADMIN_CODEX_SYSTEMD_DISABLED=PASS
ROOT_GUARD=CHECKED_AT_APPLY
```

At package preparation, this verified the installed base without applying.
The operator subsequently installed it; see deployment readback below. Package evidence is stored in
`docs/evidence/single_150_20261003/operator_package.json`.

## Operator deployment readback

The operator deployed the pinned e1263e7 release on 2026-10-03 at 16:04 Riga.
Read-only preflight reports current_mode=ENABLED. All 818 application/plan files,
release and rollback environment bytes, and all four service routes match the
reviewed package. Timers are enabled and active. ADMIN Codex remains disabled,
protected ADMIN/weekly routes match, and champion/model counts are unchanged.

The 16:00 discovery publication completed before installation; no V4 1.50
prediction was present at readback. The next scheduled discovery is 16:30 Riga.
A first qualifying 1.50 publication remains to be observed; no manual cycle,
provider request or Telegram request/send was made for this verification.

Evidence: `docs/evidence/single_150_20261003/deployed_readback.json`.

## Natural publication verification

The 16:30/17:00 scheduled cycles delivered six V4 SINGLEs to the existing Lab
destination, with odds 1.50, 1.50, 1.53, 2.10, 1.50 and 1.53. Confirmed receipt
IDs are 624–626 and 632–634. Prediction/receipt fingerprints and the immutable
1.50 policy-statistics snapshot passed. No manual cycle, provider call or
Telegram request was made. See
`docs/evidence/single_150_20261003/natural_publications.json`.
