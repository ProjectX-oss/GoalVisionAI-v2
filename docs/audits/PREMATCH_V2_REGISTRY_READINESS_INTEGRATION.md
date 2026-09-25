# Regulation registry → TEST/Lab readiness

Decision: **TEST_LAB_REGISTRY_INTEGRATION_VERIFIED**.
Genuine renewed UCL proof: **READY**, subject to the local admission interval below.
This is observation-only integration, not a real prospective football observation.

## Checkout and boundary

Start: clean `/tmp/goalvision-regulation-evidence`, HEAD
`87f9f249a594f5cf24d1e36a05f2c76ad914048b`.
Inspected `git status --short`, `git rev-parse HEAD`, `git worktree list` and the
requested branch before creating anything. Created a new isolated worktree at
`/tmp/goalvision-registry-readiness-integration`, branch
`codex/prematch-v2-registry-readiness-integration`, directly from that base.
No existing worktree was overwritten. Final checkout is that same isolated path.
The final delivery SHA is supplied with this report in the delivery response;
the report's own containing commit is resolved without a self-referential hash by:

```sh
git -C /tmp/goalvision-registry-readiness-integration log -1 --format=%H -- docs/audits/PREMATCH_V2_REGISTRY_READINESS_INTEGRATION.md
```

One focused commit. Changed files:

- `app/prematch_football_context/readiness/__main__.py`: cycle-only optional
  `--regulation-registry`; hardcoded `send=False` remains, with no send flag.
- `readiness/composition.py`: acquire once per explicitly enabled TEST/LAB run;
  associate exact receipts; resolve and retain through optional observer hooks.
- `readiness/regulations.py`: small immutable inventory, resolution/retention and
  offline verification using the existing registry contracts/evaluator/bridge.
- `readiness/ledger.py`: five additional event kinds in its existing append-only
  table; no schema migration, new database or general provenance framework.
- `readiness/report.py`: require retained proof verification before counting
  registry-backed reproduction as VERIFIED.
- `snapshot/observer.py`: optional binding resolver and pre-append retention hook.
  Existing assembly, target checks and reproduction remain authoritative.
- `tests/test_prematch_registry_readiness.py` and the existing readiness cycle
  parity test: focused integration cases and genuine-review/synthetic-football E2E.
- `docs/rehearsals/ucl_2026_regulation_renewed/{ifab,uefa,source_review}.json`
  and this report.

No change to registry semantics, snapshot contracts/serialization, Phase A
formulas, V1 fields, production constructors, environment defaults or schedulers.
With the flag absent, no registry is opened or created. Optional failures do not
return prediction inputs or change PREMATCH output.

## Decision-time possession and retained proof

Acquisition opens an **existing** registry read-only with a bounded SQLite wait.
One read transaction verifies schema, SQLite integrity, every canonical record
and its fingerprint. The complete inventory is frozen in memory and retained as
a content-addressed `REGISTRY_VIEW`. A separate `REGISTRY_ACQUISITION` retains its
identity, run, exact local path, method, actual UTC acquisition start/completion,
and the injected decision-clock reading. The connection is closed before any
Phase C decision is requested. Acquisition or persistence failure leaves the
ordinary unverified path with `REGISTRY_VIEW_UNAVAILABLE`.

`prepare()` still supplies classification and existing query scopes only. After
the actual persisted DecisionReceipt is obtained, a durable `REGISTRY_DECISION`
associates that receipt with the already acquired inventory. A backwards clock
relative to acquisition rejects this association. Snapshot assembly resolves
current and previous seasons independently at **that receipt's exact cutoff**,
using every applicable pinned record and the existing evaluator and bridge.
Review equality, expiry, incomplete incorporation and conflicts remain rejected.
A new cutoff rechecks applicability. Later imports, including records claiming
older review times, cannot enter this run. WAL concurrent-import testing confirms
one coherent inventory. An intentionally empty inventory remains unverified.

For each registry-backed format, `REGULATION_PROOF` contains the complete scoped
Resolution (including both reviewed records and incorporation edge), cutoff,
resolution fingerprint, resulting FormatEvidence and inventory identity. Identical
content deduplicates. `REGULATION_LINK`, keyed by exact snapshot ID, binds proof
IDs to acquisition, receipt, opportunity and current/previous roles. Proof and
link commits precede snapshot append. Interrupted view/acquisition/decision writes
fall back to unverified format; interrupted proof/link writes prevent the snapshot.
A snapshot append failure may leave harmless unused proof; it cannot leave a
verified snapshot missing its prerequisite proof.

Read-only report/verify checks ledger integrity, acquisition/receipt/opportunity
binding, complete retained inventory and record integrity, then independently
resolves all applicable records. It requires exact resolution, fingerprint and
bridge agreement before existing Phase D reproduction. It never reopens the
original registry or contacts the network. Missing/corrupt proof produces
`REGULATION_PROOF_UNAVAILABLE_OR_INVALID`, FAILED reproduction and blocked
readiness; its regulation is not counted as VERIFIED_90. Attempt denominators and
failed-run accounting are unchanged. Existing unverified snapshots need no new
proof and are never rewritten. A base-derived golden snapshot hash and canonical
byte hash verify compatibility; enabling a registry later leaves old stored
snapshot bytes unchanged.

## Renewed public review and local validity

Original artifacts and the accepted rehearsal report are unchanged, verified
against the base with `git diff --exit-code`. Their admission ends at
**2026-09-26T00:00:00Z**. Historical rehearsal replay uses its original recorded
cutoff; it is not a current prospective decision.

New reviews retain exact `API_FOOTBALL / competition_id=2 / season=2026` scope:

| Review | Actual review / interval start (UTC) | Exclusive local interval end (UTC) |
| --- | --- | --- |
| IFAB, new ID ending `RENEWED_113512967439` | 2026-09-25T11:35:12.967439Z | 2026-10-02T11:35:12.967232Z |
| UEFA, new ID ending `RENEWED_113512968503` | 2026-09-25T11:35:12.968503Z | 2026-10-02T11:35:12.967232Z |

The end is an **operator-controlled LOCAL TEST admission/re-review cap of at most
seven days**, not an official UEFA/IFAB expiry and not full-season trust. Review
must be strictly before decision. No backdating, extension of old records,
automatic renewal, competition expansion or season-2025 verification occurred.
At/after the cap, these records cannot verify a new decision.

The AI reviewer rechecked the authorized [API-Football public mapping guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide),
[UEFA incorporation](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-13-Competition-stages-Online),
[scope](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-1-Scope-of-application-Online?contentId=AWNVKC73_Ud10i2HCbMr4g),
[entry into force](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-96-Adoption-and-entry-into-force-Online?contentId=Xb72NoiAqwnadXykMvZmlA),
[suspended-match rules](https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/Article-28-Completion-of-suspended-matches-Online?contentId=JPk7Ltwo5tad5wvXjGvc~Q)
and [IFAB catalogue](https://www.theifab.com/laws-of-the-game-documents/).
The retained [edition-specific IFAB PDF](https://downloads.theifab.com/downloads/laws-of-the-game-202627-single-pages)
was reused after checking its 23,437,157-byte identity and SHA-256
`89398520b353c6d995a1bb2557c97dc3c5aa1712c1d3009589f580a5a23c6a7d`.
Printed pages 4, 20–21 and 93–94 were inspected through the retained extraction.
No new bulk download was needed. Public preparation used **9 web opens and 3
finds**, **0 new PDF downloads**, **0 football API calls**; underlying web-tool
HTTP/cache counts are not exposed. Per-request wall timestamps were not captured;
actual completed review timestamps above are recorded separately.

UEFA's new incorporation pins the exact new IFAB review ID and fingerprint.
Scheduled duration is supported; permitted reductions, added time, penalty
completion, abandonment and category modifications remain qualified. Selecting
IFAB 2026/27 remains a dated reviewer inference from its catalogue and effective
date, not an edition number stated by UEFA Article 13. No human personal review
or guarantee of actual match duration is asserted. AET/PEN still require explicit
regulation fulltime scores. Full reviewed records and provenance are in
[the new manifest](../rehearsals/ucl_2026_regulation_renewed/source_review.json).

Existing CLI initialization/import/verify succeeded with two records in a **new
disposable TEST registry**:
`/tmp/goalvision-renewed-ucl-test-wzdsz2bc/registry.sqlite`.
No operational registry was imported into or modified.

## End-to-end and parity results

The real readiness composition, FootballClient, PREMATCH cycle/runner/coordinator,
capture adapter, receipt, Phase A calculation and Phase D snapshot were exercised.
Only football transport/payloads and clock are synthetic. The genuine renewed
chain was imported using the existing CLI. Injected TEST cutoff:
**2026-09-25T12:35:12.968503Z**, inside both declared review intervals.

Result: **2 registry-backed UCL snapshots; 2 VERIFIED offline reproductions;
0 FAILED** after restart and original-registry removal. The sufficient-history
fixture provides 20 eligible synthetic current-season results: all four rates
and all three Pi/form fields are available under unchanged rules. A separate
sparse-opponent fixture provides four rates, leaves both forms null with
`UNSUPPORTED_PI_STATE`, and leaves Pi difference null with `INSUFFICIENT_SAMPLE`.
Previous-season source is absent; its format stays unverified. No history or TARGET
is manufactured. Missing TARGET still prevents snapshot creation. Competition 36
remains unverified; no existing real competition-36 store was opened for writing.

All nine UCL cycle modes have exactly equal PREMATCH output, canonical candidates,
V1 captured features, existing test champion state, request count and request
sequence: observation off, registry absent, valid registry, missing, corrupt,
locked, expired, conflicting, and proof-write failure. Each makes **10 fake
requests**, in this order:

1. `/status`
2. `/leagues?current=true`
3. `/odds/bookmakers`
4. `/fixtures?date=2026-09-25&timezone=UTC`
5. `/fixtures?id=7`
6. `/odds?fixture=7`
7. `/fixtures/lineups?fixture=7`
8. `/odds?date=2026-09-25&page=1`
9. `/fixtures?last=99&league=2&season=2026&status=FT`
10. `/predictions?fixture=7`

No additional TARGET, history or previous-season request. Existing near/far kickoff
parity cases also remain covered. Report/verify/diagnostics make zero network calls
and leave store bytes unchanged. Telegram construction is forbidden by the test;
Telegram sends and Official mutations are zero, LIVE has no champion or publication.
The existing test harness's disposable baseline bootstrap is unchanged; no
operational model is activated, trained, calibrated or promoted.

## Final focused verification

**722 passed, 0 failed in 177.23 seconds (2:57)** across the 14 listed files.
This includes **31 new focused integration cases** and the extended real-client
cycle test (three parameterizations, including the nine-mode UCL comparison).

Executed from the final worktree with `/home/arvis/GoalVisionAI/.venv/bin/python`:

```python
import socket, httpx, pytest

def forbidden(*args, **kwargs):
    raise AssertionError('REAL_NETWORK_FORBIDDEN_FINAL_FOCUSED_SUITE')
socket.socket.connect = forbidden
socket.create_connection = forbidden
httpx.HTTPTransport.handle_request = forbidden
httpx.AsyncHTTPTransport.handle_async_request = forbidden
raise SystemExit(pytest.main(['-q',
    'tests/test_prematch_registry_readiness.py',
    'tests/test_prematch_football_context_regulation_registry.py',
    'tests/test_prematch_football_context_incorporated_law.py',
    'tests/test_ucl_2026_regulation_rehearsal.py',
    'tests/test_prematch_football_context_regulation_evidence.py',
    'tests/test_prematch_football_context_readiness.py',
    'tests/test_prematch_football_context_readiness_hardening.py',
    'tests/test_prematch_football_context_snapshot.py',
    'tests/test_prematch_football_context_capture.py',
    'tests/test_prematch_football_context_sources.py',
    'tests/test_lab_v2_shadow.py',
    'tests/test_lab_v2_prematch.py',
    'tests/test_prematch_production_integration.py',
    'tests/adaptive_lab/test_prematch_autonomy.py',
]))
```

This is the final selection after the last implementation/test change. Earlier
development runs are not added to this count. `git diff --check` passed. No
unrelated historical/ML suite, operational training or predictive backtest was
run; prediction algorithms did not change. Offline replay/regression supplies the
relevant deterministic calculation verification.

## Later manual invocation — NOT executed against real APIs

Requires a separately authorized football cycle, an approved `FOOTBALL_API_KEY`
already supplied through the process environment/credential mechanism, the
existing Python environment, and the disposable reviewed registry still present.
Do not print/copy credentials or shell-source `.env`. Use a fresh isolated root.
Current time must be inside the reviewed interval for verification; after expiry,
fresh public review is required. No automatic renewal occurs.

```sh
cd /tmp/goalvision-registry-readiness-integration
readiness_root=$(mktemp -d /tmp/goalvision-registry-manual.XXXXXX)
/home/arvis/GoalVisionAI/.venv/bin/python -m app.prematch_football_context.readiness --root "$readiness_root" init
# Explicit observation command; internally send=False, no --send option exists.
/home/arvis/GoalVisionAI/.venv/bin/python -m app.prematch_football_context.readiness --root "$readiness_root" cycle --environment TEST --observe --regulation-registry /tmp/goalvision-renewed-ucl-test-wzdsz2bc/registry.sqlite --max-calls 40 --horizon-days 1
/home/arvis/GoalVisionAI/.venv/bin/python -m app.prematch_football_context.readiness --root "$readiness_root" verify
```

No real football API cycle, production database access/configuration change,
real readiness-store writes, `.env` modification, services/timers, deployment,
merge or push occurred. No model vectors, formula changes, nine-field V1
population, historical bookmaker odds, Phase E, Telegram sends or publication
changes. Official is unchanged; LIVE remains disabled.

TEST_LAB_REGISTRY_INTEGRATION_VERIFIED
