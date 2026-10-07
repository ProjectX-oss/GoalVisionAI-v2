# Evening PREMATCH / LIVE preparation — 2026-10-07

**Result: BLOCKED_NOT_DEPLOYED.** The user explicitly authorized preparation and
launch of daytime PREMATCH/SINGLE/COMBO and evening LIVE. This audit does not treat
the earlier LIVE-disabled instruction as a new permission barrier. The blockers
are actual provider evidence and unready LIVE runtime wiring. No production
timer, release, application source, champion or publication policy was changed.

## Current repository and runtime

- Base reviewed/pushed commit: d2512455de5ccc5d403f88f17176e7ee956c0fd5.
- Preparation branch: work/evening-quota-readiness-20261007.
- Installed PREMATCH release: /opt/goalvision-prematch-combo-double-170-6489f92-20261006.
- Installed implementation: 6489f92cf1b8da4ca894834fd2247c3dce94afef.
- Exact readback: all 856 application/resource hashes match the installed manifest.
- PREMATCH champion is unchanged: generation-aa7e535b86267741aabc967e8044de2ab94a4334b1520a829414dd55ebc7371a.
- Current discovery remains 09:00–22:30 Europe/Riga, every 30 minutes.
- Current results timer remains :05/:15/:25/:35/:45/:55, all day.
- No installed LIVE unit or running live-cycle worker. LIVE snapshots, candidates,
  publications, settlements and champion generations are all zero.
- ADMIN Codex remains disabled; Official was not accessed or changed by this work.
- Existing original checkout with preexisting dirty files was not edited.

## Requested schedule and quota contract

The read-only preparation records this target, not an installed change:

| Work | Proposed Riga schedule | Quota rule |
| --- | --- | --- |
| PREMATCH discovery, public/private SINGLE and both COMBO lanes | 10:00 inclusive to 18:00 exclusive, 16 half-hour starts | Budget against remaining slots and preserve evening/result allocation |
| PREMATCH/SINGLE/COMBO results and remaining legs | Existing all-day timer | Protected reserve, unchanged result behavior |
| LIVE discovery and exact final refresh | From 18:00; 23:00 stop is the bounded planning assumption discussed in chat | All usable remainder, on demand, after protected PREMATCH results |
| LIVE results for already published picks | Continue while unresolved, including after discovery window | Separate bounded requests; cannot consume PREMATCH reserve |

Do not just shorten the timer: the application currently has a 09–23 guard,
28-slot pacing, fixed 100-call discovery reserve and a fixed 1,800 LIVE/day cap.
A complete future change must update application guards and shared per-attempt
accounting together. In-flight PREMATCH work must not continue spending discovery
quota after 18:00. All four PREMATCH consumers must keep the same durable quota DB.

The conservative proposed PREMATCH result reserve counts every remaining
10-minute settlement start until the **UTC** quota reset at 21 attempts/run,
including status and retries, plus one possible in-flight run, with a 100-call
minimum. For 2026-10-07 18:00 Riga this is 54 remaining starts × 21 + 21 =
**1,155 requests**. This is planning arithmetic; it is not currently enforced.
It does not assume that the LIVE window end is the API day reset.

| Shared requests actually available at 18:00 (scenario) | PREMATCH result reserve | Remainder for LIVE discovery/refresh/results |
| ---: | ---: | ---: |
| 2,000 | 1,155 | 845 |
| 2,500 | 1,155 | 1,345 |
| 3,000 | 1,155 | 1,845 |
| 4,000 | 1,155 | 2,845 |

These are scenarios, not a forecast of tonight's remaining quota. Historical
Oct 4–6 replay suggests removing discovery outside 10–18 would have removed
1,728 / 651 / 1,293 recorded requests respectively, but new pacing, cache effects
and settlement demand can change actual savings. Keep 7,500/day and 300/min
limits, minimum(provider allowance, durable local allowance), retry accounting
and contention guards. Remaining allowance is permission, never an obligation to
spend every request. LIVE settlement needs its own protected scheduling and
stream isolation; it must not consume the PREMATCH reserve through the generic
SETTLEMENT exemption.

## Fresh authenticated provider evidence

At 12:06:32–12:06:34 Riga, a user-authorized bounded capability probe made **four**
GET attempts: /status, /fixtures?live=all, /odds/live/bets and the first /odds/live
page. Each attempt reserved its durable shared-quota slot **before** HTTP.
The attempt cap was four, daily reserve 2,500, no retries observed. Provider
remaining after the first call was 6,107 and after the fourth was 6,103; concurrent
normal production activity means the header difference is not our attempt count.

- 4 live fixtures; 266 catalog entries; 2 odds rows; paging 1/1.
- Both inspected rows omit bookmaker identity entirely.
- Their provider row-update ages were 36.473576 and 35.473576 seconds, exceeding
  the existing 20-second quote limit even if provisionally treated as quote time.
- A row-level update field still does not establish per-bookmaker origin semantics.
- Actual catalog remains IDs 59 Fulltime Result, 69 Both Teams to Score,
  36 Over/Under Line. The legacy adapter still lacks the reviewed actual
  BTTS/totals name/ID/period mapping.
- Isolated replay through the exact installed normalizer produced **zero quotes**
  for both rows, reason LIVE_BOOKMAKER_OR_ORIGIN_UNAVAILABLE. No invented bookmaker,
  timestamp substitution or freshness relaxation was used.

This sample establishes the current blockers for the inspected rows, not that
all future matches/leagues are permanently unsupported. No further API calls
are justified merely by re-running broad polling against the same missing fields.
Raw response payloads remain private and untracked under
/home/arvis/goalvision-operations/live-evening-preflight-20261007; only sanitized
capability facts and response fingerprints are committed.

## Additional runtime blockers

The unmodified app/adaptive_lab/worker.py live_cycle calls account_status before
binding shared quota, then claims status after HTTP. It also constructs
LearningCoordinator and calls after_settlement for LIVE and PREMATCH. Launching
this worker unchanged would not honor the current no-automatic-learning/promotion
scope. A reviewed LIVE-only no-training worker path is required.

The LIVE runner also needs settlement stream isolation and a bounded settlement
budget: the legacy shadow-settlement iteration is not restricted to LIVE. Review
bootstrap/executable baseline provenance separately; no new champion, fabricated
artifact or promotion was performed. A metadata planning document cannot certify
these missing runtime changes.

## Delivered preparation and verification

- operations/evening-quota/plan.py: credential-free, DB-free, network-free planner.
  It prints BLOCKED_NOT_DEPLOYED and exits **2 intentionally**. It is not a
  deployment command, readiness override or quota enforcer.
- tests/operations/test_evening_quota_plan.py: summer/winter Riga boundaries,
  exact timer tick/in-flight coverage, UTC reset, low-capacity reserves, invalid
  inputs and provider fail-closed cases.
- Existing LIVE regression checks plus the planner tests: **43 PASS in 4.80s**,
  outbound sockets denied and synthetic credentials only.
- Exact installed normalizer replay: zero qualified quotes; no HTTP/Telegram.
- Proposed systemd calendar strings pass syntax checks; no units were installed.
- Immutable release readback: 856 hashes PASS.
- Sanitized evidence: docs/evidence/evening_quota_20261007/.

## Operator next steps

A review-only reproduction from this branch is:

    python3 operations/evening-quota/plan.py --capability docs/evidence/evening_quota_20261007/provider_capability.json

Expected exit: 2, status BLOCKED_NOT_DEPLOYED. It deliberately has no --apply.
Do not run the old live-cycle --send entry point or install an evening LIVE timer.

The first external dependency is a verified current LIVE quote source/contract
with actual bookmaker identity and origin timestamps meeting the existing
freshness requirement. Provider-side clarification or a separately reviewed
alternative feed may resolve it; neither has been purchased or contacted here.
Then review the real market mapping, executable baseline, no-training worker,
all-consumer shared quota, 18:00 boundary guards, LIVE-only settlement and delivery
before building a deployable immutable package. Only after those tests pass can
the authorized launch be carried out (or handed to the operator if root is needed).

## Action status and exact side effects

- Schedule/quota planning and evidence: completed; preparation only.
- Provider contract/coverage: BLOCKED_NEEDS_MORE_EVIDENCE.
- LIVE worker/quota integration: LARGER_CODEX_TASK only after provider viability.
- Existing PREMATCH/COMBO deployment: NO_CHANGE.
- Production deployment, timer edits, manual discovery/settlement cycles: **0**.
- Provider HTTP attempts: **4**, durable shared quota claims: **4**.
- Other production DB mutations by this work: **0**.
- Telegram calls/sends, training, calibration fit/activation, champion changes,
  promotions and rollbacks: **0**.
- LIVE remains OFF; ADMIN Codex remains disabled; Official untouched.
- This work did not implement or activate the requested production timetable.
