"""CLI command mapping and explicit model-operations composition."""

from __future__ import annotations

from argparse import Namespace

from app.historical_model_training import (
    SQLiteHistoricalModelTrainingRepository,
)
from app.historical_probability_calibration import (
    SQLiteHistoricalProbabilityCalibrationRepository,
)
from app.model_activation import (
    ActivationExecutionCommand,
    ActivationRequest,
    DEFAULT_MODEL_ACTIVATION_POLICY,
    ModelActivationService,
    RollbackExecutionCommand,
    RollbackRequest,
    RuntimeArtifactReference,
    RuntimeChampionResolver,
    SQLiteModelActivationRepository,
)
from app.model_comparison_promotion import SQLiteModelComparisonRepository
from app.shadow_evaluation import SQLiteShadowEvaluationRepository

from .configuration import (
    open_operations_database,
    resolve_database_path,
    validate_environment_scope,
)
from .service import ModelOperationsService


READ_ONLY_COMMANDS = {
    "show-champion",
    "show-activation",
    "list-generations",
    "diagnose-state",
}


def build_service(args: Namespace):
    validate_environment_scope(args.environment, args.scope)
    path = resolve_database_path(args.database)
    opened = open_operations_database(
        path,
        read_only=args.command in READ_ONLY_COMMANDS,
    )
    repository = SQLiteModelActivationRepository(
        opened,
        migrate=False,
    )
    model_repository = SQLiteHistoricalModelTrainingRepository(
        opened,
        migrate=False,
    )
    calibration_repository = SQLiteHistoricalProbabilityCalibrationRepository(
        opened,
        migrate=False,
    )
    comparison_repository = SQLiteModelComparisonRepository(
        opened,
        migrate=False,
    )
    shadow_repository = SQLiteShadowEvaluationRepository(
        opened,
        migrate=False,
    )
    policy = DEFAULT_MODEL_ACTIVATION_POLICY
    activation_service = ModelActivationService(
        repository,
        comparison_repository,
        shadow_repository,
        model_repository,
        calibration_repository,
        policy,
    )
    resolver = RuntimeChampionResolver(
        repository,
        model_repository,
        calibration_repository,
        policy,
    )
    service = ModelOperationsService(
        repository=repository,
        activation_service=activation_service,
        resolver=resolver,
        model_repository=model_repository,
        calibration_repository=calibration_repository,
        shadow_repository=shadow_repository,
        policy=policy,
        connection=opened.connection,
    )
    return service, opened


def dispatch(args: Namespace, service: ModelOperationsService):
    if args.command == "bootstrap-champion":
        return service.bootstrap_champion(
            scope=args.scope,
            artifact=_artifact(args),
            timestamp=args.timestamp,
            reason=args.reason,
            operator=args.operator,
        )
    if args.command == "prepare-activation":
        request = ActivationRequest(
            activation_request_id=args.request_id,
            activation_name=args.name,
            model_scope=args.scope,
            current_champion_generation_id=args.current_generation_id,
            current_champion_generation_fingerprint=(
                args.current_generation_fingerprint
            ),
            current_champion=_artifact(args, "current_"),
            challenger=_artifact(args, "challenger_"),
            comparison_run_id=args.comparison_run_id,
            comparison_run_fingerprint=args.comparison_run_fingerprint,
            challenger_candidate_id=args.challenger_candidate_id,
            recommendation_id=args.recommendation_id,
            recommendation_fingerprint=args.recommendation_fingerprint,
            evidence_cutoff_timestamp_utc=args.evidence_cutoff,
            requested_timestamp_utc=args.requested_at,
            activation_reason=args.reason,
            operator_identity=args.operator,
            warning_override_reason=args.warning_override_reason,
        )
        return service.prepare_activation(
            request,
            expected_shadow_evidence_fingerprint=(
                args.shadow_evidence_fingerprint
            ),
        )
    if args.command == "execute-activation":
        return service.execute_activation(
            ActivationExecutionCommand(
                activation_execution_request_id=args.execution_request_id,
                activation_plan_id=args.plan_id,
                activation_plan_fingerprint=args.plan_fingerprint,
                execution_timestamp_utc=args.executed_at,
                operator_identity=args.operator,
            ),
            confirmation=args.confirm,
        )
    if args.command == "prepare-rollback":
        return service.prepare_rollback(
            RollbackRequest(
                rollback_request_id=args.request_id,
                rollback_name=args.name,
                model_scope=args.scope,
                current_champion_generation_id=args.current_generation_id,
                current_champion_generation_fingerprint=(
                    args.current_generation_fingerprint
                ),
                target_champion_generation_id=args.target_generation_id,
                rollback_reason=args.reason,
                incident_reference=args.incident_reference,
                operator_identity=args.operator,
                requested_timestamp_utc=args.requested_at,
            )
        )
    if args.command == "execute-rollback":
        return service.execute_rollback(
            RollbackExecutionCommand(
                rollback_execution_request_id=args.execution_request_id,
                rollback_plan_id=args.plan_id,
                rollback_plan_fingerprint=args.plan_fingerprint,
                execution_timestamp_utc=args.executed_at,
                operator_identity=args.operator,
            ),
            confirmation=args.confirm,
        )
    if args.command == "show-champion":
        return service.show_champion(args.scope)
    if args.command == "show-activation":
        return service.show_activation(args.scope, args.plan_id)
    if args.command == "list-generations":
        return service.list_generations(args.scope, args.limit)
    if args.command == "diagnose-state":
        return service.diagnose_state(args.scope)
    raise AssertionError("Unknown model operations command.")


def _artifact(args: Namespace, prefix: str = "") -> RuntimeArtifactReference:
    return RuntimeArtifactReference(
        model_artifact_id=getattr(args, prefix + "model_artifact_id"),
        model_artifact_fingerprint=getattr(
            args,
            prefix + "model_artifact_fingerprint",
        ),
        preprocessing_fingerprint=getattr(
            args,
            prefix + "preprocessing_fingerprint",
        ),
        calibration_artifact_set_id=getattr(
            args,
            prefix + "calibration_artifact_set_id",
        ),
        calibration_artifact_set_fingerprint=getattr(
            args,
            prefix + "calibration_artifact_set_fingerprint",
        ),
        feature_schema_version=getattr(
            args,
            prefix + "feature_schema_version",
        ),
        feature_schema_fingerprint=getattr(
            args,
            prefix + "feature_schema_fingerprint",
        ),
        target_contract_version=getattr(
            args,
            prefix + "target_contract_version",
        ),
        probability_contract_version=getattr(
            args,
            prefix + "probability_contract_version",
        ),
        runtime_compatibility_version=getattr(
            args,
            prefix + "runtime_compatibility_version",
        ),
    )
