from app.feature_store import FEATURE_DEFINITIONS

from .models import ModelInputFeatureMetadata, ModelInputSchema
from .policy import DEFAULT_MODEL_INPUT_BUILDER_POLICY, ModelInputBuilderPolicy


REQUIRED_BASELINE_FEATURES = frozenset({
    "home_recent_points_per_match",
    "away_recent_points_per_match",
    "home_recent_goals_scored_per_match",
    "away_recent_goals_scored_per_match",
    "home_recent_goals_conceded_per_match",
    "away_recent_goals_conceded_per_match",
})


def build_model_input_schema(
    policy: ModelInputBuilderPolicy = DEFAULT_MODEL_INPUT_BUILDER_POLICY,
) -> ModelInputSchema:
    """Build the immutable v1 schema from the Feature Store registry order."""
    metadata = tuple(
        ModelInputFeatureMetadata(
            index=index,
            name=definition.name,
            value_type=definition.value_type,
            description=definition.description,
            required_baseline=definition.name in REQUIRED_BASELINE_FEATURES,
            source_feature_schema=(
                f"{policy.source_feature_schema_name}_"
                f"{policy.source_feature_schema_version}"
            ),
        )
        for index, definition in enumerate(FEATURE_DEFINITIONS)
    )
    return ModelInputSchema(
        name=policy.schema_name,
        version=policy.schema_version,
        identifier=policy.schema_identifier,
        compatibility_version=policy.compatibility_version,
        source_feature_schema_name=policy.source_feature_schema_name,
        source_feature_schema_version=policy.source_feature_schema_version,
        ordered_feature_metadata=metadata,
    )


GOALVISION_MODEL_INPUT_V1 = build_model_input_schema()
