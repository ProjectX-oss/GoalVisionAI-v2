"""Application service for immutable evidence and promotion recommendations only."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from .betting_comparison import compare_betting_metrics
from .calibration_comparison import compare_calibration_metrics
from .decision import rank_challengers, recommend_challenger
from .eligibility import evaluate_eligibility_gates
from .exceptions import (
    ComparisonConflictError,
    ComparisonPersistenceError,
    ComparisonSourceError,
    ComparisonValidationError,
)
from .fingerprint import (
    canonical_json,
    challenger_evaluation_fingerprint,
    comparison_request_fingerprint,
    comparison_run_fingerprint,
    sha256_fingerprint,
    source_compatibility_fingerprint,
)
from .models import (
    ChallengerEvaluation,
    ComparisonExclusion,
    ComparisonOutcome,
    ComparisonStatus,
    CompatibilityStatus,
    PreparedComparisonRun,
    Recommendation,
)
from .normalization import derive_comparison_scope
from .predictive_comparison import compare_predictive_metrics
from .risk_comparison import compare_risk_metrics
from .scoring import calculate_promotion_score
from .significance import calculate_statistical_evidence
from .source_verification import verify_source_bundle
from .stability import calculate_stability
from .validation import validate_comparison_command


class ModelComparisonPromotionService:
    """Compares persisted evidence and never activates either model."""

    def __init__(
        self,
        model_repository,
        calibration_repository,
        backtest_repository,
        comparison_repository,
        policy,
    ) -> None:
        self._models = model_repository
        self._calibrations = calibration_repository
        self._backtests = backtest_repository
        self._comparisons = comparison_repository
        self._policy = policy

    def compare(self, command) -> ComparisonOutcome:
        try:
            normalized = validate_comparison_command(command, self._policy)
        except ComparisonValidationError as exc:
            return _rejected(command, ComparisonStatus.REJECTED_INVALID_REQUEST, (str(exc),))
        request_fingerprint = comparison_request_fingerprint(normalized)
        existing = self._comparisons.find_by_request_id(
            normalized.comparison_request_id
        )
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                return _outcome(
                    None,
                    ComparisonStatus.CONFLICT,
                    normalized,
                    request_fingerprint,
                    ("COMPARISON_REQUEST_ID_CONFLICT",),
                )
            return _outcome(
                existing,
                ComparisonStatus.IDEMPOTENT_EXISTING,
                normalized,
                request_fingerprint,
                ("IDEMPOTENT_EXISTING_COMPARISON",),
            )
        try:
            champion = verify_source_bundle(
                model_repository=self._models,
                calibration_repository=self._calibrations,
                backtest_repository=self._backtests,
                model_artifact_id=normalized.champion_model_artifact_id,
                model_artifact_fingerprint=normalized.champion_model_artifact_fingerprint,
                calibration_artifact_set_id=normalized.champion_calibration_artifact_set_id,
                calibration_artifact_set_fingerprint=normalized.champion_calibration_artifact_set_fingerprint,
                backtest_run_id=normalized.champion_backtest_run_id,
                backtest_run_fingerprint=normalized.champion_backtest_run_fingerprint,
                source_role="CHAMPION",
            )
        except ComparisonSourceError as exc:
            return _outcome(
                None,
                ComparisonStatus.REJECTED_CHAMPION_SOURCE,
                normalized,
                request_fingerprint,
                (str(exc),),
            )
        evaluations = []
        exclusions = []
        for candidate in normalized.challengers:
            try:
                challenger = verify_source_bundle(
                    model_repository=self._models,
                    calibration_repository=self._calibrations,
                    backtest_repository=self._backtests,
                    model_artifact_id=candidate.model_artifact_id,
                    model_artifact_fingerprint=candidate.model_artifact_fingerprint,
                    calibration_artifact_set_id=candidate.calibration_artifact_set_id,
                    calibration_artifact_set_fingerprint=candidate.calibration_artifact_set_fingerprint,
                    backtest_run_id=candidate.backtest_run_id,
                    backtest_run_fingerprint=candidate.backtest_run_fingerprint,
                    source_role="CHALLENGER",
                )
                if self._is_repeated_pair_without_material_change(
                    normalized, candidate
                ):
                    raise ComparisonSourceError(
                        "REPEATED_CHAMPION_CHALLENGER_PAIR_WITHOUT_DISTINCT_SCOPE_OR_POLICY"
                    )
                evaluations.append(
                    self._evaluate(
                        normalized,
                        request_fingerprint,
                        champion,
                        candidate,
                        challenger,
                    )
                )
            except ComparisonSourceError as exc:
                exclusion = _exclusion(
                    candidate.challenger_candidate_id,
                    "SOURCE_VERIFICATION",
                    str(exc),
                    len(exclusions),
                )
                exclusions.append(exclusion)
                if not self._policy.allow_partial_challenger_exclusion:
                    return _outcome(
                        None,
                        ComparisonStatus.REJECTED_CHALLENGER_SOURCE,
                        normalized,
                        request_fingerprint,
                        (str(exc),),
                    )
            except ValueError as exc:
                exclusions.append(
                    _exclusion(
                        candidate.challenger_candidate_id,
                        "COMPARISON",
                        str(exc),
                        len(exclusions),
                    )
                )
        if not evaluations:
            return _outcome(
                None,
                ComparisonStatus.NO_VALID_CHALLENGERS,
                normalized,
                request_fingerprint,
                tuple(item.exclusion_reason for item in exclusions)
                or ("NO_VALID_CHALLENGERS",),
            )
        evaluations = list(self._rank_and_limit_winner(tuple(evaluations)))
        winner = next(
            (
                item
                for item in evaluations
                if item.recommendation is Recommendation.PROMOTE_CHALLENGER
            ),
            None,
        )
        final_recommendation = (
            Recommendation.PROMOTE_CHALLENGER
            if winner
            else _aggregate_recommendation(evaluations)
        )
        run_material = {
            "request_fingerprint": request_fingerprint,
            "evaluation_fingerprints": tuple(
                item.evaluation_fingerprint for item in evaluations
            ),
            "ranking": tuple(
                item.candidate.challenger_candidate_id
                for item in sorted(
                    evaluations,
                    key=lambda item: (
                        item.deterministic_rank or len(evaluations) + 1,
                        item.candidate.challenger_candidate_id,
                    ),
                )
            ),
            "final_recommendation": final_recommendation,
            "final_recommended_challenger_id": (
                winner.candidate.challenger_candidate_id if winner else None
            ),
            "policy_versions": self._policy.versions,
            "exclusions": tuple(exclusions),
        }
        run_fingerprint = comparison_run_fingerprint(
            request_fingerprint,
            tuple(item.evaluation_fingerprint for item in evaluations),
            run_material["ranking"],
            final_recommendation.value,
            self._policy.versions,
        )
        comparison_run_id = f"model-comparison-run-{run_fingerprint}"
        reasons = (
            ("PROMOTION_RECOMMENDATION_ONLY_NO_ACTIVATION",)
            + tuple(item.exclusion_reason for item in exclusions)
        )
        snapshot = canonical_json(
            {
                "command": normalized,
                "run_material": run_material,
                "reason_codes": reasons,
            }
        )
        prepared = PreparedComparisonRun(
            comparison_run_id=comparison_run_id,
            command=normalized,
            request_fingerprint=request_fingerprint,
            comparison_run_fingerprint=run_fingerprint,
            evaluations=tuple(evaluations),
            final_recommended_challenger_id=(
                winner.candidate.challenger_candidate_id if winner else None
            ),
            final_recommendation=final_recommendation,
            reason_codes=reasons,
            exclusions=tuple(exclusions),
            deterministic_run_snapshot=snapshot,
        )
        try:
            self._comparisons.append_comparison_run(prepared)
        except ComparisonConflictError:
            return _outcome(
                None,
                ComparisonStatus.CONFLICT,
                normalized,
                request_fingerprint,
                ("COMPARISON_REQUEST_ID_CONFLICT",),
            )
        except ComparisonPersistenceError as exc:
            return _outcome(
                None,
                ComparisonStatus.PERSISTENCE_FAILURE,
                normalized,
                request_fingerprint,
                ("COMPARISON_ATOMIC_PERSISTENCE_FAILED", str(exc)),
            )
        return _outcome(
            prepared,
            ComparisonStatus.COMPARISON_COMPLETED,
            normalized,
            request_fingerprint,
            reasons,
        )

    def _is_repeated_pair_without_material_change(self, command, candidate):
        for prior in self._comparisons.list_comparisons_for_challenger_model(
            candidate.model_artifact_id
        ):
            if (
                prior.command.champion_model_artifact_id
                != command.champion_model_artifact_id
            ):
                continue
            same_scope = prior.command.scope == command.scope
            same_policy = _command_policy_versions(prior.command) == _command_policy_versions(command)
            if same_scope and same_policy:
                return True
        return False

    def _evaluate(
        self,
        command,
        request_fingerprint,
        champion,
        candidate,
        challenger,
    ):
        compatibility = _verify_compatibility(
            champion, challenger, command.scope, self._policy
        )
        if compatibility:
            raise ComparisonSourceError(compatibility[0])
        (
            champion_scope,
            challenger_scope,
            scope_evidence,
            scope_exclusions,
            scope_reasons,
        ) = derive_comparison_scope(
            champion.backtest_run, challenger.backtest_run, command.scope
        )
        if champion_scope is None:
            raise ComparisonSourceError(scope_reasons[0])
        source_evidence = tuple(
            replace(item, deterministic_order=index)
            for index, item in enumerate(
                champion.evidence + challenger.evidence + scope_evidence
            )
        )
        source_fingerprint = source_compatibility_fingerprint(source_evidence)
        predictive = compare_predictive_metrics(
            champion_scope, challenger_scope, self._policy
        )
        calibration = compare_calibration_metrics(
            champion_scope, challenger_scope, self._policy, len(predictive)
        )
        betting = compare_betting_metrics(
            champion_scope,
            challenger_scope,
            self._policy,
            len(predictive) + len(calibration),
        )
        risk = compare_risk_metrics(
            champion_scope,
            challenger_scope,
            self._policy,
            len(predictive) + len(calibration) + len(betting),
        )
        metrics = predictive + calibration + betting + risk
        stability = calculate_stability(
            champion_scope, challenger_scope, self._policy
        )
        statistical = calculate_statistical_evidence(
            champion_scope,
            challenger_scope,
            comparison_fingerprint=sha256_fingerprint(
                (request_fingerprint, candidate.challenger_candidate_id)
            ),
            policy=self._policy,
        )
        scope_review = bool(scope_reasons)
        gates = evaluate_eligibility_gates(
            shared_prediction_count=len(champion_scope.predictions),
            shared_selected_bet_count=min(
                len(champion_scope.selections),
                len(challenger_scope.selections),
            ),
            metric_evaluations=metrics,
            stability_groups=stability,
            challenger_run=challenger_scope,
            scope=command.scope,
            policy=self._policy,
            scope_review=scope_review,
        )
        components, score = calculate_promotion_score(
            metrics, stability, gates, statistical, self._policy
        )
        recommendation, reasons = recommend_challenger(
            gates,
            score,
            statistical,
            self._policy,
            scope_review=scope_review,
        )
        evaluation_material = {
            "candidate": candidate,
            "source_fingerprint": source_fingerprint,
            "metric_fingerprints": tuple(item.metric_fingerprint for item in metrics),
            "stability_fingerprints": tuple(
                item.stability_fingerprint for item in stability
            ),
            "statistical_fingerprints": tuple(
                item.evidence_fingerprint for item in statistical
            ),
            "gates": gates,
            "components": components,
            "score": score,
            "recommendation": recommendation,
            "reason_codes": tuple(scope_reasons) + reasons,
        }
        fingerprint = challenger_evaluation_fingerprint(evaluation_material)
        return ChallengerEvaluation(
            candidate=candidate,
            source_compatibility_fingerprint=source_fingerprint,
            evaluation_fingerprint=fingerprint,
            shared_prediction_count=len(champion_scope.predictions),
            shared_selected_bet_count=min(
                len(champion_scope.selections), len(challenger_scope.selections)
            ),
            source_evidence=source_evidence,
            metric_evaluations=metrics,
            stability_groups=stability,
            statistical_evidence=statistical,
            gate_evaluations=gates,
            score_components=components,
            promotion_score=score,
            recommendation=recommendation,
            deterministic_rank=None,
            reason_codes=tuple(scope_reasons) + reasons,
            exclusions=tuple(
                replace(
                    item,
                    challenger_candidate_id=candidate.challenger_candidate_id,
                )
                for item in scope_exclusions
            ),
        )

    def _rank_and_limit_winner(self, evaluations):
        ranked = rank_challengers(evaluations)
        promotion_awarded = False
        result = []
        for rank, item in enumerate(ranked, start=1):
            recommendation = item.recommendation
            reasons = item.reason_codes
            if recommendation is Recommendation.PROMOTE_CHALLENGER:
                if promotion_awarded:
                    recommendation = Recommendation.KEEP_CHAMPION
                    reasons = reasons + ("HIGHER_RANKED_CHALLENGER_SELECTED",)
                else:
                    promotion_awarded = True
            updated = replace(
                item,
                deterministic_rank=rank,
                recommendation=recommendation,
                reason_codes=reasons,
            )
            updated = replace(
                updated,
                evaluation_fingerprint=challenger_evaluation_fingerprint(
                    {
                        "prior_evaluation_fingerprint": item.evaluation_fingerprint,
                        "rank": rank,
                        "recommendation": recommendation,
                        "reason_codes": reasons,
                    }
                ),
            )
            result.append(updated)
        return tuple(result)


def compare_models_for_promotion(service, command):
    """Explicit one-shot comparison; no scheduling or activation."""
    return service.compare(command)


def _verify_compatibility(champion, challenger, scope, policy):
    c_model, h_model = champion.model_artifact, challenger.model_artifact
    if tuple(c_model.canonical_target_order) != tuple(h_model.canonical_target_order):
        return ("TARGET_SCHEMA_INCOMPATIBLE",)
    if c_model.label_schema_version != h_model.label_schema_version:
        return ("LABEL_SCHEMA_INCOMPATIBLE",)
    if (
        c_model.feature_schema_version != h_model.feature_schema_version
        or c_model.feature_schema_fingerprint != h_model.feature_schema_fingerprint
    ):
        return ("FEATURE_SCHEMA_FAMILY_INCOMPATIBLE",)
    for run in (champion.backtest_run, challenger.backtest_run):
        command = run.command
        required = (
            (command.odds_selection_policy_version, scope.required_odds_policy_version, "ODDS_POLICY_INCOMPATIBLE"),
            (command.selection_policy_version, scope.required_selection_policy_version, "SELECTION_POLICY_INCOMPATIBLE"),
            (command.staking_policy_version, scope.required_staking_policy_version, "STAKING_POLICY_INCOMPATIBLE"),
            (command.settlement_policy_version, scope.required_settlement_policy_version, "SETTLEMENT_POLICY_INCOMPATIBLE"),
            (command.metric_policy_version, scope.required_metric_policy_version, "METRIC_POLICY_INCOMPATIBLE"),
        )
        for actual, expected, reason in required:
            if actual != expected:
                return (reason,)
    if champion.backtest_run.command.currency != challenger.backtest_run.command.currency:
        return ("CURRENCY_INCOMPATIBLE",)
    champion_markets = tuple(
        item.value for item in champion.backtest_run.command.markets
    )
    challenger_markets = tuple(
        item.value for item in challenger.backtest_run.command.markets
    )
    if champion_markets != challenger_markets:
        return ("SUPPORTED_MARKET_SET_INCOMPATIBLE",)
    if scope.required_markets and not set(scope.required_markets).issubset(
        champion_markets
    ):
        return ("REQUIRED_MARKET_SET_UNSUPPORTED",)
    return ()


def _aggregate_recommendation(evaluations):
    values = {item.recommendation for item in evaluations}
    for recommendation in (
        Recommendation.REVIEW_REQUIRED,
        Recommendation.INSUFFICIENT_EVIDENCE,
        Recommendation.KEEP_CHAMPION,
        Recommendation.REJECT_CHALLENGER,
    ):
        if recommendation in values:
            return recommendation
    return Recommendation.KEEP_CHAMPION


def _command_policy_versions(command):
    return (
        command.promotion_policy_version,
        command.evidence_policy_version,
        command.compatibility_policy_version,
        command.significance_policy_version,
        command.predictive_score_policy_version,
        command.calibration_score_policy_version,
        command.betting_score_policy_version,
        command.risk_score_policy_version,
        command.stability_score_policy_version,
        command.tie_break_policy_version,
    )


def _exclusion(candidate_id, stage, reason, order):
    return ComparisonExclusion(
        exclusion_id=f"model-comparison-exclusion-{sha256_fingerprint((candidate_id, stage, reason, order))}",
        challenger_candidate_id=candidate_id,
        exclusion_stage=stage,
        exclusion_reason=reason,
        detail_snapshot=canonical_json({"fail_closed": True}),
        deterministic_order=order,
    )


def _outcome(run, status, command, request_fingerprint, reasons):
    return ComparisonOutcome(
        status=status,
        comparison_run_id=run.comparison_run_id if run else None,
        comparison_request_id=command.comparison_request_id,
        request_fingerprint=request_fingerprint,
        comparison_run_fingerprint=run.comparison_run_fingerprint if run else None,
        champion_model_artifact_id=command.champion_model_artifact_id,
        champion_model_artifact_fingerprint=command.champion_model_artifact_fingerprint,
        champion_calibration_artifact_set_id=command.champion_calibration_artifact_set_id,
        champion_calibration_artifact_set_fingerprint=command.champion_calibration_artifact_set_fingerprint,
        champion_backtest_run_id=command.champion_backtest_run_id,
        champion_backtest_run_fingerprint=command.champion_backtest_run_fingerprint,
        challenger_count=len(command.challengers),
        valid_challenger_count=len(run.evaluations) if run else 0,
        final_recommended_challenger_id=(
            run.final_recommended_challenger_id if run else None
        ),
        final_recommendation=run.final_recommendation if run else None,
        challenger_evaluations=run.evaluations if run else (),
        ordered_reason_codes=tuple(reasons),
        policy_versions=(
            (
                ("promotion", command.promotion_policy_version),
                ("evidence", command.evidence_policy_version),
                ("compatibility", command.compatibility_policy_version),
                ("significance", command.significance_policy_version),
                ("predictive_score", command.predictive_score_policy_version),
                ("calibration_score", command.calibration_score_policy_version),
                ("betting_score", command.betting_score_policy_version),
                ("risk_score", command.risk_score_policy_version),
                ("stability_score", command.stability_score_policy_version),
                ("tie_break", command.tie_break_policy_version),
            )
        ),
        comparison_scope=command.scope,
        comparison_timestamp=command.comparison_timestamp,
    )


def _rejected(command, status, reasons):
    request_id = getattr(command, "comparison_request_id", "")
    return ComparisonOutcome(
        status=status,
        comparison_run_id=None,
        comparison_request_id=request_id,
        request_fingerprint=None,
        comparison_run_fingerprint=None,
        champion_model_artifact_id=getattr(command, "champion_model_artifact_id", ""),
        champion_model_artifact_fingerprint=getattr(command, "champion_model_artifact_fingerprint", ""),
        champion_calibration_artifact_set_id=getattr(command, "champion_calibration_artifact_set_id", ""),
        champion_calibration_artifact_set_fingerprint=getattr(command, "champion_calibration_artifact_set_fingerprint", ""),
        champion_backtest_run_id=getattr(command, "champion_backtest_run_id", ""),
        champion_backtest_run_fingerprint=getattr(command, "champion_backtest_run_fingerprint", ""),
        challenger_count=len(getattr(command, "challengers", ())),
        valid_challenger_count=0,
        final_recommended_challenger_id=None,
        final_recommendation=None,
        challenger_evaluations=(),
        ordered_reason_codes=tuple(reasons),
        policy_versions=(),
        comparison_scope=None,
        comparison_timestamp=None,
    )
