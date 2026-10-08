# LIVE quote age diagnostic policy — 2026-10-08

Status: reviewed implementation; operator deployment remains separate.

## Authorization

At 20:18:13 Europe/Riga the user requested that LIVE coefficient freshness no
longer be a selection blocker. This specifically supersedes the LIVE 20-second
quote-age limit. It does not change PREMATCH/COMBO thresholds or Official.
LIVE discovery remains 18:00–23:00 Riga; pending results continue outside that
window. No automatic production deployment, training, promotion or rollback.

## Contract

The new opt-in GOALVISION_LIVE_QUOTE_AGE_DIAGNOSTIC=1 is routed only to the LIVE
service. It requires the existing explicitly accepted provider-feed mode.
Policy: LAB_LIVE_API_FEED_AGE_DIAGNOSTIC_V2.

- Quote origin/retrieval age has no upper rejection bound in broad feed discovery,
  candidate readiness or final preclaim readiness. Original timestamps remain
  unchanged; diagnostic ages and the old 20-second reference are recorded.
- Fresh-feed counts still mean <=20 seconds. Eligible-feed and age-diagnostic
  counts are separate; old quotes are never relabeled fresh.
- Missing/invalid/future/reversed quote timestamps remain rejected.
- Final exact fixture/events/quote refresh, same score/minute state, 30-second
  state/event freshness, genuine LIVE provenance, valid odds/probability,
  active market, positive EV, uncertainty, divergence and duplicate/exposure
  checks remain in force.
- No new quote-age rank penalty is added. Existing max-ten-fixture scan and
  max-one-publication per natural cycle remain. Existing per-run, daily/minute
  ceilings and PREMATCH result reserve remain unchanged.
- Forecast values/model/champion do not change. New policy identities cannot
  reuse old immutable rejected candidates. Existing records/results are retained.
- Default/legacy mode keeps the prior age gate. No historical bookmaker odds.

## Fixed evidence and replay

The 18:00–20:07 Riga window had 26 completed natural cycles, 104 actual provider
calls, zero claims/sends. Twenty-five cycles had zero fresh active feed fixtures.
One cycle reviewed five fixtures: four quote/state mismatches; NEC–Express
produced seven market candidates with quotes aged about 30 seconds.
Last observed pre-request daily remainder: 4551, protected reserve 882.

Offline replay at each candidate's original timestamp removes only
STALE_LIVE_ODDS. Three candidates pass the other original readiness gates;
four retain NON_POSITIVE_EV. This is not a replayed publication, proof of an
available present quote, profitability evidence or permission to resend history.
The four state mismatches remain a separate blocker and were not relaxed.

## Verification

114 focused tests PASS (10.22 seconds), outbound sockets denied and synthetic
credentials. This includes default-policy compatibility, aged feed discovery,
missing/future/reversed timestamps, state/event limits, worker opt-in,
final refresh/transport rejection, duplicate claims, protected quota and real
SQLite contention, plus operator route recovery.
An earlier mixed-directory invocation reported 19 missing-fixture setup errors;
the isolated quota run passed 23 tests, and the correctly grouped final matrix
passed all 114. No application failure was hidden.

The operator package is an exact installed-base copy with five reviewed overlays:
app/adaptive_lab/daypart.py, app/adaptive_lab/worker.py, app/live_lab/engine.py,
app/live_lab/service.py, app/live_lab/runner.py.
It excludes unrelated research and the previously prepared monitoring-source fix.
The base is /opt/goalvision-live-evening-4f547cf-20261007.
Package build records full hashes, isolated import proof and protected routes.

## Operator commands

Run after the checksummed package has been prepared:

```bash
python3 ~/goalvision-operations/live-quote-age.py
sudo python3 ~/goalvision-operations/live-quote-age.py --apply
```

Default command is read-only. Apply requires root and changes only the existing
LIVE service EnvironmentFile through one new drop-in; it pauses only the LIVE
timer, waits for its in-flight service, then restores the prior timer activity.
It never manually starts the service or a discovery cycle. Interrupted installation
recovers only its partial route, with no model/history rollback.

Expected success: LAB_LIVE_QUOTE_AGE_DIAGNOSTIC_DEPLOYED.
Verify using the default command again, then inspect the next natural cycle:
eligible_feed_fixtures may exceed fresh_feed_fixtures; quote age alone is not a
blocker. No forced pick, provider test, Telegram test or existing-pick resend.
PREMATCH/COMBO/research/ADMIN routes, timer schedules, champion and Official remain
unchanged. ADMIN Codex remains disabled.
