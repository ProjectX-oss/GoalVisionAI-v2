import sqlite3
from pathlib import Path


class Database:

    def __init__(self):

        Path("data").mkdir(exist_ok=True)

        self.connection = sqlite3.connect(
            "data/goalvision.db"
        )

        self.connection.row_factory = sqlite3.Row

    def cursor(self):
        return self.connection.cursor()

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()