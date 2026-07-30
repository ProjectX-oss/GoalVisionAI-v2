"""Composition over the existing snapshot, feature, inference, calibration and EV services."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from app.calibrated_market_probabilities import (
    CalibrationRegistry,
    CalibrationSetDefinition,
    CalibrationTargetMapping,
    ExistingProbabilityCalibrationEngineFactory,
    SQLiteCalibratedMarketProbabilityRepository,
    build_calibrated_market_probability_service,
)
from app.calibrated_market_probabilities.policy import (
    DEFAULT_CALIBRATED_MARKET_PROBABILITY_POLICY,
)
from app.database import Database
from app.feature_store import SCHEMA_VERSION as FEATURE_SCHEMA_VERSION
from app.feature_store import build_feature_store_service
from app.historical_model_training import (
    SQLiteHistoricalModelTrainingRepository,
    predict_raw_probabilities,
)
from app.historical_probability_calibration import (
    SQLiteHistoricalProbabilityCalibrationRepository,
    to_runtime_calibration_artifacts,
)
from app.historical_training_dataset import SQLiteHistoricalTrainingDatasetRepository
from app.market_value_assessment import (
    MarketMappingRegistry,
    MarketSelection,
    MarketStatus,
    MarketType,
    SQLiteMarketValueAssessmentRepository,
    SuppliedOddsSnapshot,
    build_market_value_assessment_service,
)
from app.market_value_assessment.policy import DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY
from app.match_data_snapshot import (
    SQLiteMatchDataSnapshotRepository,
    build_match_data_snapshot_service,
)
from app.model_activation import ActivationStatus, build_runtime_champion_resolver
from app.model_input_builder import build_model_input_builder
from app.prediction_inference import (
    DEFAULT_PREDICTION_INFERENCE_POLICY,
    MissingValueSupport,
    ModelAdapterOutput,
    OFFICIAL_TARGET_ORDER,
    PredictionModelRegistry,
    SQLitePredictionInferenceRepository,
    build_prediction_inference_service,
)

from .models import EngineEvidence, MarketEvaluation, RealMatchLabInput
from .policy import LabSelectionPolicy


class EngineRejected(RuntimeError):
    def __init__(self, reason_code: str, explanation: str) -> None:
        super().__init__(explanation)
        self.reason_code = reason_code


class ApprovedChampionAdapter:
    """Safe persisted-parameter adapter; it performs no artifact discovery."""

    def __init__(self, artifact) -> None:
        self.artifact = artifact
        self.model_artifact_id = artifact.artifact_id
        self.model_name = "approved-historical-logistic"
        self.model_version = artifact.artifact_id
        self.model_family = artifact.model_family
        self.input_schema_name = "goalvision_model_input"
        self.input_schema_version = "v1"
        self.compatibility_version = "official_prediction_model_input_v1"
        self.supported_targets = OFFICIAL_TARGET_ORDER
        self.missing_value_support = MissingValueSupport.OPTIONAL_FEATURES

    def validate_compatibility(self, model_input) -> None:
        if (
            self.artifact.feature_schema_version != model_input.schema_version
            or self.artifact.ordered_feature_names != model_input.ordered_feature_names
        ):
            raise ValueError(
                "Approved champion feature schema is incompatible with the live model input."
            )

    def infer(self, model_input):
        prediction = predict_raw_probabilities(
            self.artifact, model_input.ordered_feature_values,
            model_input.missingness_mask,
            feature_schema_version=self.artifact.feature_schema_version,
            feature_schema_fingerprint=self.artifact.feature_schema_fingerprint,
            ordered_feature_names=model_input.ordered_feature_names,
        )
        return tuple(
            ModelAdapterOutput(item.target, item.probability)
            for item in prediction.raw_probabilities.ordered_probabilities
        )


class RealDomainAnalysisEngine:
    """Run the real domain stack. Every unavailable boundary rejects safely."""

    def __init__(self, database: Database, policy: LabSelectionPolicy) -> None:
        self.database = database
        self.policy = policy

    def analyze(self, command: RealMatchLabInput, now: datetime) -> EngineEvidence:
        snapshot_service = build_match_data_snapshot_service(self.database)
        snapshot_outcome = snapshot_service.register_match_data_snapshot(
            command.match_snapshot
        )
        if snapshot_outcome.snapshot_id is None:
            raise EngineRejected(
                "MATCH_SNAPSHOT_REJECTED",
                "Immutable match snapshot validation or persistence failed.",
            )
        snapshot_repo = SQLiteMatchDataSnapshotRepository(self.database, migrate=False)
        snapshot = snapshot_repo.find_snapshot_by_id(snapshot_outcome.snapshot_id)
        if snapshot is None:
            raise EngineRejected("MATCH_SNAPSHOT_MISSING", "Persisted snapshot is unavailable.")

        feature_outcome = build_feature_store_service(
            self.database
        ).generate_match_feature_set(
            snapshot, schema_version=FEATURE_SCHEMA_VERSION,
            feature_timestamp=command.collected_at,
        )
        if feature_outcome.feature_set is None:
            raise EngineRejected(
                "FEATURE_STORE_REJECTED", "Feature Store rejected the supplied facts."
            )
        features = feature_outcome.feature_set
        input_outcome = build_model_input_builder(
            self.database
        ).generate_model_input(features)
        if input_outcome.model_input is None:
            raise EngineRejected(
                "MODEL_INPUT_REJECTED", "Model-input construction failed safely."
            )
        model_input = input_outcome.model_input

        resolution = build_runtime_champion_resolver(
            self.database, migrate=False
        ).resolve(command.scope)
        if (
            resolution.status is not ActivationStatus.CHAMPION_RESOLVED
            or resolution.champion_generation is None
        ):
            raise EngineRejected(
                "CHAMPION_NOT_RESOLVED",
                "The approved champion cannot be resolved safely.",
            )
        reference = resolution.champion_generation.artifact
        model_repo = SQLiteHistoricalModelTrainingRepository(
            self.database, migrate=False
        )
        artifact = model_repo.load_model_artifact(reference.model_artifact_id)
        if artifact is None or artifact.artifact_fingerprint != reference.model_artifact_fingerprint:
            raise EngineRejected("MODEL_PROVENANCE_MISMATCH", "Champion model differs from activation provenance.")
        adapter = ApprovedChampionAdapter(artifact)
        try:
            adapter.validate_compatibility(model_input)
        except ValueError as exc:
            raise EngineRejected("MODEL_INPUT_SCHEMA_INCOMPATIBLE", str(exc)) from exc

        inference_repo = SQLitePredictionInferenceRepository(self.database)
        registry = PredictionModelRegistry(
            DEFAULT_PREDICTION_INFERENCE_POLICY
        ).register(adapter, active_official=True)
        inference_service = build_prediction_inference_service(
            inference_repo, registry, DEFAULT_PREDICTION_INFERENCE_POLICY
        )
        inference_outcome = inference_service.generate_raw_prediction(
            model_input, model_artifact_id=artifact.artifact_id,
            inference_timestamp=now,
        )
        if inference_outcome.inference_id is None:
            raise EngineRejected(
                "INFERENCE_REJECTED",
                "Approved model inference failed the canonical probability contract.",
            )
        inference = inference_repo.load_inference_by_id(inference_outcome.inference_id)

        historical_cal_repo = SQLiteHistoricalProbabilityCalibrationRepository(
            self.database, migrate=False
        )
        historical_set = historical_cal_repo.load_calibration_artifact_set(
            reference.calibration_artifact_set_id
        )
        if (
            historical_set is None
            or historical_set.artifact_set_fingerprint
            != reference.calibration_artifact_set_fingerprint
        ):
            raise EngineRejected(
                "CALIBRATION_PROVENANCE_MISMATCH",
                "Champion calibration differs from activation provenance.",
            )
        calibration_run = historical_cal_repo.load_calibration_run(
            historical_set.calibration_run_id
        )
        training_examples = SQLiteHistoricalTrainingDatasetRepository(
            self.database, migrate=False
        )
        runtime_artifacts = tuple(
            replace(item, active=True)
            for item in to_runtime_calibration_artifacts(
                historical_set, calibration_run.predictions, training_examples
            )
        )
        calibration_policy = DEFAULT_CALIBRATED_MARKET_PROBABILITY_POLICY
        mappings = tuple(
            CalibrationTargetMapping(item.target, item.artifact_id)
            for item in runtime_artifacts
        )
        definition = CalibrationSetDefinition(
            historical_set.artifact_set_id, "approved-champion", "v1",
            artifact.artifact_id, (artifact.artifact_id,), mappings,
            calibration_policy.version, True, now, now,
            historical_set.artifact_set_fingerprint,
        )
        calibration_registry = CalibrationRegistry(
            calibration_policy, runtime_artifacts, (definition,)
        )
        calibrated_repo = SQLiteCalibratedMarketProbabilityRepository(self.database)
        calibrated_service = build_calibrated_market_probability_service(
            inference_repo, calibration_registry, calibrated_repo, calibrated_repo,
            ExistingProbabilityCalibrationEngineFactory(), calibration_policy,
        )
        calibrated_outcome = calibrated_service.generate(
            inference, calibration_effective_timestamp=now,
            calibration_set_id=historical_set.artifact_set_id,
        )
        if calibrated_outcome.calibrated_assembly_id is None:
            raise EngineRejected(
                "CALIBRATION_REJECTED", "Calibrated market assembly failed safely."
            )
        assembly = calibrated_repo.load_assembly_by_id(
            calibrated_outcome.calibrated_assembly_id
        )

        value_repo = SQLiteMarketValueAssessmentRepository(self.database)
        value_service = build_market_value_assessment_service(
            value_repo, value_repo, MarketMappingRegistry(),
            DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY,
        )
        evaluations = []
        raw_by_target = {
            item.target.value: item.probability
            for item in inference.raw_probabilities.ordered_probabilities
        }
        for supplied in command.odds:
            market_type, selection, line = _market_identity(supplied.market)
            odds = SuppliedOddsSnapshot(
                supplied.snapshot_id, supplied.source_provider,
                supplied.bookmaker_id, supplied.source_event_id,
                command.match_id, market_type, selection, line,
                supplied.decimal_odds, supplied.captured_at, supplied.captured_at,
                command.collected_at, command.kickoff_utc, False,
                MarketStatus.OPEN, False, True,
            )
            outcome = value_service.assess(assembly, odds, now)
            if outcome.value_assessment_id is None:
                raise EngineRejected(
                    "VALUE_ASSESSMENT_REJECTED",
                    f"Value assessment rejected market {supplied.market}.",
                )
            stored = value_repo.load_assessment_by_id(outcome.value_assessment_id)
            evaluations.append(MarketEvaluation(
                market=supplied.market,
                raw_probability=raw_by_target[supplied.market],
                calibrated_probability=stored.fair_probability,
                fair_odds=stored.fair_decimal_odds,
                bookmaker_odds=stored.bookmaker_decimal_odds,
                implied_probability=stored.implied_probability,
                edge=stored.absolute_probability_edge,
                expected_value=stored.expected_value,
                confidence=_confidence(stored.fair_probability),
                freshness=stored.overall_freshness.value,
                selected=False,
                official_minimum_odds_pass=(
                    stored.bookmaker_decimal_odds >= self.policy.official_minimum_odds
                ),
                official_quality_gate_pass=False,
                rejection_reasons=(
                    () if stored.actionability_status.value == "ACTIONABLE"
                    else (stored.actionability_status.value,)
                ),
                odds_fingerprint=stored.odds_fingerprint,
                value_assessment_id=stored.value_assessment_id,
            ))
        selected_evaluations, _ = self.policy.select(tuple(evaluations))
        return EngineEvidence(
            snapshot.snapshot_id, features.feature_set_id,
            features.feature_fingerprint, model_input.model_input_id,
            model_input.model_input_fingerprint, artifact.artifact_id,
            artifact.artifact_fingerprint, historical_set.artifact_set_id,
            historical_set.artifact_set_fingerprint, inference.inference_id,
            inference.inference_fingerprint, assembly.calibrated_assembly_id,
            selected_evaluations,
            max(0, int((now - features.feature_timestamp).total_seconds())),
            _lineup_status(command), _reasoning(command),
        )


def _market_identity(market):
    if market in {"HOME_WIN", "DRAW", "AWAY_WIN"}:
        return MarketType.MATCH_WINNER, {
            "HOME_WIN": MarketSelection.HOME,
            "DRAW": MarketSelection.DRAW,
            "AWAY_WIN": MarketSelection.AWAY,
        }[market], None
    if market.startswith(("OVER_", "UNDER_")):
        side, major, minor = market.split("_")
        return MarketType.TOTALS, MarketSelection(side), Decimal(f"{major}.{minor}")
    return MarketType.BTTS, (
        MarketSelection.YES if market == "BTTS_YES" else MarketSelection.NO
    ), None


def _confidence(probability):
    if probability >= Decimal("0.70"):
        return "⭐⭐⭐⭐⭐"
    if probability >= Decimal("0.60"):
        return "⭐⭐⭐⭐"
    if probability >= Decimal("0.52"):
        return "⭐⭐⭐"
    return "⭐⭐"


def _lineup_status(command):
    home = command.match_snapshot.home_availability
    away = command.match_snapshot.away_availability
    if home and away and home.confirmed_lineup and away.confirmed_lineup:
        return "CONFIRMED"
    if home or away:
        return "PARTIAL_OR_PROBABLE"
    return "NOT_AVAILABLE"


def _reasoning(command):
    home = command.match_snapshot.home_recent_form
    away = command.match_snapshot.away_recent_form
    home_ppm = Decimal(3 * home.wins + home.draws) / Decimal(home.match_count)
    away_ppm = Decimal(3 * away.wins + away.draws) / Decimal(away.match_count)
    facts = []
    if home_ppm != away_ppm:
        side = command.home_team if home_ppm > away_ppm else command.away_team
        facts.append(f"{side} has the stronger supplied recent points rate")
    if home.goals_scored != away.goals_scored:
        side = command.home_team if home.goals_scored > away.goals_scored else command.away_team
        facts.append(f"{side} has the stronger supplied recent scoring total")
    facts.append(f"lineup information is {_lineup_status(command).lower()}")
    return tuple(facts)
