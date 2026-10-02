# PREMATCH current-odds de-vig integration — 2026-10-02

Engineering: **PASS**. Forward predictive quality: **NEEDS_MORE_EVIDENCE**.
Production deployment: **OPERATOR DEPLOYED; READBACK PASS**.
Champion promotion: **NOT AUTHORIZED**.
The package-preparation section below records the earlier, pre-deployment state.

## Scope and reviewed base

Implemented on isolated branch `research/prematch-devig-shadow-20261002`, starting
at `29e4cb84ac4be9a99facae354718e5efeb69d894`. VPS read-only preflight verified
the actual `f81aa2c` SINGLE-floor release and all four PREMATCH routes.
The research mathematics was selectively ported from
`938402ae7e2279f2e36a5abd8cb8124e793d7495`, including the later provenance work.
The old research runner was not substituted for the current runner.

SINGLE >=1.30 inclusive; COMBO has no economic floor. Today-only Europe/Riga,
existing 09:00–23:00 kickoff window, probability/quality/freshness checks,
early COMBO loss and remaining-leg tracking are preserved. Official is unchanged.
LIVE and ADMIN Codex remain DISABLED; normal ADMIN monitoring continues.

## New behavior

Only `GOALVISION_LAB_DEVIG_RESEARCH=1` enables the optional adapters.
Absent/0/other values leave research disabled. This flag cannot activate
selection, publication, training, a provider, a timer or champion promotion.

After the existing candidate selection and core evidence persistence, discovery
uses exactly the already received current-odds payloads and consensus records.
It makes no extra API calls. It retains immutable `devig_research` siblings in
the existing shadow evidence table and reports a bounded status in cycle stdout.
All captured market families are considered, including unpublished/rejected
candidates and explicit unavailable families. No winner-only sample is created.

The V2 capture contains the exact source consensus (including Decimal spelling),
source/quote fingerprints, fixture and market family/line, bookmaker, origin and
retrieval times, actual capture cutoff, method version, frozen candidate/model
references and current selection policy context. Full probability vectors are
retained for multiplicative, numerical Shin, Power and OO-EPC.

Inputs must be complete mutually exclusive outcomes from one bookmaker and one
fixture/line, with identical origin/retrieval timestamps within the market.
Future, reversed, stale, post-kickoff, tampered and duplicate evidence is rejected.
Duplicate raw provider outcomes are detected before the consensus normalizer's
deduplication can conceal them. Incomplete bookmaker sets are explicitly counted;
a different valid complete bookmaker may still provide research evidence.
Quote-integrity failures block the affected capture. No probability is clamped.

Shin underround is NOT_APPLICABLE. OO-EPC's nonpositive-output case retains an
explicit FALLBACK_MULTIPLICATIVE reason. Research never replaces the existing
selection's multiplicative baseline. Failed research calculation/persistence
produces sanitized UNAVAILABLE evidence in the cycle, and does not swallow core
candidate/consensus errors. Research writes have a scoped 50ms SQLite busy timeout;
the existing timeout is restored in finally.

## Observer and forward metrics

The existing observer obtains a bounded read-only snapshot of research captures,
then closes the source connection before validation and numerical work. No schema
migration or new scheduled job is added. It joins existing SINGLE, canonical and
shadow result evidence only. COMBO financial settlements and COMBO_LEG rows do not
become comparator samples or learning/calibration observations. No result request
is issued by this integration.

The first valid capture per fixture/bookmaker/market family is retained for scoring.
Later cycles cannot replace its probabilities/model references or multiply sample N.
Conflicting first captures at the same timestamp are rejected. Future results are
excluded before checking as-of score conflicts. A result must be available after
the frozen kickoff and no later than the snapshot cutoff. Repeated identical
scores from different tracked markets share one fixture result.

Each method reports the multiplicative baseline on its exact comparable sample.
A separate common cohort includes only events applicable to all four methods.
Model scores and market scores use the same subset of available frozen model
references. Counts expose missing/invalid models, blocked/stale captures,
incomplete bookmakers, pending/void outcomes, future facts and duplicates.

Scores use the established mean binary-outcome Brier/log loss, ECE/MCE and
reliability bins. Favourite/other classification is fixed from multiplicative
probabilities for every method; signed bias and model-market disagreement are
reported. Policy/market-family segments preserve differing cohorts. Unique fixture,
book-market and correlated outcome counts remain distinct. No independent
learning observations, new holdout or superiority claim is created.

Full metrics persist as immutable `devig_metrics` rows in the existing shadow
evidence table. `observer_runs` retains only a fixed-size DEVIG_RESEARCH summary
and snapshot fingerprint. This preserves the installed ADMIN monitor's health
document size contract without changing ADMIN. Scheduled observe/research stdout
is also bounded; status/why-no-picks can compute full detail. The flag does not
turn observe/research commands into read-only commands.

## Capacity and limitations

Capture persistence uses the existing primary-key index to retain the first
family observation (including unavailable evidence), then only records adding a
previously unseen valid bookmaker. Repeated timer ticks do not duplicate full
sources; per-cycle status/reason counts remain in the existing cycle report.
A later valid quote after an initially blocked capture is admitted. Later model
changes never replace the original forward reference. Backdated writes and
ambiguous simultaneous first observations fail explicitly. No index migration
or scan of unrelated fixtures is required.

The source reader refuses the whole research snapshot above 50,000 rows,
256 MiB of JSON or a five-second SQL budget, with explicit UNAVAILABLE evidence;
it never publishes selective partial scores. This preserves source-lock and memory
bounds. Archival/incremental aggregation is a later reviewed capacity task.
Result coverage depends on already existing SINGLE/canonical/shadow tracking;
untracked captures stay pending. Bookmakers and outcomes on one fixture are
correlated and cannot be presented as additional independent matches.

The runtime contains zero de-vig captures before this deployment. Synthetic replay
evidence is marked CONTROLLED_SYNTHETIC_OFFLINE_TEST_ONLY and is not predictive
quality evidence. Genuine paired forward evidence begins only after separate
operator activation and subsequent natural cycles.

## Verification

- Broad affected-path suite: **879 tests PASS**, 108.27s.
- Final affected slice after provenance, ADMIN-size and capture-sampling refinements:
  **312 PASS**, 11.53s, including **47 de-vig tests**.
- Counts overlap; do not sum them.
- Network socket/DNS connections were disabled in the test process; all provider
  and Telegram interactions used fakes. Imports and changed-file compilation PASS.
- Actual runner output/candidates/provider-call lists match with research off,
  on, calculation failure and research-write failure.
- SINGLE/COMBO preparation, floor boundaries, today scope, early-loss accounting,
  remaining-leg completion, observer, readiness/manual-promotion and source-lock
  regressions passed in the affected suite.
- Append-only update/delete guards, replay/conflict handling, source reproduction,
  paired/common cohorts, pending/void/future labels, failure isolation, bounded
  health/stdout, indexed first-valid capture sampling and package apply/replay/rollback/failure recovery are covered.
- New test fixtures initially violated existing cache/ledger path guards; their
  paths were corrected. Final tests do not weaken those guards.
- The existing blanket tampered-quote rejection regression was preserved;
  the V2 incomplete-book behavior explicitly retains healthy complete siblings.

Evidence:
`docs/evidence/prematch_devig_20261002/runtime_preflight.json`,
`protected_state_before.json`, `protected_state_after.json`, `verification.json`,
`synthetic_replay.json`, `runtime_readback.json` and the two JUnit reports.
Package preparation and final protected-state readback are recorded separately.

## Changed files

Runtime:
- `app/adaptive_lab/devig_research.py`
- `app/adaptive_lab/devig_metrics.py`
- `app/adaptive_lab/devig_integration.py`
- `app/adaptive_lab/observer.py`
- `app/adaptive_lab/prematch.py`
- `app/lab_v2_shadow/runner.py`
- `app/lab_v2_shadow/operator_output.py`

Tests/operations: `tests/adaptive_lab/test_devig_research.py`,
`tests/adaptive_lab/test_devig_integration.py`,
`tests/test_prematch_settlement_upgrade.py`,
`operations/prematch-devig/build.py`, `operations/prematch-devig/update.py`.
TASKS.md and this report/evidence are updated. All other application files match
the installed SINGLE-floor application byte-for-byte.

## Operator handoff

A checksummed package is built from committed sources against the exact installed
`/opt/goalvision-prematch-single-floor-f81aa2c-20261002` application/environment.
It pins the full tree, seven reviewed overlay modules, configured commands,
protected ADMIN/weekly/legacy routes and the disabled ADMIN worker.

The prepared wrapper is `~/goalvision-operations/devig-shadow.py`.
Without arguments it only validates. Installation is a separate operator action;
nothing in this task runs --apply. Apply pauses only the four PREMATCH timers,
allows active services to drain naturally for up to 45s, refuses busy services
without killing them, and restores each prior timer state.
Configuration/hash drift is refused before controls.

Rollback disables only GOALVISION_LAB_DEVIG_RESEARCH. It preserves SINGLE 1.30,
today-only, early COMBO loss, remaining-leg tracking and stored research/history.
There is no provider/send/manual-cycle step in installation or rollback.
After separately authorized installation, inspect route/flag readback and the
next natural discovery/observer pair; a clock time cannot establish sample quality.

### Prepared package readback

- Implementation commit: `83958d1f6505fd5f6687b250cbd19e96f7e5c060`.
- Package: `/home/arvis/goalvision-operations/prematch-devig-83958d1-20261002`.
- Read-only wrapper validation: PASS, `current_mode=BASE; ADMIN_CODEX_DISABLED=PASS`.
- SHA256SUMS: all nine files PASS. Exact 807-module installed base; 810-module
  candidate tree, with seven reviewed overlays (three new modules).
- No apply, rollback or service-control command was executed; the candidate
  release is not installed. Runtime remains the SINGLE-floor release.
- Champion pointer, activation/generation/learning-cycle/holdout counts and zero
  LIVE publications match the pre-change readback.
- Package hashes and wrapper/source pins: `docs/evidence/prematch_devig_20261002/operator_package.json`.
- Genuine forward verdict remains NEEDS_MORE_EVIDENCE. Installation and natural
  evidence readback are the next separately authorized operator step.

## Mathematics references

Checked primary descriptions on 2026-10-02:
- https://www.sciencepublishinggroup.com/article/10.11648/j.ajss.20170506.12
- https://arxiv.org/html/2604.17194v1 (Algorithms 2, 4 and 5).

Only the odds-only formulae are used, with bounded bracketed numerical roots.
No historical bookmaker-odds dataset, FL-GLM fitting or provider download was used.


## Operator deployment readback — 2026-10-02 14:16 Europe/Riga

The operator applied the prepared package and supplied PREMATCH_DEVIG_DEPLOYED.
Independent read-only validation confirms all four PREMATCH routes use
`/opt/goalvision-prematch-devig-83958d1-20261002/release.env` and all expected
flags remain enabled. The pinned wrapper validates with current_mode=ENABLED.
All four timers are enabled/active; ADMIN Codex remains disabled, while the ADMIN
monitor is enabled and healthy. The post-deployment 14:15 settlement service
finished successfully. Champion pointers and protected activation/learning/holdout
counts match the earlier snapshot; LIVE remains DISABLED in the latest observer.

At readback there are zero de-vig captures/metric rows: the first new discovery
is due at 14:30 and the observer at 14:38 Europe/Riga. Natural-cycle integration
verification is PENDING; forward quality remains NEEDS_MORE_EVIDENCE.
No manual cycle, provider request, Telegram test or service control was executed
during this verification. Evidence: `deployment_readback.json` in the evidence
directory above.


## Natural-cycle verification — 2026-10-02 evening

Readback cutoff: 20:44:32 Europe/Riga; latest persisted metrics: 20:38:01.
Natural integration: **PASS**. Predictive quality: **NEEDS_MORE_EVIDENCE**.

- 13 natural discovery cycles (14:30–20:30) all recorded CAPTURED.
- 13 natural observer cycles (14:38–20:38) all retained linked immutable metrics;
  no UNAVAILABLE snapshot. The initial five correctly had no settled outcomes.
- 1,459 capture records across 251 attempted fixtures: 608 AVAILABLE and 851
  BLOCKED. Valid bookmaker evidence covers 122 unique fixtures.
- Blocked evidence: 830 unavailable quotes, 16 no complete valid bookmaker,
  five stale sources. These are explicit source exclusions, not integration errors.
- The only outside-today capture family belongs to future-dated fixture 1587495;
  all five family records are BLOCKED/CURRENT_QUOTES_UNAVAILABLE and excluded.
  Current discovery scope remains TODAY_RIGA.
- First-valid sampling retains 2,294 book/market samples: 342 resolved and 1,952
  pending. Resolved unique fixtures: **18**, not 342 independent matches.
- Pure offline reproduction of all 1,459 captures, hashes for 13 metrics and all
  13 observer links PASS. No future-capture or invalid-result-chronology samples.
- Readable discovery/observer/settlement journals contain no research-unavailable,
  traceback, error-priority or process-failure entries in the inspected window.
  ADMIN emitted no application journal entries in the readable scope; its latest
  service readback is success and its timer remains active.
- Runtime preflight PASS; protected champion/activation/learning-cycle/holdout
  counts unchanged. LIVE and ADMIN Codex remain disabled; Official mutations zero.
  SINGLE 1.30, COMBO no floor, today-only and early-loss flags remain pinned.

Descriptive results on the same 18 fixtures / 342 correlated book-market rows
(lower is better; these are probability errors, not win rate):

| Method | Brier | Log loss | ECE |
| --- | ---: | ---: | ---: |
| Multiplicative | 0.202271 | 0.590682 | 0.044611 |
| Shin | 0.201254 | 0.587962 | 0.050511 |
| Power | 0.200754 | 0.586321 | 0.052570 |
| OO-EPC | 0.200726 | 0.586528 | 0.061712 |

Small Brier/log-loss differences coexist with worse ECE on this tiny correlated
sample. No method is approved as superior. No threshold, selector, champion or
deployment changed. Next evidence step: allow remaining naturally tracked matches
to settle, then review broader forward coverage and stability across days/families.

Evidence: `docs/evidence/prematch_devig_20261002/natural_cycles_evening.json`.
