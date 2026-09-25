# PREMATCH adaptive shadow audit and hardening

Base: `50a73ced91110bc2fa6f216c565ce7d846fb2d0d`. Isolated development worktree;
no production DB access, external requests, Telegram or service changes.

## Audit recorded before implementation

Reviewed CLI filtering and `_leg()`, `LearningCoordinator.shadow()`, `opportunity()`,
canonical repository transactions/fingerprint checks/immutability, `Governance.observe()`,
quote freshness, model numeric contracts, canonical settlement linkage and existing
adaptive/Lab V2 tests. The prior incident report is
`/home/arvis/GoalVisionAI/SHADOW_CHRONOLOGY_DIAGNOSTIC_2026-09-23.md`.

Confirmed defects:

1. Incoming future kickoff passes validation, then canonical substitution replays an
   expired kickoff. Fixture `1612047:DRAW` had incoming kickoff 2026-09-23 20:00 UTC,
   frozen kickoff 18:00, frozen preparation 17:35:50.099876 and shadow observation
   18:35:54.526834. Governance correctly raises, aborting later candidates. Exactly
   one of 215 inputs in the diagnosed cycle had this defect; this is not a claim
   about all historical expired records. Provider date and Unix timestamp both
   changed by two hours; actual rescheduling versus provider correction is unknown.
2. Additional code-confirmed defect: supplied future `prepared_at_utc` is overwritten
   with observation `now` when first freezing a canonical record. On replay it is
   replaced by the older canonical preparation. Neither path validates the incoming
   preparation before substitution, so an integrity error can be hidden. No claim
   that this occurred in the production incident.

Other audited behavior and limits:

- `50a73ce` rejects None/nonfinite/closed-boundary baseline probabilities before
  adaptive replay; leave this fix unchanged. Approved shadow inputs use stricter
  numeric contracts: malformed/nonfinite values raise `INVALID_NUMBER`; do not
  reinterpret these integrity failures as recoverable batch conditions. Finite
  out-of-range probabilities, odds <= 1 and nonpositive EV already skip incoming
  shadow selection. No new numeric policy is needed.
- Current incoming quotes require origin <= retrieval <= now and existing age
  limits. Missing/stale/future quotes are already non-actionable. Old canonical
  quotes intentionally retain historical evidence and must not be refreshed or
  re-keyed on replay. A kickoff revision with both kickoffs still future retains
  the original opportunity; a past incoming kickoff is rejected before replay.
- Canonical identity is fixture:market; only the PREMATCH path writes it. Lookup
  verifies the document fingerprint. Transactions serialize first creation and
  append guards reject conflicting replay; database triggers forbid mutation.
  Opportunity identity includes original candidate and quote/probability evidence;
  shadow identity additionally includes the shadow run. Duplicate valid replay is
  idempotent. No reachable additional identity defect was found in this path.
- `opportunity()` deliberately projects pre-outcome evidence, copies preparation
  into prediction creation, and validates numeric feature inputs. Governance
  checks chronology before model resolution and shadow insertion. Exceptions from
  fingerprint, feature, model and governance checks must propagate. An expired
  record is not permission to hide future preparation or repository corruption.
- No publication, odds, quota, LIVE, Official or betting-policy changes are needed.

## Implementation contract

Only `LearningCoordinator.shadow()` and a small diagnostic helper change runtime
behavior, confined to PREMATCH. Reject future incoming preparation before selection
or canonical creation. After canonical lookup, reject future frozen preparation
before checking expiry. Skip canonical kickoff <= now, appending structured evidence
to the existing `linkage_diagnostics` table. Include original/incoming identities,
both kickoffs, preparation and observation time. Deterministic diagnostic identity
deduplicates the same attempted observation; later attempts remain separate evidence.

Keep governance unchanged; no broad exception handling, canonical mutation, re-key,
probability clamping or backdating. Preserve existing first-observation timestamp
semantics for newly created canonical records only after validating source time.
The only new continuation is the explicit expired-canonical case. Diagnostic write
failures also propagate rather than silently losing evidence.

## Verification

Focused synthetic regression and integration tests cover the incident, continuation,
equality/expiry, incoming/frozen future preparation, unchanged valid replay and
canonical fingerprints, direct governance chronology, numeric/quote gates,
unrelated errors and corruption. Existing baseline-probability tests remain intact.
Results are recorded after execution below. This changes orchestration, not a
prediction algorithm; deterministic incident replay replaces any need for new
model training or predictive backtesting. No full suite or production rehearsal
is authorized in this task.

### Executed results

- Before runtime edits, four new regression cases failed on `50a73ce`: expired
  canonical kickoff equal to/before now raised, and future incoming preparation
  was accepted on both first capture and replay. This confirms both runtime defects.
- After runtime edits: new chronology tests plus unchanged probability-hotfix
  tests: **39 passed**. After refining the incident's historical quote timestamps,
  the final chronology file alone: **28 passed**.
- Combined focused run (`tests/adaptive_lab` plus the five Lab V2 files below):
  **628 passed, 1 failed**, including **379 passing adaptive tests**. The failure
  was an existing test's string-based self-import after changing directory, not
  an application failure.
- Repeating the Lab V2 subset with an absolute import path exposed existing
  wall-clock dependence in two fake-publication tests when their generated
  kickoff crossed the publication window. Fixed tests only: use an advancing,
  deterministic daytime clock in `_install_controlled_cycle_fakes()` and patch
  the loaded module's globals instead of importing a second module by string.
  This does not change any production publication policy or implementation.
- Final Lab V2 subset: **250 passed in 37.94 seconds**. Together with the passing
  adaptive subset, all **629 focused cases** are covered successfully. The full
  repository suite was not run. The runtime patch did not change after the
  successful adaptive run.

Lab V2 subset:

```text
tests/test_lab_v2_shadow.py
tests/test_lab_v2_prematch.py
tests/test_lab_v2_hardening.py
tests/test_lab_v2_global.py
tests/test_lab_v2_throughput.py
```

The combined and Lab V2 runs used the existing Python environment with
`PYTHONDONTWRITEBYTECODE=1`, the isolated checkout as working directory, and
in-process socket `connect`, `connect_ex` and `create_connection` blockers before
invoking pytest. Provider/Telegram cases use fake clients/transports; no external
requests or real sends occurred. SQLite fixtures use temporary databases.
`git diff --check` passes. Governance, numeric contracts and the baseline replay
hotfix/tests remain unchanged. No production database, configuration, timer or
service was accessed by the implementation or tests.

## Operational recommendation

Perform a separately authorized PREMATCH no-send rehearsal before restarting the
discovery timer. Check skip diagnostics, no shadow insert for expired canonical
evidence, later-candidate progress and unchanged canonical identities/fingerprints.
No-send alone does not mean read-only or offline: the normal cycle can call the
provider and write audit evidence, so use isolated copies/offline inputs first and
explicit authorization before any production rehearsal.
