# Current-data prediction-quality options — 2026-10-03

Scope: requested GitHub/forum research alongside the authorized SINGLE 1.50 test.
This is a source review and proposed next experiment, not a production model
change. No external package was installed or source code copied. No historical
bookmaker odds were downloaded or requested.

## Recommendation

Start with one independent Dixon–Coles goal-model challenger on our existing
chronological match-result inputs. Compare its goal-derived totals/BTTS/1X2
probabilities against the current model and the already implemented current-odds
de-vig comparator on identical future fixtures. This is a proposed research
experiment, not evidence that the challenger will improve GoalVision.

Our source review found no Dixon–Coles, bivariate-Poisson, Glicko or hierarchical
Bayesian implementation in app/. The active adaptive registry currently offers
LOGISTIC, REGULARIZED_LOGISTIC, STUMP_ENSEMBLE and CALIBRATED_ENSEMBLE. Existing
Poisson/history foundations do not by themselves establish the additional
low-score dependence or uncertainty models discussed below.

## Maintained reusable implementation: penaltyblog

[Repository](https://github.com/martineastwood/penaltyblog)
[Model documentation](https://penaltyblog.readthedocs.io/en/latest/models/overview.html)
[Release history](https://github.com/martineastwood/penaltyblog/releases)
[License](https://github.com/martineastwood/penaltyblog/blob/master/LICENCE)

The project has an MIT license and implementations of Dixon–Coles, bivariate
Poisson and hierarchical Bayesian goal models. Its documented score grid derives
consistent totals, BTTS and match-outcome probabilities. Dixon–Coles adjusts
low-score dependence; the hierarchical model estimates league-level priors and
parameter uncertainty. These are implementation capabilities, not demonstrated
GoalVision performance gains. Its August 21, 2026 v1.12.0 release reduces Bayesian
memory/serialization overhead and exposes parallel-chain controls; a v1.13.0
release is also listed for October 1. The newest scraper feature is not needed
for our model experiment.

Proposed order:
1. Dixon–Coles first: comparatively small new model family using results already
   available before each forecast. Keep the same legal markets; a score grid is
   an internal representation, not permission to publish correct-score bets.
2. Add a bivariate alternative only if held-out diagnostics show relevant
   dependence that the first challenger misses.
3. Consider hierarchical uncertainty after the simpler comparison, especially
   for sparse competition/team samples. Measure resource cost and convergence;
   do not turn uncertainty into an unreviewed live exclusion threshold.

Before any integration, pin and review the exact dependency/source version.
GoalVision's artifact boundary requires deterministic, audited JSON/provenance,
not untrusted pickled external model files. Benchmark outside timer processes.
No automatic installation, training, promotion or new source scraping is
authorized by this review.

## Confirmed starting-XI model: useful design, non-reusable repository

[footymodel](https://github.com/tanamsethi31/footymodel) distinguishes team-level
forecasts from a player attack/defence model using confirmed starting lineups.
Its author reports stronger goal forecasts in their own tests, while also
reporting negative results for other approaches. These are author-reported
results, not independently reproduced evidence.

The repository explicitly reserves all rights and grants no copying/modification
license. Do not vendor or copy it. Its historical-odds and scraping pipelines
also do not match this project's approved scope.

The transferable research question is narrower: does a separately designed
confirmed-XI attack/defence adjustment add information to our current forecast?
We already have usage-weighted injuries/absence signals and opponent-adjusted
form in context_signals.py, wired into runner.py and audit.py. Rebuilding those
would repeat completed work. A genuine extension would require verified
pre-kickoff XI/player coverage and an independently evaluated player model.
Missing lineups must remain missing, and the experiment must not narrow all
production discovery to big leagues or delay every existing publication.

## Forum findings: hypotheses, not authority

[Recent r/algobetting discussion](https://www.reddit.com/r/algobetting/comments/1voeo3v/college_student_building_soccer_betting_model/)
describes a developer whose out-of-sample improvement over simple baselines did
not produce a reliable advantage over market probabilities. Participants suggest
timing, extra lineup information, market consistency and league-level evaluation.
The author explicitly distinguishes uncertain quote timestamps from verified
closing prices. This is useful first-hand discussion, not independently checked
proof or a source for selecting GoalVision thresholds.

We will not adopt claimed hit rates/ROI, arbitrary forum filters, undocumented
closing-price labels, new staking rules, historical-odds acquisition or automatic
bet execution. The existing captured current-odds evidence already provides the
appropriate forward comparison mechanism.

## Concrete proposed evaluation

- Keep the running SINGLE 1.50 publication experiment separate from model-quality
  research. Its before/after results are descriptive, not a randomized causal test.
- Prospectively declare challenger inputs/version and evaluation dates. Preserve
  the current frozen calibration plan and all reserved/consumed holdout fixtures.
- Use only completed football results available before each model input and
  timestamped current odds captured during natural operation. No retrospective
  bookmaker-odds source is needed.
- Compare exactly paired future fixtures/markets against champion, simple
  baseline and de-vig comparator. Report excluded/missing coverage, league,
  market, odds bands, kickoff distance and independent fixture/day sample counts.
- Use probability scores and calibration alongside full W/L/VOID/pending counts,
  selection volume and flat-unit results. Do not retune on the evaluation sample
  or declare success from a short winning streak.
- First review can reject the challenger. Any selection or champion change still
  needs separate evidence and explicit operator approval.

Already present and not proposed again: de-vig research, calibration readiness,
league/context segmentation, Pi ratings, opponent-adjusted recent form, weighted
player-availability signals, chronological partitions, retained claims/results,
COMBO separation and Telegram Reply settlements.
