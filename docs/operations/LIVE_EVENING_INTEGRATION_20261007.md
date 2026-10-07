# LIVE evening integration — 2026-10-07

Status: READY_FOR_EXPLICIT_OPERATOR_APPLY. Implementation 4f547cf0ac305393c656cfb270d98ea379310a18.
Production remains on the COMBO Double release until the explicit root apply below.

## Scope and source contract

The user authorized PREMATCH/SINGLE/COMBO discovery 10:00–18:00 Riga, LIVE
from 18:00, ongoing results, and a solution using the existing subscription.
The bounded LIVE discovery end remains 23:00 as discussed; LIVE results continue
outside that window while unresolved. This work introduces no new provider,
purchase, historical odds acquisition or model training.

The official API-Football LIVE contract supplies provider-level odds snapshots,
not a bookmaker field. It documents independent LIVE market IDs, unique
main=false/null values, and an update cadence that can vary between 5 and 60
seconds. Sources:
- https://api-sports.io/documentation/football/v3#tag/Odds-(In-Play)
- https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide

Strict attributed-bookmaker mode remains the default. The new, separately
opted-in LIVE Lab contract accepts a traceable API-Football snapshot with
bookmaker_id=null and bookmaker=null. It freezes source identity, provider
update timestamp, raw payload fingerprint, exact live market ID/name and quote
fingerprint. It never invents a bookmaker or treats retrieval as source update.

Every such message explicitly says that the bookmaker is unspecified and the
API price is indicative; availability must be checked at the recipient's
bookmaker. Its results/statistics use the captured indicative price and are
labeled accordingly. This is a distinct source-contract choice, not proof of
an executable bookmaker offer. Root apply requires --accept-api-feed-quotes
so that this change from the earlier strict-only requirement is reviewable.

**The existing 20-second quote limit is unchanged.** State/events retain their
30-second limits, exact score/minute matching, supported markets, EV, uncertainty,
divergence, exposure, duplicate and final-refresh guards. No publication threshold,
PREMATCH odds/probability floor, model formula, staking or champion was changed.
An evening with no fresh qualifying quotes legitimately produces no LIVE pick.

## Implemented behavior

| Work | Schedule / behavior |
| --- | --- |
| PREMATCH, public/private SINGLE, DC COMBO, Double | New discovery/publication only 10:00 <= Riga time < 18:00 |
| Existing PREMATCH/SINGLE/COMBO results | Existing all-day :05/:15/:25/:35/:45/:55 timer |
| LIVE Lab | Discovery 18:00 <= Riga time < 23:00; at most one new single per natural cycle |
| LIVE unresolved results | All day, only when needed; Reply to original message |
| LIVE timer | Every five minutes at :02/:07/.../:57; no catch-up and no startup test send |

LIVE uses the existing verified Lab bot/destination, visibly labeled LIVE, with
separate LIVE tables and statistics. It does not use Official or the COMBO bot.

Application window checks and shared per-attempt quota checks enforce the same
boundary as the timers. PREMATCH fixture kickoff eligibility still permits the
existing same-day 09–23 range; only the discovery/publication clock changes.
Existing published picks continue settlement after 18:00.

The shared account still allows at most 7,500/day and 300/min, using the lower of
provider headers and durable local allowance. The PREMATCH result reserve counts
remaining six-per-hour cycles to UTC reset at <=21 attempts/run, plus one possible
in-flight run, retaining a minimum 100. At 18:00 Riga on October 7 the bound is
1,155 requests. LIVE discovery, final refresh AND LIVE results cannot spend it.

Daytime discovery additionally protects an initial 1,800-call evening allocation
and paces its 16 half-hour slots. In evening mode the old fixed LIVE 1,800/day cap
is removed; LIVE can use the actual remainder above the PREMATCH reserve.
Requests remain bounded to <=80/run and paced across the remaining evening slots.
Available quota is a ceiling, not a target that must be spent.

LIVE broad odds coverage/freshness is checked before expensive individual
history calls. Catalog/team history is reused within one cycle, including
publication refresh; state, events and quotes are always fetched again.
No persistent odds cache or stale-quote fallback was introduced.

The LIVE worker reserves its status request before HTTP, no longer constructs
the learning coordinator or calls its after_settlement hooks, and settles only
LIVE shadow records. Model resolution fails on invalid artifacts instead of
automatically rolling back. The existing LIVE_POISSON_BASELINE_V1 formula is
unchanged; no trained LIVE champion is fabricated or bootstrapped. LIVE observations
can accumulate prospectively without fitting or activating a model.

## Verification

- Final focused regressions: 310 passed, 8 subtests passed in 16.51 seconds.
- Includes LIVE API-feed provenance, exact 20-second boundary, real ID/name/line
  mapping, unique/duplicate main flags, final-refresh rejection, fake end-to-end
  publish/settle/Reply, idempotency, no automatic learning/rollback, 18:00 cutoff,
  winter Riga offset, result reserve, removal of only the fixed LIVE cap,
  before-HTTP status claims, all-day settlement and idle zero-call behavior.
- Existing PREMATCH adaptive discovery, same-day publication, private SINGLE,
  COMBO Double, settlement Replies and quota/contention tests included.
- All tests used synthetic credentials/recording transports and denied outbound
  sockets. No full suite was run because the focused affected boundaries passed.
- Operator-controller tests use temporary files/fake systemd, including partial
  installation recovery and explicit source-contract/root guards.
- New unit files pass systemd-analyze verify.
- Isolated import/idle-worker smoke: 576 app modules; no source fallback, HTTP,
  Telegram, training or champion artifacts.
- Exact installed base and retained flags/routes verified before preparation.
- Replay of the already saved 12:06 Riga LIVE capture: 14 provider-feed quotes
  normalize (7 per fixture), bookmaker identity remains null, and all 14 still
  fail the unchanged 20-second age limit. No actual prediction or publication
  readiness is claimed for that saved sample. No new authenticated call was made.
- Evidence: docs/evidence/live_evening_20261007/.

## Operator activation

The builder creates a pinned package and wrapper under ~/goalvision-operations.
Optional read-only validation:

    python3 ~/goalvision-operations/live-evening.py

Authorized activation, with explicit acceptance of labeled API-feed quotes:

    sudo python3 ~/goalvision-operations/live-evening.py --apply --accept-api-feed-quotes

The wrapper validates exact source hashes and installed base/routes, requires
ADMIN Codex disabled, pauses/drains only affected Lab timers, stages the immutable
release, changes the four existing Lab import routes and discovery timer, and
enables only the new natural LIVE timer. No service cycle or test send is invoked.
A failed installation restores its own configuration changes/timer states; it
does not perform model rollback. Other service commands, Official, ADMIN and
research routes remain unchanged.

After the operator applies, inspect the first natural LIVE timer evidence:

    systemctl status goalvision-lab-live-evening.timer --no-pager
    journalctl -u goalvision-lab-live-evening.service -n 20 --no-pager

Do not manually invoke live-cycle --send. Observe natural-cycle fixture counts,
fresh-feed coverage, final-review outcomes, durable receipts and later results.
Fresh eligibility and genuine delivery remain prospective acceptance checks.

## Exact effects of this implementation turn

New provider calls: 0. Telegram calls/sends: 0. New subscriptions/purchases: 0.
Production deployment/timer changes: 0 before operator apply. No manual cycle.
Production application and original dirty checkout were not edited.
Official, PREMATCH champion, model formula, thresholds, calibration/holdout,
bankroll, ADMIN Codex and existing historical records remain unchanged.
The four shared quota claims from the earlier authorized capability probe belong
to that prior audit; no additional production database write was made here.

## Prepared package readback

- Package: /home/arvis/goalvision-operations/live-evening-4f547cf-20261007
- Target: /opt/goalvision-live-evening-4f547cf-20261007
- Read-only wrapper preflight: PASS, current_mode=BASE.
- Immutable application: 857 verified Python/JSON files; 11-file overlay.
- Exact package import/idle smoke: 576 modules PASS, no checkout fallback.
- Source commit: 4f547cf0ac305393c656cfb270d98ea379310a18.
- Wrapper and package SHA-256 pins: docs/evidence/live_evening_20261007/operator_package.json.
- LIVE is still OFF and PREMATCH still uses the original schedule until operator apply.

The theoretical PREMATCH quota projection also uses the active 16-slot schedule. The earlier unapplied package 1b425b5 is superseded; the pinned live-evening.py wrapper points only to 4f547cf.
