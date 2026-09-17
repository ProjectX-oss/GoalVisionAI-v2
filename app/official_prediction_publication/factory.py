from collections.abc import Callable
from datetime import datetime

from app.database import Database, SQLitePredictionResultRepository

from .config import (
    DEFAULT_OFFICIAL_PREDICTION_MESSAGE_POLICY,
    OfficialPredictionMessagePolicy,
)
from .message_builder import OfficialPredictionMessageBuilder
from .models import OfficialPredictionDestination
from .ports import OfficialPredictionPublicFactsProvider, TelegramPredictionSender
from .publisher_adapter import OfficialPredictionPublisherAdapter
from .repository import SQLiteAtomicPredictionPublicationRepository


def build_official_prediction_publisher_adapter(
    database: Database,
    telegram: TelegramPredictionSender,
    public_facts: OfficialPredictionPublicFactsProvider,
    destination: OfficialPredictionDestination,
    clock: Callable[[], datetime],
    *,
    policy: OfficialPredictionMessagePolicy = (
        DEFAULT_OFFICIAL_PREDICTION_MESSAGE_POLICY
    ),
    enabled: bool = True,
) -> OfficialPredictionPublisherAdapter:
    """Build the concrete adapter without sending or scheduling anything."""
    return OfficialPredictionPublisherAdapter(
        messages=OfficialPredictionMessageBuilder(policy),
        facts=public_facts,
        publications=SQLiteAtomicPredictionPublicationRepository(database),
        telegram=telegram,
        published_predictions=SQLitePredictionResultRepository(
            database,
            migrate=False,
        ),
        destination=destination,
        clock=clock,
        enabled=enabled,
    )
