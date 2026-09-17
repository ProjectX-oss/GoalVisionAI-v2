# LAB V2 competition-aware global discovery

This package is the isolated Lab-only V2 selection path. It consumes only
current/upcoming fixture data, completed football results/goals, current
API-Football predictions and current bookmaker quotes captured during the
run. The default `rehearse` command never constructs Telegram transport. The
separate `controlled-cycle --send` boundary can publish only final-reviewed
READY evidence through the existing exactly-once Lab ledger and settlement.

Persisted analysis records intentionally retain `analysis_mode =
LAB_V2_NO_SEND` because candidate generation itself cannot send. They also
record `publication_requested` and `publication_enabled`, while a separate
`publication_cycle` record captures transport construction, READY count,
publication attempts and successful Telegram sends for the outer controlled
handoff. A claimed delivery is treated as consumed even when its outcome is
unknown, so a later quote refresh or replay cannot create a duplicate send.

It never retrieves historical bookmaker odds, cannot address Official, cannot
mutate Official state and never installs or starts a timer by itself.

For newly classified candidates, optional lineups, injuries, standings and
advanced statistics contribute profile-specific uncertainty instead of global
rejection. All markets still require exact current fixture and quote refresh
before readiness. Legacy unprofiled evidence retains its historical rules.
Near-kickoff review calls are reserved before optional prediction enrichment,
and imminent kickoffs are reviewed first. The reserve includes all three
bounded provider attempts for each exact refresh endpoint. Provider errors do
not satisfy lineup/injury freshness, and a refreshed kickoff replaces the
discovery kickoff before readiness is decided.

V4 counts evidence families, not adapter rows: Pi, goals/form CMI and the
persisted CMI-derived model share one result-history/model-context independence
group. Every vote is selected inside the candidate's own market family, so a
totals preference cannot be treated as a 1X2 vote. Probability edge and
decimal expected value are retained as separate quantities.

Each discovered fixture receives an explicit coverage/lifecycle status,
including no odds, stale odds, unsupported markets, unnormalizable odds,
incomplete page coverage, missing model context, evaluated rejection, EARLY,
FINAL_REVIEW and READY. Full date-odds pages are not retained as a 15-minute
cache because the operational cycle is 30 minutes; normalized current quote
and candidate evidence remains append-only. Cycle summaries reference the
individual candidate documents instead of duplicating their full payloads.

EARLY fixture/market identities now survive discovery cycles in the small
`lab_v2_final_review_pending` projection, backed by immutable
`final_review_tracking` evidence. Upcoming legacy EARLY candidate documents
are recovered through an indexed kickoff-range query. Previously captured
odds are never copied into a new evaluation. Tracked fixtures enter the
reserved final-review shortlist even if broad fixture or odds discovery
omits them or rejects their odds as stale. Exact fixture/current-odds,
lineup and injury requests bypass cache near kickoff; current-season result
context and supported predictions are also refreshed within the call budget.

`tracked_final_reviews` retains explicit READY, rejection, pending budget,
unavailable odds, stale odds, invalid fixture and expiry outcomes. The current
window remains T-75 through T-10, using the refreshed UTC kickoff. A failed
exact quote response supersedes broad quotes; it cannot reuse an older price.
Terminal outcomes remain inspectable with `summary --fixture-id`, which also
resolves `candidate_ids` to concise per-market evidence. Quotes and candidate
fingerprints may change while the tracked identity remains fixture ID/market.

The incident evidence and regression results are documented in
`docs/LAB_V2_EARLY_CANDIDATE_AUDIT_2026-09-17.md`. No service-unit changes are
needed; the new Lab-only table/index are created on the next authorized run.
The discovery timer remains stopped for operator review.

V2 has no hard minimum decimal-odds floor for singles, individual combo legs or
combined combo odds. Current valid prices and every existing ensemble, value,
freshness, final-review, independence, correlation, exposure and exactly-once
gate remain mandatory. Odds bands are retained only for transparent reporting.
Official odds policy is separate and unchanged.

```bash
PYTHONPATH=. python -m app.lab_v2_shadow audit
PYTHONPATH=. python -m app.lab_v2_shadow summary
PYTHONPATH=. python -m app.lab_v2_shadow summary --fixture-id 123456
PYTHONPATH=. python -m app.lab_v2_shadow rehearse --max-calls 100 --daily-reserve 1500
PYTHONPATH=. python -m app.lab_v2_shadow controlled-cycle --send --max-calls 100 --daily-reserve 1500
```

The launch runbook and safety report are
`docs/LAB_V2_BROAD_COVERAGE_LAUNCH.md`. The Phase 1 baseline remains in
`docs/LAB_V2_PHASE1_PI_COVERAGE_SHADOW.md`.

The global redesign, thirteen competition profiles, candidate lanes, immutable
forward evidence, fair enrichment and no-send diagnostic commands are described
in `docs/LAB_V2_GLOBAL_COMPETITION_POLICY.md`. The measured baseline, one real
rehearsal, offline correction replay and verification limitations are in
`docs/audits/lab_v2_global_overhaul_2026-09-17.md`.
