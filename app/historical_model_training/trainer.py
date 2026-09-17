"""Historical model-training application service."""

from __future__ import annotations

from dataclasses import asdict, replace

from app.historical_dataset_split import Partition
from app.prediction_inference.models import OFFICIAL_TARGET_ORDER

from .artifact import predict_raw_probabilities
from .dataset_loader import load_verified_partitions
from .estimators import construct_targets, fit_estimators, validate_class_support
from .exceptions import (
    EstimatorConvergenceError, FeatureSchemaError, InsufficientClassSupportError,
    InsufficientExamplesError, InvalidProbabilityError, LabelSchemaError,
    PartitionSafetyError, PreprocessingError, SourceSplitError, TrainingConflictError,
    TrainingPersistenceError, TrainingRequestValidationError,
)
from .fingerprint import canonical_json, sha256_fingerprint
from .feature_contracts import (
    LEGACY_TRAINING_FEATURE_CONTRACT,
    resolve_training_feature_contract,
)
from .metrics import calculate_metrics
from .models import (
    HistoricalModelTrainingCommand, ModelArtifact, PreparedTrainingRun, TrainingExampleLink,
    TrainingOutcome, TrainingStatus,
)
from .policy import (
    DEFAULT_MODEL_TRAINING_POLICY, DEFAULT_PREPROCESSING_POLICY, ModelTrainingPolicy,
    PreprocessingPolicy,
)
from .preprocessing import fit_preprocessing, transform_examples
from .validation import normalize_training_command


class HistoricalModelTrainer:
    def __init__(
        self, training_repository, split_repository, model_repository,
        preprocessing_policy: PreprocessingPolicy = DEFAULT_PREPROCESSING_POLICY,
        model_policy: ModelTrainingPolicy = DEFAULT_MODEL_TRAINING_POLICY,
    ) -> None:
        self._training = training_repository
        self._splits = split_repository
        self._models = model_repository
        self._preprocessing_policy = preprocessing_policy
        self._model_policy = model_policy

    def train(self, command: HistoricalModelTrainingCommand) -> TrainingOutcome:
        try:
            normalized = normalize_training_command(command)
            self._validate_policies(normalized)
        except (TrainingRequestValidationError, ValueError) as exc:
            return _rejected(command, TrainingStatus.REJECTED_INVALID_REQUEST, ("INVALID_TRAINING_REQUEST", str(exc)))
        request_fingerprint = sha256_fingerprint({"command": normalized})
        existing = self._models.find_by_request_id(normalized.training_request_id)
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                return _rejected(command, TrainingStatus.CONFLICT, ("TRAINING_REQUEST_ID_CONFLICT",), request_fingerprint)
            return _outcome(existing, TrainingStatus.IDEMPOTENT_EXISTING, ("IDENTICAL_TRAINING_RUN_EXISTS",))
        try:
            _, _, train, validation = load_verified_partitions(
                normalized, self._training, self._splits,
            )
        except SourceSplitError as exc:
            return _rejected(command, TrainingStatus.REJECTED_SOURCE_SPLIT, ("SOURCE_SPLIT_REJECTED", str(exc)), request_fingerprint)
        except PartitionSafetyError as exc:
            return _rejected(command, TrainingStatus.REJECTED_PARTITION_SAFETY, ("PARTITION_SAFETY_REJECTED", str(exc)), request_fingerprint)
        except FeatureSchemaError as exc:
            return _rejected(command, TrainingStatus.REJECTED_FEATURE_SCHEMA, ("FEATURE_SCHEMA_REJECTED", str(exc)), request_fingerprint)
        except LabelSchemaError as exc:
            return _rejected(command, TrainingStatus.REJECTED_LABEL_SCHEMA, ("LABEL_SCHEMA_REJECTED", str(exc)), request_fingerprint)
        if len(train) < self._model_policy.minimum_training_examples:
            return _rejected(command, TrainingStatus.REJECTED_INSUFFICIENT_EXAMPLES, ("INSUFFICIENT_TRAIN_EXAMPLES",), request_fingerprint)
        try:
            preprocessing = fit_preprocessing(train, normalized.ordered_feature_names, self._preprocessing_policy)
            train_matrix = transform_examples(train, preprocessing)
            validation_matrix = transform_examples(validation, preprocessing)
        except PreprocessingError as exc:
            return _rejected(command, TrainingStatus.REJECTED_PREPROCESSING, ("PREPROCESSING_REJECTED", str(exc)), request_fingerprint)
        targets = construct_targets(train)
        try:
            validate_class_support(targets)
            fitting_policy = self._fitting_policy(normalized)
            estimators = fit_estimators(train_matrix, targets, fitting_policy, normalized.estimator.random_seed)
        except InsufficientClassSupportError as exc:
            return _rejected(command, TrainingStatus.REJECTED_INSUFFICIENT_CLASS_SUPPORT, ("INSUFFICIENT_CLASS_SUPPORT", str(exc)), request_fingerprint)
        except EstimatorConvergenceError as exc:
            return _rejected(command, TrainingStatus.REJECTED_CONVERGENCE, ("ESTIMATOR_DID_NOT_CONVERGE", str(exc)), request_fingerprint)

        training_run_id = f"historical-model-training-run-{request_fingerprint}"
        feature_contract = resolve_training_feature_contract(
            normalized.feature_schema_version,
            normalized.feature_schema_fingerprint,
            normalized.ordered_feature_names,
        )
        compatibility_material = {
            "model_family": normalized.model_family,
            "feature_schema_version": normalized.feature_schema_version,
            "feature_schema_fingerprint": normalized.feature_schema_fingerprint,
            "ordered_feature_names": normalized.ordered_feature_names,
            "original_feature_count": len(normalized.ordered_feature_names),
            "transformed_feature_count": len(preprocessing.transformed_feature_names),
            "label_schema_version": normalized.label_schema_version,
            "target_schema_version": normalized.target_schema_version,
            "canonical_target_order": tuple(item.value for item in OFFICIAL_TARGET_ORDER),
            "preprocessing_policy_version": normalized.preprocessing_policy_version,
            "model_policy_version": normalized.model_policy_version,
            "artifact_format_version": normalized.artifact_format_version,
            "raw_uncalibrated": True,
        }
        if feature_contract is not LEGACY_TRAINING_FEATURE_CONTRACT:
            compatibility_material.update({
                "input_schema_identifier": feature_contract.schema_identifier,
                "compatibility_version": feature_contract.compatibility_version,
                "fingerprint_version": feature_contract.fingerprint_version,
                "feature_count": feature_contract.feature_count,
            })
        compatibility = canonical_json(compatibility_material)
        provenance = canonical_json({
            "training_request_fingerprint": request_fingerprint,
            "source_split_id": normalized.source_split_id,
            "source_split_fingerprint": normalized.source_split_fingerprint,
            "fold_id": normalized.fold_id, "fold_fingerprint": normalized.fold_fingerprint,
            "training_example_ids": tuple(item.training_example_id for item in train),
            "training_example_fingerprints": tuple(item.example_fingerprint for item in train),
            "validation_example_ids": tuple(item.training_example_id for item in validation),
            "validation_example_fingerprints": tuple(item.example_fingerprint for item in validation),
            "training_example_evidence": tuple({
                "id": item.training_example_id, "fingerprint": item.example_fingerprint,
                "completeness_score": item.completeness_score,
                "missingness_mask": item.missingness_mask,
                "feature_provenance": item.feature_provenance,
            } for item in train),
            "validation_example_evidence": tuple({
                "id": item.training_example_id, "fingerprint": item.example_fingerprint,
                "completeness_score": item.completeness_score,
                "missingness_mask": item.missingness_mask,
                "feature_provenance": item.feature_provenance,
            } for item in validation),
            "training_timestamp": normalized.training_timestamp, "code_version": normalized.code_version,
            "dependency_metadata_version": normalized.dependency_metadata_version,
            "environment_metadata_version": normalized.environment_metadata_version,
        })
        provisional = ModelArtifact(
            artifact_id="PENDING", artifact_fingerprint="PENDING", training_run_id=training_run_id,
            training_request_fingerprint=request_fingerprint, source_split_id=normalized.source_split_id,
            source_split_fingerprint=normalized.source_split_fingerprint, fold_id=normalized.fold_id,
            fold_fingerprint=normalized.fold_fingerprint, model_family=normalized.model_family,
            feature_schema_version=normalized.feature_schema_version,
            feature_schema_fingerprint=normalized.feature_schema_fingerprint,
            ordered_feature_names=normalized.ordered_feature_names,
            label_schema_version=normalized.label_schema_version,
            target_schema_version=normalized.target_schema_version,
            canonical_target_order=tuple(OFFICIAL_TARGET_ORDER),
            artifact_format_version=normalized.artifact_format_version, preprocessing=preprocessing,
            estimators=estimators, training_timestamp=normalized.training_timestamp,
            compatibility_snapshot=compatibility, provenance_snapshot=provenance,
        )
        try:
            train_predictions = tuple(
                predict_raw_probabilities(
                    provisional, item.ordered_feature_vector, item.missingness_mask,
                    feature_schema_version=item.feature_schema_version,
                    feature_schema_fingerprint=normalized.feature_schema_fingerprint,
                    ordered_feature_names=normalized.ordered_feature_names,
                ).raw_probabilities for item in train
            )
            validation_predictions = tuple(
                predict_raw_probabilities(
                    provisional, item.ordered_feature_vector, item.missingness_mask,
                    feature_schema_version=item.feature_schema_version,
                    feature_schema_fingerprint=normalized.feature_schema_fingerprint,
                    ordered_feature_names=normalized.ordered_feature_names,
                ).raw_probabilities for item in validation
            )
        except (InvalidProbabilityError, PreprocessingError, ValueError) as exc:
            return _rejected(command, TrainingStatus.REJECTED_INVALID_PROBABILITIES, ("INVALID_RAW_PROBABILITIES", str(exc)), request_fingerprint)
        train_metrics, aggregate_train = calculate_metrics(Partition.TRAIN, train, train_predictions)
        validation_metrics, aggregate_validation = calculate_metrics(
            Partition.VALIDATION, validation, validation_predictions, len(train_metrics),
        ) if validation else ((), ())
        metrics = (*train_metrics, *validation_metrics)
        artifact_fingerprint = sha256_fingerprint({
            "request_fingerprint": request_fingerprint,
            "source_fingerprints": (normalized.source_split_fingerprint, normalized.fold_fingerprint),
            "preprocessing_fingerprint": preprocessing.preprocessing_fingerprint,
            "estimator_fingerprints": tuple(item.estimator_fingerprint for item in estimators),
            "canonical_target_order": tuple(item.value for item in OFFICIAL_TARGET_ORDER),
            "metrics": tuple(metrics), "compatibility": compatibility,
            "artifact_format_version": normalized.artifact_format_version,
        })
        artifact = replace(
            provisional, artifact_id=f"historical-model-artifact-{artifact_fingerprint}",
            artifact_fingerprint=artifact_fingerprint,
        )
        links = tuple(
            TrainingExampleLink(item.training_example_id, item.example_fingerprint, partition, index)
            for partition, examples in ((Partition.TRAIN, train), (Partition.VALIDATION, validation))
            for index, item in enumerate(examples)
        )
        training_run_fingerprint = sha256_fingerprint({
            "request_fingerprint": request_fingerprint, "artifact_fingerprint": artifact_fingerprint,
            "ordered_examples": links, "outcome": "MODEL_TRAINED",
            "policy_versions": (normalized.preprocessing_policy_version, normalized.model_policy_version),
        })
        snapshot = canonical_json({
            "command": asdict(normalized), "request_fingerprint": request_fingerprint,
            "artifact_fingerprint": artifact_fingerprint,
            "training_run_fingerprint": training_run_fingerprint,
            "aggregate_training_metrics": aggregate_train,
            "aggregate_validation_metrics": aggregate_validation,
        })
        run = PreparedTrainingRun(
            training_run_id=training_run_id, command=normalized, request_fingerprint=request_fingerprint,
            training_run_fingerprint=training_run_fingerprint, artifact=artifact,
            training_examples=links, metrics=tuple(metrics),
            aggregate_training_metrics=aggregate_train,
            aggregate_validation_metrics=aggregate_validation,
            deterministic_run_snapshot=snapshot,
        )
        try:
            duplicate = self._models.find_by_training_run_fingerprint(training_run_fingerprint)
            if duplicate is not None:
                return _outcome(duplicate, TrainingStatus.IDEMPOTENT_EXISTING, ("IDENTICAL_TRAINING_RUN_EXISTS",))
            self._models.append_training_run(run)
        except TrainingConflictError:
            return _rejected(command, TrainingStatus.CONFLICT, ("IMMUTABLE_TRAINING_CONFLICT",), request_fingerprint)
        except TrainingPersistenceError:
            return _rejected(command, TrainingStatus.PERSISTENCE_FAILURE, ("ATOMIC_TRAINING_PERSISTENCE_FAILURE",), request_fingerprint)
        return _outcome(run, TrainingStatus.MODEL_TRAINED, ("MODEL_ARTIFACT_PERSISTED",))

    def _validate_policies(self, command):
        if command.preprocessing_policy_version != self._preprocessing_policy.version:
            raise TrainingRequestValidationError("Injected preprocessing policy version mismatch.")
        if command.model_policy_version != self._model_policy.version:
            raise TrainingRequestValidationError("Injected model policy version mismatch.")
        if command.missing_value_policy is not self._preprocessing_policy.missing_value_policy:
            raise TrainingRequestValidationError("Command missing-value policy differs from injected policy.")
        if command.scaling_policy is not self._preprocessing_policy.scaling_policy:
            raise TrainingRequestValidationError("Command scaling policy differs from injected policy.")
        if command.append_missingness_indicators != self._preprocessing_policy.append_missingness_indicators:
            raise TrainingRequestValidationError("Missingness-indicator policy mismatch.")

    def _fitting_policy(self, command):
        config = command.estimator
        return ModelTrainingPolicy(
            version=self._model_policy.version, model_family=command.model_family, solver=config.solver,
            regularization=config.regularization, learning_rate=config.learning_rate,
            maximum_iterations=config.maximum_iterations, convergence_tolerance=config.convergence_tolerance,
            probability_tolerance=self._model_policy.probability_tolerance,
            classification_threshold=self._model_policy.classification_threshold,
            class_weight_policy=config.class_weight_policy,
            minimum_training_examples=self._model_policy.minimum_training_examples,
        )


def train_historical_model(service: HistoricalModelTrainer, command: HistoricalModelTrainingCommand) -> TrainingOutcome:
    return service.train(command)


def _outcome(run, status, reasons):
    train_count = sum(item.partition is Partition.TRAIN for item in run.training_examples)
    validation_count = sum(item.partition is Partition.VALIDATION for item in run.training_examples)
    return TrainingOutcome(
        status=status, training_run_id=run.training_run_id, artifact_id=run.artifact.artifact_id,
        training_request_id=run.command.training_request_id,
        training_request_fingerprint=run.request_fingerprint,
        training_run_fingerprint=run.training_run_fingerprint,
        artifact_fingerprint=run.artifact.artifact_fingerprint,
        source_split_id=run.command.source_split_id, fold_id=run.command.fold_id,
        model_family=run.command.model_family, training_row_count=train_count,
        validation_row_count=validation_count,
        original_feature_count=len(run.artifact.ordered_feature_names),
        transformed_feature_count=len(run.artifact.preprocessing.transformed_feature_names),
        target_count=11, ordered_target_identities=tuple(item.value for item in OFFICIAL_TARGET_ORDER),
        aggregate_training_metrics=run.aggregate_training_metrics,
        aggregate_validation_metrics=run.aggregate_validation_metrics,
        ordered_reason_codes=reasons,
        policy_versions=(("preprocessing", run.command.preprocessing_policy_version), ("model", run.command.model_policy_version)),
        training_timestamp=run.command.training_timestamp,
    )


def _rejected(command, status, reasons, fingerprint=None):
    partition = getattr(command, "source_split_id", "")
    estimator = getattr(command, "model_family", "")
    timestamp = getattr(command, "training_timestamp", None)
    timestamp = timestamp if isinstance(timestamp, str) and timestamp else None
    return TrainingOutcome(
        status=status, training_run_id=None, artifact_id=None,
        training_request_id=getattr(command, "training_request_id", ""),
        training_request_fingerprint=fingerprint, training_run_fingerprint=None,
        artifact_fingerprint=None, source_split_id=partition, fold_id=getattr(command, "fold_id", ""),
        model_family=estimator, training_row_count=0, validation_row_count=0,
        original_feature_count=0, transformed_feature_count=0, target_count=0,
        ordered_target_identities=(), aggregate_training_metrics=(), aggregate_validation_metrics=(),
        ordered_reason_codes=reasons, policy_versions=(), training_timestamp=timestamp,
    )
