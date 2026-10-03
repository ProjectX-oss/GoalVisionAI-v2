# PREMATCH COMBO per-leg minimum 1.30 — 2026-10-03

Operator update: calibration observer has since been installed. Use the R2
runbook `docs/operations/PREMATCH_COMBO_LEG_FLOOR_R2_20261003.md` and the
new `combo-leg-floor-r2.py` command. The original ff55669 preparation below
is retained as historical evidence.

User clarification at 10:22 Europe/Riga: each selected COMBO leg must have
decimal odds at least 1.30. This is not a 1.30 combined-odds threshold.
SINGLE remains >=1.30. There is no additional combined-odds minimum.

## Selection and frozen evidence

`GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130=1` enables exact Decimal comparisons
against 1.30, inclusive and without display rounding. The floor applies before
the accuracy selector chooses the highest-probability eligible market per
fixture. A lower-probability market >=1.30 can therefore replace an ineligible
high-probability market on the same fixture.

The accuracy COMBO policy becomes
`LAB_COMBO_ACCURACY_FROM_SINGLES_V2_LEG_MIN_ODDS_130`.
The policy participates in prediction identity. New documents retain the
per-leg floor metadata and use the existing three-leg, probability ranking,
disjoint batch and correlation rules. Public previews state the leg minimum.
Existing V1 documents and preview bytes remain unchanged. Existing claims
prevent fixture reuse across policy versions.

The legacy V2 positive-value selector, experimental batch selector and reviewed
single composition also apply the same floor. All retain their existing upper
safety limits and non-odds eligibility requirements.

Both Lab COMBO delivery entry points check every captured leg before a new
durable claim or transport attempt, including unpublished old-policy previews.
Captured/leg odds aliases must agree. A large aggregate cannot hide a leg below
1.30. New frozen V2 evidence remains subject to its 1.30 contract even if runtime
floor enforcement is subsequently disabled.

Blockers are `LAB_COMBO_LEG_ODDS_BELOW_1_30` and
`INVALID_CURRENT_DECIMAL_ODDS`. The compact discovery output retains the
floor metadata and only allowlisted, bounded odds rejection counts. Full
diagnostics remain in immutable cycle evidence.

## Preserved behavior

Published predictions, receipts, quotes, history and statistics are immutable.
The new-pick check never runs for result notifications. Existing low-odds
COMBOs can still settle WON/LOST/VOID/partial-void and publish their result.
Early financial loss and remaining-leg tracking remain installed and enabled.
Today-only Europe/Riga, publication windows, quote freshness, quality,
independence, correlation and duplicate protections remain.

Official policy is unchanged. LIVE and ADMIN Codex remain DISABLED.
No model training, probability change, champion promotion, manual operational
cycle, provider request or real Telegram send is performed by this work.

## Offline verification and evidence

`tests/test_prematch_combo_leg_odds_floor.py` covers exact boundaries,
pre-ranking alternatives, high aggregate/low leg rejection, disjoint batches,
quality gates, prepared-preview rejection, both delivery entry points,
cross-policy claims, frozen-contract tampering, invalid odds/configuration,
legacy selectors, compatible flag rollback, historical settlement and controlled
fake CLI persistence. Existing SINGLE, COMBO, settlement, output, delivery and
installer regressions remain in the validation matrix.

Final validation: **1,147 passed, one inapplicable inherited installer case skipped**.
The earlier focused matrix passed 426 tests; counts overlap.
See `docs/evidence/combo_leg_floor_20261003/validation.json` for final counts,
commands and hashes. All tests use the network-denying offline runner and
disposable databases/fake providers/transports.

`readonly_routes.json` records actual installed routes, source parity and
disabled ADMIN state. `protected_state.json` records query-only protected
audit counts against the preceding 10:13 Riga baseline; all counts match. Production databases are not modified
by tests or the package preparation.

This is an operator-requested odds restriction, not evidence of an improved win
rate or profitability. No historical bookmaker-odds acquisition or backtest is
performed.

## Original preparation before calibration was installed

At preflight all four PREMATCH services still use
`/opt/goalvision-prematch-devig-83958d1-20261002/release.env`.
The previously approved calibration observer package from implementation
`c4daf63` and evidence commit `45d51a4` has not been installed.

The new package includes those five reviewed readiness files unchanged, plus
the COMBO floor changes. It replaces the two-step deployment with one reviewed
operator action. Use the new entry point below for both pending changes.
The earlier calibration-only wrapper remains pinned and is not rewritten;
its old-route guards will reject it after the new package is installed.

Thirteen overlay files plus the exact installed base reproduce the full
candidate application: 814 Python files and the frozen plan JSON. The immutable
release routes discovery, observer, settlement and research together so every
reader shares the new policy contract. Weekly and ADMIN routes are protected.
The readiness observer remains descriptive; research service behavior and
champion state are unchanged.

The operator pins the installed base, full source/JSON manifests, environment,
configured commands and protected routes; requires disabled ADMIN Codex;
pauses only the four affected PREMATCH timers; waits up to 45 seconds for
natural completion; switches atomically; and restores the original timer
states. It never starts or kills a service. Failed changes restore prior
routes and timer states. Root apply also requires the installed ADMIN
`autorepair.enabled=false` and `DISABLED` marker.

After package preparation:

```bash
python3 ~/goalvision-operations/combo-leg-floor-r2.py
sudo python3 ~/goalvision-operations/combo-leg-floor-r2.py --apply
```

Compatible rollback:

```bash
sudo python3 ~/goalvision-operations/combo-leg-floor-r2.py --apply --rollback
```

Rollback disables only the COMBO leg-floor flag; SINGLE 1.30, readiness reporting,
de-vig research, today-only, early loss, compatible readers and all evidence
remain. No migration or history rewrite is needed.

Normal-user preflight cannot inspect the root-owned ADMIN guard files and
reports that they are checked at apply. No deployment is performed in this
development task. After operator apply, inspect the loaded flags and next
natural discovery/observer evidence; do not run a manual cycle or test send.

Package pins and the source commit are recorded in
`docs/evidence/combo_leg_floor_20261003/package.json`.

## Prepared release

Source commit: `ff55669330e99d7f26e7e470000959ae1395853a`.

Package:
`/home/arvis/goalvision-operations/combo-leg-floor-ff55669-20261003`.

All 15 checksum entries and the read-only pinned-wrapper preflight pass.
Current mode remains BASE; ADMIN Codex systemd disabled guard passes.
Root-owned guard files will be checked at apply. Protected routes match.
The intended release is
`/opt/goalvision-prematch-combo-leg-floor-ff55669-20261003`.
It has not been installed. Use the single new operator command above to
install both the COMBO leg floor and the previously approved readiness observer.
