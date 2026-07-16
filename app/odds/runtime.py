from dataclasses import dataclass
from datetime import datetime, timezone

from app.database import Database

from .config import OddsIngestionConfig
from .ingestion import OddsIngestionService
from .models import OddsIngestionReport
from .providers import NullOddsProvider, OddsProvider
from .repository import SQLiteOddsRepository


@dataclass(slots=True)
class OddsIngestionRuntime:
    config: OddsIngestionConfig
    provider: OddsProvider
    database: Database | None = None

    def start(self) -> OddsIngestionReport | None:
        if not self.config.enabled:
            return None
        if self.database is None:
            self.database = Database()
        database = self.database
        repository = SQLiteOddsRepository(database)
        return OddsIngestionService(repository).ingest(
            (self.provider,),
            occurred_at=datetime.now(timezone.utc),
        )

    def close(self) -> None:
        if self.database is not None:
            self.database.close()


def build_odds_ingestion_runtime(
    config: OddsIngestionConfig | None = None,
    provider: OddsProvider | None = None,
    database: Database | None = None,
) -> OddsIngestionRuntime:
    return OddsIngestionRuntime(
        config=config or OddsIngestionConfig.from_environment(),
        provider=provider or NullOddsProvider(),
        database=database,
    )
