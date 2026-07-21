"""Application service for one calibrated assembly and one supplied price."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from app.calibrated_market_probabilities import (
    CalibratedMarketProbabilityAssembly,
)

from .calculations import (
    calculate,
    classify_calibrated_freshness,
    classify_market_value,
    classify_odds_freshness,
    worst_freshness,
)
from .exceptions import (
    IncompatibleMarketError,
    InvalidCalibrationError,
    InvalidOddsError,
    MarketValueConflictError,
    MarketValuePersistenceError,
    ProvenanceMismatchError,
)
from .fingerprint import assessment_fingerprint
from .market_mapping import MarketMappingRegistry
from .models import (
    ActionabilityStatus,
    AssessmentOutcomeStatus,
    AssessmentValidationSummary,
    FreshnessState,
    MarketValueAssessment,
    MarketValueAssessmentOutcome,
    SuppliedOddsSnapshot,
)
from .odds import normalize_odds_snapshot
from .policy import MarketValueAssessmentPolicy
from .ports import MarketValueRepository
from .validation import validate_calibrated_assembly, validate_provenance


class MarketValueAssessmentService:
    """Deterministically assess value without selecting or publishing a bet."""

    def __init__(
        self,
        repository: MarketValueRepository,
        mappings: MarketMappingRegistry,
        policy: MarketValueAssessmentPolicy,
    ) -> None:
        self.repository = repository
        self.mappings = mappings
        self.policy = policy

    def assess(
        self,
        assembly: CalibratedMarketProbabilityAssembly | None,
        supplied_odds: SuppliedOddsSnapshot,
        assessment_timestamp: datetime,
    ) -> MarketValueAssessmentOutcome:
        assembly_id = (
            assembly.calibrated_assembly_id
            if isinstance(assembly, CalibratedMarketProbabilityAssembly)
            else ""
        )
        match_id = (
            assembly.match_id
            if isinstance(assembly, CalibratedMarketProbabilityAssembly)
            else ""
        )
        try:
            source = validate_calibrated_assembly(assembly, self.policy)
            persisted_assembly_fingerprint = (
                self.repository.load_calibrated_assembly_fingerprint(
                    source.calibrated_assembly_id
                )
            )
            if (
                persisted_assembly_fingerprint
                != source.calibrated_assembly_fingerprint
            ):
                raise InvalidCalibrationError(
                    "Calibrated assembly is not persisted or differs from history."
                )
            persisted_kickoff = self.repository.load_source_kickoff(
                source.source_snapshot_id
            )
        except InvalidCalibrationError as exc:
            return self._failure(
                AssessmentOutcomeStatus.REJECTED_INVALID_CALIBRATION,
                assembly_id,
                match_id,
                "",
                "",
                assessment_timestamp,
                "INVALID_CALIBRATION",
                str(exc),
            )
        except MarketValuePersistenceError:
            return self._failure(
                AssessmentOutcomeStatus.PERSISTENCE_FAILURE,
                assembly_id,
                match_id,
                "",
                "",
                assessment_timestamp,
                "PERSISTENCE_FAILURE",
                "Persistence failed safely.",
            )

        try:
            odds = normalize_odds_snapshot(supplied_odds, self.policy)
        except InvalidOddsError as exc:
            return self._failure(
                AssessmentOutcomeStatus.REJECTED_INVALID_ODDS,
                assembly_id,
                match_id,
                getattr(supplied_odds, "bookmaker_id", ""),
                "",
                assessment_timestamp,
                "INVALID_ODDS",
                str(exc),
            )

        market_identity = _market_identity(
            odds.market_type.value,
            odds.selection.value,
            odds.market_line,
        )
        try:
            effective_timestamp = validate_provenance(
                source,
                odds,
                persisted_kickoff,
                assessment_timestamp,
                self.policy,
            )
        except ProvenanceMismatchError as exc:
            return self._failure(
                AssessmentOutcomeStatus.REJECTED_PROVENANCE_MISMATCH,
                assembly_id,
                match_id,
                odds.bookmaker_id,
                market_identity,
                assessment_timestamp,
                "PROVENANCE_MISMATCH",
                str(exc),
                odds.decimal_odds,
            )

        try:
            mapping = self.mappings.resolve(
                odds.market_type,
                odds.selection,
                odds.market_line,
            )
        except IncompatibleMarketError as exc:
            return self._failure(
                AssessmentOutcomeStatus.REJECTED_INCOMPATIBLE_MARKET,
                assembly_id,
                match_id,
                odds.bookmaker_id,
                market_identity,
                effective_timestamp,
                "INCOMPATIBLE_MARKET",
                str(exc),
                odds.decimal_odds,
            )

        probabilities = {
            item.target: item.calibrated_probability
            for item in source.ordered_target_results
        }
        fair_probability = sum(
            (probabilities[target] for target in mapping.source_targets),
            Decimal(0),
        )
        lower_probability, upper_probability = mapping.valid_probability_range
        if not lower_probability <= fair_probability <= upper_probability:
            return self._failure(
                AssessmentOutcomeStatus.REJECTED_INVALID_CALIBRATION,
                assembly_id,
                match_id,
                odds.bookmaker_id,
                market_identity,
                effective_timestamp,
                "DERIVED_PROBABILITY_OUT_OF_RANGE",
                "Mapped calibrated probability is outside its valid range.",
                odds.decimal_odds,
            )

        metrics = calculate(fair_probability, odds.decimal_odds, self.policy)
        calibrated_timestamp = source.calibration_effective_timestamp.astimezone(
            timezone.utc
        )
        odds_age = int(
            (effective_timestamp - odds.odds_effective_timestamp).total_seconds()
        )
        calibrated_age = int(
            (effective_timestamp - calibrated_timestamp).total_seconds()
        )
        time_to_kickoff = int(
            (odds.kickoff_timestamp - effective_timestamp).total_seconds()
        )
        odds_freshness = classify_odds_freshness(odds_age, self.policy)
        calibrated_freshness = classify_calibrated_freshness(
            calibrated_age, self.policy
        )
        overall_freshness = worst_freshness(
            odds_freshness, calibrated_freshness
        )
        actionability, reason_codes = self._actionability(
            odds_freshness,
            overall_freshness,
            time_to_kickoff,
        )
        validation_summary = AssessmentValidationSummary(
            mapping_version=self.mappings.version,
            ordered_checks=(
                "CALIBRATED_PROVENANCE_VALID",
                "ODDS_VALID",
                "MARKET_MAPPING_VALID",
                "TIMESTAMPS_VALID",
            ),
        )
        assessment = MarketValueAssessment(
            value_assessment_id="",
            calibrated_assembly_id=assembly_id,
            inference_id=source.inference_id,
            model_input_id=source.model_input_id,
            match_id=match_id,
            source_snapshot_id=source.source_snapshot_id,
            feature_set_id=source.source_feature_set_id,
            source_model_artifact_id=source.source_model_artifact_id,
            source_model_version=source.source_model_version,
            calibration_set_id=source.calibration_set_id,
            calibration_set_fingerprint=source.calibration_set_fingerprint,
            odds_record_id=odds.odds_record_id,
            odds_fingerprint=odds.odds_fingerprint,
            source_provider=odds.source_provider,
            bookmaker_id=odds.bookmaker_id,
            market_type=odds.market_type,
            selection=odds.selection,
            market_line=odds.market_line,
            source_calibrated_targets=mapping.source_targets,
            probability_derivation_type=mapping.probability_source_type,
            derivation_version=self.mappings.version,
            fair_probability=metrics.fair_probability,
            fair_decimal_odds=metrics.fair_decimal_odds,
            bookmaker_decimal_odds=metrics.bookmaker_decimal_odds,
            implied_probability=metrics.implied_probability,
            break_even_probability=metrics.break_even_probability,
            absolute_probability_edge=metrics.absolute_probability_edge,
            relative_probability_edge=metrics.relative_probability_edge,
            expected_value=metrics.expected_value,
            expected_return=metrics.expected_return,
            potential_profit=metrics.potential_profit,
            odds_age_seconds=odds_age,
            calibrated_age_seconds=calibrated_age,
            time_to_kickoff_seconds=time_to_kickoff,
            value_classification=classify_market_value(
                fair_probability,
                odds.decimal_odds,
                self.policy,
            ),
            odds_freshness=odds_freshness,
            calibrated_freshness=calibrated_freshness,
            overall_freshness=overall_freshness,
            actionability_status=actionability,
            assessment_timestamp=effective_timestamp,
            kickoff_timestamp=odds.kickoff_timestamp,
            value_policy_version=self.policy.version,
            calibrated_assembly_fingerprint=(
                source.calibrated_assembly_fingerprint
            ),
            assessment_fingerprint="",
            ordered_reason_codes=reason_codes,
            validation_summary=validation_summary,
            created_timestamp=effective_timestamp,
        )
        fingerprint = assessment_fingerprint(assessment)
        assessment = replace(
            assessment,
            value_assessment_id=_assessment_id(fingerprint),
            assessment_fingerprint=fingerprint,
        )

        try:
            stored, existing = self.repository.append_assessment_with_odds(
                odds, assessment
            )
        except MarketValueConflictError as exc:
            return self._failure(
                AssessmentOutcomeStatus.CONFLICT,
                assembly_id,
                match_id,
                odds.bookmaker_id,
                market_identity,
                effective_timestamp,
                "CONFLICT",
                str(exc),
                metrics.bookmaker_decimal_odds,
            )
        except MarketValuePersistenceError:
            return self._failure(
                AssessmentOutcomeStatus.PERSISTENCE_FAILURE,
                assembly_id,
                match_id,
                odds.bookmaker_id,
                market_identity,
                effective_timestamp,
                "PERSISTENCE_FAILURE",
                "Persistence failed safely.",
                metrics.bookmaker_decimal_odds,
            )

        if existing:
            final_status = AssessmentOutcomeStatus.IDEMPOTENT_EXISTING
        elif stored.actionability_status is ActionabilityStatus.ACTIONABLE:
            final_status = AssessmentOutcomeStatus.ASSESSED
        else:
            final_status = AssessmentOutcomeStatus.NON_ACTIONABLE
        return MarketValueAssessmentOutcome(
            value_assessment_id=stored.value_assessment_id,
            calibrated_assembly_id=assembly_id,
            match_id=match_id,
            bookmaker_id=stored.bookmaker_id,
            market_identity=market_identity,
            final_status=final_status,
            value_classification=stored.value_classification,
            actionability_status=stored.actionability_status,
            fair_probability=stored.fair_probability,
            fair_odds=stored.fair_decimal_odds,
            bookmaker_odds=stored.bookmaker_decimal_odds,
            expected_value=stored.expected_value,
            probability_edge=stored.absolute_probability_edge,
            assessment_fingerprint=stored.assessment_fingerprint,
            ordered_reason_codes=stored.ordered_reason_codes,
            explanations=("Deterministic market value assessment persisted.",),
            assessment_timestamp=effective_timestamp,
            policy_version=self.policy.version,
        )

    def _actionability(
        self,
        odds_freshness: FreshnessState,
        overall_freshness: FreshnessState,
        time_to_kickoff: int,
    ) -> tuple[ActionabilityStatus, tuple[str, ...]]:
        if odds_freshness is FreshnessState.EXPIRED:
            return ActionabilityStatus.NON_ACTIONABLE_EXPIRED, ("ODDS_EXPIRED",)
        if time_to_kickoff < self.policy.minimum_time_before_kickoff_seconds:
            return (
                ActionabilityStatus.NON_ACTIONABLE_TOO_CLOSE_TO_KICKOFF,
                ("TOO_CLOSE_TO_KICKOFF",),
            )
        if (
            overall_freshness is FreshnessState.STALE
            and not self.policy.stale_is_actionable
        ):
            return ActionabilityStatus.NON_ACTIONABLE_STALE, ("DATA_STALE",)
        return ActionabilityStatus.ACTIONABLE, ("STRUCTURALLY_ACTIONABLE",)

    def _failure(
        self,
        status: AssessmentOutcomeStatus,
        assembly_id: str,
        match_id: str,
        bookmaker_id: str,
        market_identity: str,
        timestamp: datetime,
        reason_code: str,
        explanation: str,
        bookmaker_odds: Decimal | None = None,
    ) -> MarketValueAssessmentOutcome:
        return MarketValueAssessmentOutcome(
            value_assessment_id=None,
            calibrated_assembly_id=assembly_id,
            match_id=match_id,
            bookmaker_id=bookmaker_id,
            market_identity=market_identity,
            final_status=status,
            value_classification=None,
            actionability_status=None,
            fair_probability=None,
            fair_odds=None,
            bookmaker_odds=bookmaker_odds,
            expected_value=None,
            probability_edge=None,
            assessment_fingerprint=None,
            ordered_reason_codes=(reason_code,),
            explanations=(explanation,),
            assessment_timestamp=timestamp,
            policy_version=self.policy.version,
        )


def assess_market_value(
    service: MarketValueAssessmentService,
    assembly: CalibratedMarketProbabilityAssembly | None,
    odds: SuppliedOddsSnapshot,
    *,
    assessment_timestamp: datetime,
) -> MarketValueAssessmentOutcome:
    """Public single-assessment boundary with an explicit effective timestamp."""

    return service.assess(assembly, odds, assessment_timestamp)


def _assessment_id(fingerprint: str) -> str:
    return "market-value-" + hashlib.sha256(
        f"market-value-id-v1|{fingerprint}".encode("utf-8")
    ).hexdigest()


def _market_identity(
    market_type: str,
    selection: str,
    market_line: Decimal | None,
) -> str:
    line = "" if market_line is None else format(market_line.normalize(), "f")
    return f"{market_type}/{selection}/{line}"
