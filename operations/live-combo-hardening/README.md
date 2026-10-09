# LIVE / COMBO accuracy hardening: offline only

This development audit uses the existing immutable Lab repositories and closes
read transactions before expensive replay. It has no worker, timer, publisher,
provider, model activation or production configuration hook. No new dependency
is installed. Existing `combo_evidence`, `combo_research`, de-vig, Poisson and
settlement functions are reused.

## Scope and missing-data behavior

- `app/live_lab/context_research.py`: zero-card venue/competition Poisson
  ablation, using the existing minimum history requirement. Uses frozen
  pre-kickoff results, actual score/minute/events and venue-specific observed
  attack/defence. Validates clocks, score/event agreement and dismissal counts.
  Filters future/current fixtures out of the history response. It refuses
  card-affected inference without an estimated effect, missing venue samples,
  unsupported goal semantics and unmodelled remaining stoppage time. It does not
  invent xG, shots, an opponent-strength regression or a card multiplier.
- `app/live_lab/policy_research.py`: A = installed inclusive 60–70% band,
  probability ranking and diagnostic EV. B adds positive raw EV, positive
  multiplicative fair edge and the existing divergence bound applied to a
  complete simultaneous market. C remains a no-pick evidence screen because
  no reviewed LIVE calibrator or context-effects evidence exists. PREMATCH
  calibration must not be applied to the different LIVE model.
- `app/adaptive_lab/joint_scenarios.py`: exact finite joint-score integration
  from a separately pinned, as-of research artifact. No fitted artifact or
  correlation coefficient is supplied. Rational mass summation avoids Decimal
  rounding away an invalid total. A supplied scenario estimate is unvalidated,
  not proof of positive EV and never production eligible. Cross-fixture Poisson
  marginals do not define a joint dependency model; a risk flag is not one either.
- The existing COMBO A/B selectors and C evidence screen remain the source of
  truth. The only edit to their offline adapter materializes immutable records
  before CPU computation, fixing a reproduced SQLite progress-deadline failure.

LIVE retained rows lack exact initial/final-refresh phase tags. The comparator
therefore evaluates original snapshot pools, **not** a counterfactual natural
cycle or executable bet sequence. A nomination is not publication. Alternative
final quotes are unavailable; no retrospective replacement or fabricated
receipt is allowed. Outcome attachment happens after inference and selection.
Different nominee populations do not yield a paired strategy score delta.

These are development replays, not pre-registered prospective results. Thresholds
and model parameters must not be tuned on these outcomes or a sealed holdout.

## Reproduce

From the reviewed worktree, using the existing virtualenv:

```bash
/home/arvis/GoalVisionAI/.venv/bin/python -B operations/live-combo-hardening/audit.py \
  --database /home/arvis/GoalVisionAI/var/adaptive_lab/audit.db \
  --ledger /home/arvis/GoalVisionAI/var/lab_combo/ledger.db \
  --since 2026-10-07T00:00:00+00:00 \
  --until 2026-10-09T10:15:18.755867+00:00 \
  --output /tmp/goalvision-hardening-reproduction.json

/home/arvis/GoalVisionAI/.venv/bin/python -B operations/live-combo-research/offline_tests.py \
  tests/adaptive_lab/test_accuracy_hardening.py
```

Output is immutable: rerunning the same cutoff accepts identical bytes and
rejects a different report at the same path. The audit entry point denies
outbound sockets. Tests replace provider/Telegram transports with existing
fakes; the harness denies outbound connections before test imports. Production
SQLite inputs use read-only/query-only connections.

Do not deploy these modules or add an automatic capture job. Genuine new-policy
LIVE results must come from the already enabled natural timer. Further passive
HTTP/phase telemetry wiring requires a separate reviewed operator release.
Calibration remains blocked until both the existing independent-fixture minimum
and the frozen calendar close are satisfied. No COMBO coupon becomes a PREMATCH
learning observation.
