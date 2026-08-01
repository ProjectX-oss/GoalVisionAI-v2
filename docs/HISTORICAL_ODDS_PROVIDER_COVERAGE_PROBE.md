# Historical odds provider coverage probe

Status: credential-ready; provider access not configured on 2026-08-01.

This adapter establishes whether TheStatsAPI can lawfully and technically cover
GoalVision AI's unchanged Bundesliga VALIDATION and TEST windows before any bulk
acquisition is considered. It does not change prediction logic, calibration,
bankroll rules, Telegram behavior, scheduling, startup, or production state.

## Safety and access

Set `GOALVISION_THESTATSAPI_API_KEY` only in the operator environment. Never put
the value in Git, CLI arguments, evidence, logs, exceptions, or provider URLs.
The package does not read the variable at import time. Missing credentials return
the exact terminal result `PROVIDER_CREDENTIAL_NOT_CONFIGURED` and make zero
network requests.

Network use occurs only under an explicit command. Requests use Bearer
authentication, a bounded timeout, at most two retries for transient transport or
server failures, and no retries for authentication, authorization, missing data,
or quota responses. Receipts retain only a sanitized endpoint, status, byte count,
response hash, and non-secret quota headers.

Examples:

```text
python -c "from app.reviewed_historical_odds.cli import main; main(['provider-diagnose','--provider','thestatsapi','--output','json'])"
python -c "from app.reviewed_historical_odds.cli import main; main(['coverage-probe','--provider','thestatsapi','--competition','bundesliga','--date-from','2023-05-13T13:30:00Z','--date-to','2025-05-17T13:30:00Z','--sample-limit','10','--max-requests','25','--output','json'])"
python -c "from app.reviewed_historical_odds.cli import main; main(['export-plan','--provider','thestatsapi','--output','json'])"
```

## Deterministic probe

The probe samples one deterministic fixture from each of six narrow periods:
the beginning, middle, and end of VALIDATION, and the beginning, middle, and end
of TEST. It normalizes at most ten fixtures and performs at most 25 requests. A
provider is confirmed only when every period returns odds with real capture
timestamps. Opening or last-seen labels without their actual timestamps are
preserved as unknown-time data and cannot satisfy coverage.

Possible terminal outcomes include confirmed, partial, insufficient,
authentication failed, quota insufficient, terms review required, incompatible
response, and credential not configured. Advertised coverage never substitutes
for observed coverage.

## Bulk plan and authorization

The unchanged target contains 313 VALIDATION and 313 TEST fixtures. With a
100-item fixture page, the deterministic estimate is seven listing requests plus
626 per-fixture odds requests: 633 baseline and 64 safety-margin requests, 697
total. The 46.95 MB raw and 15.65 MB normalized figures are planning assumptions,
not measurements. Quota units, duration, and monetary cost remain unknown until
an authorized provider response supplies them.

Bulk download is fail-closed. It requires all of the following: an environment
credential, source terms approved for import, a confirmed probe, provider-reported
quota covering the plan, and the exact phrase
`DOWNLOAD_REVIEWED_HISTORICAL_ODDS`. Resume manifests must be contiguous and
content-hashed. None of those gates authorizes publication, model activation, or
production deployment.

No database migration is needed for a missing-credential probe. Sanitized
evidence is a versioned Git artifact; actual restricted raw responses belong only
in operator-controlled ignored storage. If a real import is later authorized,
the existing immutable source review, manifest, quote, linkage, and coverage
records remain the canonical persistence boundary.

## Provider review

TheStatsAPI's official pages advertise Bundesliga coverage, five bookmakers,
common football markets, opening and last-seen prices, and up to ten years of
history for major leagues. Exact competition/date/bookmaker/market/timestamp
coverage still varies and has not been verified. Public pages do not resolve the
project's storage and redistribution requirements, and published rate-limit
figures vary by page or plan. The source therefore remains `REVIEW_REQUIRED`.

Official references reviewed 2026-08-01:

- https://www.thestatsapi.com/
- https://www.thestatsapi.com/football-api
- https://www.thestatsapi.com/odds-api
- https://www.thestatsapi.com/odds-api/historical-football-odds
- https://www.thestatsapi.com/odds-api/pinnacle
- https://www.thestatsapi.com/coverage
