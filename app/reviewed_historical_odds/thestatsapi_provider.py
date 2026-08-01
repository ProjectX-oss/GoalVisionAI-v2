"""TheStatsAPI adapter for explicitly authorized, bounded coverage checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .fingerprint import sha256_fingerprint
from .models import SourceOddsEvent, SourceOddsQuote
from .provider_http import BoundedJsonHttpClient
from .provider_models import (
    HistoricalOddsProvider, ProviderCompetition, ProviderCredentialConfig,
    ProviderFixture, ProviderMetadata, ProviderQuotaSnapshot, ProviderResponseReceipt,
)


class TheStatsApiProvider:
    BASE_URL = "https://api.thestatsapi.com/api"

    def __init__(self, credential: ProviderCredentialConfig, client: BoundedJsonHttpClient | None = None) -> None:
        if not credential.configured or not credential.secret_value:
            raise ValueError("TheStatsAPI credential is not configured")
        self.credential = credential
        self.client = client or BoundedJsonHttpClient(base_url=self.BASE_URL, secret=credential.secret_value)

    def diagnose_credentials(self) -> tuple[bool, ProviderResponseReceipt | None]:
        response = self.client.get("football/competitions", {"per_page": 1})
        return True, response.receipt

    def fetch_provider_metadata(self) -> ProviderMetadata:
        raw = {
            "provider": HistoricalOddsProvider.THESTATSAPI, "base_url": self.BASE_URL,
            "authentication_scheme": "Bearer API key", "advertised_history": "Up to 10 years for major leagues; exact coverage must be probed",
            "advertised_bookmakers": ("Bet365", "Pinnacle", "Paddy Power", "Betfair Sportsbook", "Kambi"),
            "advertised_markets": ("1X2", "totals", "BTTS", "Asian handicap"),
            "opening_price_claimed": True, "last_seen_price_claimed": True,
            "rate_limit_per_minute": None, "monthly_request_limit": None,
            "metadata_timestamp_utc": "2026-08-01T00:00:00Z",
        }
        return ProviderMetadata(**raw, metadata_fingerprint=sha256_fingerprint(raw))

    def list_supported_competitions(self) -> tuple[ProviderCompetition, ...]:
        payload = self.client.get("football/competitions", {"per_page": 250}).payload
        return tuple(sorted((_competition(item) for item in _records(payload)), key=lambda item: item.provider_competition_id))

    def resolve_competition(self, query: str) -> ProviderCompetition | None:
        needle = query.casefold().replace(" ", "").replace("-", "")
        matches = [item for item in self.list_supported_competitions() if needle in "".join(filter(None, (item.provider_competition_id, item.name, item.slug))).casefold().replace(" ", "").replace("-", "")]
        return sorted(matches, key=lambda item: (item.name.casefold() != query.casefold(), item.provider_competition_id))[0] if matches else None

    def list_historical_fixtures(self, competition_id: str, date_from: str, date_to: str) -> tuple[ProviderFixture, ...]:
        payload = self.client.get("football/matches", {"competition_id": competition_id, "date_from": date_from[:10], "date_to": date_to[:10], "per_page": 100}).payload
        return tuple(sorted((_fixture(item, competition_id) for item in _records(payload)), key=lambda item: (item.kickoff_utc, item.provider_fixture_id)))

    def inspect_fixture_odds_availability(self, fixture_id: str) -> bool:
        payload = self.client.get(f"football/matches/{fixture_id}/odds").payload
        root = payload.get("data") if isinstance(payload, Mapping) and isinstance(payload.get("data"), Mapping) else payload
        return bool(isinstance(root, Mapping) and (root.get("bookmakers") or root.get("odds")))

    def fetch_fixture_odds_sample(self, fixture_id: str) -> tuple[SourceOddsEvent, tuple[SourceOddsQuote, ...]]:
        payload = self.client.get(f"football/matches/{fixture_id}/odds").payload
        envelope = payload if isinstance(payload, Mapping) else {}
        root = envelope.get("data") if isinstance(envelope.get("data"), Mapping) else envelope
        match = root.get("match") if isinstance(root.get("match"), Mapping) else root.get("fixture")
        match = match if isinstance(match, Mapping) else root
        event = SourceOddsEvent(
            source_event_id=str(_pick(match, "id", "match_id", default=fixture_id)),
            competition=str(_name(_pick(match, "competition", "league", default=""))),
            kickoff_utc=str(_pick(match, "kickoff_utc", "utc_date", "kickoff", "start_time", "date", default="")),
            home_team=str(_name(_pick(match, "home_team", "home", default=""))),
            away_team=str(_name(_pick(match, "away_team", "away", default=""))),
            season=str(_pick(match, "season", "season_id", default="")) or None,
        )
        quotes = tuple(sorted(_parse_quotes(root, event.source_event_id), key=lambda quote: quote.source_quote_id))
        return event, quotes

    def inspect_quota(self) -> ProviderQuotaSnapshot:
        if not self.client.receipts:
            return ProviderQuotaSnapshot(None, None, None, None, sha256_fingerprint({"quota": "unknown"}))
        return self.client.receipts[-1].quota


def _records(payload: object) -> list[Mapping[str, object]]:
    if isinstance(payload, list): return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("data", "results", "competitions", "matches", "odds"):
            value = payload.get(key)
            if isinstance(value, list): return [item for item in value if isinstance(item, Mapping)]
            if isinstance(value, Mapping):
                nested = _records(value)
                if nested: return nested
    return []


def _pick(item: Mapping[str, object], *keys: str, default: object = None) -> object:
    for key in keys:
        if item.get(key) not in (None, ""): return item[key]
    return default


def _name(value: object) -> str:
    if isinstance(value, Mapping): return str(_pick(value, "name", "title", "short_name", default=""))
    return str(value)


def _competition(item: Mapping[str, object]) -> ProviderCompetition:
    return ProviderCompetition(str(_pick(item, "id", "competition_id")), _name(_pick(item, "name", "title")), str(item.get("country") or "") or None, str(item.get("slug") or "") or None)


def _fixture(item: Mapping[str, object], competition_id: str) -> ProviderFixture:
    return ProviderFixture(str(_pick(item, "id", "match_id")), competition_id, str(_pick(item, "kickoff_utc", "utc_date", "kickoff", "start_time", "date")), _name(_pick(item, "home_team", "home")), _name(_pick(item, "away_team", "away")), str(item.get("status") or "unknown"), str(item.get("season_id") or "") or None)


def _parse_quotes(root: Mapping[str, object], event_id: str) -> list[SourceOddsQuote]:
    nested = _nested_quotes(root, event_id)
    if nested: return nested
    rows = _records(root.get("odds", root))
    quotes: list[SourceOddsQuote] = []
    for row_index, row in enumerate(rows):
        bookmaker = _name(_pick(row, "bookmaker", "bookmaker_name", default="unknown"))
        market = _name(_pick(row, "market", "market_name", default="unknown"))
        selection = _name(_pick(row, "selection", "outcome", "name", default="unknown"))
        for label, value_keys, time_keys in (
            ("opening", ("opening", "opening_odds"), ("opening_at", "first_seen_at", "opening_timestamp")),
            ("last_seen", ("last_seen", "last_odds", "closing"), ("last_seen_at", "updated_at", "last_seen_timestamp")),
        ):
            value = _pick(row, *value_keys)
            if isinstance(value, Mapping): value = _pick(value, "odds", "price", "value")
            captured = _pick(row, *time_keys)
            if value in (None, ""): continue
            identity = {"event": event_id, "bookmaker": bookmaker, "market": market, "selection": selection, "point": label, "row": row_index}
            quotes.append(SourceOddsQuote(
                source_quote_id=f"thestatsapi-{sha256_fingerprint(identity)}", source_event_id=event_id,
                source_bookmaker_id=bookmaker.casefold().replace(" ", "-"), source_bookmaker_name=bookmaker,
                source_market_name=market, source_selection_name=selection, odds_value=str(value),
                original_odds_format="decimal", captured_at_utc=str(captured) if captured else None,
                source_effective_timestamp_utc=str(captured) if captured else "UNKNOWN_CAPTURE_TIME", source_point=label,
            ))
    return quotes


def _nested_quotes(root: Mapping[str, object], event_id: str) -> list[SourceOddsQuote]:
    books = root.get("bookmakers")
    if not isinstance(books, list) and isinstance(root.get("odds"), Mapping):
        books = [{"bookmaker": name, "markets": markets} for name, markets in root["odds"].items()]
    if not isinstance(books, list): return []
    quotes: list[SourceOddsQuote] = []
    for book_index, book in enumerate(books):
        if not isinstance(book, Mapping): continue
        bookmaker = _name(_pick(book, "bookmaker", "name", default="unknown"))
        markets = book.get("markets")
        if not isinstance(markets, Mapping): continue
        for market, selections in sorted(markets.items(), key=lambda item: str(item[0])):
            if not isinstance(selections, Mapping): continue
            for selection, prices in sorted(selections.items(), key=lambda item: str(item[0])):
                if selection == "line": continue
                price_map = prices if isinstance(prices, Mapping) else {"last_seen": prices}
                for label, timestamp_keys in (("opening", ("opening_at", "first_seen_at", "opening_timestamp")), ("last_seen", ("last_seen_at", "updated_at", "last_seen_timestamp"))):
                    price = price_map.get(label)
                    if price in (None, ""): continue
                    captured = _pick(price_map, *timestamp_keys)
                    identity = {"event": event_id, "bookmaker": bookmaker, "market": str(market), "selection": str(selection), "point": label, "book": book_index}
                    quotes.append(SourceOddsQuote(
                        source_quote_id=f"thestatsapi-{sha256_fingerprint(identity)}", source_event_id=event_id,
                        source_bookmaker_id=bookmaker.casefold().replace(" ", "-"), source_bookmaker_name=bookmaker,
                        source_market_name=str(market), source_selection_name=str(selection), odds_value=str(price),
                        original_odds_format="decimal", captured_at_utc=str(captured) if captured else None,
                        source_effective_timestamp_utc=str(captured) if captured else "UNKNOWN_CAPTURE_TIME", source_point=label,
                    ))
    return sorted(quotes, key=lambda quote: quote.source_quote_id)
