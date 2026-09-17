"""Explicit Lab services for pre-match evaluation and later settlement."""

from __future__ import annotations

from .decision_comparison import compare, select_one
from .fingerprint import canonical_json, sha256_fingerprint
from .inference import infer
from .market_comparison import assess_inference
from .metrics import aggregate_snapshot, pre_match_metrics, settlement_metrics
from .models import (
    ModelRole, ShadowEvaluationOutcome, ShadowExecution,
    ShadowExecutionStatus,
)
from .outcome_tracking import build_settlement
from .source_verification import load_model_bundle, verify_approval
from .validation import validate_command, validate_input, validate_odds


class ShadowEvaluationService:
    """Runs one approved challenger beside one authoritative champion."""

    def __init__(
        self, repository, comparison_repository, model_repository,
        calibration_repository, input_source, policy,
    ) -> None:
        self._repository = repository
        self._comparison_repository = comparison_repository
        self._model_repository = model_repository
        self._calibration_repository = calibration_repository
        self._input_source = input_source
        self._policy = policy

    def run(self, command):
        validate_command(command, self._policy)
        request_fingerprint = sha256_fingerprint(command)
        existing = self._repository.find_by_request_id(command.shadow_request_id)
        if existing:
            if existing.request_fingerprint != request_fingerprint:
                from .exceptions import ShadowConflictError
                raise ShadowConflictError("Shadow request ID has different immutable content.")
            return _outcome(existing, ShadowExecutionStatus.IDEMPOTENT_EXISTING)
        verify_approval(command, self._comparison_repository, self._policy)
        champion_artifact, champion_calibration = load_model_bundle(
            command, self._model_repository, self._calibration_repository, "champion",
        )
        challenger_artifact, challenger_calibration = load_model_bundle(
            command, self._model_repository, self._calibration_repository, "challenger",
        )
        snapshot = self._input_source.load_model_input(command.model_input_vector_id)
        odds_set = self._input_source.load_odds_snapshot_set(command.odds_snapshot_set_id)
        if snapshot is None or odds_set is None:
            from .exceptions import ShadowSourceError
            raise ShadowSourceError("Explicit model input or supplied odds snapshot set is missing.")
        validate_input(command, snapshot)
        validate_odds(command, odds_set)
        for artifact in (champion_artifact, challenger_artifact):
            if (
                artifact.feature_schema_version != snapshot.feature_schema_version
                or artifact.feature_schema_fingerprint != snapshot.feature_schema_fingerprint
                or artifact.ordered_feature_names != snapshot.ordered_feature_names
            ):
                from .exceptions import ShadowSourceError
                raise ShadowSourceError("A model artifact is incompatible with the exact shared input.")
        champion_inference = infer(ModelRole.CHAMPION, champion_artifact, champion_calibration, snapshot, namespace=request_fingerprint)
        challenger_inference = infer(ModelRole.CHALLENGER, challenger_artifact, challenger_calibration, snapshot, namespace=request_fingerprint)
        champion_assessments = assess_inference(champion_inference, odds_set, self._policy, namespace=request_fingerprint)
        challenger_assessments = assess_inference(challenger_inference, odds_set, self._policy, namespace=request_fingerprint)
        champion_selection = select_one(ModelRole.CHAMPION, champion_assessments, self._policy, namespace=request_fingerprint)
        challenger_selection = select_one(ModelRole.CHALLENGER, challenger_assessments, self._policy, namespace=request_fingerprint)
        disagreement = compare(
            champion_inference, challenger_inference, champion_selection,
            challenger_selection, self._policy, namespace=request_fingerprint,
        )
        execution_id = f"shadow-execution-{sha256_fingerprint((request_fingerprint, snapshot.input_snapshot_fingerprint, odds_set.odds_snapshot_set_fingerprint))}"
        inferences = (champion_inference, challenger_inference)
        selections = (champion_selection, challenger_selection)
        metrics = pre_match_metrics(execution_id, inferences, selections, disagreement)
        aggregate = aggregate_snapshot((execution_id,), (), "OVERALL", "ALL", namespace=execution_id)
        core = {
            "request_fingerprint": request_fingerprint,
            "input_snapshot_fingerprint": snapshot.input_snapshot_fingerprint,
            "odds_snapshot_set_fingerprint": odds_set.odds_snapshot_set_fingerprint,
            "inferences": tuple(item.calibrated_inference_fingerprint for item in inferences),
            "assessments": tuple(item.assessment_fingerprint for item in (*champion_assessments, *challenger_assessments)),
            "selections": tuple(item.selection_fingerprint for item in selections),
            "comparison": disagreement.comparison_fingerprint,
            "metrics": tuple(item.metric_fingerprint for item in metrics),
            "policy": self._policy.version,
        }
        execution_fingerprint = sha256_fingerprint(core)
        deterministic_snapshot = canonical_json(core)
        execution = ShadowExecution(
            shadow_execution_id=execution_id, command=command,
            request_fingerprint=request_fingerprint, input_snapshot=snapshot,
            odds_snapshot_set=odds_set, inferences=inferences,
            market_assessments=(*champion_assessments, *challenger_assessments),
            selections=selections, comparison=disagreement, metrics=metrics,
            aggregate_snapshots=(aggregate,), exclusions=(),
            execution_fingerprint=execution_fingerprint,
            deterministic_snapshot=deterministic_snapshot,
        )
        self._repository.append_shadow_evaluation(execution)
        return _outcome(execution, ShadowExecutionStatus.PRE_MATCH_EVALUATED)


class ShadowSettlementService:
    def __init__(self, repository, policy) -> None:
        self._repository = repository
        self._policy = policy

    def settle(self, command):
        if command.settlement_policy_version != self._policy.settlement_policy_version:
            from .exceptions import ShadowSettlementError
            raise ShadowSettlementError("Settlement policy version is unsupported.")
        execution = self._repository.load_shadow_execution(command.shadow_execution_id)
        if execution is None:
            from .exceptions import ShadowSettlementError
            raise ShadowSettlementError("Shadow execution does not exist.")
        settlement = build_settlement(command, execution)
        existing = self._repository.find_settlement_for_execution(execution.shadow_execution_id)
        if existing:
            if existing.settlement_fingerprint != settlement.settlement_fingerprint:
                from .exceptions import ShadowConflictError
                raise ShadowConflictError("Settlement differs from immutable prior evidence.")
            return existing
        metrics = settlement_metrics(execution.shadow_execution_id, settlement)
        aggregates = (
            aggregate_snapshot((execution,), (settlement,), "OVERALL", "ALL", namespace=execution.shadow_execution_id),
            aggregate_snapshot((execution,), (settlement,), "MODEL_PAIR", f"{execution.command.champion_model_artifact_id}:{execution.command.challenger_model_artifact_id}", namespace=execution.shadow_execution_id),
            aggregate_snapshot((execution,), (settlement,), "COMPETITION", execution.command.competition, namespace=execution.shadow_execution_id),
            aggregate_snapshot((execution,), (settlement,), "DISAGREEMENT_SEVERITY", execution.comparison.severity.value, namespace=execution.shadow_execution_id),
        )
        self._repository.append_shadow_settlement(settlement, metrics, aggregates)
        return settlement


def run_shadow_evaluation(service: ShadowEvaluationService, command):
    return service.run(command)


def settle_shadow_evaluation(service: ShadowSettlementService, command):
    return service.settle(command)


def _outcome(execution, status):
    champion, challenger = execution.selections
    return ShadowEvaluationOutcome(
        status=status, shadow_execution_id=execution.shadow_execution_id,
        shadow_request_id=execution.command.shadow_request_id,
        request_fingerprint=execution.request_fingerprint,
        execution_fingerprint=execution.execution_fingerprint,
        champion_outcome=champion.outcome, challenger_outcome=challenger.outcome,
        disagreement_type=execution.comparison.disagreement_type,
        severity=execution.comparison.severity,
        champion_selection=champion, challenger_selection=challenger,
        reason_codes=execution.comparison.reason_codes,
    )
