# Risk Management Boundary

Risk management remains downstream of deterministic Official market selection.
The selection engine does not call the risk service, calculate a stake, inspect
bankroll or exposure, or imply approval. A successful immutable
`SelectedOfficialPrediction` can be transformed with
`to_official_risk_handoff(...)` into a read-only payload containing the decision
and assessment IDs, market/bookmaker identity, fair probability, odds, implied
probability, edge, EV, freshness, and full model/calibration fingerprints.

That handoff deliberately contains no stake. A future integration may adapt it
into the risk engine's explicit request only after supplying the remaining
bankroll and exposure context required by the existing risk policy. A
no-selection decision cannot cross the handoff. Candidate registration,
Quality Gate execution, scheduling, publication, and the future two-leg
exception-combo workflow remain separate and are not triggered by selection.
