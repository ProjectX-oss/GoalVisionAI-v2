"""Composition over the existing snapshot, feature, inference, calibration and EV services."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from app.calibrated_market_probabilities import (
    CalibrationSetDefinition,
    CalibrationTargetMapping,
    SQLiteCalibratedMarketProbabilityRepository,
)
from app.calibration_freshness import (
    CalibrationActionabilityStatus,
    DEFAULT_CALIBRATION_FRESHNESS_POLICY,
    assess_calibration_freshness,
)
from app.calibration_quality_review import (
    build_calibration_quality_report,
    market_quality_reasons,
)
from app.calibrated_market_probabilities.fingerprint import (
    assembly_fingerprint,
    target_result_fingerprint,
)
from app.calibrated_market_probabilities.models import (
    CalibratedMarketProbabilityAssembly,
    CalibratedTargetResult,
)
from app.calibrated_market_probabilities.validation import CalibratedAssemblyValidator
from app.calibrated_market_probabilities.policy import (
    DEFAULT_CALIBRATED_MARKET_PROBABILITY_POLICY,
)
from app.database import Database
from app.feature_store import SCHEMA_VERSION as FEATURE_SCHEMA_VERSION
from app.feature_store import build_feature_store_service
from app.historical_model_training import (
    LIVE_TRAINING_FEATURE_CONTRACT,
    SQLiteHistoricalModelTrainingRepository,
    predict_raw_probabilities,
    verify_feature_compatibility,
)
from app.historical_probability_calibration import (
    DEFAULT_HISTORICAL_CALIBRATION_POLICY,
    SQLiteHistoricalProbabilityCalibrationRepository,
    ValidationPrediction,
    to_runtime_calibration_artifacts,
)
from app.historical_probability_calibration.artifact import apply_calibration
from app.historical_dataset_split import Partition
from app.historical_model_training.fingerprint import sha256_fingerprint
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
from app.match_data_snapshot import (
    SQLiteMatchDataSnapshotRepository,
    build_match_data_snapshot_service,
)
from app.model_activation import ActivationStatus, build_runtime_champion_resolver
from app.model_activation_audit import ModelActivationAuditService
from app.model_activation_audit.repository import ReadOnlyAuditRepository
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
from .policy import (
    LAB_MARKET_VALUE_ASSESSMENT_POLICY,
    SUPPORTED_MARKETS,
    LabSelectionPolicy,
)


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
            or self.artifact.feature_schema_fingerprint
            != LIVE_TRAINING_FEATURE_CONTRACT.schema_fingerprint
            or self.artifact.ordered_feature_names != model_input.ordered_feature_names
            or len(model_input.ordered_feature_names)
            != LIVE_TRAINING_FEATURE_CONTRACT.feature_count
        ):
            raise ValueError(
                "Approved champion feature schema is incompatible with the live model input."
            )
        failures = verify_feature_compatibility(
            self.artifact,
            LIVE_TRAINING_FEATURE_CONTRACT.schema_version,
            LIVE_TRAINING_FEATURE_CONTRACT.schema_fingerprint,
            LIVE_TRAINING_FEATURE_CONTRACT.ordered_feature_names,
        )
        if failures:
            raise ValueError(
                "Approved champion compatibility verification failed: "
                + "|".join(failures)
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
        if command.source_commit is None:
            raise EngineRejected(
                "CALIBRATION_REVIEW_MISSING",
                "A source commit is required for the independent Lab audit.",
            )
        audit_repository = ReadOnlyAuditRepository(str(self.database.path))
        try:
            audit = ModelActivationAuditService(audit_repository).audit(
                source_commit=command.source_commit,
                generated_timestamp_utc=now.isoformat(timespec="seconds").replace(
                    "+00:00", "Z"
                ),
                environment="LAB",
                scope=command.scope,
            )
        finally:
            audit_repository.close()
        if audit.overall_status.value != "AUDIT_PASSED":
            raise EngineRejected(
                "CALIBRATION_REVIEW_AUDIT_FAILED",
                "Independent activation audit did not pass.",
            )
        calibration_freshness = assess_calibration_freshness(
            self.database,
            historical_set,
            environment=command.environment,
            assessment_timestamp=now,
            review_timestamp=datetime.fromisoformat(
                audit.generated_timestamp_utc.replace("Z", "+00:00")
            ),
            policy=DEFAULT_CALIBRATION_FRESHNESS_POLICY,
        )
        if (
            calibration_freshness.actionability_status
            is not CalibrationActionabilityStatus.ACTIONABLE_FOR_LAB
        ):
            reason = (
                calibration_freshness.ordered_reason_codes[0]
                if calibration_freshness.ordered_reason_codes
                else "CALIBRATION_NON_ACTIONABLE"
            )
            raise EngineRejected(
                reason,
                "Calibration freshness validation failed closed: "
                + ", ".join(calibration_freshness.ordered_reason_codes),
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
        calibration_created_at = datetime.fromisoformat(
            historical_set.command.calibration_timestamp.replace("Z", "+00:00")
        )
        calibration_effective_at = calibration_freshness.evidence_timestamp
        if calibration_effective_at is None:
            raise EngineRejected(
                "CALIBRATION_EVIDENCE_TIMESTAMP_MISSING",
                "Calibration evidence timestamp is unavailable.",
            )
        definition = CalibrationSetDefinition(
            historical_set.artifact_set_id, "approved-champion", "v1",
            artifact.artifact_id, (artifact.artifact_id,), mappings,
            calibration_policy.version, True,
            calibration_created_at, calibration_effective_at,
            historical_set.artifact_set_fingerprint,
        )
        calibrated_repo = SQLiteCalibratedMarketProbabilityRepository(self.database)
        assembly = _persist_historical_calibrated_assembly(
            inference, historical_set, runtime_artifacts, definition,
            calibrated_repo, now, calibration_effective_at,
        )
        quality_report = build_calibration_quality_report(
            self.database, artifact, historical_set, calibration_run,
            inference.raw_probabilities, model_input,
            audit_status=audit.overall_status.value,
            freshness_status=calibration_freshness.actionability_status.value,
        )
        traces = {item.target: item for item in quality_report.traces}
        support = {item.target: item for item in quality_report.target_evidence}

        value_repo = SQLiteMarketValueAssessmentRepository(self.database)
        value_service = build_market_value_assessment_service(
            value_repo, value_repo, MarketMappingRegistry(),
            LAB_MARKET_VALUE_ASSESSMENT_POLICY,
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
            trace = traces[supplied.market]
            quality_reasons = market_quality_reasons(quality_report, trace)
            value_reasons = (
                () if stored.actionability_status.value == "ACTIONABLE"
                else (stored.actionability_status.value,)
            )
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
                rejection_reasons=tuple(dict.fromkeys((*value_reasons, *quality_reasons))),
                odds_fingerprint=stored.odds_fingerprint,
                value_assessment_id=stored.value_assessment_id,
                calibration_method=trace.method,
                absolute_calibration_adjustment=trace.absolute_adjustment,
                extreme_status=trace.extreme_status,
                calibration_support_status=support[supplied.market].support_status,
                distribution_shift_status=quality_report.distribution_shift.status.value,
                calibration_quality_outcome=(
                    "CALIBRATION_QUALITY_INELIGIBLE" if quality_reasons
                    else "CALIBRATION_QUALITY_ACCEPTABLE"
                ),
                actionable=not value_reasons and not quality_reasons,
            ))
        mathematical = tuple(sorted(
            (
                item for item in evaluations
                if item.expected_value > self.policy.minimum_expected_value
                and item.bookmaker_odds > Decimal("1")
            ),
            key=lambda item: (
                -item.calibrated_probability,
                -item.expected_value,
                SUPPORTED_MARKETS.index(item.market),
            ),
        ))
        ranks = {
            item.value_assessment_id: rank
            for rank, item in enumerate(mathematical, 1)
        }
        evaluations = [
            replace(item, mathematical_rank=ranks.get(item.value_assessment_id))
            for item in evaluations
        ]
        selected_evaluations, _ = self.policy.select(tuple(evaluations))
        feature_age = int((now - features.feature_timestamp).total_seconds())
        if feature_age < 0 or feature_age > self.policy.feature_snapshot_max_age_seconds:
            raise EngineRejected("FEATURE_SNAPSHOT_STALE", "Feature snapshot is not fresh.")
        lineup_freshness = _lineup_freshness(command, now, self.policy.lineup_snapshot_max_age_seconds)
        if lineup_freshness == "STALE":
            raise EngineRejected("LINEUP_DATA_STALE", "Supplied lineup-sensitive data is stale.")
        return EngineEvidence(
            snapshot.snapshot_id, features.feature_set_id,
            features.feature_fingerprint, model_input.model_input_id,
            model_input.model_input_fingerprint, artifact.artifact_id,
            artifact.artifact_fingerprint, historical_set.artifact_set_id,
            historical_set.artifact_set_fingerprint, inference.inference_id,
            inference.inference_fingerprint, assembly.calibrated_assembly_id,
            selected_evaluations,
            feature_age,
            _lineup_status(command), _reasoning(command),
            calibration_freshness, "FRESH", lineup_freshness,
            audit.overall_status.value, audit.audit_fingerprint,
            quality_report,
            mathematical[0].market if mathematical else None,
            quality_report.send_eligible,
        )


def _persist_historical_calibrated_assembly(
    inference, historical_set, runtime_artifacts, definition, repository, now,
    calibration_effective_at,
):
    """Apply the persisted historical parameters, including reconciliation."""
    temporary = ValidationPrediction(
        training_example_id=f"runtime:{inference.match_id}",
        example_fingerprint=inference.model_input_fingerprint,
        artifact_id=inference.model_artifact_id,
        artifact_fingerprint=inference.inference_fingerprint,
        training_run_id="runtime-inference",
        split_id="runtime-inference",
        fold_id="runtime-inference",
        partition=Partition.VALIDATION,
        raw_probabilities=inference.raw_probabilities,
        calibrated_probabilities=None,
        raw_prediction_fingerprint=inference.inference_fingerprint,
    )
    calibrated = apply_calibration(
        temporary,
        historical_set.target_artifacts,
        DEFAULT_HISTORICAL_CALIBRATION_POLICY,
    ).calibrated_probabilities
    artifacts = {item.target: item for item in runtime_artifacts}
    diagnostics = (
        "PERSISTED_HISTORICAL_CALIBRATION_APPLIED",
        "CANONICAL_RECONCILIATION_APPLIED",
    )
    results = []
    for raw_item, calibrated_item in zip(
        inference.raw_probabilities.ordered_probabilities,
        calibrated.ordered_probabilities,
        strict=True,
    ):
        runtime = artifacts[raw_item.target]
        report_reference = sha256_fingerprint(
            (
                historical_set.artifact_set_fingerprint,
                runtime.quality_metadata_reference,
                inference.inference_fingerprint,
                raw_item.target.value,
                calibrated_item.probability,
            )
        )
        target_fingerprint = target_result_fingerprint(
            target=raw_item.target.value,
            raw=raw_item.probability,
            calibrated=calibrated_item.probability,
            artifact=runtime,
            report_reference=report_reference,
            diagnostics=diagnostics,
        )
        results.append(CalibratedTargetResult(
            raw_item.target,
            raw_item.probability,
            calibrated_item.probability,
            runtime.artifact_id,
            runtime.method,
            runtime.calibration_model_version,
            runtime.calibration_policy_version,
            report_reference,
            runtime.quality_metadata_reference,
            None,
            diagnostics,
            target_fingerprint,
        ))
    ordered = tuple(results)
    policy = DEFAULT_CALIBRATED_MARKET_PROBABILITY_POLICY
    validation = CalibratedAssemblyValidator().validate_outputs(ordered, policy)
    fingerprint = assembly_fingerprint(
        inference_id=inference.inference_id,
        raw_inference_fingerprint=inference.inference_fingerprint,
        model_artifact_id=inference.model_artifact_id,
        model_version=inference.model_version,
        calibration_identity=historical_set.artifact_set_fingerprint,
        targets=ordered,
        policy_version=policy.version,
        effective_timestamp=calibration_effective_at,
    )
    assembly = CalibratedMarketProbabilityAssembly(
        "calibrated-assembly-"
        + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest(),
        inference.inference_id,
        inference.model_input_id,
        inference.match_id,
        inference.source_snapshot_id,
        inference.source_feature_set_id,
        inference.model_artifact_id,
        inference.model_name,
        inference.model_version,
        inference.inference_fingerprint,
        historical_set.artifact_set_id,
        historical_set.artifact_set_fingerprint,
        policy.version,
        calibration_effective_at,
        now,
        ordered,
        validation,
        fingerprint,
    )
    repository.append_calibration_set(definition)
    stored, _ = repository.append_calibrated_assembly(assembly)
    return stored


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


def _lineup_freshness(command, now, maximum_age):
    timestamps = tuple(
        timestamp
        for availability in (
            command.match_snapshot.home_availability,
            command.match_snapshot.away_availability,
        )
        if availability is not None
        for timestamp in (availability.lineup_source_timestamp,)
        if timestamp is not None
    )
    if not timestamps:
        return "NOT_AVAILABLE"
    ages = tuple(int((now - value).total_seconds()) for value in timestamps)
    return "FRESH" if all(0 <= age <= maximum_age for age in ages) else "STALE"


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
