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

`RiskAssessmentPhase.PRE_PUBLICATION_GATE` is the explicit phase used by
Official candidate preparation. It requires a missing gate status and preserves
the existing deterministic bankroll, exposure, drawdown, loss-streak, and stake
rules without pretending approval has occurred. The historical/default
`POST_PUBLICATION_GATE` phase retains the prior behavior: a missing or review
gate status produces `REVIEW_REQUIRED`.

Candidate preparation supplies immutable Official EUR bankroll/exposure facts,
calls this service exactly once, and validates the returned identity, phase,
policy, snapshots, decision, and exact 1%-3% recommendation. It never copies
stake calculation. `REVIEW_REQUIRED` and `INELIGIBLE` are persisted as valid
no-registration outcomes; only `ELIGIBLE` and `REDUCED_STAKE` can reach the
Candidate Registry.

Historical backtesting pins `official-risk-v1` and its conservative 1%,
standard 2%, and maximum 3% bands against an isolated supplied EUR bankroll.
It adds only an explicit deterministic equal-kickoff batch exposure cap; every
simultaneous selection sees the same pre-group balance. There is no martingale,
loss recovery, borrowing, negative bankroll, or mutation of a real account.
