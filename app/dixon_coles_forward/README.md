# Prospective constrained model and COMBO shadow

Plan declared in 8b51f67 before implementation. Model/artifact and dedicated state are separate from the installed V1 cohort and development-only artifacts. Pure numerical routines and clock/source/metric/scheduler guards are reused through explicit dependency injection. Original public APIs retain their defaults.

The operator package installs only goalvision-dixon-coles-forward.timer/service, at :12:30/:42:30 Riga. The worker checks all four production services and original V1 research are idle, uses a nonblocking lock, 45-second whole-cycle deadline and dedicated append-only storage capped at 512 MiB. The service is network isolated, CPU 25%, nice 10, memory 256 MiB; late starts do not catch up. No provider/Telegram configuration is loaded.

New captures must follow the pinned declaration, precede kickoff, remain fresh and respect frozen training/holdout boundaries. Known development fixtures 1498855, 1602097 and 1641278 are excluded. Original DC is freshly fitted on the same inputs; its failures remain explicit and do not remove successful constrained-model forecasts. Paired/common probability metrics report coverage. No artifact import or development backfill.

COMBO compares ensemble-first versus minimum-of-DC/ensemble/multiplicative-de-vig ranking on the same covered candidate pool. The minimum is a ranking score, not a calibrated probability or confidence interval. Three distinct fixtures/six teams, per-leg odds >=1.30, no additional combined floor, existing accuracy review and Riga today-only are required. Both policies have disjoint batches; the union of prior selections excludes reused fixtures and same-day teams. First prospective family forecasts only: this is a restricted shadow comparison, not a replay of all actual publications. Current candidate odds are retained for hypothetical accounting; bookmaker probabilities come from the prospectively fixed reference bookmaker in the paired forecast.

Selections and both policies are frozen before outcomes. Result readers use existing SINGLE/canonical football facts, never COMBO leg outcomes as independent labels. Separate hypothetical one-unit metrics retain pending, early loss, remaining legs, win and partial/full voids. Full forecast and batch reconstruction precedes evaluation. No claims, receipts, public messages, bankroll or champion updates are created.

Runbook: docs/operations/DIXON_COLES_FORWARD_COMBO_20261003.md.
