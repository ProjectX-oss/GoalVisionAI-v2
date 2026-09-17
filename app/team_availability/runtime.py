from dataclasses import dataclass
from datetime import datetime, timezone

from app.database import Database

from .config import TeamAvailabilityIngestionConfig
from .ingestion import AvailabilityIngestionService
from .models import AvailabilityIngestionReport
from .providers import AvailabilityProvider, NullAvailabilityProvider
from .repository import SQLiteTeamAvailabilityRepository


@dataclass(slots=True)
class TeamAvailabilityRuntime:
    config: TeamAvailabilityIngestionConfig
    provider: AvailabilityProvider
    database: Database | None = None

    def start(self) -> AvailabilityIngestionReport | None:
        if not self.config.enabled:
            return None
        if self.database is None:
            self.database = Database()
        repository = SQLiteTeamAvailabilityRepository(self.database)
        return AvailabilityIngestionService(repository).ingest(
            (self.provider,),
            occurred_at=datetime.now(timezone.utc),
        )

    def close(self) -> None:
        if self.database is not None:
            self.database.close()


def build_team_availability_runtime(
    config: TeamAvailabilityIngestionConfig | None = None,
    provider: AvailabilityProvider | None = None,
    database: Database | None = None,
) -> TeamAvailabilityRuntime:
    return TeamAvailabilityRuntime(
        config or TeamAvailabilityIngestionConfig.from_environment(),
        provider or NullAvailabilityProvider(),
        database,
    )
