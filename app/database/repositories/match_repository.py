import sqlite3

from app.models import Match


class MatchRepository:

    def __init__(self, connection: sqlite3.Connection):

        self.connection = connection

    def save(
        self,
        match: Match,
    ):

        self.connection.execute(

            """
            INSERT OR REPLACE INTO matches(

                fixture_id,
                league_id,
                league_name,
                season,

                home_team_id,
                home_team_name,

                away_team_id,
                away_team_name,

                kickoff,
                status

            )

            VALUES(
                ?,?,?,?,?,?,?,?,?,?
            )
            """,

            (

                match.fixture_id,
                match.league_id,
                match.league_name,
                match.season,

                match.home_team_id,
                match.home_team_name,

                match.away_team_id,
                match.away_team_name,

                match.kickoff.isoformat(),

                match.status,

            ),

        )

        self.connection.commit()

    def all(self):

        cursor = self.connection.execute(

            """
            SELECT *

            FROM matches
            """
        )

        return cursor.fetchall()