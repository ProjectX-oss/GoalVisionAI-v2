"""Immutable supplied-odds normalization, provenance, and temporal safety."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from re import fullmatch

from .exceptions import BacktestOddsProvenanceError
from .fingerprint import sha256_fingerprint
from .models import (
    HistoricalOddsDataset,
    HistoricalOddsSnapshot,
    OddsMarketStatus,
    StoredOddsSnapshot,
    SupportedMarket,
)
from .validation import normalize_utc


def odds_source_fingerprint(snapshot: HistoricalOddsSnapshot) -> str:
    return sha256_fingerprint(
        {
            "odds_snapshot_id": snapshot.odds_snapshot_id,
            "source_identity": snapshot.source_identity,
            "source_version": snapshot.source_version,
            "historical_match_id": snapshot.historical_match_id,
            "competition": snapshot.competition,
            "kickoff_utc": normalize_utc(snapshot.kickoff_utc, "kickoff_utc"),
            "snapshot_timestamp_utc": normalize_utc(snapshot.snapshot_timestamp_utc, "snapshot_timestamp_utc"),
            "bookmaker_identity": snapshot.bookmaker_identity,
            "market_identity": SupportedMarket(snapshot.market_identity),
            "selection_identity": snapshot.selection_identity,
            "decimal_odds": snapshot.decimal_odds,
            "currency": snapshot.currency,
            "market_status": OddsMarketStatus(snapshot.market_status),
            "source_record_identity": snapshot.source_record_identity,
            "metadata_version": snapshot.metadata_version,
        }
    )


def create_odds_dataset(
    odds_dataset_id: str,
    snapshots: tuple[HistoricalOddsSnapshot, ...],
    *,
    metadata_version: str = "v1",
) -> HistoricalOddsDataset:
    ordered = tuple(sorted(snapshots, key=_snapshot_key))
    fingerprint = sha256_fingerprint(
        {
            "odds_dataset_id": odds_dataset_id,
            "source_fingerprints": tuple(item.source_fingerprint for item in ordered),
            "metadata_version": metadata_version,
        }
    )
    return HistoricalOddsDataset(odds_dataset_id, fingerprint, ordered, metadata_version)


def verify_and_select_odds(
    dataset: HistoricalOddsDataset,
    *,
    expected_id: str,
    expected_fingerprint: str,
    examples,
    markets: tuple[SupportedMarket, ...],
    bookmaker_filters: tuple[str, ...],
    closing: bool = False,
) -> tuple[StoredOddsSnapshot, ...]:
    if not isinstance(dataset, HistoricalOddsDataset):
        raise BacktestOddsProvenanceError("Odds input must be an immutable HistoricalOddsDataset.")
    if dataset.odds_dataset_id != expected_id or dataset.odds_dataset_fingerprint != expected_fingerprint:
        raise BacktestOddsProvenanceError("Odds dataset identity or fingerprint mismatch.")
    rebuilt = create_odds_dataset(dataset.odds_dataset_id, dataset.snapshots, metadata_version=dataset.metadata_version)
    if rebuilt.odds_dataset_fingerprint != dataset.odds_dataset_fingerprint:
        raise BacktestOddsProvenanceError("Odds dataset fingerprint is not reproducible.")
    by_match = {item.historical_match_id: item for item in examples}
    logical: dict[tuple[str, SupportedMarket, str], list[tuple[HistoricalOddsSnapshot, str, str, OddsMarketStatus]]] = defaultdict(list)
    seen_ids: set[str] = set()
    for snapshot in dataset.snapshots:
        if snapshot.odds_snapshot_id in seen_ids:
            raise BacktestOddsProvenanceError("Duplicate odds snapshot identity.")
        seen_ids.add(snapshot.odds_snapshot_id)
        try:
            expected_source_fingerprint = odds_source_fingerprint(snapshot)
        except (ValueError, TypeError, KeyError) as exc:
            raise BacktestOddsProvenanceError("Odds market or provenance is malformed.") from exc
        if snapshot.source_fingerprint != expected_source_fingerprint:
            raise BacktestOddsProvenanceError("Odds source fingerprint mismatch.")
        for value, label in (
            (snapshot.odds_snapshot_id, "odds snapshot ID"),
            (snapshot.source_identity, "source identity"),
            (snapshot.source_version, "source version"),
            (snapshot.source_record_identity, "source record identity"),
            (snapshot.bookmaker_identity, "bookmaker identity"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise BacktestOddsProvenanceError(f"{label} is required.")
        if fullmatch(r"[0-9a-f]{64}", snapshot.source_fingerprint) is None:
            raise BacktestOddsProvenanceError("Malformed odds source fingerprint.")
        if not isinstance(snapshot.decimal_odds, Decimal) or not snapshot.decimal_odds.is_finite() or snapshot.decimal_odds <= Decimal("1.00"):
            raise BacktestOddsProvenanceError("Decimal odds must be finite and greater than 1.00.")
        market = SupportedMarket(snapshot.market_identity)
        status = OddsMarketStatus(snapshot.market_status)
        kickoff = normalize_utc(snapshot.kickoff_utc, "odds kickoff") or ""
        observed = normalize_utc(snapshot.snapshot_timestamp_utc, "odds timestamp") or ""
        example = by_match.get(snapshot.historical_match_id)
        if example is None:
            continue
        if kickoff != normalize_utc(example.kickoff_utc, "TEST kickoff") or snapshot.competition != example.competition:
            raise BacktestOddsProvenanceError("Odds match provenance does not match the TEST example.")
        if not closing and observed >= kickoff:
            raise BacktestOddsProvenanceError("Decision odds must be strictly before kickoff.")
        if market not in markets or (bookmaker_filters and snapshot.bookmaker_identity not in bookmaker_filters):
            continue
        key = (snapshot.historical_match_id, market, snapshot.bookmaker_identity)
        logical[key].append((snapshot, kickoff, observed, status))
    selected: list[tuple[HistoricalOddsSnapshot, str, str, SupportedMarket, OddsMarketStatus]] = []
    for key in sorted(logical, key=lambda item: (item[0], item[1].value, item[2])):
        values = sorted(logical[key], key=lambda item: (item[2], item[0].source_record_identity, item[0].odds_snapshot_id))
        newest_timestamp = values[-1][2]
        newest = tuple(item for item in values if item[2] == newest_timestamp)
        if len({(item[0].decimal_odds, item[3], item[0].source_fingerprint) for item in newest}) != 1:
            raise BacktestOddsProvenanceError("Conflicting odds snapshots fail closed.")
        snapshot, kickoff, observed, status = newest[-1]
        selected.append((snapshot, kickoff, observed, key[1], status))
    selected.sort(key=lambda item: (item[1], item[0].competition, item[0].historical_match_id, item[3].value, item[0].bookmaker_identity))
    return tuple(
        StoredOddsSnapshot(
            stored_odds_row_id=f"historical-backtest-odds-{sha256_fingerprint((expected_fingerprint, item[0].odds_snapshot_id, closing))}",
            snapshot=item[0], normalized_kickoff_utc=item[1],
            normalized_snapshot_timestamp_utc=item[2], market_identity=item[3],
            market_status=item[4], closing=closing, deterministic_order=index,
        )
        for index, item in enumerate(selected)
    )


def verify_odds_temporal_safety(snapshots: tuple[StoredOddsSnapshot, ...]) -> tuple[str, ...]:
    return tuple(
        f"POST_KICKOFF_ODDS:{item.snapshot.odds_snapshot_id}"
        for item in snapshots
        if not item.closing and item.normalized_snapshot_timestamp_utc >= item.normalized_kickoff_utc
    )


def _snapshot_key(item: HistoricalOddsSnapshot):
    return (
        normalize_utc(item.kickoff_utc, "kickoff") or "",
        item.competition, item.historical_match_id,
        SupportedMarket(item.market_identity).value,
        item.bookmaker_identity,
        normalize_utc(item.snapshot_timestamp_utc, "snapshot") or "",
        item.source_record_identity, item.odds_snapshot_id,
    )
