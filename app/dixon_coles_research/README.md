# Dixon–Coles research

This is an isolated manual research tool, implemented after the user's 2026-10-03
approval at **normal priority**. It does not change discovery, publication,
selection, staking, the adaptive model registry, calibration, or champion state.
No production module imports this package. No service, timer, environment flag,
deployment script, external dependency, provider client or Telegram client was added.

## What is fitted

A league-specific, regularized Dixon–Coles goal model jointly estimates a global
goal rate, mean-zero team attack/defence strengths, home advantage, and the
low-score dependence parameter. The likelihood uses regulation-time FT goals.
Exponential weighting has a fixed 180-day half-life. The ridge, 40-match minimum,
three-result target-team minimum, 64-team/500-result bounds and optimizer options
are declared in the immutable plan before fitting; they were not tuned on outcomes.

The implementation is original standard-library Python, using analytic gradients
and bounded-iteration BFGS with Armijo line search. It returns no model on failed
convergence. Parameters are immutable fingerprinted JSON, never pickle.
The four-cell correction and parameter feasibility follow the published formulation:
[Michels, Ötting and Karlis, section 2.1](https://arxiv.org/pdf/2307.02139)
and [Dixon and Coles (1997)](https://doi.org/10.1111/1467-9876.00065).
The score grid is internal; only the existing 11 legal 1X2/BTTS/totals markets are exposed.
The grid expands until omitted mass is <=1e-12, records its tail, and rejects
negative cells or excessive rates. No silent parameter clipping or probability fallback.

The same fitted goal rates with rho=0 provide a clearly labelled
POISSON_SAME_RATES ablation. This is not a separately fitted Poisson model.
Known neutral targets omit home advantage. All-neutral supplied training pins it
to zero. Cached API result rows have no trusted neutral flag: the adapter explicitly
assumes the provider's home/away designation. This is a research limitation,
particularly for neutral-site competitions, not new evidence of venue certainty.

## Prospective boundary

The committed plan is plan_20261003.json (declaration commit 3de240d).
Training goals must come from matches before 2026-10-02 00:00 UTC and must have
been observed by the original comparator capture time. Existing calendar
reservations and dynamically consumed holdout fixture IDs are excluded.
Results on/after the training cutoff cannot enter fitting. The research window
ends before the existing sealed holdout opens on 2026-10-19. The existing
calendar plan, its dates, counts and model policy are not modified.

Each forecast requires a natural current-odds capture after declaration,
a still-upcoming kickoff, current source/retrieval clocks, exact candidate,
quote and result-source fingerprints, and the same fixture/market references.
The CLI uses actual completion time; it offers no backdating switch.
A stale capture, missing team history, invalid reference or non-converged fit
is retained as unavailable, never substituted with a guessed prediction.

The source adapter reads at most the newest 500 de-vig records (64 MiB total),
with a five-second SQLite budget and short read-only connections. It uses only
the existing cache, supporting both list and response-envelope result payloads.
It does not acquire historical bookmaker odds or request any provider data.
It never constructs a write-capable production repository.

Existing de-vig first-capture sampling is retained. Thus older first captures,
missing model references, and the bounded intake can limit coverage. Counts are
reported. The initial sample is opportunistic, not a representative all-league
quality study. This change does not introduce a new capture hook or automatic job.

## Paired evaluation and persistence

For each fixture/family, choose the lowest numeric available bookmaker ID (then
name, with missing IDs last) before results are known. Compare Dixon–Coles,
the same-rate Poisson ablation, the existing ensemble and the already implemented
MULTIPLICATIVE/SHIN/POWER/OO_EPC methods on exactly matching markets. An
inapplicable method remains missing and a multiplicative fallback remains labelled.

The store freezes the first accepted forecast per plan/fixture/family. Later
calls cannot replace it or inflate the denominator. Metrics reproduce forecasts
from their immutable model/input records, join only existing SINGLE/canonical
results, reject conflicting labels, and distinguish pending and void matches.
COMBO legs do not become learning labels. Model registration, fitting and metrics
remain entirely outside the production adaptive audit database.

Reports contain paired and common-cohort Brier/log loss/reliability scores,
unique fixtures and dates, and league/market/family/odds/lead-time segments.
Complementary markets are correlated, not independent samples. They do not
implement a research bet-selection policy, so no research ROI is invented.
The public SINGLE 1.50 experiment retains its own actual publication statistics.
The initial quality verdict remains NEEDS_MORE_EVIDENCE; no automatic promotion.

The dedicated database rejects foreign schemas, production path aliases and
symlinks; its records have update/delete guards, integrity checks and immutable
conflict detection. Source databases always use mode=ro and query_only=ON.

## Manual commands

Run from the committed research worktree using the existing VPS virtualenv:

    cd /home/arvis/goalvision-worktrees/dixon-coles-research-20261003

Inspect inputs without creating a research database:

    /home/arvis/GoalVisionAI/.venv/bin/python -m app.dixon_coles_research readiness --shadow-database /home/arvis/GoalVisionAI/var/lab_v2/shadow.db --audit-database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db

Capture only qualifying still-upcoming comparisons into the separate research store:

    /home/arvis/GoalVisionAI/.venv/bin/python -m app.dixon_coles_research capture --shadow-database /home/arvis/GoalVisionAI/var/lab_v2/shadow.db --audit-database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db --research-database var/dixon_coles_forward.db --limit 12

Evaluate already stored forecasts using existing result facts:

    /home/arvis/GoalVisionAI/.venv/bin/python -m app.dixon_coles_research evaluate --shadow-database /home/arvis/GoalVisionAI/var/lab_v2/shadow.db --audit-database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db --ledger-database /home/arvis/GoalVisionAI/var/lab_combo/ledger.db --research-database var/dixon_coles_forward.db

Each CLI process lowers only its own CPU scheduling priority to nice >=10.
Systemd priorities and schedules are untouched. No command sends a message,
fetches provider data, starts a production cycle, or activates a model.
Installing an automatic research job remains a separate reviewed operator action.

## Evidence

See docs/research/DIXON_COLES_RESEARCH_20261003.md and
docs/evidence/dixon_coles_20261003/. Tests use controlled fixtures. The cached
result fit check uses genuine previously captured scores, which demonstrates
input compatibility and numerical convergence only, not predictive superiority.
