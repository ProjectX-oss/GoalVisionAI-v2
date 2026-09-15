"""Reviewed bookmaker relevance without claiming quote availability in Latvia."""

from __future__ import annotations

from dataclasses import dataclass


CATALOGUE_CACHE_DAYS = 7
REVIEW_VERSION = "goalvision-lab-v2-latvian-bookmaker-review-v1"

# These exact consumer brands have documented Latvian-facing operations.  A
# provider catalogue row is tagged only on an exact normalized-name match; the
# tag never asserts that any individual quote is offered to a Latvian account.
REVIEWED_LATVIAN_FACING_NAMES = frozenset({"optibet", "olybet", "betsafe", "tonybet"})
REPUTABLE_CONSENSUS_NAMES = frozenset({
    "bet365", "betfair", "betano", "pinnacle", "william hill", "unibet",
    "betvictor",
})


@dataclass(frozen=True, slots=True)
class BookmakerCatalogueEntry:
    bookmaker_id: int
    bookmaker_name: str
    relevance: str
    review_version: str = REVIEW_VERSION


def normalize_bookmaker_name(value: object) -> str:
    return " ".join(str(value or "").casefold().replace("-", " ").split())


def review_bookmaker_catalogue(payload: object) -> tuple[BookmakerCatalogueEntry, ...]:
    rows = payload.get("response") if isinstance(payload, dict) else None
    result: dict[int, BookmakerCatalogueEntry] = {}
    for row in rows if isinstance(rows, list) else ():
        if not isinstance(row, dict):
            continue
        try:
            identity = int(row["id"])
        except (KeyError, TypeError, ValueError):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        normalized = normalize_bookmaker_name(name)
        relevance = (
            "REVIEWED_LATVIAN_FACING_NAME_MATCH"
            if normalized in REVIEWED_LATVIAN_FACING_NAMES
            else "REPUTABLE_CURRENT_CONSENSUS_SOURCE"
            if normalized in REPUTABLE_CONSENSUS_NAMES
            else "OTHER_CURRENT_PROVIDER_SOURCE"
        )
        result[identity] = BookmakerCatalogueEntry(identity, name, relevance)
    return tuple(result[key] for key in sorted(result))


def catalogue_summary(entries: tuple[BookmakerCatalogueEntry, ...]) -> dict[str, object]:
    reviewed = [item for item in entries if item.relevance == "REVIEWED_LATVIAN_FACING_NAME_MATCH"]
    reputable = [item for item in entries if item.relevance == "REPUTABLE_CURRENT_CONSENSUS_SOURCE"]
    return {
        "review_version": REVIEW_VERSION,
        "catalogue_count": len(entries),
        "reviewed_latvian_facing_matches": [
            {"bookmaker_id": item.bookmaker_id, "bookmaker_name": item.bookmaker_name}
            for item in reviewed
        ],
        "reputable_consensus_sources": [
            {"bookmaker_id": item.bookmaker_id, "bookmaker_name": item.bookmaker_name}
            for item in reputable
        ],
        "limitation": (
            "A name match identifies a reviewed Latvian-facing brand, not account-level "
            "availability. Every published price remains attributed only to its actual API provider."
        ),
    }
