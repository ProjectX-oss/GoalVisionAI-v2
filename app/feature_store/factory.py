from app.database import Database
from app.match_data_snapshot import SQLiteMatchDataSnapshotRepository

from .extractors import OfficialPrematchFeatureExtractor
from .fingerprint import FeatureSetFingerprint
from .policy import DEFAULT_FEATURE_STORE_POLICY, FeatureStorePolicy
from .repository import SQLiteFeatureStoreRepository
from .service import FeatureStoreService
from .validation import FeatureStoreValidator


def build_feature_store_service(
    database: Database,
    *,
    policy: FeatureStorePolicy = DEFAULT_FEATURE_STORE_POLICY,
) -> FeatureStoreService:
    """Compose the feature store without model or provider integration."""
    return FeatureStoreService(
        SQLiteFeatureStoreRepository(database),
        SQLiteMatchDataSnapshotRepository(database, migrate=False),
        OfficialPrematchFeatureExtractor(policy),
        FeatureStoreValidator(policy),
        FeatureSetFingerprint(),
        policy,
    )
