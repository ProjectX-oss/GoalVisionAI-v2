# Market Probability and Value Assessment

`app.market_value_assessment` combines one persisted calibrated probability
assembly with one caller-supplied immutable pre-match odds snapshot. It owns
market normalization, fair-value calculations, structural actionability, and
append-only audit persistence. It never fetches odds, removes bookmaker margin,
selects a bet, recommends stake, invokes risk or the Quality Gate, registers a
candidate, or publishes.

## Canonical markets

The immutable `market-mapping-v1` registry supports exactly 14 identities:

| Market | Selections and calibrated source |
| --- | --- |
| Match winner | HOME → HOME_WIN; DRAW → DRAW; AWAY → AWAY_WIN |
| Double chance | HOME_DRAW → HOME_WIN + DRAW; HOME_AWAY → HOME_WIN + AWAY_WIN; DRAW_AWAY → DRAW + AWAY_WIN |
| Totals 1.5 | OVER → OVER_1_5; UNDER → UNDER_1_5 |
| Totals 2.5 | OVER → OVER_2_5; UNDER → UNDER_2_5 |
| Totals 3.5 | OVER → OVER_3_5; UNDER → UNDER_3_5 |
| BTTS | YES → BTTS_YES; NO → BTTS_NO |

Double chance is a deterministic sum of the two named calibrated match-result
targets. It is not independently calibrated. The assessment preserves both
source targets, the derivation type, formula version, and calibrated assembly
provenance. Unsupported markets, selections, combinations, and lines fail
closed.

## Supplied odds and validation

The caller owns odds collection and passes `SuppliedOddsSnapshot`; this package
has no provider client or ingestion activation. Normalization applies NFKC
Unicode and whitespace normalization, controlled enums, canonical UTC
timestamps, normalized Decimal lines, sorted immutable metadata, and optional
uppercase currency. Decimal odds must be finite, greater than 1.00, and at most
1000. Totals require exactly 1.5, 2.5, or 3.5; other markets reject a line.

Only open, available, unsuspended pre-match prices are accepted. Effective and
source-update timestamps cannot postdate registration, odds must precede
kickoff, and assessment must follow calibration, odds, and registration while
remaining before the persisted source-snapshot kickoff. Match and kickoff
provenance must agree. Metadata rejects URLs, affiliate material, credentials,
and tokens. Optional stake limits are validated but never used to recommend a
stake. Prices below the Official 1.60 publication threshold remain structurally
assessable.

## Decimal formulas and classifications

All intermediates use a 50-digit local Decimal context. The default policy
quantizes final probabilities, odds, edges, and EV fields to six decimal places
using `ROUND_HALF_EVEN`; it never rounds intermediates, clamps EV/edge, or
corrects bookmaker margin. For fair probability `p` and decimal odds `o`:

- fair odds = `1 / p`
- implied probability = break-even probability = `1 / o`
- absolute edge = `p - (1 / o)`
- relative edge = `(p / (1 / o)) - 1`
- expected value per unit = `(p * o) - 1`
- expected return per unit = `p * o`
- potential profit per winning unit = `o - 1`

Default odds freshness is FRESH through 300 seconds, AGING through 900,
STALE through 1800, and EXPIRED thereafter. Calibrated data is FRESH through
1800 seconds, AGING through 7200, and STALE thereafter. Overall freshness is
the worst state. Expired odds, policy-blocked stale data, and fewer than 300
seconds to kickoff produce calculated but non-actionable assessments.

EV classification is descriptive: below zero is NEGATIVE, zero through below
0.02 is NEUTRAL, 0.02 through below 0.05 is POSITIVE, and 0.05 or above is
STRONG. `ACTIONABLE` means only structurally usable by a future selection
engine; it is never publication eligibility or approval.

## Fingerprints, persistence, and boundaries

The odds SHA-256 covers supplied/source/event/match identity, normalized market,
selection and line, price, effective/update/kickoff timestamps, status and
availability, and source/metadata versions. Registration execution time is
excluded. The assessment SHA-256 covers calibrated/model/calibration provenance,
odds fingerprint, mapped targets and derivation version, calculated probability,
odds, edge and EV, freshness, actionability, explicit assessment timestamp, and
policy version. Canonical serialization excludes dictionary ordering, execution
duration, logs, repository identity, and credentials.

Identical calibrated fingerprint, odds fingerprint, mapping/policy versions,
and assessment timestamp return the existing record. A material change creates
a new immutable assessment. Migration v19 adds `market_odds_snapshots` and
`market_value_assessments` with unique fingerprints, foreign keys to calibrated
assemblies and odds, deterministic Decimal/JSON text, query indexes, and
update/delete prevention triggers. Previously unseen odds and their assessment
are inserted in one transaction, so an assessment failure cannot leave a
partial odds record.

The explicit production boundaries are
`build_market_value_assessment_service(...)` and `assess_market_value(...)`.
The factory requires explicit odds repository, assessment repository, mapping
registry, and policy and performs no work at construction. Only ACTIONABLE
records map through `to_future_official_selection_input(...)`; that typed,
read-only payload has no stake, risk, exposure, candidate, gate, or publication
state.

External odds providers, ingestion and scheduling, bet selection, staking,
candidate registration, Quality Gate execution, and publication remain
intentionally deferred.
