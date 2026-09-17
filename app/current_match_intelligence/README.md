# Current Match Intelligence

This package enriches one already-filtered upcoming fixture with immutable,
field-provenanced API-Football context. It is deliberately separate from the
live-78 champion contract: new fields are stored under
`goalvision-current-match-intelligence-features-v1` and are not sent to the
current model.

The collector is explicit and inert until invoked. It never publishes, runs
inference, changes bankroll/statistics, or schedules itself. Discovery should
first select its strongest surviving fixture and then call this service. The
existing API-Football request counter is tightened to at most 40 calls for the
whole run. Required enrichment is pre-planned; optional prior-match statistics
and lineups stop when the remaining allowance is exhausted.
`enrich_discovery_result()` is the explicit discovery handoff and preserves
the discovery order while enriching at most one fixture by default.

Use the one-fixture diagnostic without running it as a rehearsal here:

```bash
python -m app.current_match_intelligence collect \
  --fixture-id FIXTURE_ID --database var/lab.db --max-api-calls 40 --output human
```

An existing snapshot can be inspected without network access:

```bash
python -m app.current_match_intelligence inspect \
  --snapshot-id SNAPSHOT_ID --database var/lab.db --output json
```

`RealMatchLabIntelligenceBridge.context_for_analysis()` resolves the latest
snapshot at or before the analysis cutoff. It returns the immutable snapshot
identity and the future feature vector while explicitly reporting
`live_78_consumption=NOT_CONNECTED`.
