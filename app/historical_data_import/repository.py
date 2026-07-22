"""Append-only SQLite persistence for normalized historical match data."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from app.database import Database, MigrationManager

from .exceptions import HistoricalImportConflictError, HistoricalImportPersistenceError
from .fingerprint import canonical_decimal, canonical_json, sha256_fingerprint
from .models import (
    FullTimeResult,
    HistoricalImportResult,
    HistoricalImportStatus,
    NormalizedHistoricalLineup,
    NormalizedHistoricalStatistics,
    PreparedHistoricalDataset,
    PreparedHistoricalMatch,
    StoredHistoricalLineup,
    StoredHistoricalMatch,
    StoredHistoricalStatistics,
    TeamSide,
)


@dataclass(frozen=True, slots=True)
class _MatchAppend:
    prepared: PreparedHistoricalMatch
    historical_match_id: str
    version: int


class SQLiteHistoricalMatchRepository:
    """Persist a complete supplied dataset in one append-only transaction."""

    def __init__(self, database: Database, *, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def append_import(self, dataset: PreparedHistoricalDataset) -> HistoricalImportResult:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._find_import_identity(
                dataset.provider_identity,
                dataset.dataset_id,
                dataset.dataset_version,
            )
            if existing is not None:
                if existing["dataset_fingerprint"] != dataset.dataset_fingerprint:
                    raise HistoricalImportConflictError(
                        "The immutable provider dataset identity already has different content."
                    )
                result = self._replay_result(existing)
                self._connection.commit()
                return result

            inserts: list[_MatchAppend] = []
            reused_ids: dict[str, str] = {}
            for prepared in dataset.matches:
                exact = self._connection.execute(
                    "SELECT historical_match_id,logical_identity_fingerprint FROM historical_matches WHERE match_fingerprint=?",
                    (prepared.match_fingerprint,),
                ).fetchone()
                if exact is not None:
                    if exact["logical_identity_fingerprint"] != prepared.logical_identity_fingerprint:
                        raise HistoricalImportConflictError("A match fingerprint collision was detected.")
                    reused_ids[prepared.match_fingerprint] = exact["historical_match_id"]
                    continue
                natural_conflict = self._connection.execute(
                    """
                    SELECT logical_identity_fingerprint FROM historical_matches
                    WHERE natural_identity_fingerprint=?
                    ORDER BY match_version DESC LIMIT 1
                    """,
                    (prepared.natural_identity_fingerprint,),
                ).fetchone()
                if (
                    natural_conflict is not None
                    and natural_conflict["logical_identity_fingerprint"]
                    != prepared.logical_identity_fingerprint
                ):
                    raise HistoricalImportConflictError(
                        "A normalized match identity is already assigned to another provider match ID."
                    )
                latest = self._connection.execute(
                    """
                    SELECT historical_match_id,match_version,kickoff_utc
                    FROM historical_matches
                    WHERE logical_identity_fingerprint=?
                    ORDER BY match_version DESC LIMIT 1
                    """,
                    (prepared.logical_identity_fingerprint,),
                ).fetchone()
                if latest is not None and latest["kickoff_utc"] != prepared.match.kickoff_utc:
                    raise HistoricalImportConflictError(
                        "A provider match identity cannot change its normalized kickoff."
                    )
                version = int(latest["match_version"]) + 1 if latest is not None else 1
                match_id = _historical_match_id(prepared, version)
                inserts.append(_MatchAppend(prepared, match_id, version))

            import_id = _historical_import_id(dataset.dataset_fingerprint)
            inserted_count = len(inserts)
            reused_count = len(dataset.matches) - inserted_count
            self._insert_import(dataset, import_id, inserted_count, reused_count)
            inserted_ids: dict[str, str] = {}
            for item in inserts:
                self._insert_match(item, import_id, dataset.import_timestamp)
                self._insert_children(item)
                inserted_ids[item.prepared.match_fingerprint] = item.historical_match_id
            match_ids = tuple(
                inserted_ids.get(match.match_fingerprint)
                or reused_ids[match.match_fingerprint]
                for match in dataset.matches
            )
            self._connection.commit()
            return HistoricalImportResult(
                import_id=import_id,
                status=HistoricalImportStatus.IMPORTED,
                provider=dataset.provider,
                dataset_id=dataset.dataset_id,
                dataset_version=dataset.dataset_version,
                dataset_fingerprint=dataset.dataset_fingerprint,
                supplied_match_count=len(dataset.matches),
                inserted_match_count=inserted_count,
                reused_match_count=reused_count,
                historical_match_ids=match_ids,
                import_timestamp=dataset.import_timestamp,
                policy_version=dataset.policy_version,
            )
        except HistoricalImportConflictError:
            _rollback(self._connection)
            raise
        except sqlite3.DatabaseError as exc:
            _rollback(self._connection)
            raise HistoricalImportPersistenceError(
                "The historical dataset append transaction failed."
            ) from exc

    def find_import(self, import_id: str) -> HistoricalImportResult | None:
        row = self._connection.execute(
            "SELECT * FROM historical_match_imports WHERE import_id=?",
            (import_id,),
        ).fetchone()
        return self._stored_result(row) if row is not None else None

    def find_match_by_id(self, historical_match_id: str) -> StoredHistoricalMatch | None:
        row = self._connection.execute(
            "SELECT * FROM historical_matches WHERE historical_match_id=?",
            (historical_match_id,),
        ).fetchone()
        return _stored_match(row) if row is not None else None

    def find_match_by_fingerprint(self, match_fingerprint: str) -> StoredHistoricalMatch | None:
        row = self._connection.execute(
            "SELECT * FROM historical_matches WHERE match_fingerprint=?",
            (match_fingerprint,),
        ).fetchone()
        return _stored_match(row) if row is not None else None

    def list_match_versions(self, logical_identity_fingerprint: str) -> tuple[StoredHistoricalMatch, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM historical_matches
            WHERE logical_identity_fingerprint=?
            ORDER BY match_version,historical_match_id
            """,
            (logical_identity_fingerprint,),
        ).fetchall()
        return tuple(_stored_match(row) for row in rows)

    def load_statistics(self, historical_match_id: str) -> tuple[StoredHistoricalStatistics, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM historical_match_statistics
            WHERE historical_match_id=? ORDER BY team_side
            """,
            (historical_match_id,),
        ).fetchall()
        return tuple(_stored_statistics(row) for row in rows)

    def load_lineups(self, historical_match_id: str) -> tuple[StoredHistoricalLineup, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM historical_lineups
            WHERE historical_match_id=? ORDER BY team_side
            """,
            (historical_match_id,),
        ).fetchall()
        return tuple(_stored_lineup(row) for row in rows)

    def _find_import_identity(self, provider: str, dataset_id: str, version: str) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT * FROM historical_match_imports
            WHERE provider_identity=? AND dataset_id=? AND dataset_version=?
            """,
            (provider, dataset_id, version),
        ).fetchone()

    def _insert_import(
        self,
        dataset: PreparedHistoricalDataset,
        import_id: str,
        inserted: int,
        reused: int,
    ) -> None:
        snapshot = canonical_json({
            "dataset": json.loads(dataset.deterministic_dataset_snapshot),
            "import_id": import_id,
            "import_timestamp": dataset.import_timestamp,
            "inserted_match_count": inserted,
            "reused_match_count": reused,
        })
        self._connection.execute(
            """
            INSERT INTO historical_match_imports (
                import_id,provider,provider_identity,dataset_id,dataset_version,
                dataset_schema_version,dataset_fingerprint,dataset_content_fingerprint,
                supplied_match_count,inserted_match_count,reused_match_count,
                match_fingerprint_snapshot,import_timestamp,policy_version,
                metadata_version,deterministic_import_snapshot
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                import_id,
                dataset.provider,
                dataset.provider_identity,
                dataset.dataset_id,
                dataset.dataset_version,
                dataset.schema_version,
                dataset.dataset_fingerprint,
                dataset.dataset_content_fingerprint,
                len(dataset.matches),
                inserted,
                reused,
                dataset.match_fingerprint_snapshot,
                dataset.import_timestamp,
                dataset.policy_version,
                dataset.metadata_version,
                snapshot,
            ),
        )

    def _insert_match(self, item: _MatchAppend, import_id: str, created: str) -> None:
        match = item.prepared.match
        self._connection.execute(
            """
            INSERT INTO historical_matches (
                historical_match_id,import_id,logical_identity_fingerprint,
                natural_identity_fingerprint,match_fingerprint,match_version,
                source_provider,source_match_id,competition,competition_identity,
                season,competition_round,kickoff_utc,home_team,home_team_identity,
                away_team,away_team_identity,full_time_home_score,
                full_time_away_score,half_time_home_score,half_time_away_score,
                full_time_result,venue,referee,attendance,normalized_match_snapshot,
                created_timestamp
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                item.historical_match_id,
                import_id,
                item.prepared.logical_identity_fingerprint,
                item.prepared.natural_identity_fingerprint,
                item.prepared.match_fingerprint,
                item.version,
                match.source_provider,
                match.source_match_id,
                match.competition,
                match.competition_identity,
                match.season,
                match.round,
                match.kickoff_utc,
                match.home_team,
                match.home_team_identity,
                match.away_team,
                match.away_team_identity,
                match.full_time_home_score,
                match.full_time_away_score,
                match.half_time_home_score,
                match.half_time_away_score,
                match.full_time_result.value,
                match.venue,
                match.referee,
                match.attendance,
                item.prepared.normalized_match_snapshot,
                created,
            ),
        )

    def _insert_children(self, item: _MatchAppend) -> None:
        match = item.prepared.match
        for side, statistics in (
            (TeamSide.HOME, match.home_statistics),
            (TeamSide.AWAY, match.away_statistics),
        ):
            if statistics is not None:
                self._insert_statistics(item, side, statistics)
        for side, lineup in (
            (TeamSide.HOME, match.home_lineup),
            (TeamSide.AWAY, match.away_lineup),
        ):
            if lineup is not None:
                self._insert_lineup(item, side, lineup)

    def _insert_statistics(
        self,
        item: _MatchAppend,
        side: TeamSide,
        statistics: NormalizedHistoricalStatistics,
    ) -> None:
        fingerprint = sha256_fingerprint({
            "match_fingerprint": item.prepared.match_fingerprint,
            "team_side": side.value,
            "statistics": statistics,
        })
        self._connection.execute(
            """
            INSERT INTO historical_match_statistics (
                statistics_id,historical_match_id,team_side,possession,shots,
                shots_on_target,expected_goals,corners,yellow_cards,red_cards,
                fouls,offsides,statistics_fingerprint,normalized_statistics_snapshot
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                f"historical-statistics-{fingerprint}",
                item.historical_match_id,
                side.value,
                _decimal_or_none(statistics.possession),
                statistics.shots,
                statistics.shots_on_target,
                _decimal_or_none(statistics.expected_goals),
                statistics.corners,
                statistics.yellow_cards,
                statistics.red_cards,
                statistics.fouls,
                statistics.offsides,
                fingerprint,
                canonical_json(statistics),
            ),
        )

    def _insert_lineup(
        self,
        item: _MatchAppend,
        side: TeamSide,
        lineup: NormalizedHistoricalLineup,
    ) -> None:
        fingerprint = sha256_fingerprint({
            "match_fingerprint": item.prepared.match_fingerprint,
            "team_side": side.value,
            "lineup": lineup,
        })
        self._connection.execute(
            """
            INSERT INTO historical_lineups (
                lineup_id,historical_match_id,team_side,formation,
                starting_xi_snapshot,substitutes_snapshot,starting_xi_count,
                substitute_count,lineup_fingerprint,normalized_lineup_snapshot
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                f"historical-lineup-{fingerprint}",
                item.historical_match_id,
                side.value,
                lineup.formation,
                canonical_json(lineup.starting_xi),
                canonical_json(lineup.substitutes),
                len(lineup.starting_xi),
                len(lineup.substitutes),
                fingerprint,
                canonical_json(lineup),
            ),
        )

    def _replay_result(self, row: sqlite3.Row) -> HistoricalImportResult:
        fingerprints = tuple(json.loads(row["match_fingerprint_snapshot"]))
        ids = tuple(
            self._connection.execute(
                "SELECT historical_match_id FROM historical_matches WHERE match_fingerprint=?",
                (fingerprint,),
            ).fetchone()[0]
            for fingerprint in fingerprints
        )
        return HistoricalImportResult(
            import_id=row["import_id"],
            status=HistoricalImportStatus.IDEMPOTENT_REPLAY,
            provider=row["provider"],
            dataset_id=row["dataset_id"],
            dataset_version=row["dataset_version"],
            dataset_fingerprint=row["dataset_fingerprint"],
            supplied_match_count=row["supplied_match_count"],
            inserted_match_count=0,
            reused_match_count=row["supplied_match_count"],
            historical_match_ids=ids,
            import_timestamp=row["import_timestamp"],
            policy_version=row["policy_version"],
        )

    def _stored_result(self, row: sqlite3.Row) -> HistoricalImportResult:
        fingerprints = tuple(json.loads(row["match_fingerprint_snapshot"]))
        ids = tuple(
            self._connection.execute(
                "SELECT historical_match_id FROM historical_matches WHERE match_fingerprint=?",
                (fingerprint,),
            ).fetchone()[0]
            for fingerprint in fingerprints
        )
        return HistoricalImportResult(
            import_id=row["import_id"],
            status=HistoricalImportStatus.IMPORTED,
            provider=row["provider"],
            dataset_id=row["dataset_id"],
            dataset_version=row["dataset_version"],
            dataset_fingerprint=row["dataset_fingerprint"],
            supplied_match_count=row["supplied_match_count"],
            inserted_match_count=row["inserted_match_count"],
            reused_match_count=row["reused_match_count"],
            historical_match_ids=ids,
            import_timestamp=row["import_timestamp"],
            policy_version=row["policy_version"],
        )


def _historical_import_id(fingerprint: str) -> str:
    return f"historical-import-{fingerprint}"


def _historical_match_id(prepared: PreparedHistoricalMatch, version: int) -> str:
    return (
        f"historical-match-{prepared.logical_identity_fingerprint[:16]}-"
        f"v{version:06d}-{prepared.match_fingerprint[:16]}"
    )


def _decimal_or_none(value: Decimal | None) -> str | None:
    return canonical_decimal(value) if value is not None else None


def _stored_match(row: sqlite3.Row) -> StoredHistoricalMatch:
    return StoredHistoricalMatch(
        historical_match_id=row["historical_match_id"],
        import_id=row["import_id"],
        logical_identity_fingerprint=row["logical_identity_fingerprint"],
        match_fingerprint=row["match_fingerprint"],
        match_version=row["match_version"],
        source_provider=row["source_provider"],
        source_match_id=row["source_match_id"],
        competition=row["competition"],
        season=row["season"],
        round=row["competition_round"],
        kickoff_utc=row["kickoff_utc"],
        home_team=row["home_team"],
        away_team=row["away_team"],
        full_time_home_score=row["full_time_home_score"],
        full_time_away_score=row["full_time_away_score"],
        full_time_result=FullTimeResult(row["full_time_result"]),
    )


def _stored_statistics(row: sqlite3.Row) -> StoredHistoricalStatistics:
    statistics = NormalizedHistoricalStatistics(
        possession=_stored_decimal(row["possession"]),
        shots=row["shots"],
        shots_on_target=row["shots_on_target"],
        expected_goals=_stored_decimal(row["expected_goals"]),
        corners=row["corners"],
        yellow_cards=row["yellow_cards"],
        red_cards=row["red_cards"],
        fouls=row["fouls"],
        offsides=row["offsides"],
    )
    return StoredHistoricalStatistics(
        row["historical_match_id"],
        TeamSide(row["team_side"]),
        statistics,
        row["statistics_fingerprint"],
    )


def _stored_lineup(row: sqlite3.Row) -> StoredHistoricalLineup:
    lineup = NormalizedHistoricalLineup(
        tuple(json.loads(row["starting_xi_snapshot"])),
        tuple(json.loads(row["substitutes_snapshot"])),
        row["formation"],
    )
    return StoredHistoricalLineup(
        row["historical_match_id"],
        TeamSide(row["team_side"]),
        lineup,
        row["lineup_fingerprint"],
    )


def _stored_decimal(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.rollback()
