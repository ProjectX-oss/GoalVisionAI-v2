# PREMATCH SINGLE floor — settlement deployment compatibility (2026-10-02)

Implementation and offline verification: **PASS**. Activation still requires the operator command below.

## Cause and runtime evidence

The operator successfully installed settlement release `04a0751` before applying the
SINGLE-floor package prepared against quality release `3ad346b`. The latter correctly
rejected the changed discovery route with `PREMATCH_ROUTE_MISMATCH`; its failure
occurred before release creation, timer controls or route writes.

Read-only verification confirmed:
- All four PREMATCH services use `/opt/goalvision-prematch-settlement-04a0751-20261002/release.env`.
- All 806 installed Python modules match the settlement deployment manifest.
- Early COMBO loss is enabled. The ADMIN worker is inactive and its timer disabled.
- The failed SINGLE-floor target and its systemd drop-ins do not exist.

## Fix

The operator package now pins the installed settlement release and its exact environment.
Its three runtime overlays contain the already tested SINGLE-floor implementation:
`app/lab_combo/service.py`, `app/lab_v2_shadow/publication.py`,
`app/lab_v2_shadow/single_odds_policy.py`.
Application source has not changed from the previously verified implementation.

SINGLE minimum remains **1.30 inclusive**; COMBO has no per-leg or combined minimum.
The new rollback disables only the SINGLE-floor flag and preserves the previously
installed early COMBO loss behavior and compatible readers.

Changed files in this compatibility fix:
- `operations/prematch-single-floor/build.py`
- `operations/prematch-single-floor/update.py`
- `tests/test_prematch_settlement_upgrade.py`
- `TASKS.md`, the original SINGLE-floor report notice, and this report.

**126 tests passed in 4.14s**, with network connections disabled:
operator apply/replay/rollback and failure recovery; SINGLE/COMBO floor boundaries
and delivery; early-loss settlement compatibility. Added checks reject old or mixed
base routes before any timer controls or target creation. The unchanged application
had previously passed the broader 373-test suite.

## Command

Use the new entry point, which leaves the old checksummed package intact:

```bash
sudo python3 ~/goalvision-operations/prematch-policy-compat.py --apply
```

Optional read-only validation:

```bash
python3 ~/goalvision-operations/prematch-policy-compat.py
```

Compatible rollback after deployment:

```bash
sudo python3 ~/goalvision-operations/prematch-policy-compat.py --apply --rollback
```

The installer retains source/configuration pins, the shared operator lock, timer
restoration, a bounded natural service drain and protected ADMIN/weekly routes.
No production route was changed while preparing this fix; no manual operational
cycle, provider request or Telegram test send was performed.

After the operator command, verify its deployment readback and the next natural
PREMATCH cycle. Offline validation alone does not establish runtime activation.

## Prepared package readback

Source commit: `f81aa2c2c1aae4af8decaa9b454d182c82f74af8`.
Package: `/home/arvis/goalvision-operations/prematch-single-floor-f81aa2c-20261002`.
Three reviewed overlays; complete application manifest: 807 Python modules.

```text
PREMATCH_SINGLE_FLOOR_PLAN_VALIDATED=/opt/goalvision-prematch-single-floor-f81aa2c-20261002
current_mode=BASE; ADMIN_CODEX_DISABLED=PASS
```

Metadata SHA-256: `4a3a870ef03fc7d2093ce833e0b1a4128a3a1d6d2aec512dde6e1812593606bb`.
Wrapper SHA-256: `7449b07ff683425bf56fcac68145f6f935bb804134c2ac809ca5d49d038c59b7`.
The original operator entry point remains byte-for-byte unchanged.
Final verdict: **PASS** for the compatibility fix, 126 tests and read-only VPS preflight.
**BLOCKED pending operator activation** for SINGLE minimum enforcement on the running system.
