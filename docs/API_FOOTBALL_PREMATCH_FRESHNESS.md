# API-Football pre-match freshness and quota diagnostics

Scope: current odds discovery and Lab Combo quote revalidation only. Probability,
value, calibration, confidence, publication, and bankroll rules are unchanged.

Policy `api-football-prematch-3h-plus-30m-v1` accepts API-Football pre-match
provider snapshots up to **12,600 seconds (3 hours 30 minutes)** old. The provider
[documents a three-hour pre-match update cadence](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide).
The additional 30 minutes allows a bounded scheduling/propagation tolerance;
it is a local conservative choice, not a provider guarantee. This policy does
not apply to live odds or other sources. It does not prove the bookmaker's
price remains executable.

The `/odds` root `update` is the provider-origin snapshot time, not the
GoalVision capture time. GoalVision records the actual HTTP response retrieval
time, independent of discovery start. Both retrieval and capture must remain
within 900 seconds at validation. Missing, invalid, naive, future or inconsistent
provider timestamps fail closed; retrieval cannot replace a missing API-Football
origin. Other sources retain their existing source-age classification.

The provider response does not supply independent bookmaker/market update times
in this normalization contract. Discovery records that age as unknown. Immutable
quote/snapshot evidence retains separate origin and retrieval timestamps;
quote fingerprints now bind provider origin too. Discovery records the policy,
limits and original timestamps for valid and stale normalized responses in its
append-only Lab run evidence. Historical evidence is never rewritten.

HTTP-200 `errors` payloads are rejected before histories and report their actual
provider error fields and HTTP/quota metadata. A response with missing or invalid
quota headers cannot overwrite the last valid exact quota observation. Bounded
clients stop subsequent requests with
`API_FOOTBALL_QUOTA_HEADERS_MISSING_OR_INVALID`, preserving the offending response
metadata and the last observed quota. Preserved quota is historical evidence,
not permission to continue spending. Valid new headers, including headers on
error responses, remain authoritative. No automatic recovery probes were added.

The previous 21-call run recorded fixture 1550122 as rejected but discarded its
error body. Its exact rejection cause cannot be recovered from that ledger.
The bounded post-fix run and focused HTTP-200 regression cases provide the new
diagnostic evidence. No prediction algorithm changed; deterministic discovery
replays cover the cadence boundaries, rejection and quota handling.
