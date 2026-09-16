# Lab Combo workflow

The Lab-only `app.lab_combo` command composes current fixture discovery, Real
Match Lab analysis, sealed odds, reasoning, governance and the existing single
publication review. Nothing is wired into application startup or Official.
The existing run coordinator is explicitly Official-scoped; its bankroll and
publication contracts are inappropriate here. These bounded commands reuse the
Lab services, with one process lock and optional systemd timers, not a new scheduler.

Discovery now checks fixture/capability eligibility, then supported bookmaker
odds and freshness, then team histories. The existing context-keyed history cache
is shared across all candidates, including successful ones. Default discovery
still returns one fixture; `maximum_fixtures` enables a bounded collection.
The reviewed 50-candidate / 40-call limits, full candidate cost reservation,
15-minute odds checks and minimum 20-call daily reserve remain intact. The real
client enforces the request ceiling and reserve before retries too. Historical
rehearsal documents describing the former history-first ordering remain unchanged.

Each leg must be the selected actionable single, pass the complete existing Lab
publication review (including reasoning and governance), have no single-market
rejection, and retain its captured quote. Provider-origin freshness is rechecked
at combination and delivery. There is no hard minimum decimal-odds floor for a
leg. No quality threshold or model activation is changed.
Exactly three legs are required, from different fixtures, teams and competitions,
and the same captured bookmaker. The competition restriction conservatively
avoids shared standings context; it is not a claim of statistical independence.
There is no hard minimum combined-odds floor; the experimental 3.50 upper safety
limit remains. Ranking maximizes the weakest leg's probability, then summed
value, with immutable IDs breaking ties. It does not maximize combined odds.
This is an experimental selection rule, not a validated profitability claim.

`var/lab_combo/analysis.db` is an explicit copy of the selected Lab model database.
The independent `ledger.db` contains append-only predictions, leg results,
settlements, previews, claims, receipts and run diagnostics, with hashes and
UPDATE/DELETE guards. There is no Official bankroll or statistics write. Combo
statistics use hypothetical fixed one-unit stakes, include losses and voids,
and distinguish published combinations from all prepared experimental records.
Prepared fixtures are not reused in another combo.

## Commands

From `/home/arvis/GoalVisionAI`, initialize once using an existing approved Lab
model database (the source is opened read-only and backed up with SQLite):

```sh
.venv/bin/python -m app.lab_combo initialize --source-database var/real_match_lab/freshness_policy_20260731/goalvision_lab_policy_review.db
.venv/bin/python -m app.lab_combo discover
.venv/bin/python -m app.lab_combo discover --send
.venv/bin/python -m app.lab_combo settle
.venv/bin/python -m app.lab_combo settle --send
```

Choose one discovery command per intended run; do not execute both to force a
selection. `--send` is explicit Lab-only authorization and permits at most one
purposeful message per invocation. No combo means no Telegram connectivity test.
Existing credentials are loaded without editing `.env`; destination and actual
bot username are checked. Imports are inert. JSON output and immutable run
records report calls, discovery skips, individual review blockers and delivery.

Settlement reuses the existing single-market win rules and fixture cancellation
policy. FT/AET/PEN use `score.fulltime`, never extra-time or shootout goals.
Cancelled and abandoned fixtures become VOID; postponed/missing/malformed results
stay unresolved. All legs must resolve before final settlement. Any loss means
LOST; all void means VOID; otherwise WON with a partial-void flag where relevant.
Voided legs contribute 1.00 to effective odds. Each bounded sweep uses at most
20 result calls (plus one quota refresh), caches fixture responses and prepares
notifications automatically. Empty queues make no provider call. Later sweeps
recover a missing preview after a crash. Already resolved legs are never fetched
again or overwritten.

Telegram delivery claims are durable before sending. A timeout, wrong receipt or
crash after claiming is ambiguous: it is never automatically retried. Inspect
Lab and reconcile the immutable claim/receipt evidence manually; never delete a
claim or historical loss. This provides at-most-once attempts, not an impossible
exactly-once guarantee across Telegram and SQLite. Pending unclaimed predictions
are reviewed again before delivery; expired odds remain blocked. Per-ledger
process locking prevents overlapping timer executions on the VPS.

## Continuous VPS operation — separate deployment

The timers are prepared but **not installed or enabled** by this task. They use
user `arvis`, this workspace and `.venv/bin/python`; discovery runs at 10:00 UTC
daily, result checks every fifteen minutes. Verify the initialized Lab copy has
current approved model/calibration/governance evidence; a stale source copy will
correctly produce no selections. Source refresh/approval remains an operator
model-governance operation, never automatic model activation.

After review, the exact installation commands are:

```sh
sudo install -m 0644 app/lab_combo/systemd/goalvision-lab-combo-* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now goalvision-lab-combo-discover.timer goalvision-lab-combo-settle.timer
```

The service stdout is suppressed because full sanitized run evidence is already
stored immutably in the Lab ledger. Inspect with a read-only SQLite connection,
for example `SELECT document FROM evidence WHERE kind='run' ORDER BY identity DESC
LIMIT 1`. An invalid config or ambiguous delivery requires operator attention;
neither triggers unbounded retries. No production service is installed by the CLI.

## Validation

Focused tests cover rejected stale/unavailable odds without history requests,
shared-budget multiple-fixture collection, deterministic permutations,
correlation/target exclusions, the unmodified existing single-publication review,
immutable replay/concurrent claims, Lab destination locks, ambiguous delivery,
provider reserve enforcement on retry, result recovery and all 27 three-leg
WON/LOST/VOID outcome combinations. This controlled replay validates mechanics;
it is not a historical profitability backtest or permission for production activation.

The single genuine task rehearsal consumed 22 API calls and stopped on
`FootballQuotaError`, before analysis or publication. The initial top-level
handler did not retain the quota subcode or partial discovery counters; those
counts are explicitly unknown in the evidence artifact, not zero. The final
follow-up preserves partial traces, per-request costs, quota state and typed
termination on an interrupted discovery. That fix was tested offline; neither
real discovery nor the full suite was repeated. Full-suite result before that
final diagnostic hardening: 1,529 passed and 563 subtests passed. Final focused
result: 76 passed and 8 subtests passed. A later scheduled bounded execution will
provide current quota evidence; do not loosen reserve or freshness gates to force
success. Treat continuous publication readiness as unproven until that execution
completes with adequate quota and all individual quality gates satisfied.

## Integrity failure diagnosis and replay fix (2026-09-13)

A read-only SQLite backup of the existing analysis database into memory reproduced
the latest persisted failure without provider calls. The failed runs had already
persisted all 21 accumulated analyses and observations. The failing statement was
`INSERT INTO forward_test_governance_scope_statuses VALUES (?,?,?,?,?,?,?,?)`,
raising `NOT NULL constraint failed: forward_test_governance_scope_statuses.scope_value`.
It was not a market-evaluation UNIQUE failure. Governance projected explicit null
model/calibration IDs from blocked observations with `dict.get(key, "UNKNOWN")`;
that default only handles absent keys. These null IDs are legitimate immutable
evidence of an analysis that did not reach calibration.

Governance now maps absent/null artifact identities to its existing `UNKNOWN`
category consistently in collection and publication/snapshot lookups. Source
observations retain their nulls, fingerprints and rejection reasons. No schema,
UNIQUE/FK/NOT NULL constraint, threshold or historical record is changed. A failed
legacy projection rolls back atomically; corrected evaluation, exact replay,
subsequent cutoff and reproduction succeed. The existing persisted-data replay
retains `GOVERNANCE_SAMPLE_INSUFFICIENT` and blocks publication.

The separate Real Match Lab evaluation identity fix is retained: analysis ID,
deterministic order and evaluation content identify an analysis-owned row. Two
analyses may legitimately have identical evaluation content. Exact replay and
immutable old rows are retained, without a migration or evidence rewrite.

The 0.5-second request-start pacing is retained. Request-slot reservation and
capacity checks now happen within its lock, with capacity rechecked after waiting,
so concurrent callers cannot bypass the total request ceiling. Retries use the
same paced reservation. Existing provider-origin/retrieval freshness work is
preserved; see `API_FOOTBALL_PREMATCH_FRESHNESS.md`.

Terminal diagnostics retain an application stage and allowlisted SQLite constraint
code. Only the exact known schema failure above is retained as message text;
arbitrary exception/trigger/provider/Telegram text is not copied into that field.
Offline regressions cover the actual NOT NULL failure, rollback, corrected replay,
immutable observations, repeated evaluation content, concurrent pacing and secret
redaction. This is a persistence/transport repair, not a prediction algorithm change.

The former `CALIBRATION_REVIEW_MISSING` wiring defect is repaired without using
the runtime checkout's `HEAD`. Before analyzing any selected fixture, the Lab
Combo path resolves the active champion and verifies its exact model and
calibration artifacts. It then matches that immutable artifact pair and activation
generation to the allowlisted, fingerprint-verified recent-calibration review
evidence and propagates that evidence document's full `source_commit` into the
sealed Real Match Lab input.
The analysis engine independently resolves the same review, rejects a missing or
mismatched input commit, and asks `ModelActivationAuditService` to verify the
commit against that reviewed artifact before calculating the audit fingerprint.
Missing, ambiguous, altered, or mismatched evidence fails closed.

The remaining verification is one separately authorized bounded Lab Combo
discovery rehearsal through the existing activation/calibration, reasoning, and
governance gates. Do not repeat that real API rehearsal, send Telegram, weaken a
gate, modify Official state, or enable timers as part of the source-provenance
repair itself.

Focused provenance regression result: **93 passed, 5 subtests passed**. Earlier
persistence/transport repair validation: **157 passed, 13 subtests passed**;
the full suite ran once, **1,553 passed, 563 subtests passed** (444.75 seconds).
The single real `.venv/bin/python -m app.lab_combo discover` rehearsal on
2026-09-13 consumed **38 API calls**, found **5 fresh-odds candidates**, and
reported `ELIGIBLE_CURRENT_FIXTURE_FOUND` with **no terminal error**. All five
analyses were immutably rejected with `CALIBRATION_REVIEW_MISSING`; governance
persisted successfully, eligible singles were **0**, and the combo blocker was
`FEWER_THAN_THREE_ELIGIBLE_SINGLES`. Combo **NO**, Lab send **NO**. The database
foreign-key check returned no violations. The complete run remains in the local
append-only ledger, with stdout at
`var/lab_combo/integrity_rehearsal_20260913.json`. No second real discovery,
timer enablement, model activation or historical-evidence edit was performed.
