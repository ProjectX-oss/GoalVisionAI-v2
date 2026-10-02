> Superseded operator instructions after the separate settlement deployment: use
> `docs/operations/PREMATCH_SINGLE_FLOOR_COMPAT_20261002.md` and `prematch-policy-compat.py`.
> The original package and evidence below remain historical records.

# PREMATCH Lab SINGLE minimum 1.30 — 2026-10-02

Implementation and offline verification: **PASS**.
Production activation and forward-cycle readback: **BLOCKED — operator deployment pending**.
This report records a prepared change, not a deployed runtime policy.

## Authorized behavior

Arvis explicitly requested minimum odds 1.30 for PREMATCH SINGLE only, with COMBO
remaining without a minimum. This supersedes the earlier no-floor instruction
only for PREMATCH Lab SINGLE. No probability, value, quality or model threshold is changed.

- SINGLE: captured current decimal odds must be >= 1.30, without display rounding.
- Filter before choosing the best market per fixture, so an eligible alternate market remains available.
- Recheck before delivery and the first claim, including previously prepared no-floor/legacy singles.
- COMBO: retain the full quality-approved accuracy candidate pool, independently of SINGLE eligibility.
  Neither legs nor combined odds acquire an economic minimum. Valid odds >1 and all existing
  quality, freshness, identity, probability, independence and correlation checks remain required.
- New SINGLE decisions freeze `LAB_SINGLE_ACCURACY_FIRST_PER_FIXTURE_V3_MIN_ODDS_130`,
  minimum `1.30`, and a separate decision identity. The existing renderer displays `koef. ≥1.30`.
- Historical previews, claims, receipts and results are not rewritten. Previously published low-odds
  singles still settle and announce normally. Claimed fixtures are not republished by preparation.

## Changed files

New policy changes:

- `app/lab_v2_shadow/single_odds_policy.py`: explicit activation flag, strict Decimal boundary, rejection reason.
- `app/lab_v2_shadow/publication.py`: separate SINGLE and COMBO pools; frozen version/minimum/identity.
- `app/lab_combo/service.py`: final SINGLE-only floor guard and frozen V3 evidence validation.
- `tests/test_prematch_single_odds_floor.py`: boundary, old-queue, whole-cycle, COMBO and settlement regressions.
- `tests/test_prematch_settlement_upgrade.py`: shared failure/rollback tests for both operator packages.
- `operations/prematch-single-floor/{build,update}.py`: combined pinned operator package.
- `PRODUCT_RULES.md`, `TASKS.md`, and this report: authorization, implementation and pending activation.

The combined package also includes the previously prepared settlement correction from
`04a075134b1c3d825bb3dbd029db77e20d3a6953`, documented in
`docs/operations/PREMATCH_SETTLEMENT_FIX_20261002.md`:
confirmed losing COMBO leg settles the financial loss once; remaining leg evidence continues;
compatible adaptive readers and bounded unresolved-result diagnostics are retained.
Its runtime files are `app/lab_combo/{service,settlement,presentation,cli,result_diagnostics}.py`
and `app/adaptive_lab/metrics.py`. No historical result is deleted or recomputed.

## Verification

**373 passed in 13.24s**, with network connections disabled and fake providers/transports.
Test modules: the new SINGLE-floor suite; accuracy delivery; accuracy COMBO;
Lab V2 shadow; today scope; PREMATCH V2 enablement; COMBO early loss; Lab COMBO;
experimental selection; no-COMBO-learning; settlement upgrade; performance snapshot.

Evidence includes:

- 1.29 and 1.299999999999999999999999999 rejected; exactly 1.30 and above accepted.
- An alternate >=1.30 market selected when the highest-probability market is below the floor.
- COMBO with three 1.05 legs (combined 1.157625) passes preparation and simulated delivery.
- Stale, contradictory, correlated and otherwise invalid candidates remain blocked.
- An old prepared 1.05 SINGLE cannot create a new delivery claim after activation.
- Complete fake CLI cycles persist the floor rejection; with three qualifying COMBO legs,
  the cycle publishes a COMBO even when zero SINGLE bets qualify.
- A previously published 1.05 SINGLE still settles WON at +0.05u and announces its result.
- Old previews are byte-stable; replay and fixture deduplication remain intact.
- Operator tests cover hash/configuration drift, partial route failures, busy services,
  timer-state restoration, disabled ADMIN worker and compatible rollback.

These are behavioral regressions, not a claim of improved ROI or calibration. Forward performance
continues to require natural resolved observations; no historical bookmaker odds were used.

## Operator activation

Use this combined command instead of the earlier `settlement-fix.py` command:

```bash
sudo python3 ~/goalvision-operations/prematch-policy-fix.py --apply
```

Read-only preflight (no sudo):

```bash
python3 ~/goalvision-operations/prematch-policy-fix.py
```

The package is pinned to the currently deployed quality release
`/opt/goalvision-prematch-quality-3ad346b-20261001` and verifies all source hashes,
service commands, protected routes and the disabled ADMIN worker before routing.
Discovery, observer, settlement and research must share the compatible readers.
Only the four PREMATCH timers are briefly paused during the operator action;
active services drain naturally (maximum 45 seconds), and previous timer states are restored.
An active service is never killed or manually rerun. Configuration drift fails closed.

Enabled flags are `GOALVISION_LAB_SINGLE_MIN_ODDS_130=1` and
`GOALVISION_LAB_EARLY_COMBO_LOSS=1`; same-day Riga scope and accuracy COMBOs stay enabled.
Official, LIVE, ADMIN and weekly service routes remain outside this change.
No model training, champion promotion, provider call, manual operational cycle or Telegram test send
was performed while preparing this package.

Compatible rollback:

```bash
sudo python3 ~/goalvision-operations/prematch-policy-fix.py --apply --rollback
```

Rollback disables the new SINGLE floor and new early COMBO loss decisions while retaining
compatible readers for any already recorded early results and outstanding leg evidence.
It does not return to an older binary that cannot read those immutable records.

After operator deployment, verify the four route/environment readbacks and the next natural
publication/settlement evidence. Runtime success is not established by offline tests alone.

## Prepared package evidence

Source commit: `d73359111532fb2bbf0bc2e2e3d6a94f465b3f29`.
Branch: `fix/prematch-single-floor-20261002`.
Package: `/home/arvis/goalvision-operations/prematch-single-floor-d733591-20261002`.
Pinned wrapper: `/home/arvis/goalvision-operations/prematch-policy-fix.py`.
Target on operator deployment: `/opt/goalvision-prematch-single-floor-d733591-20261002`.
Eight reviewed runtime overlay files; complete expected tree: **807 Python modules**.

Read-only preflight returned:

```text
PREMATCH_SINGLE_FLOOR_PLAN_VALIDATED=/opt/goalvision-prematch-single-floor-d733591-20261002
current_mode=BASE; ADMIN_CODEX_DISABLED=PASS
```

Metadata SHA-256: `994d8212ce41efe5abfc2365e93feebb76716f1d5576ddf379745062c01b549f`.
Wrapper SHA-256: `8cc5b13716248ce7b5d87c406975a65c153e91e5ec309a466097e2be09fc9906`.
The package retains its own SHA256SUMS and pinned source/configuration metadata.
Final result: **PASS** for implementation, 373 tests and read-only package validation;
**BLOCKED pending operator activation** for production and subsequent natural-cycle verification.
