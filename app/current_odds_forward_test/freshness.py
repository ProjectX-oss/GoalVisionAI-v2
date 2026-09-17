"""Source snapshot age and retrieval age are independent freshness gates."""
from __future__ import annotations

from datetime import datetime

from app.market_value_assessment import DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY
from app.market_value_assessment.calculations import classify_odds_freshness

API_FOOTBALL_PREMATCH_POLICY = "api-football-prematch-3h-plus-30m-v1"
API_FOOTBALL_PREMATCH_MAX_AGE_SECONDS = 3 * 3600 + 30 * 60
RETRIEVAL_MAX_AGE_SECONDS = 900


def current_odds_freshness(*, provider_type: str, provider_origin: datetime | None,
                           captured: datetime, retrieved: datetime, now: datetime) -> str:
    """Require provider origin for API-Football; retain other source policies.

    API-Football's root update describes the provider snapshot, not an
    independently observed bookmaker/market update. No such age is inferred.
    """
    if provider_type == "API_FOOTBALL_CURRENT_ODDS":
        if provider_origin is None:
            raise ValueError("MISSING_PROVIDER_ODDS_TIMESTAMP")
        age = (now - provider_origin).total_seconds()
        retrieval_age = (now - retrieved).total_seconds()
        capture_age = (now - captured).total_seconds()
        if not (provider_origin <= retrieved <= now and captured <= retrieved
                and 0 <= age <= API_FOOTBALL_PREMATCH_MAX_AGE_SECONDS
                and 0 <= retrieval_age <= RETRIEVAL_MAX_AGE_SECONDS
                and 0 <= capture_age <= RETRIEVAL_MAX_AGE_SECONDS):
            return "STALE"
        return "FRESH"
    age = (now - (provider_origin or captured)).total_seconds()
    if age < 0:
        return "STALE"
    return classify_odds_freshness(int(age), DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY).value
