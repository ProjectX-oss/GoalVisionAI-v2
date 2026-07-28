"""Immutable evidence returned by the controlled real-artifact builder."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from app.model_activation import RuntimeArtifactReference


CONTROLLED_SOURCE_LABEL = "CONTROLLED_SYNTHETIC_STAGING_SOURCE"
CHAIN_SCHEMA_VERSION = "goalvision-controlled-staging-real-artifact-chain-v1"


@dataclass(frozen=True, slots=True)
class RealArtifactChainManifest:
    schema_version: str
    label: str
    model_scope: str
    source_import_id: str
    source_dataset_fingerprint: str
    source_match_count: int
    dataset_build_id: str
    dataset_fingerprint: str
    included_example_count: int
    split_id: str
    split_fingerprint: str
    fold_id: str
    fold_fingerprint: str
    train_count: int
    validation_count: int
    test_count: int
    champion_training_run_id: str
    challenger_training_run_id: str
    champion: RuntimeArtifactReference
    challenger: RuntimeArtifactReference
    champion_calibration_run_id: str
    challenger_calibration_run_id: str
    champion_backtest_run_id: str
    challenger_backtest_run_id: str
    champion_backtest_fingerprint: str
    challenger_backtest_fingerprint: str
    comparison_run_id: str
    comparison_run_fingerprint: str
    challenger_candidate_id: str
    recommendation_id: str
    recommendation_fingerprint: str
    promotion_recommendation: str
    promotion_score: str
    evidence_cutoff_timestamp_utc: str
    shadow_evidence_fingerprint: str
    settled_shadow_count: int
    observation_days: str
    chain_fingerprint: str

    def as_json(self) -> str:
        return json.dumps(
            asdict(self),
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
        )
