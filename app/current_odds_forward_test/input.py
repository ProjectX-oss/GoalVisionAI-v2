"""Manual and API-Football current-odds normalization."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re

from app.market_value_assessment import DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY
from app.market_value_assessment.calculations import classify_odds_freshness
from app.real_match_lab_analysis.fingerprint import fingerprint
from app.real_match_lab_analysis.policy import SUPPORTED_MARKETS

from .models import (
    ODDS_SCHEMA_VERSION, CurrentOddsQuote, CurrentOddsSnapshot,
    CurrentOddsSourceType,
)


class CurrentOddsValidationError(ValueError): pass


def parse_current_odds(raw: object, *, now: datetime | None = None) -> CurrentOddsSnapshot:
    if not isinstance(raw, dict) or raw.get("schema_version") != ODDS_SCHEMA_VERSION:
        raise CurrentOddsValidationError("Unsupported current-odds schema version.")
    now = _time(now or datetime.now(timezone.utc), "now")
    fixture = _text(raw.get("fixture_id"), "fixture_id")
    kickoff = _time(raw.get("kickoff_utc"), "kickoff_utc")
    selected = _time(raw.get("source_selected_at_utc"), "source_selected_at_utc")
    captured = _time(raw.get("captured_at_utc"), "captured_at_utc")
    retrieved = _time(raw.get("source_retrieval_timestamp_utc"), "source_retrieval_timestamp_utc")
    if not selected <= captured <= retrieved <= now: raise CurrentOddsValidationError("Odds source/capture/retrieval order is invalid.")
    if captured >= kickoff: raise CurrentOddsValidationError("ODDS_CAPTURE_AFTER_KICKOFF")
    age = int((now - captured).total_seconds())
    freshness = classify_odds_freshness(age, DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY).value
    if freshness in {"STALE", "EXPIRED"}: raise CurrentOddsValidationError("STALE_CURRENT_ODDS")
    try: source_type = CurrentOddsSourceType(_text(raw.get("source_type"), "source_type"))
    except ValueError as exc: raise CurrentOddsValidationError("Unsupported current odds source type.") from exc
    provider = _text(raw.get("provider_source_id"), "provider_source_id")
    bookmaker = _text(raw.get("bookmaker"), "bookmaker")
    event = _text(raw.get("provider_event_id"), "provider_event_id")
    provenance = _text(raw.get("provenance"), "provenance", maximum=2000)
    if re.search(r"(?i)(api[_ -]?key|token|secret|password|authorization\s*:|bearer\s+)", provenance):
        raise CurrentOddsValidationError("ODDS_PROVENANCE_INCOMPLETE")
    direct = _boolean(raw.get("direct_bookmaker"), "direct_bookmaker")
    operator = source_type is not CurrentOddsSourceType.API_FOOTBALL_CURRENT_ODDS
    by_goalvision = _boolean(raw.get("captured_at_by_goalvision"), "captured_at_by_goalvision")
    provider_time = _optional_time(raw.get("provider_origin_timestamp_utc"), "provider_origin_timestamp_utc")
    if by_goalvision == (provider_time is not None):
        raise CurrentOddsValidationError("Exactly one provider-origin or GoalVision retrieval timestamp mode is required.")
    markets = raw.get("markets")
    if not isinstance(markets, list) or not markets: raise CurrentOddsValidationError("At least one current quote is required.")
    quotes = []
    seen = set()
    for item in markets:
        if not isinstance(item, dict): raise CurrentOddsValidationError("Each market quote must be an object.")
        market = _text(item.get("market"), "market")
        if market not in SUPPORTED_MARKETS: raise CurrentOddsValidationError("Correct score and combos are unsupported.")
        if market in seen: raise CurrentOddsValidationError("ODDS_QUOTE_REPLACEMENT_CONFLICT")
        seen.add(market)
        try: odds = Decimal(str(item.get("decimal_odds")))
        except (InvalidOperation, ValueError) as exc: raise CurrentOddsValidationError("Invalid decimal odds.") from exc
        if not odds.is_finite() or odds <= 1 or odds > 1000: raise CurrentOddsValidationError("Invalid decimal odds.")
        material = {"provider": provider, "event": event, "fixture": fixture, "bookmaker": bookmaker, "market": market, "odds": odds, "captured": captured, "retrieved": retrieved, "provenance": provenance}
        quote_fp = fingerprint(material)
        quotes.append(CurrentOddsQuote(
            quote_id="current-odds-quote-" + quote_fp, provider_source_id=provider,
            provider_type=source_type, bookmaker_name=bookmaker, provider_event_id=event,
            canonical_fixture_id=fixture, market=market, selection=market,
            decimal_odds=odds, captured_at_utc=captured,
            source_retrieval_timestamp_utc=retrieved,
            provider_origin_timestamp_utc=provider_time, captured_at_by_goalvision=by_goalvision,
            direct_bookmaker=direct, operator_supplied=operator, provenance=provenance,
            quote_fingerprint=quote_fp,
        ))
    quotes = tuple(sorted(quotes, key=lambda item: SUPPORTED_MARKETS.index(item.market)))
    material = {"schema_version": ODDS_SCHEMA_VERSION, "fixture": fixture, "kickoff": kickoff, "status": _text(raw.get("fixture_status"), "fixture_status"), "provider": provider, "source_type": source_type, "bookmaker": bookmaker, "source_selected": selected, "captured": captured, "sealed": now, "freshness": freshness, "quotes": quotes}
    snapshot_fp = fingerprint(material)
    return CurrentOddsSnapshot(
        snapshot_id="current-odds-snapshot-" + snapshot_fp, schema_version=ODDS_SCHEMA_VERSION,
        canonical_fixture_id=fixture, kickoff_utc=kickoff, fixture_status=material["status"],
        provider_source_id=provider, provider_type=source_type, bookmaker_name=bookmaker,
        source_selected_at_utc=selected, captured_at_utc=captured, sealed_at_utc=now,
        freshness_status=freshness, quotes=quotes, snapshot_fingerprint=snapshot_fp,
    )


def normalize_api_football_current_odds(payload: object, *, fixture_id: str, kickoff_utc: str, retrieved_at_utc: str, source_selected_at_utc: str) -> dict:
    """Convert an API-Football `/odds?fixture=` response to the manual contract."""
    if not isinstance(payload, dict) or not isinstance(payload.get("response"), list) or not payload["response"]:
        raise CurrentOddsValidationError("API-Football odds response is empty or incompatible.")
    root = payload["response"][0]
    bookmakers = root.get("bookmakers") if isinstance(root, dict) else None
    if not isinstance(bookmakers, list) or not bookmakers: raise CurrentOddsValidationError("API-Football bookmaker response is empty.")
    book = sorted(bookmakers, key=lambda item: str(item.get("name", "")))[0]
    mappings = {("Match Winner", "Home"): "HOME_WIN", ("Match Winner", "Draw"): "DRAW", ("Match Winner", "Away"): "AWAY_WIN", ("Both Teams Score", "Yes"): "BTTS_YES", ("Both Teams Score", "No"): "BTTS_NO"}
    markets = []
    for bet in book.get("bets", []):
        name = str(bet.get("name", ""))
        for value in bet.get("values", []):
            label = str(value.get("value", "")); market = mappings.get((name, label))
            if name == "Goals Over/Under" and label in {"Over 1.5", "Under 1.5", "Over 2.5", "Under 2.5", "Over 3.5", "Under 3.5"}: market = label.upper().replace(" ", "_").replace(".", "_")
            if market: markets.append({"market": market, "decimal_odds": str(value.get("odd"))})
    updated = root.get("update") if isinstance(root, dict) else None
    return {"schema_version": ODDS_SCHEMA_VERSION, "fixture_id": fixture_id, "kickoff_utc": kickoff_utc, "fixture_status": "SCHEDULED", "provider_source_id": "API_FOOTBALL", "source_type": CurrentOddsSourceType.API_FOOTBALL_CURRENT_ODDS.value, "bookmaker": str(book.get("name")), "provider_event_id": fixture_id, "source_selected_at_utc": source_selected_at_utc, "captured_at_utc": updated or retrieved_at_utc, "source_retrieval_timestamp_utc": retrieved_at_utc, "provider_origin_timestamp_utc": updated, "captured_at_by_goalvision": updated is None, "direct_bookmaker": False, "provenance": "API-Football current pre-match odds endpoint retrieved by GoalVision AI", "markets": markets}


def _text(value, label, maximum=512):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum: raise CurrentOddsValidationError(f"{label} is required text.")
    return " ".join(value.strip().split())
def _time(value, label):
    if isinstance(value, datetime): parsed = value
    elif isinstance(value, str):
        try: parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc: raise CurrentOddsValidationError(f"{label} must be ISO-8601.") from exc
    else: raise CurrentOddsValidationError(f"{label} is required.")
    if parsed.tzinfo is None: raise CurrentOddsValidationError(f"{label} must include a UTC offset.")
    return parsed.astimezone(timezone.utc)
def _optional_time(value, label): return None if value is None else _time(value, label)
def _boolean(value, label):
    if type(value) is not bool: raise CurrentOddsValidationError(f"{label} must be boolean.")
    return value
