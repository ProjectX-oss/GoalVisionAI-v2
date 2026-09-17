from .database import Database


class HistoryRepository:

    def __init__(self):

        self.db = Database()

    def create_table(self):

        cursor = self.db.cursor()

        cursor.execute("""

        CREATE TABLE IF NOT EXISTS history_predictions(

            fixture_id INTEGER PRIMARY KEY,

            league TEXT,

            home_team TEXT,

            away_team TEXT,

            predicted_winner TEXT,

            home_probability REAL,

            away_probability REAL,

            confidence TEXT,

            algorithm_version TEXT,

            created_at TEXT,

            result_checked INTEGER DEFAULT 0,

            winner_correct INTEGER DEFAULT 0

        )

        """)

        self.db.commit()

    def save(self, prediction):

        cursor = self.db.cursor()

        cursor.execute("""

        INSERT OR REPLACE INTO history_predictions(

            fixture_id,

            league,

            home_team,

            away_team,

            predicted_winner,

            home_probability,

            away_probability,

            confidence,

            algorithm_version,

            created_at

        )

        VALUES(

            ?,?,?,?,?,?,?,?,?,?

        )

        """,(

            prediction.fixture_id,

            prediction.league,

            prediction.home_team,

            prediction.away_team,

            prediction.predicted_winner,

            prediction.home_probability,

            prediction.away_probability,

            prediction.confidence,

            prediction.algorithm_version,

            prediction.created_at.isoformat()

        ))

        self.db.commit()