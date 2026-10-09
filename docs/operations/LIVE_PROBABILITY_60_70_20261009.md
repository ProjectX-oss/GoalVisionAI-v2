# LIVE probability 60–70%, EV diagnostic-only — 2026-10-09

User authorization: "Ev sledz ara, un varbutibu jabun no 60-70%".
This is an explicitly requested prospective Lab selection experiment, not proven
predictive improvement and not a new or calibrated model.

## Behavior

- LIVE only, explicit flag `GOALVISION_LIVE_PROBABILITY_60_70=1`; default off.
- Model probability must be **0.60 <= p <= 0.70**, inclusive without display rounding.
- The model probability is retained unchanged. Values above 70% also do not qualify.
- EV does not filter or rank; zero and negative EV may qualify.
- Deterministic ranking: descending model probability, then immutable prediction ID.
- Maximum one pick per natural cycle. Final-refresh failure does not force a replacement.
- Band rechecked during initial readiness, selector and final refresh before claim.
- Policy `LAB_LIVE_PROBABILITY_60_70_V1`; frozen prospective cohort `LIVE_P60_70_20261009_V1`.
- EV/edge remain audit fields; new experiment messages display probability and
  experiment status without EV/edge. Existing historical messages are not edited.
- Existing LIVE settlement/result Reply behavior handles both old and new predictions.
- Existing total LIVE statistics are retained, with new-policy identity available for
  separate cohort analysis; no history reset or hidden losses.
- Existing shadow opportunity capture remains available outside the new selection band;
  this publication filter must not silently erase otherwise admissible research inputs.

## Unchanged

Quote age remains diagnostic-only. Exact final refresh, state/event freshness,
quote identity/clock integrity, score/minute agreement, active markets, uncertainty,
model–market divergence and duplicate/fixture exposure guards remain. No new odds
floor/cap. Existing three-per-fixture/rebet policy and unchanged red-card limitations
remain; this change does not claim to fix model context or fit a card coefficient.

LIVE discovery 18:00–23:00 Europe/Riga; results continue outside discovery.
API ceilings/reserves, request ordering, PREMATCH/SINGLE/COMBO, champion, Official,
ADMIN Codex disabled state, bankroll/staking and frozen research calendars unchanged.

## Validation

Focused and adjacent tests use fake/mock transports and denied outbound sockets.
They cover exact lower/upper bounds, rejected rounding/out-of-band/NaN/infinite values,
negative and zero EV, EV-independent ranking/ties, no-selection, legacy compatibility,
prospective identities, exact final refresh, drift outside band before claim, suspended/
missing/mismatched quotes, state freshness, divergence, uncertainty, duplicates/exposure,
settlement/result replies, worker wiring/quota counts, no automatic learning and
operator package read-only/default/root guards, route restoration and new-module assembly.

Reproducible historical input replay:
```bash
/home/arvis/GoalVisionAI/.venv/bin/python -I -B operations/live-probability-band/replay.py \
  --database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db \
  --since 2026-10-08T15:00:00+00:00 \
  --until 2026-10-08T20:00:00+00:00 \
  --output /tmp/goalvision-live-probability-replay-20261009.json
```

448 captured candidate versions / 29 fixtures; 43 initially admissible versions /
18 fixtures, including 19 negative-EV versions. Actual old publications inside
the new band: 0 of 9. These are repeated observations, not 43 independent bets.
Replay uses original captured inputs and actual historical exposure. It performs
no replacement selection, final refresh, publication or outcome scoring.
It is not a backtest proving improved hit rate, ROI or guaranteed future volume.

## Operator application

Prepared source and package do not activate the policy.
Only the operator may apply the reviewed package:

```bash
python3 ~/goalvision-operations/live-probability-band.py
sudo python3 ~/goalvision-operations/live-probability-band.py --apply
```

Expected success marker: `LAB_LIVE_PROBABILITY_60_70_DEPLOYED`.
The read-only command must pass against the current exact base
`/opt/goalvision-live-quote-age-42a441f-20261008`.
Root ADMIN guard is checked at apply. Abort on route/file/environment/timer drift.

The package copies the installed immutable application and overlays only six
reviewed LIVE/daypart/worker files, including the new selection module. Frozen
JSON runtime assets are retained and included in the manifest. Isolated imports
must resolve from the assembled release, with sockets denied.

Apply briefly pauses only the LIVE timer, drains its running one-shot worker,
installs a later-sorting LIVE service environment drop-in, reloads systemd and
restores that timer's prior activity. It never starts a manual service cycle,
enables/disables timers, sends a test or mutates historical DBs. Failure recovery
restores only this installation's partial configuration; no model rollback.
All PREMATCH/COMBO/ADMIN/research routes and configured commands are pinned.

After operator apply, verify its marker and wait for natural 18–23 Riga cycles.
Do not trigger discovery or test Telegram. If no candidate meets all requirements,
NO_SELECTION is correct.

Final source SHA, package hashes, smoke/test results and safety verification are
recorded in `docs/evidence/live_probability_band_validation_20261009.json`.
