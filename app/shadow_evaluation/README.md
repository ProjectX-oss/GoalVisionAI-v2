# Shadow Evaluation Foundation

`app.shadow_evaluation` is a Lab-only deterministic evidence boundary. One
explicit champion and one explicitly promoted challenger consume the exact same
immutable pre-match feature vector and supplied odds. The champion remains
authoritative; challenger probabilities, value assessments, and its
hypothetical single selection are evidence only.

The service verifies comparison and recommendation fingerprints, the promoted
candidate, mandatory gates, model/calibration linkages, feature order and
provenance, strict pre-kickoff chronology, and supplied odds. Each persisted
model applies its own stored preprocessing and linked calibration exactly once.
Both outputs must satisfy the canonical 11-target result-simplex, complement,
monotonic-totals, finite-bounds, and no-correct-score contract.

Every supported Official market retains Decimal fair odds, implied probability,
edge, and `probability * odds - 1` EV. The active-odds, 1.60 odds-floor, and
0.02 EV-floor rules determine eligibility. Each role independently produces at
most one hypothetical single. Complete disagreement deltas, type, and severity
are retained.

Pre-match executions end at `PRE_MATCH_EVALUATED`. Settlement is a separate
explicit post-kickoff command using one immutable result source. It calculates
only hypothetical one-unit outcomes and never reads or mutates bankroll,
exposure, publication state, or Official statistics.

Migration v30 adds ten append-only tables for executions, shared inputs, both
inferences, every assessment, both selections, comparisons, settlements,
metrics, aggregates, and exclusions. Exact replay is idempotent; changed
content conflicts. Every table rejects updates and deletes.

Runtime observation is disabled by default. The optional isolation adapter
always returns the original champion candidate and converts shadow failures
into safe diagnostic evidence. It is not wired into startup or Official.

```text
backtest -> PROMOTE recommendation -> shadow evaluation -> shadow settlement
  -> rolling evidence -> controlled activation (separate approval; deferred)
```

`app.model_activation` can consume settled shadow rows only through an explicit
manual plan. Shadow evaluation itself never activates a model, and additional
shadow evidence invalidates an unexecuted plan until it is prepared again.

The manual `app.model_operations` CLI requires the operator to supply the exact
settled-shadow evidence fingerprint before plan preparation. Shadow evaluation
still cannot activate or roll back a champion and sends no Telegram messages.
