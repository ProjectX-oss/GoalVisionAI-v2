from dataclasses import dataclass
from datetime import datetime, timezone

from app.database import Database

from .config import FormFeatureIngestionConfig
from .ingestion import HistoricalMatchIngestionService
from .models import FormFeatureReport
from .providers import HistoricalMatchProvider, NullHistoricalMatchProvider
from .repository import SQLiteFormFeatureRepository
from .normalization import normalize_identifier, normalize_source


@dataclass(slots=True)
class FormFeatureRuntime:
    config: FormFeatureIngestionConfig
    provider: HistoricalMatchProvider
    database: Database | None = None

    def start(self) -> FormFeatureReport | None:
        if not self.config.enabled:
            return None
        if self.database is None:
            self.database = Database()
        repository = SQLiteFormFeatureRepository(self.database)
        source_name = normalize_source(self.provider.source_name)
        repository.save_source(
            normalize_identifier(source_name, "Source ID"),
            source_name,
        )
        return HistoricalMatchIngestionService(repository).ingest(
            (self.provider,),
            evaluation_timestamp=datetime.now(timezone.utc),
        )

    def close(self) -> None:
        if self.database is not None:
            self.database.close()


def build_form_feature_runtime(
    config: FormFeatureIngestionConfig | None = None,
    provider: HistoricalMatchProvider | None = None,
    database: Database | None = None,
) -> FormFeatureRuntime:
    return FormFeatureRuntime(
        config or FormFeatureIngestionConfig.from_environment(),
        provider or NullHistoricalMatchProvider(),
        database,
    )
