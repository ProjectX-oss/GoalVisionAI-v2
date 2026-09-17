from app.models import Match, Prediction

from .database import Database


class Repository:

    def __init__(self):

        self.db = Database()

    def create_tables(self):

        cursor = self.db.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches(

            fixture_id INTEGER PRIMARY KEY,

            league_id INTEGER,

            league_name TEXT,

            season INTEGER,

            home_team_id INTEGER,

            home_team_name TEXT,

            away_team_id INTEGER,

            away_team_name TEXT,

            kickoff TEXT,

            status TEXT

        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions(

            fixture_id INTEGER PRIMARY KEY,

            winner TEXT,

            probability REAL,

            home_score REAL,

            away_score REAL,

            goals_pick TEXT,

            status TEXT,

            created_at TEXT

        )
        """)

        self.db.commit()

    def save_match(
        self,
        match: Match
    ):

        cursor = self.db.cursor()

        cursor.execute("""

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

        """, (

            match.fixture_id,

            match.league_id,

            match.league_name,

            match.season,

            match.home_team_id,

            match.home_team_name,

            match.away_team_id,

            match.away_team_name,

            match.kickoff.isoformat(),

            match.status

        ))

        self.db.commit()

    def save_prediction(
        self,
        prediction: Prediction
    ):

        cursor = self.db.cursor()

        cursor.execute("""

        INSERT OR REPLACE INTO predictions(

            fixture_id,

            winner,

            probability,

            home_score,

            away_score,

            goals_pick,

            status,

            created_at

        )

        VALUES(

            ?,?,?,?,?,?,

            'PENDING',

            datetime('now')

        )

        """, (

            prediction.fixture_id,

            prediction.winner,

            prediction.probability,

            prediction.home_score,

            prediction.away_score,

            prediction.goals_pick

        ))

        self.db.commit()