from datetime import datetime
from decimal import Decimal

from app.database import Database, MigrationManager

from .models import HistoricalMatchObservation


class SQLiteFormFeatureRepository:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._connection = database.connection
        MigrationManager(self._connection).migrate()

    def save_source(
        self,
        source_id: str,
        source_name: str,
        *,
        enabled: bool = True,
    ) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO form_feature_sources (
                    source_id, source_name, enabled
                ) VALUES (?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    source_name=excluded.source_name,
                    enabled=excluded.enabled
                """,
                (source_id, source_name, int(enabled)),
            )

    def source_enabled(self, source_name: str) -> bool | None:
        row = self._connection.execute(
            """
            SELECT enabled FROM form_feature_sources
            WHERE lower(source_name) = lower(?) OR source_id = ?
            """,
            (source_name, source_name),
        ).fetchone()
        return bool(row["enabled"]) if row else None

    def insert(self, item: HistoricalMatchObservation) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO historical_match_observations (
                    fixture_id, competition, kickoff_time,
                    home_team_id, away_team_id, home_goals, away_goals,
                    match_status, observed_at, home_xg, away_xg,
                    home_shots, away_shots, home_red_cards, away_red_cards,
                    penalties, source_name, source_reference, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING
                """,
                (
                    item.fixture_id,
                    item.competition,
                    item.kickoff_time.isoformat(),
                    item.home_team_id,
                    item.away_team_id,
                    item.home_goals,
                    item.away_goals,
                    item.match_status,
                    item.observed_at.isoformat(),
                    _decimal(item.home_xg),
                    _decimal(item.away_xg),
                    item.home_shots,
                    item.away_shots,
                    item.home_red_cards,
                    item.away_red_cards,
                    item.penalties,
                    item.source_name,
                    item.source_reference,
                    item.created_at.isoformat(),
                ),
            )
        return cursor.rowcount == 1

    def history(
        self,
        team_id: str,
        *,
        cutoff: datetime,
        competition: str | None = None,
        completed_only: bool = True,
    ) -> tuple[HistoricalMatchObservation, ...]:
        clauses = [
            "(home_team_id = ? OR away_team_id = ?)",
            "kickoff_time < ?",
            "observed_at <= ?",
        ]
        values: list[object] = [
            team_id,
            team_id,
            cutoff.isoformat(),
            cutoff.isoformat(),
        ]
        if competition is not None:
            clauses.append("competition = ?")
            values.append(competition)
        if completed_only:
            clauses.append("match_status IN ('FT', 'AET', 'PEN')")
        rows = self._connection.execute(
            f"""
            SELECT * FROM historical_match_observations
            WHERE {' AND '.join(clauses)}
            ORDER BY kickoff_time, fixture_id, observed_at, source_name
            """,
            tuple(values),
        )
        return tuple(_observation(row) for row in rows)


def _decimal(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def _observation(row) -> HistoricalMatchObservation:
    return HistoricalMatchObservation(
        fixture_id=row["fixture_id"],
        competition=row["competition"],
        kickoff_time=datetime.fromisoformat(row["kickoff_time"]),
        home_team_id=row["home_team_id"],
        away_team_id=row["away_team_id"],
        home_goals=row["home_goals"],
        away_goals=row["away_goals"],
        match_status=row["match_status"],
        observed_at=datetime.fromisoformat(row["observed_at"]),
        home_xg=Decimal(row["home_xg"]) if row["home_xg"] is not None else None,
        away_xg=Decimal(row["away_xg"]) if row["away_xg"] is not None else None,
        home_shots=row["home_shots"],
        away_shots=row["away_shots"],
        home_red_cards=row["home_red_cards"],
        away_red_cards=row["away_red_cards"],
        penalties=row["penalties"],
        source_name=row["source_name"],
        source_reference=row["source_reference"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )
