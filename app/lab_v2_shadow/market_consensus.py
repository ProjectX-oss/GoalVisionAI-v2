"""Current-only multi-bookmaker consensus and immutable quote provenance."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext

from app.current_odds_forward_test.freshness import API_FOOTBALL_PREMATCH_MAX_AGE_SECONDS
from app.real_match_lab_analysis.fingerprint import fingerprint


@dataclass(frozen=True, slots=True)
class CurrentQuote:
    fixture_id: int
    bookmaker_id: int | None
    bookmaker_name: str
    market: str
    decimal_odds: Decimal
    provider_origin_timestamp_utc: datetime
    retrieved_at_utc: datetime
    provenance_fingerprint: str


@dataclass(frozen=True, slots=True)
class BookmakerFairMarket:
    bookmaker_id: int | None
    bookmaker_name: str
    market_family: str
    margin: Decimal
    fair_probabilities: dict[str, Decimal]


@dataclass(frozen=True, slots=True)
class CurrentMarketConsensus:
    fixture_id: int
    market_family: str
    status: str
    fair_probabilities: dict[str, Decimal]
    bookmaker_count: int
    quote_count: int
    dispersion: dict[str, Decimal]
    bookmaker_markets: tuple[BookmakerFairMarket, ...]
    quotes: tuple[CurrentQuote, ...]
    reason: str | None


_MAPPINGS = {
    ("match winner", "home"): "HOME_WIN",
    ("match winner", "draw"): "DRAW",
    ("match winner", "away"): "AWAY_WIN",
    ("both teams score", "yes"): "BTTS_YES",
    ("both teams score", "no"): "BTTS_NO",
}
_FAMILIES = {
    "1X2": ("HOME_WIN", "DRAW", "AWAY_WIN"),
    "BTTS": ("BTTS_YES", "BTTS_NO"),
    "TOTAL_1_5": ("OVER_1_5", "UNDER_1_5"),
    "TOTAL_2_5": ("OVER_2_5", "UNDER_2_5"),
    "TOTAL_3_5": ("OVER_3_5", "UNDER_3_5"),
}


def current_market_consensus(
    payload: object, *, fixture_id: int, retrieved_at: datetime, now: datetime,
) -> dict[str, CurrentMarketConsensus]:
    """Build consensus only from complete, comparable, fresh current markets."""
    retrieved, clock = _utc(retrieved_at), _utc(now)
    rows = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        return {}
    matching = [row for row in rows if isinstance(row, dict)
                and str((row.get("fixture") or {}).get("id")) == str(fixture_id)]
    if len(matching) != 1:
        return {}
    root = matching[0]
    try:
        updated = _utc(datetime.fromisoformat(str(root["update"]).replace("Z", "+00:00")))
    except (KeyError, TypeError, ValueError):
        return {}
    if not updated <= retrieved <= clock or (clock - updated).total_seconds() > API_FOOTBALL_PREMATCH_MAX_AGE_SECONDS:
        return {family: _unavailable(fixture_id, family, "STALE_CURRENT_ODDS") for family in _FAMILIES}
    quotes = _quotes(root, fixture_id=fixture_id, updated=updated, retrieved=retrieved)
    result: dict[str, CurrentMarketConsensus] = {}
    for family, outcomes in _FAMILIES.items():
        bookmaker_markets = []
        for key, group in _by_bookmaker(quotes).items():
            selected = {item.market: item for item in group if item.market in outcomes}
            if set(selected) != set(outcomes):
                continue
            fair = remove_margin_multiplicative({market: selected[market].decimal_odds for market in outcomes})
            if fair is None:
                continue
            probabilities, margin = fair
            bookmaker_markets.append(BookmakerFairMarket(key[0], key[1], family, margin, probabilities))
        bookmaker_markets.sort(key=lambda item: (item.bookmaker_name.casefold(), item.bookmaker_id or -1))
        relevant = tuple(item for item in quotes if item.market in outcomes)
        if len(bookmaker_markets) < 2:
            result[family] = CurrentMarketConsensus(
                int(fixture_id), family, "INSUFFICIENT_COMPARABLE_BOOKMAKERS", {},
                len(bookmaker_markets), len(relevant), {}, tuple(bookmaker_markets), relevant,
                "CONSENSUS_REQUIRES_TWO_COMPLETE_BOOKMAKERS",
            )
            continue
        with localcontext() as context:
            context.prec = 28
            consensus = {market: sum((book.fair_probabilities[market] for book in bookmaker_markets), Decimal(0)) / len(bookmaker_markets)
                         for market in outcomes}
            consensus[outcomes[-1]] = Decimal(1) - sum(
                (consensus[market] for market in outcomes[:-1]), Decimal(0)
            )
            dispersion = {market: max(book.fair_probabilities[market] for book in bookmaker_markets)
                           - min(book.fair_probabilities[market] for book in bookmaker_markets) for market in outcomes}
        result[family] = CurrentMarketConsensus(
            int(fixture_id), family, "AVAILABLE", consensus, len(bookmaker_markets),
            len(relevant), dispersion, tuple(bookmaker_markets), relevant, None,
        )
    return result


def remove_margin_multiplicative(odds: dict[str, Decimal]) -> tuple[dict[str, Decimal], Decimal] | None:
    """Transparent normalization equivalent to penaltyblog's multiplicative method."""
    if len(odds) < 2 or any(value <= 1 or not value.is_finite() for value in odds.values()):
        return None
    with localcontext() as context:
        context.prec = 28
        raw = {key: Decimal(1) / value for key, value in odds.items()}
        total = sum(raw.values(), Decimal(0))
        margin = total - Decimal(1)
        if not Decimal("-0.02") <= margin <= Decimal("0.30") or total <= 0:
            return None
        probabilities = {key: value / total for key, value in raw.items()}
        last = next(reversed(probabilities))
        probabilities[last] = Decimal(1) - sum(
            (value for key, value in probabilities.items() if key != last), Decimal(0)
        )
        return probabilities, margin


def best_current_price(consensus: CurrentMarketConsensus, market: str) -> CurrentQuote | None:
    candidates = [item for item in consensus.quotes if item.market == market]
    return max(candidates, key=lambda item: (item.decimal_odds, item.bookmaker_name.casefold(), item.bookmaker_id or -1), default=None)


def consensus_document(value: CurrentMarketConsensus) -> dict[str, object]:
    return {
        **asdict(value),
        "quotes": [asdict(item) for item in value.quotes],
        "bookmaker_markets": [asdict(item) for item in value.bookmaker_markets],
    }


def _quotes(root: dict, *, fixture_id: int, updated: datetime, retrieved: datetime) -> tuple[CurrentQuote, ...]:
    result: list[CurrentQuote] = []
    books = root.get("bookmakers") if isinstance(root.get("bookmakers"), list) else ()
    for book in books:
        if not isinstance(book, dict):
            continue
        bookmaker_id = _integer(book.get("id"))
        bookmaker_name = str(book.get("name") or bookmaker_id or "UNKNOWN")
        bets = book.get("bets") if isinstance(book.get("bets"), list) else ()
        for bet in bets:
            if not isinstance(bet, dict):
                continue
            bet_name = str(bet.get("name") or "")
            values = bet.get("values") if isinstance(bet.get("values"), list) else ()
            for raw in values:
                if not isinstance(raw, dict):
                    continue
                market = _market(bet_name, str(raw.get("value") or ""))
                odds = _decimal(raw.get("odd"))
                if market is None or odds is None or odds <= 1:
                    continue
                material = {
                    "provider": "API_FOOTBALL", "fixture_id": fixture_id,
                    "bookmaker_id": bookmaker_id, "bookmaker": bookmaker_name,
                    "market": market, "odds": odds, "provider_updated": updated,
                    "retrieved_at": retrieved,
                }
                result.append(CurrentQuote(
                    fixture_id, bookmaker_id, bookmaker_name, market, odds,
                    updated, retrieved, fingerprint(material),
                ))
    unique = {(item.bookmaker_id, item.bookmaker_name, item.market): item for item in result}
    return tuple(sorted(unique.values(), key=lambda item: (
        item.bookmaker_name.casefold(), item.bookmaker_id or -1, item.market,
    )))


def _market(bet: str, value: str) -> str | None:
    direct = _MAPPINGS.get((bet.casefold(), value.casefold()))
    if direct:
        return direct
    if bet.casefold() == "goals over/under" and value.casefold() in {
        "over 1.5", "under 1.5", "over 2.5", "under 2.5", "over 3.5", "under 3.5",
    }:
        return value.upper().replace(" ", "_").replace(".", "_")
    return None


def _by_bookmaker(quotes: tuple[CurrentQuote, ...]) -> dict[tuple[int | None, str], list[CurrentQuote]]:
    result: dict[tuple[int | None, str], list[CurrentQuote]] = {}
    for quote in quotes:
        result.setdefault((quote.bookmaker_id, quote.bookmaker_name), []).append(quote)
    return result


def _unavailable(fixture_id: int, family: str, reason: str) -> CurrentMarketConsensus:
    return CurrentMarketConsensus(int(fixture_id), family, reason, {}, 0, 0, {}, (), (), reason)


def _decimal(value: object) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _integer(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("CURRENT_QUOTE_TIMESTAMP_REQUIRES_OFFSET")
    return value.astimezone(timezone.utc)
