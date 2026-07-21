from datetime import timezone
from decimal import Decimal

from app.match_data_snapshot import (
    MatchDataSnapshotFingerprint,
    MatchSnapshotStatus,
    SnapshotLifecycleState,
)

from .definitions import FEATURE_DEFINITION_BY_NAME, FEATURE_DEFINITIONS
from .exceptions import FeatureValidationError, InvalidSourceSnapshotError, UnsupportedFeatureSchemaError
from .models import FeatureGenerationRequest, FeatureValue
from .policy import FeatureStorePolicy


class FeatureStoreValidator:
    def __init__(self, policy: FeatureStorePolicy) -> None:
        self.policy = policy

    def validate_request(
        self,
        request: FeatureGenerationRequest,
        current_state: SnapshotLifecycleState | None,
    ) -> None:
        if not self.policy.supports(request.schema_version):
            raise UnsupportedFeatureSchemaError("Unsupported feature schema.")
        if request.model_compatibility_version != self.policy.model_compatibility_version:
            raise UnsupportedFeatureSchemaError("Unsupported model compatibility version.")
        snapshot = request.snapshot
        command = snapshot.prepared.command
        if current_state is not SnapshotLifecycleState.ACTIVE and not request.historical_replay:
            raise InvalidSourceSnapshotError("Snapshot is not currently ACTIVE.")
        if command.scheduled_status is not MatchSnapshotStatus.SCHEDULED:
            raise InvalidSourceSnapshotError("Only scheduled pre-match snapshots can generate features.")
        if command.is_live or command.cancelled_indicator:
            raise InvalidSourceSnapshotError("Live or cancelled snapshots are unsupported.")
        if command.snapshot_effective_timestamp >= command.kickoff_timestamp:
            raise InvalidSourceSnapshotError("Snapshot is not pre-match.")
        if request.feature_timestamp.tzinfo is None or request.feature_timestamp.utcoffset() is None:
            raise InvalidSourceSnapshotError("Feature timestamp must be timezone-aware.")
        feature_time = request.feature_timestamp.astimezone(timezone.utc)
        if feature_time != command.snapshot_effective_timestamp:
            raise InvalidSourceSnapshotError(
                "Feature timestamp must equal immutable snapshot effective time."
            )
        if command.home_recent_form is None or command.away_recent_form is None:
            raise InvalidSourceSnapshotError("Both recent-form baselines are required.")
        expected = MatchDataSnapshotFingerprint().content(command)
        if expected != snapshot.content_fingerprint:
            raise InvalidSourceSnapshotError("Source snapshot fingerprint mismatch.")
        if not snapshot.logical_identity_fingerprint or len(snapshot.logical_identity_fingerprint) != 64:
            raise InvalidSourceSnapshotError("Snapshot logical identity is malformed.")

    @staticmethod
    def validate_features(values: tuple[FeatureValue, ...]) -> None:
        names = tuple(item.name for item in values)
        expected = tuple(item.name for item in FEATURE_DEFINITIONS)
        if names != expected:
            raise FeatureValidationError("Feature order differs from the schema registry.")
        for item in values:
            definition = FEATURE_DEFINITION_BY_NAME[item.name]
            value = item.value
            if value is None or definition.valid_range is None:
                continue
            numeric = Decimal(int(value)) if isinstance(value, bool) else Decimal(value)
            lower, upper = definition.valid_range
            if lower is not None and numeric < lower:
                raise FeatureValidationError(f"{item.name} is below its valid range.")
            if upper is not None and numeric > upper:
                raise FeatureValidationError(f"{item.name} is above its valid range.")
