import sqlite3

from app.models import Prediction


class PredictionRepository:

    def __init__(
        self,
        connection: sqlite3.Connection,
    ):

        self.connection = connection

    def save(
        self,
        prediction: Prediction,
    ):

        self.connection.execute(

            """
            INSERT OR REPLACE INTO predictions(

                fixture_id,

                winner,

                home_probability,

                away_probability,

                confidence,

                rating_difference,

                created_at

            )

            VALUES(

                ?,?,?,?,?,?,

                datetime('now')

            )
            """,

            (

                prediction.fixture_id,

                prediction.winner,

                prediction.home_probability,

                prediction.away_probability,

                prediction.confidence,

                prediction.rating_difference,

            ),

        )

        self.connection.commit()