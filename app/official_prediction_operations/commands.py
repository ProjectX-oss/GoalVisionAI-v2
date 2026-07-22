"""Controlled commands over the real deterministic Official prediction services."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.calibrated_market_probabilities import (
    DEFAULT_CALIBRATED_MARKET_PROBABILITY_POLICY,
    CalibrationArtifact, CalibrationRegistry, CalibrationTargetMapping,
    ExistingProbabilityCalibrationEngineFactory,
    SQLiteCalibratedMarketProbabilityRepository,
    build_calibrated_market_probability_service,
    generate_calibrated_market_probabilities,
)
from app.database import Database
from app.feature_store import SCHEMA_IDENTIFIER, build_feature_store_service, generate_match_feature_set
from app.market_value_assessment import (
    DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY, MarketMappingRegistry, MarketSelection,
    MarketStatus, MarketType, SQLiteMarketValueAssessmentRepository,
    SuppliedOddsSnapshot, assess_market_value, build_market_value_assessment_service,
)
from app.match_data_snapshot import (
    FormRecord, HeadToHeadRecord, MatchContextRecord, MatchDataSnapshotRegistrationCommand,
    MatchSnapshotStatus, OddsContextRecord, SeasonAggregateRecord, TeamAvailabilityRecord,
    VenueSplitRecord, build_match_data_snapshot_service,
)
from app.model_input_builder import build_model_input_builder, generate_model_input
from app.official_candidate_preparation import (
    DEFAULT_OFFICIAL_CANDIDATE_PREPARATION_POLICY,
    OfficialBankrollPreparationContext, OfficialCandidatePreparationCommand,
    OfficialCandidateRegistrationFacts, OfficialExposurePreparationContext,
    SQLiteOfficialCandidatePreparationRepository, bankroll_context_fingerprint,
    build_official_candidate_preparation_service, exposure_context_fingerprint,
)
from app.official_prediction_candidate_registry import (
    CandidateLifecycleState, OfficialPredictionReasoningFact, ReasoningFactType,
    SQLiteOfficialCandidatePublicationGuard, SQLiteOfficialPredictionCandidateRepository,
    build_official_prediction_candidate_registry,
)
from app.official_prediction_orchestration import (
    ModelHealthRecord, OfficialCandidateAssemblyRequest, OfficialCandidateFingerprint,
    OfficialPredictionCandidateAssembler, OfficialPredictionFacts,
    OfficialPredictionOrchestrationService, SQLiteOfficialPublicationStateReader,
    SQLiteOrchestrationHistoryRepository,
)
from app.official_prediction_pipeline import (
    CandidateState, CandidateStateVerification,
    DEFAULT_OFFICIAL_PREDICTION_PIPELINE_POLICY, ExistingMessagePreviewAdapter,
    ExistingPreapprovedOrchestrationAdapter, ExistingPublicationStateAdapter,
    OfficialPredictionPipelineCommand, OfficialPredictionPipelineService,
    PersistedQualityGateAdapter, PipelinePublicationState, PublicationStateVerification,
    SQLiteCandidateRegistryStateAdapter, SQLiteOfficialPredictionPipelineRepository,
)
from app.official_prediction_publication import (
    ApprovedPublicReasoning, DEFAULT_OFFICIAL_PREDICTION_MESSAGE_POLICY,
    OfficialPredictionDestination, OfficialPredictionMessageBuilder,
    OfficialPredictionPublicFacts, SQLiteAtomicPredictionPublicationRepository,
    TelegramPredictionSender, build_official_prediction_publisher_adapter,
)
from app.official_prediction_selection import (
    DEFAULT_OFFICIAL_PREDICTION_RANKING_POLICY, DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY,
    OfficialPredictionSelectionCommand, OfficialSelectionOutcomeStatus,
    PublicationProtectionState, SQLiteOfficialPredictionSelectionRepository,
    build_official_prediction_selection_service, select_official_prediction,
)
from app.prediction_inference import (
    DEFAULT_PREDICTION_INFERENCE_POLICY, OFFICIAL_TARGET_ORDER, MissingValueSupport,
    ModelAdapterOutput, PredictionModelRegistry, PredictionTarget,
    SQLitePredictionInferenceRepository, build_prediction_inference_service,
    generate_raw_prediction,
)
from app.probability_calibration import (
    CalibrationMethod, CalibrationMetricSummary, ProbabilityCalibrationConfig,
    ProbabilityCalibrationReport,
)
from app.publication_quality_gate import (
    ConfidenceLevel, FactStatus, LineupStatus, MarketAvailability, ModelHealthStatus,
    OfficialPublicationQualityGate, SQLiteQualityGateEvaluationRepository,
    DEFAULT_OFFICIAL_PUBLICATION_QUALITY_GATE_POLICY,
)
from app.risk_management import (
    BankrollStateSnapshot, ExposureSnapshot, RiskAssessmentDecision,
    RiskAssessmentService, RiskProductScope, DEFAULT_OFFICIAL_RISK_POLICY,
)

from .exceptions import ConfirmationError, MaterializationError
from .factory import (
    DestinationVerificationPort, DestinationVerificationState, NoSendTelegramTransport, OperationsEnvironment,
    verify_publish_destination,
)
from .fixture_models import OfficialPredictionFixture
from .summaries import OperationsExitCode, OperationsResult, exit_code_for_status
from .validation import parse_decimal, parse_utc_timestamp


PUBLISH_TOKEN = "YES_PUBLISH_OFFICIAL"
PRODUCTION_TOKEN = "PRODUCTION_OFFICIAL"
RETRY_TOKEN = "YES_RETRY_OFFICIAL"


class FixturePredictionModelAdapter:
    """Explicit deterministic replacement for the external model-artifact boundary."""

    def __init__(self, fixture: OfficialPredictionFixture) -> None:
        section = fixture.section("inference")
        self.model_artifact_id = str(section["model_artifact_id"])
        self.model_name = str(section["model_name"])
        self.model_version = str(section["model_version"])
        self.model_family = "fixture-only"
        self.input_schema_name = "goalvision_model_input"
        self.input_schema_version = "v1"
        self.compatibility_version = "official_prediction_model_input_v1"
        self.supported_targets = OFFICIAL_TARGET_ORDER
        self.missing_value_support = MissingValueSupport.OPTIONAL_FEATURES
        supplied = section["raw_probabilities"]
        self._values = {target: parse_decimal(supplied[target.value], f"inference.{target.value}") for target in OFFICIAL_TARGET_ORDER}
        self.calls = 0

    def validate_compatibility(self, model_input: object) -> None:
        return None

    def infer(self, model_input: object) -> tuple[ModelAdapterOutput, ...]:
        self.calls += 1
        return tuple(ModelAdapterOutput(target, self._values[target]) for target in OFFICIAL_TARGET_ORDER)


class _SelectionPublicationProtection:
    def classify(self, *args: object) -> PublicationProtectionState:
        return PublicationProtectionState.NOT_PUBLISHED


class _FixturePublicationState:
    """Failure-injection boundary; valid fixtures use durable publication state."""

    def __init__(self, state: PipelinePublicationState, observed_at: datetime) -> None:
        self.state = state
        self.observed_at = observed_at

    def verify(self, command: OfficialPredictionPipelineCommand) -> PublicationStateVerification:
        return PublicationStateVerification(self.state, self.observed_at, claim_identity="fixture-existing-claim")


class _QualityGateTimePublicationState:
    """Keep the read-only durable state observation inside the gate chronology."""

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate

    def verify(self, command: OfficialPredictionPipelineCommand) -> PublicationStateVerification:
        value = self._delegate.verify(command)
        return replace(value, observed_at=min(value.observed_at, command.quality_gate_evaluation_timestamp))


class _SupersededCandidateState:
    """Explicit lifecycle failure injection for the superseded fixture."""

    def verify(self, command: OfficialPredictionPipelineCommand) -> CandidateStateVerification:
        return CandidateStateVerification(CandidateState.SUPERSEDED, command.candidate, False, fingerprint=command.candidate_fingerprint)


@dataclass(slots=True)
class _PublicFacts:
    candidate: Any
    stake: Any

    def get(self, approved: Any) -> OfficialPredictionPublicFacts:
        item = self.candidate.prepared
        return OfficialPredictionPublicFacts(
            prediction_id=approved.assembly.prediction_id,
            match_id=approved.assembly.match_id,
            orchestration_id=approved.orchestration_id,
            gate_evaluation_id=approved.quality_gate_evaluation.evaluation_id,
            candidate_fingerprint=approved.candidate_fingerprint,
            model_version=item.model_version,
            policy_version=approved.quality_gate_evaluation.policy_version,
            competition=item.competition_name,
            home_team=item.home_team_name,
            away_team=item.away_team_name,
            bankroll_scope=RiskProductScope.OFFICIAL,
            risk_decision=RiskAssessmentDecision.ELIGIBLE,
            stake_recommendation=self.stake,
            reasoning=ApprovedPublicReasoning(tuple(fact.text for fact in item.public_reasoning_facts)),
        )


@dataclass(frozen=True, slots=True)
class MaterializedFixture:
    command: OfficialPredictionPipelineCommand
    pipeline: OfficialPredictionPipelineService
    candidate: Any
    selection: Any
    preparation: Any
    no_send_transport: NoSendTelegramTransport | None


async def execute_fixture(
    fixture: OfficialPredictionFixture,
    database: Database,
    *,
    database_path: Path,
    environment: OperationsEnvironment,
    execution_time: datetime,
    quality_gate_time: datetime,
    publication_time: datetime,
    request_id: str,
    dry_run: bool,
    retry: bool = False,
    telegram: TelegramPredictionSender | None = None,
    destination_verifier: DestinationVerificationPort | None = None,
    expected_candidate_id: str | None = None,
    expected_match_id: str | None = None,
    expected_destination: str | None = None,
    confirm_publish: str | None = None,
    confirm_environment: str | None = None,
) -> OperationsResult:
    if dry_run:
        if environment is not OperationsEnvironment.FIXTURE:
            raise ConfirmationError("dry-run-fixture requires --environment fixture.")
        if telegram is not None and not isinstance(telegram, NoSendTelegramTransport):
            raise ConfirmationError("Fixture dry-run refuses a real-send transport.")
        transport: TelegramPredictionSender = telegram or NoSendTelegramTransport()
    else:
        if environment not in {OperationsEnvironment.STAGING, OperationsEnvironment.PRODUCTION}:
            raise ConfirmationError("publish-fixture requires staging or production.")
        if confirm_publish != PUBLISH_TOKEN:
            raise ConfirmationError("Exact publish confirmation token is required.")
        if environment is OperationsEnvironment.PRODUCTION and confirm_environment != PRODUCTION_TOKEN:
            raise ConfirmationError("Exact production environment confirmation token is required.")
        if environment is OperationsEnvironment.PRODUCTION and fixture.payload["metadata"]["non_production"] is True:
            raise ConfirmationError("A fixture explicitly marked non-production cannot publish to production.")
        if telegram is None or isinstance(telegram, NoSendTelegramTransport):
            raise ConfirmationError("Publish requires an injected real/test Telegram transport.")
        if destination_verifier is None:
            raise ConfirmationError("Publish requires explicit destination verification.")
        if not expected_candidate_id or not expected_match_id or not expected_destination:
            raise ConfirmationError("Candidate, match, and destination confirmations are required.")
        verify_publish_destination(
            destination_verifier,
            expected_identity=expected_destination,
            expected_type=str(fixture.section("publication")["destination_type"]),
            environment=environment,
        )
        transport = telegram

    materialized = _materialize(
        fixture, database, execution_time=execution_time,
        quality_gate_time=quality_gate_time, publication_time=publication_time,
        request_id=request_id, dry_run=dry_run, retry=retry,
        telegram=transport, environment=environment,
        destination_identity=(expected_destination or fixture.destination_identity),
    )
    command = materialized.command
    if not dry_run:
        if expected_candidate_id != command.candidate_id:
            raise ConfirmationError("Expected candidate ID does not match the verified READY candidate.")
        if expected_match_id != command.match_id or expected_match_id != fixture.match_id:
            raise ConfirmationError("Expected match ID does not match the verified pipeline command.")
        if expected_destination != fixture.destination_identity:
            raise ConfirmationError("Expected destination does not match the signed fixture.")
    outcome = await materialized.pipeline.execute(command)
    code = exit_code_for_status(outcome.final_status.value)
    warnings: tuple[str, ...] = ()
    if fixture.candidate_id != command.candidate_id:
        warnings = ("FIXTURE_EXPECTED_CANDIDATE_ID_DIFFERS_FROM_DERIVED",)
    no_send_calls = materialized.no_send_transport.calls if materialized.no_send_transport else 0
    if dry_run and no_send_calls:
        raise AssertionError("Dry-run attempted to invoke Telegram transport.")
    return OperationsResult(
        command="dry-run-fixture" if dry_run else "publish-fixture",
        success=code == OperationsExitCode.SUCCESS,
        final_status=outcome.final_status.value,
        exit_code=int(code), fixture_id=fixture.fixture_id, request_id=request_id,
        execution_id=outcome.pipeline_execution_id,
        candidate_id=outcome.candidate_id, candidate_version=outcome.candidate_version,
        match_id=outcome.match_id, gate_status=outcome.quality_gate_status,
        orchestration_status=outcome.orchestration_status,
        publication_status=outcome.publication_status,
        message_fingerprint=outcome.message_fingerprint,
        reason_codes=outcome.ordered_reason_codes, warnings=warnings,
        database_path=str(database_path), environment=environment.value,
        dry_run=dry_run, retry=retry,
        timestamps=(("execution_time", execution_time.isoformat()), ("quality_gate_time", quality_gate_time.isoformat()), ("publication_time", publication_time.isoformat())),
        policy_versions=(("pipeline", outcome.pipeline_policy_version), ("quality_gate", DEFAULT_OFFICIAL_PUBLICATION_QUALITY_GATE_POLICY.version)),
        details={"fixture_fingerprint": fixture.fixture_fingerprint, "telegram_send_count": getattr(telegram, "calls", 0) if telegram is not None else 0},
    )


def execute_fixture_sync(*args: Any, **kwargs: Any) -> OperationsResult:
    return asyncio.run(execute_fixture(*args, **kwargs))


async def retry_persisted_execution(
    database: Database,
    *,
    database_path: Path,
    execution_id: str,
    execution_time: datetime,
    publication_time: datetime,
    confirm_retry: str,
    telegram: TelegramPredictionSender,
    destination_verifier: DestinationVerificationPort,
) -> OperationsResult:
    """Retry one confirmed-safe failed send without recreating upstream state."""

    from app.official_candidate_preparation.mapping import map_to_quality_gate_handoff
    from app.official_prediction_pipeline import SQLiteOfficialPredictionPipelineRepository

    if confirm_retry != RETRY_TOKEN:
        raise ConfirmationError("Exact retry confirmation token is required.")
    verification = destination_verifier.verify()
    if (
        verification.state is not DestinationVerificationState.VERIFIED
        or not verification.enabled
        or verification.environment not in {OperationsEnvironment.STAGING, OperationsEnvironment.PRODUCTION}
        or not verification.destination_identity
        or verification.destination_type != "TELEGRAM_CHANNEL"
    ):
        raise ConfirmationError("Retry destination verification is not safely VERIFIED.")
    pipeline_repository = SQLiteOfficialPredictionPipelineRepository(database, migrate=False)
    previous = pipeline_repository.load_pipeline_execution(execution_id)
    if previous is None:
        raise ConfirmationError("Retry execution does not exist.")
    from .recovery import analyze_execution_recovery
    analysis = analyze_execution_recovery(database, execution_id)
    if not analysis.retry_safe or analysis.resend_forbidden:
        raise ConfirmationError(f"Execution is not retryable: {analysis.classification.value}.")
    if execution_time <= previous.pipeline_execution_timestamp or publication_time < execution_time:
        raise ConfirmationError("Retry execution/publication timestamps must move forward explicitly.")

    candidates = SQLiteOfficialPredictionCandidateRepository(database, migrate=False)
    candidate = candidates.find_candidate_by_id(previous.candidate_id)
    if candidate is None or candidates.current_state(candidate.registry_candidate_id) is not CandidateLifecycleState.READY:
        raise ConfirmationError("Retry candidate is not the exact current READY version.")
    provenance = dict(candidate.prepared.provenance)
    preparation_row = database.connection.execute(
        "SELECT integration_execution_id FROM official_candidate_preparation_executions WHERE registry_candidate_id=? ORDER BY candidate_preparation_timestamp DESC LIMIT 1",
        (candidate.registry_candidate_id,),
    ).fetchone()
    if preparation_row is None:
        raise ConfirmationError("Persisted candidate preparation linkage is missing.")
    preparation_repository = SQLiteOfficialCandidatePreparationRepository(database, migrate=False)
    prepared = preparation_repository.load_execution_with_risk_snapshot(preparation_row[0])
    if prepared is None or prepared.risk_snapshot is None:
        raise ConfirmationError("Persisted risk snapshot is missing.")
    handoff = map_to_quality_gate_handoff(
        candidate, CandidateLifecycleState.READY, prepared.execution, prepared.risk_snapshot,
    )
    selection_repository = SQLiteOfficialPredictionSelectionRepository(database, migrate=False)
    selection = selection_repository.load_selection_decision(provenance["selection_decision_id"])
    if selection is None or not hasattr(selection, "fair_probability"):
        raise ConfirmationError("Persisted selected decision is missing.")
    calibrated_repository = SQLiteCalibratedMarketProbabilityRepository(database, migrate=False)
    calibrated = calibrated_repository.load_assembly_by_id(provenance["calibrated_assembly_id"])
    gate_repository = SQLiteQualityGateEvaluationRepository(database, migrate=False)
    gate = gate_repository.get(previous.quality_gate_evaluation_id) if previous.quality_gate_evaluation_id else None
    if calibrated is None or gate is None or gate.final_decision.value != "APPROVED":
        raise ConfirmationError("Retry requires the persisted approved gate and calibrated assembly.")
    request = _assembly_request_from_history(candidate, handoff, gate, calibrated)
    destination = OfficialPredictionDestination(RiskProductScope.OFFICIAL, verification.destination_identity)
    facts = _PublicFacts(candidate, prepared.risk_snapshot.audit.recommendation)
    publisher = build_official_prediction_publisher_adapter(database, telegram, facts, destination, lambda: publication_time)
    publication_reader = SQLiteOfficialPublicationStateReader(database)
    gate_engine = OfficialPublicationQualityGate(DEFAULT_OFFICIAL_PUBLICATION_QUALITY_GATE_POLICY)
    assembler = OfficialPredictionCandidateAssembler()
    orchestration_service = OfficialPredictionOrchestrationService(
        assembler, OfficialCandidateFingerprint(), gate_engine, gate_repository,
        SQLiteOrchestrationHistoryRepository(database, migrate=False), publication_reader, publisher,
    )
    events = SQLiteAtomicPredictionPublicationRepository(database, migrate=False)
    pipeline = OfficialPredictionPipelineService(
        DEFAULT_OFFICIAL_PREDICTION_PIPELINE_POLICY,
        SQLiteCandidateRegistryStateAdapter(candidates),
        _QualityGateTimePublicationState(ExistingPublicationStateAdapter(publication_reader, events)),
        PersistedQualityGateAdapter(gate_engine, gate_repository),
        ExistingPreapprovedOrchestrationAdapter(orchestration_service),
        ExistingMessagePreviewAdapter(assembler, publication_reader, OfficialPredictionMessageBuilder(DEFAULT_OFFICIAL_PREDICTION_MESSAGE_POLICY), facts, destination),
        pipeline_repository, assembler,
    )
    audit = prepared.risk_snapshot.audit
    command = OfficialPredictionPipelineCommand(
        candidate=candidate, assembly_request=request,
        pipeline_request_identity=f"{previous.pipeline_request_identity}:retry:{execution_time.isoformat()}",
        candidate_id=candidate.registry_candidate_id, candidate_version=candidate.candidate_version,
        candidate_fingerprint=candidate.content_fingerprint, candidate_lifecycle_status=CandidateLifecycleState.READY,
        match_id=candidate.match_id, kickoff_timestamp=candidate.prepared.kickoff_timestamp,
        bankroll_scope=RiskProductScope.OFFICIAL, destination_scope=RiskProductScope.OFFICIAL,
        normalized_market=candidate.prepared.market_identity.market.value.replace("_", " "),
        normalized_selection=candidate.prepared.market_identity.selection,
        normalized_line=candidate.prepared.market_identity.market_line,
        preparation_execution_id=prepared.execution.integration_execution_id,
        selection_decision_id=selection.selection_decision_id,
        selected_value_assessment_id=selection.selected_value_assessment_id,
        model_input_id=selection.model_input_id, inference_id=selection.inference_id,
        calibrated_assembly_id=selection.calibrated_assembly_id,
        calibration_set_id=selection.calibration_set_id or "none",
        odds_snapshot_identity=provenance["odds_record_id"], bookmaker_provider_identity=selection.bookmaker_id,
        odds_fingerprint=selection.odds_fingerprint,
        calibrated_assembly_fingerprint=selection.calibrated_assembly_fingerprint,
        selection_fingerprint=selection.selection_fingerprint,
        value_assessment_fingerprint=selection.selected_assessment_fingerprint,
        risk_fingerprint=provenance["risk_fingerprint"],
        candidate_preparation_fingerprint=provenance["preparation_request_fingerprint"],
        bookmaker_odds=selection.bookmaker_decimal_odds, calibrated_probability=selection.fair_probability,
        fair_odds=selection.fair_decimal_odds, implied_probability=selection.implied_probability,
        expected_value=selection.expected_value, value_classification=selection.value_classification.value,
        freshness=selection.freshness.overall_freshness.value, risk_outcome=audit.final_decision,
        stake_recommendation=audit.recommendation,
        internal_stake_percentage=audit.recommendation.internal_stake_percentage,
        stake_amount=audit.recommendation.final_stake,
        bankroll_snapshot_identity=prepared.execution.bankroll_snapshot_identity,
        exposure_snapshot_identity=prepared.execution.exposure_snapshot_identity,
        quality_gate_evaluation_timestamp=gate.evaluated_at,
        pipeline_execution_timestamp=execution_time,
        publication_effective_timestamp=publication_time,
        pipeline_policy_version=DEFAULT_OFFICIAL_PREDICTION_PIPELINE_POLICY.version,
        metadata_version="v1", manual_run_identity=previous.manual_run_identity,
        dry_run=False, retry=True,
        metadata=(("environment", verification.environment.value), ("recovery_source_execution", execution_id)),
    )
    outcome = await pipeline.execute(command)
    code = exit_code_for_status(outcome.final_status.value)
    return OperationsResult(
        command="retry-execution", success=code == OperationsExitCode.SUCCESS,
        final_status=outcome.final_status.value, exit_code=int(code),
        request_id=outcome.pipeline_request_identity, execution_id=outcome.pipeline_execution_id,
        candidate_id=outcome.candidate_id, candidate_version=outcome.candidate_version,
        match_id=outcome.match_id, gate_status=outcome.quality_gate_status,
        orchestration_status=outcome.orchestration_status,
        publication_status=outcome.publication_status, message_fingerprint=outcome.message_fingerprint,
        reason_codes=outcome.ordered_reason_codes, database_path=str(database_path),
        environment=verification.environment.value, retry=True,
        timestamps=(("execution_time", execution_time.isoformat()), ("publication_time", publication_time.isoformat()), ("quality_gate_time", gate.evaluated_at.isoformat())),
        policy_versions=(("pipeline", outcome.pipeline_policy_version), ("quality_gate", gate.policy_version)),
    )


def retry_persisted_execution_sync(*args: Any, **kwargs: Any) -> OperationsResult:
    return asyncio.run(retry_persisted_execution(*args, **kwargs))


def _materialize(
    fixture: OfficialPredictionFixture,
    database: Database,
    *,
    execution_time: datetime,
    quality_gate_time: datetime,
    publication_time: datetime,
    request_id: str,
    dry_run: bool,
    retry: bool,
    telegram: TelegramPredictionSender,
    environment: OperationsEnvironment,
    destination_identity: str,
) -> MaterializedFixture:
    match = fixture.section("match")
    odds_data = fixture.section("odds")
    risk_data = fixture.section("risk")
    kickoff = parse_utc_timestamp(str(match["kickoff_utc"]), "match.kickoff_utc")
    effective = parse_utc_timestamp(str(match["snapshot_effective_time"]), "match.snapshot_effective_time")
    odds_time = parse_utc_timestamp(str(odds_data["odds_effective_timestamp"]), "odds.odds_effective_timestamp")
    if not effective <= odds_time <= quality_gate_time < execution_time < kickoff:
        raise MaterializationError("Explicit execution chronology is unsafe or inconsistent.")
    if publication_time < execution_time:
        raise MaterializationError("Publication time cannot precede execution time.")

    snapshots = build_match_data_snapshot_service(database)
    registered = snapshots.register_match_data_snapshot(_snapshot_command(fixture, effective, kickoff))
    if registered.snapshot_id is None:
        raise MaterializationError(f"Match snapshot rejected: {registered.ordered_reason_codes}")
    snapshot = snapshots.repository.find_snapshot_by_id(registered.snapshot_id)
    feature_outcome = generate_match_feature_set(
        build_feature_store_service(database), snapshot,
        schema_version=SCHEMA_IDENTIFIER, feature_timestamp=effective,
    )
    if feature_outcome.feature_set is None:
        raise MaterializationError(f"Feature generation rejected: {feature_outcome.ordered_reason_codes}")
    vector_outcome = generate_model_input(build_model_input_builder(database), feature_outcome.feature_set)
    if vector_outcome.model_input is None:
        raise MaterializationError(f"Model input rejected: {vector_outcome.ordered_reason_codes}")
    vector = vector_outcome.model_input

    model_adapter = FixturePredictionModelAdapter(fixture)
    inference_repository = SQLitePredictionInferenceRepository(database)
    inference_service = build_prediction_inference_service(
        inference_repository,
        PredictionModelRegistry(DEFAULT_PREDICTION_INFERENCE_POLICY).register(model_adapter),
        DEFAULT_PREDICTION_INFERENCE_POLICY,
    )
    inferred = generate_raw_prediction(
        inference_service, vector, model_artifact_id=model_adapter.model_artifact_id,
        inference_timestamp=effective + timedelta(minutes=1),
    )
    if inferred.inference_id is None:
        raise MaterializationError(f"Inference rejected: {inferred.ordered_reason_codes}")
    inference = inference_repository.load_inference_by_id(inferred.inference_id)

    calibrated_repository = SQLiteCalibratedMarketProbabilityRepository(database)
    registry = _calibration_registry(fixture, inference, effective + timedelta(minutes=2))
    calibrated_service = build_calibrated_market_probability_service(
        inference_repository, registry, calibrated_repository, calibrated_repository,
        ExistingProbabilityCalibrationEngineFactory(), DEFAULT_CALIBRATED_MARKET_PROBABILITY_POLICY,
    )
    calibrated_outcome = generate_calibrated_market_probabilities(
        calibrated_service, inference,
        calibration_set_id=str(fixture.section("calibration")["calibration_set_id"]),
        calibration_effective_timestamp=effective + timedelta(minutes=2),
    )
    if calibrated_outcome.calibrated_assembly_id is None:
        raise MaterializationError(f"Calibration rejected: {calibrated_outcome.ordered_reason_codes}")
    assembly = calibrated_repository.load_assembly_by_id(calibrated_outcome.calibrated_assembly_id)

    value_repository = SQLiteMarketValueAssessmentRepository(database)
    value_service = build_market_value_assessment_service(
        value_repository, value_repository, MarketMappingRegistry(),
        DEFAULT_MARKET_VALUE_ASSESSMENT_POLICY,
    )
    supplied_odds = SuppliedOddsSnapshot(
        snapshot_id=str(odds_data["odds_snapshot_identity"]),
        source_provider=str(odds_data["provider"]), bookmaker_id=str(odds_data["bookmaker"]),
        source_event_id=str(odds_data["source_event_id"]), match_id=str(match["match_id"]),
        market_type=MarketType.MATCH_WINNER, selection=MarketSelection.HOME, market_line=None,
        decimal_odds=parse_decimal(odds_data["decimal_odds"], "odds.decimal_odds"),
        odds_effective_timestamp=odds_time, source_updated_timestamp=odds_time,
        registration_timestamp=odds_time, kickoff_timestamp=kickoff,
        is_live=False, market_status=MarketStatus.OPEN, suspended=False,
        available=bool(odds_data["available"]), currency="EUR",
    )
    assessed = assess_market_value(
        value_service, assembly, supplied_odds,
        assessment_timestamp=odds_time + timedelta(seconds=10),
    )
    if assessed.value_assessment_id is None:
        raise MaterializationError(f"Value assessment rejected: {assessed.ordered_reason_codes}")
    assessment = value_repository.load_assessment_by_id(assessed.value_assessment_id)

    selection_repository = SQLiteOfficialPredictionSelectionRepository(database)
    selection_service = build_official_prediction_selection_service(
        selection_repository, DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY,
        DEFAULT_OFFICIAL_PREDICTION_RANKING_POLICY, _SelectionPublicationProtection(),
    )
    selected = select_official_prediction(selection_service, OfficialPredictionSelectionCommand(
        selection_request_identity=f"fixture-selection:{fixture.fixture_id}",
        match_id=str(match["match_id"]), selection_timestamp=odds_time + timedelta(seconds=20),
        kickoff_timestamp=kickoff, bankroll_scope=RiskProductScope.OFFICIAL,
        destination_scope=RiskProductScope.OFFICIAL, assessments=(assessment,),
        selection_policy_version=DEFAULT_OFFICIAL_PREDICTION_SELECTION_POLICY.version,
        source_run_identity=f"fixture:{fixture.fixture_id}",
    ))
    if selected.final_status not in {OfficialSelectionOutcomeStatus.SELECTED, OfficialSelectionOutcomeStatus.IDEMPOTENT_EXISTING} or selected.decision is None:
        raise MaterializationError(f"Official selection produced no candidate: {tuple(item.value for item in selected.ordered_reason_codes)}")
    selection = selected.decision

    candidates = SQLiteOfficialPredictionCandidateRepository(database)
    publication_reader = SQLiteOfficialPublicationStateReader(database)
    registry_service = build_official_prediction_candidate_registry(
        database, publication_guard=SQLiteOfficialCandidatePublicationGuard(publication_reader),
    )
    preparation_repository = SQLiteOfficialCandidatePreparationRepository(database)
    preparation_service = build_official_candidate_preparation_service(
        preparation_repository=preparation_repository,
        selection_repository=selection_repository, value_assessment_repository=selection_repository,
        risk_service=RiskAssessmentService(DEFAULT_OFFICIAL_RISK_POLICY),
        candidate_registry=registry_service, candidate_lifecycle=candidates,
        policy=DEFAULT_OFFICIAL_CANDIDATE_PREPARATION_POLICY,
    )
    bank = _bankroll_context(fixture, odds_time, kickoff)
    exposure = _exposure_context(fixture, odds_time, kickoff)
    preparation = preparation_service.prepare_official_candidate(OfficialCandidatePreparationCommand(
        integration_request_identity=f"fixture-preparation:{fixture.fixture_id}",
        selection=selection, bankroll=bank, exposure=exposure,
        candidate_facts=OfficialCandidateRegistrationFacts(
            fixture_id=int(match["match_id"]), source_event_id=str(match["source_event_id"]),
            odds_source_id=str(odds_data["bookmaker"]).strip().lower().replace(" ", "-"), competition_id=str(match["competition_id"]),
            competition_name=str(match["competition_name"]), home_team_id=str(match["home_team_id"]),
            home_team_name=str(match["home_team_name"]), away_team_id=str(match["away_team_id"]),
            away_team_name=str(match["away_team_name"]),
            raw_model_probability=inference.raw_probabilities.probability_for(PredictionTarget.HOME_WIN),
            core_match_data_timestamp=effective,
            lineup_status=LineupStatus(str(risk_data["lineup_status"])),
            lineup_data_timestamp=effective if risk_data["lineup_status"] == "CONFIRMED" else None,
            injury_suspension_status=FactStatus(str(risk_data["injury_status"])),
            injury_suspension_data_timestamp=effective if risk_data["injury_status"] == "AVAILABLE" else None,
            confidence_level=ConfidenceLevel(str(risk_data["confidence_level"])),
            public_reasoning_facts=(OfficialPredictionReasoningFact(
                ReasoningFactType.MARKET_STATISTICAL_EVIDENCE,
                "The calibrated model probability exceeds the supplied fictional market baseline.",
                "fixture-controlled-selection-v1",
            ),),
            source_data_version="fixture-feature-snapshot-v1",
            supporting_data_status=FactStatus(str(risk_data["supporting_data_status"])),
            market_availability=MarketAvailability(str(risk_data["market_availability"])),
            model_confidence=Decimal("0.80"), uncertainty=Decimal("0.10"),
            calibration_sample_size=int(fixture.section("calibration")["sample_size"]),
            model_sample_size=200,
            team_ids=(str(match["away_team_id"]), str(match["home_team_id"])),
            market_family="match-result", model_name=model_adapter.model_name,
            calibration_artifact_references=(assembly.calibration_set_fingerprint,),
        ),
        risk_assessment_timestamp=odds_time + timedelta(seconds=30),
        candidate_preparation_timestamp=odds_time + timedelta(seconds=40),
        bankroll_scope=RiskProductScope.OFFICIAL, destination_scope=RiskProductScope.OFFICIAL,
        integration_policy_version=DEFAULT_OFFICIAL_CANDIDATE_PREPARATION_POLICY.version,
        source_run_identity=f"fixture:{fixture.fixture_id}", metadata=(("source_stage", "controlled-fixture"),),
    ))
    if preparation.registry_candidate_id is None or preparation.execution is None:
        raise MaterializationError(f"Candidate preparation failed: {tuple(item.value for item in preparation.ordered_reason_codes)} {preparation.explanations}")
    handoff = preparation_service.quality_gate_handoff(preparation.integration_execution_id)
    candidate = handoff.candidate

    orchestration_request = _assembly_request(
        fixture, candidate, handoff, quality_gate_time, assembly,
    )
    destination = OfficialPredictionDestination(RiskProductScope.OFFICIAL, destination_identity)
    facts = _PublicFacts(candidate, preparation.stake_recommendation)
    publisher = build_official_prediction_publisher_adapter(
        database, telegram, facts, destination, lambda: publication_time,
        enabled=not dry_run,
    )
    gate_engine = OfficialPublicationQualityGate(DEFAULT_OFFICIAL_PUBLICATION_QUALITY_GATE_POLICY)
    gate_repository = SQLiteQualityGateEvaluationRepository(database, migrate=False)
    assembler = OfficialPredictionCandidateAssembler()
    orchestration_service = OfficialPredictionOrchestrationService(
        assembler, OfficialCandidateFingerprint(), gate_engine, gate_repository,
        SQLiteOrchestrationHistoryRepository(database, migrate=False), publication_reader, publisher,
    )
    events = SQLiteAtomicPredictionPublicationRepository(database, migrate=False)
    initial = str(fixture.section("publication")["initial_state"])
    state_adapter: Any = _QualityGateTimePublicationState(
        ExistingPublicationStateAdapter(publication_reader, events)
    )
    if initial in {"ACTIVE_CLAIM", "INDETERMINATE_POST_SEND"}:
        state_adapter = _FixturePublicationState(
            PipelinePublicationState.ACTIVE_CLAIM if initial == "ACTIVE_CLAIM" else PipelinePublicationState.INDETERMINATE,
            execution_time,
        )
    candidate_state_adapter: Any = SQLiteCandidateRegistryStateAdapter(candidates)
    if initial == "SUPERSEDED_CANDIDATE":
        candidate_state_adapter = _SupersededCandidateState()
    pipeline = OfficialPredictionPipelineService(
        DEFAULT_OFFICIAL_PREDICTION_PIPELINE_POLICY,
        candidate_state_adapter, state_adapter,
        PersistedQualityGateAdapter(gate_engine, gate_repository),
        ExistingPreapprovedOrchestrationAdapter(orchestration_service),
        ExistingMessagePreviewAdapter(
            assembler, publication_reader,
            OfficialPredictionMessageBuilder(DEFAULT_OFFICIAL_PREDICTION_MESSAGE_POLICY),
            facts, destination,
        ),
        SQLiteOfficialPredictionPipelineRepository(database, migrate=False), assembler,
    )
    provenance = dict(candidate.prepared.provenance)
    risk_audit = handoff.risk_snapshot.audit
    command = OfficialPredictionPipelineCommand(
        candidate=candidate, assembly_request=orchestration_request,
        pipeline_request_identity=request_id,
        candidate_id=candidate.registry_candidate_id, candidate_version=candidate.candidate_version,
        candidate_fingerprint=candidate.content_fingerprint,
        candidate_lifecycle_status=CandidateLifecycleState.READY,
        match_id=candidate.match_id, kickoff_timestamp=kickoff,
        bankroll_scope=RiskProductScope.OFFICIAL, destination_scope=RiskProductScope.OFFICIAL,
        normalized_market="MATCH WINNER", normalized_selection="HOME", normalized_line=None,
        preparation_execution_id=preparation.integration_execution_id,
        selection_decision_id=selection.selection_decision_id,
        selected_value_assessment_id=selection.selected_value_assessment_id,
        model_input_id=selection.model_input_id, inference_id=selection.inference_id,
        calibrated_assembly_id=selection.calibrated_assembly_id,
        calibration_set_id=selection.calibration_set_id or "none",
        odds_snapshot_identity=provenance["odds_record_id"],
        bookmaker_provider_identity=selection.bookmaker_id,
        odds_fingerprint=selection.odds_fingerprint,
        calibrated_assembly_fingerprint=selection.calibrated_assembly_fingerprint,
        selection_fingerprint=selection.selection_fingerprint,
        value_assessment_fingerprint=selection.selected_assessment_fingerprint,
        risk_fingerprint=provenance["risk_fingerprint"],
        candidate_preparation_fingerprint=provenance["preparation_request_fingerprint"],
        bookmaker_odds=selection.bookmaker_decimal_odds,
        calibrated_probability=selection.fair_probability, fair_odds=selection.fair_decimal_odds,
        implied_probability=selection.implied_probability, expected_value=selection.expected_value,
        value_classification=selection.value_classification.value,
        freshness=selection.freshness.overall_freshness.value,
        risk_outcome=risk_audit.final_decision,
        stake_recommendation=risk_audit.recommendation,
        internal_stake_percentage=risk_audit.recommendation.internal_stake_percentage,
        stake_amount=risk_audit.recommendation.final_stake,
        bankroll_snapshot_identity=bank.snapshot_identity,
        exposure_snapshot_identity=exposure.snapshot_identity,
        quality_gate_evaluation_timestamp=quality_gate_time,
        pipeline_execution_timestamp=execution_time,
        publication_effective_timestamp=publication_time,
        pipeline_policy_version=DEFAULT_OFFICIAL_PREDICTION_PIPELINE_POLICY.version,
        metadata_version="v1", manual_run_identity=f"fixture:{fixture.fixture_id}",
        dry_run=dry_run, retry=retry,
        metadata=(("environment", environment.value), ("fixture_id", fixture.fixture_id)),
    )
    return MaterializedFixture(
        command, pipeline, candidate, selection, preparation,
        telegram if isinstance(telegram, NoSendTelegramTransport) else None,
    )


def _snapshot_command(fixture: OfficialPredictionFixture, effective: datetime, kickoff: datetime) -> MatchDataSnapshotRegistrationCommand:
    match = fixture.section("match")
    odds = fixture.section("odds")
    form = FormRecord(5, 3, 1, 1, 9, 5, 2, 1, Decimal("8.4"), Decimal("5.7"), 60, 25, Decimal("54.2"))
    return MatchDataSnapshotRegistrationCommand(
        source_provider=str(match["source_provider"]), source_event_id=str(match["source_event_id"]),
        source_snapshot_id=str(match["source_snapshot_identity"]), match_id=str(match["match_id"]),
        competition_id=str(match["competition_id"]), competition_name=str(match["competition_name"]),
        season_identifier="2026-27", home_team_id=str(match["home_team_id"]), home_team_name=str(match["home_team_name"]),
        away_team_id=str(match["away_team_id"]), away_team_name=str(match["away_team_name"]), kickoff_timestamp=kickoff,
        snapshot_effective_timestamp=effective, source_updated_timestamp=effective - timedelta(minutes=2),
        registration_timestamp=effective + timedelta(seconds=5), scheduled_status=MatchSnapshotStatus.SCHEDULED,
        postponed_indicator=False, cancelled_indicator=False, neutral_venue_indicator=False,
        venue="Fictional Ground", home_recent_form=form, away_recent_form=replace(form, wins=2, draws=2),
        home_venue_split=VenueSplitRecord(6,4,1,1,12,5,3,1,Decimal("10.2"),Decimal("5.1")),
        away_venue_split=VenueSplitRecord(6,2,2,2,8,8,2,2,Decimal("7.5"),Decimal("8.2")),
        home_season_aggregate=SeasonAggregateRecord(10,22,20,9,2,Decimal("18.2"),Decimal("10.1")),
        away_season_aggregate=SeasonAggregateRecord(10,16,14,13,7,Decimal("13.5"),Decimal("14.2")),
        head_to_head=HeadToHeadRecord(4,2,1,1,11,3,2,effective-timedelta(days=90)),
        home_availability=TeamAvailabilityRecord(True,False,2,0,1,"available",effective-timedelta(minutes=10),effective-timedelta(hours=1)),
        away_availability=TeamAvailabilityRecord(True,False,3,1,2,"available",effective-timedelta(minutes=10),effective-timedelta(hours=1)),
        context=MatchContextRecord(6,4,Decimal("20.5"),Decimal("350.2"),1,2,"Regular Season",True,"Dry","Good"),
        # The actionable supplied odds enter at Market Value Assessment below;
        # the immutable match snapshot deliberately carries no second odds copy.
        odds_snapshot=None,
    )


def _calibration_registry(fixture: OfficialPredictionFixture, inference: Any, timestamp: datetime) -> CalibrationRegistry:
    policy = DEFAULT_CALIBRATED_MARKET_PROBABILITY_POLICY
    registry = CalibrationRegistry(policy)
    mappings = []
    for target in OFFICIAL_TARGET_ORDER:
        artifact_id = f"fixture-identity-{target.value.lower()}"
        registry = registry.register_artifact(CalibrationArtifact(
            artifact_id=artifact_id, target=target, method=CalibrationMethod.IDENTITY,
            calibration_model_version="fixture-identity-v1", source_model_artifact_id=inference.model_artifact_id,
            compatible_source_model_versions=(inference.model_version,),
            input_probability_schema=policy.input_probability_schema,
            input_probability_schema_version=policy.input_probability_schema_version,
            calibration_policy_version="probability-calibration-v1",
            config=ProbabilityCalibrationConfig(method=CalibrationMethod.IDENTITY), historical_data=(), active=True,
        ))
        mappings.append(CalibrationTargetMapping(target, artifact_id))
    return registry.define_set(
        calibration_set_id=str(fixture.section("calibration")["calibration_set_id"]),
        set_name="Fixture identity calibration set", set_version="1",
        source_model_artifact_id=inference.model_artifact_id,
        compatible_source_model_versions=(inference.model_version,), mappings=tuple(mappings),
        policy_version="probability-calibration-v1", active=True,
        created_timestamp=timestamp, effective_timestamp=timestamp,
    )


def _bankroll_context(fixture: OfficialPredictionFixture, timestamp: datetime, kickoff: datetime) -> OfficialBankrollPreparationContext:
    item = fixture.section("bankroll")
    current = parse_decimal(item["current_bankroll"], "bankroll.current_bankroll")
    state = BankrollStateSnapshot(
        product_scope=RiskProductScope.OFFICIAL, currency="EUR", opening_bankroll=current,
        current_bankroll=current, peak_bankroll=current, current_drawdown_amount=Decimal("0"),
        current_drawdown_percentage=Decimal("0"), consecutive_wins=0, consecutive_losses=0,
        settled_bet_count=200, unsettled_exposure=Decimal("0"), snapshot_timestamp=timestamp,
        authoritative_source_reference="fixture-bankroll-ledger-v1",
    )
    value = OfficialBankrollPreparationContext(
        snapshot_identity=str(item["snapshot_id"]), fingerprint="",
        match_id=str(fixture.section("match")["match_id"]), kickoff_timestamp=kickoff,
        available_bankroll=parse_decimal(item["available_bankroll"], "bankroll.available_bankroll"),
        reserved_exposure=Decimal("0"), state=state,
    )
    return replace(value, fingerprint=bankroll_context_fingerprint(value))


def _exposure_context(fixture: OfficialPredictionFixture, timestamp: datetime, kickoff: datetime) -> OfficialExposurePreparationContext:
    item = fixture.section("exposure")
    value = OfficialExposurePreparationContext(
        snapshot_identity=str(item["snapshot_id"]), fingerprint="",
        match_id=str(fixture.section("match")["match_id"]), kickoff_timestamp=kickoff,
        snapshot=ExposureSnapshot(
            product_scope=RiskProductScope.OFFICIAL, positions=(), snapshot_timestamp=timestamp,
            authoritative_source_reference="fixture-exposure-ledger-v1",
        ),
    )
    return replace(value, fingerprint=exposure_context_fingerprint(value))


def _assembly_request(fixture: OfficialPredictionFixture, candidate: Any, handoff: Any, evaluated_at: datetime, assembly: Any) -> OfficialCandidateAssemblyRequest:
    item = candidate.prepared
    calibration = fixture.section("calibration")
    target = next(value for value in assembly.ordered_target_results if value.target is PredictionTarget.HOME_WIN)
    report = ProbabilityCalibrationReport(
        calibration_run_id=target.calibration_report_fingerprint,
        raw_probability=target.raw_probability, calibrated_probability=target.calibrated_probability,
        delta=target.calibrated_probability-target.raw_probability,
        calibration_method=target.calibration_method,
        metric_summary=CalibrationMetricSummary(
            observation_count=int(calibration["sample_size"]),
            brier_score=parse_decimal(calibration["brier_score"], "calibration.brier_score"),
            log_loss=parse_decimal(calibration["log_loss"], "calibration.log_loss"),
            expected_calibration_error=parse_decimal(calibration["expected_calibration_error"], "calibration.ece"),
            maximum_calibration_error=parse_decimal(calibration["maximum_calibration_error"], "calibration.mce"),
            reliability_bins=(),
        ), confidence_histogram=(), timestamp=assembly.calibration_effective_timestamp,
        model_version=item.model_version, calibration_version=target.calibration_model_version,
    )
    market = "MATCH WINNER"
    prediction = OfficialPredictionFacts(
        prediction_id=item.prediction_id, match_id=item.match_id, model_version=item.model_version,
        market=market, selection=item.market_identity.selection, market_line=item.market_identity.market_line,
        raw_probability=item.raw_model_probability, decimal_odds=item.decimal_odds,
        odds_timestamp=item.odds_timestamp, expected_value=item.supplied_expected_value,
        confidence=item.confidence_level, prediction_timestamp=item.prediction_creation_timestamp,
        kickoff_timestamp=item.kickoff_timestamp, core_data_timestamp=item.core_match_data_timestamp,
        supporting_data_status=item.supporting_data_status, market_availability=item.market_availability,
        lineup_status=item.lineup_status, injury_status=item.injury_suspension_status,
        registry_candidate_id=candidate.registry_candidate_id,
        registry_content_fingerprint=candidate.content_fingerprint,
    )
    return OfficialCandidateAssemblyRequest(
        prediction=prediction, calibration_records=(report,),
        model_health_records=(ModelHealthRecord(
            f"fixture-health:{candidate.registry_candidate_id}", item.model_version,
            ModelHealthStatus(str(fixture.section("risk")["model_health_status"])),
            evaluated_at - timedelta(minutes=1),
        ),),
        risk_evaluations=(handoff.risk_evaluation,), exposure_evaluations=(handoff.exposure_evaluation,),
        bankroll=handoff.bankroll, evaluation_timestamp=evaluated_at, dry_run=False,
    )


def _assembly_request_from_history(candidate: Any, handoff: Any, gate: Any, assembly: Any) -> OfficialCandidateAssemblyRequest:
    """Rebuild only the typed read model required to reuse a persisted approval."""

    normalized = dict(gate.normalized_input)
    item = candidate.prepared
    target = next(value for value in assembly.ordered_target_results if value.raw_probability == item.raw_model_probability)
    report = ProbabilityCalibrationReport(
        calibration_run_id=target.calibration_report_fingerprint,
        raw_probability=target.raw_probability, calibrated_probability=target.calibrated_probability,
        delta=target.calibrated_probability-target.raw_probability,
        calibration_method=target.calibration_method,
        metric_summary=CalibrationMetricSummary(
            observation_count=int(normalized["calibration_sample_size"]),
            brier_score=Decimal(normalized["calibration_brier"]),
            log_loss=Decimal(normalized["calibration_log_loss"]),
            expected_calibration_error=Decimal(normalized["calibration_ece"]),
            maximum_calibration_error=Decimal(normalized["calibration_mce"]),
            reliability_bins=(),
        ), confidence_histogram=(), timestamp=assembly.calibration_effective_timestamp,
        model_version=item.model_version, calibration_version=target.calibration_model_version,
    )
    prediction = OfficialPredictionFacts(
        prediction_id=item.prediction_id, match_id=item.match_id, model_version=item.model_version,
        market=item.market_identity.market.value.replace("_", " "),
        selection=item.market_identity.selection, market_line=item.market_identity.market_line,
        raw_probability=item.raw_model_probability, decimal_odds=item.decimal_odds,
        odds_timestamp=item.odds_timestamp, expected_value=item.supplied_expected_value,
        confidence=item.confidence_level, prediction_timestamp=item.prediction_creation_timestamp,
        kickoff_timestamp=item.kickoff_timestamp, core_data_timestamp=item.core_match_data_timestamp,
        supporting_data_status=item.supporting_data_status, market_availability=item.market_availability,
        lineup_status=item.lineup_status, injury_status=item.injury_suspension_status,
        registry_candidate_id=candidate.registry_candidate_id,
        registry_content_fingerprint=candidate.content_fingerprint,
    )
    health_time = datetime.fromisoformat(normalized["model_health_checked_at"])
    return OfficialCandidateAssemblyRequest(
        prediction=prediction, calibration_records=(report,),
        model_health_records=(ModelHealthRecord(
            f"retry-health:{candidate.registry_candidate_id}", item.model_version,
            ModelHealthStatus(normalized["model_health_status"]), health_time,
        ),),
        risk_evaluations=(handoff.risk_evaluation,), exposure_evaluations=(handoff.exposure_evaluation,),
        bankroll=handoff.bankroll, evaluation_timestamp=gate.evaluated_at, dry_run=False,
    )
