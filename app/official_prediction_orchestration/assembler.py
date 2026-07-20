from datetime import datetime
from decimal import Decimal

from app.probability_calibration import ProbabilityCalibrationReport
from app.publication_quality_gate import (
    CalibrationQualityFacts,
    ModelHealthFacts,
    OfficialPublicationCandidate,
    PublicationState,
)
from app.risk_management import RiskProductScope

from .exceptions import CandidateAssemblyError
from .fingerprint import canonical_items
from .models import (
    AssemblyReason,
    ExposureEvaluationRecord,
    ModelHealthRecord,
    OfficialCandidateAssembly,
    OfficialCandidateAssemblyRequest,
    OfficialPredictionFacts,
    PublicationDeliveryState,
    PublicationStateRecord,
    RiskEvaluationRecord,
)


_SUPPORTED_MARKETS = {
    "MATCH WINNER",
    "MONEYLINE",
    "1X2",
    "DOUBLE CHANCE",
    "TOTALS",
    "OVER UNDER",
    "BTTS",
    "BOTH TEAMS TO SCORE",
}


class OfficialPredictionCandidateAssembler:
    """Selects supplied immutable facts without recalculating domain decisions."""

    def assemble(
        self,
        request: OfficialCandidateAssemblyRequest,
        publication: PublicationStateRecord | None,
    ) -> OfficialCandidateAssembly:
        prediction = request.prediction
        self._validate_prediction(prediction, request.evaluation_timestamp)
        calibration = self._select_calibration(request)
        health = self._select_health(request)
        risk = self._select_risk(request)
        exposure = self._select_exposure(request)
        bankroll = request.bankroll
        if bankroll is None:
            self._fail(
                AssemblyReason.BANKROLL_FACTS_MISSING,
                "An immutable bankroll-scope record is required.",
            )
        if bankroll.product_scope is not RiskProductScope.OFFICIAL:
            self._fail(
                AssemblyReason.WRONG_BANKROLL_SCOPE,
                "Only the Official bankroll scope can form an Official candidate.",
            )
        self._valid_past_timestamp(
            bankroll.snapshot_timestamp,
            request.evaluation_timestamp,
            "Bankroll snapshot",
        )
        if publication is None:
            self._fail(
                AssemblyReason.PUBLICATION_STATE_MISSING,
                "Publication state must be supplied by the publication-state port.",
            )
        if (
            publication.prediction_id != prediction.prediction_id
            or publication.match_id != prediction.match_id
        ):
            self._fail(
                AssemblyReason.PUBLICATION_IDENTITY_MISMATCH,
                "Publication state does not match the prediction and match identity.",
            )
        self._valid_past_timestamp(
            publication.observed_at,
            request.evaluation_timestamp,
            "Publication-state observation",
        )

        verified_ev = (
            calibration.calibrated_probability * prediction.decimal_odds
            - Decimal("1")
        )
        gate_candidate = OfficialPublicationCandidate(
            prediction_id=prediction.prediction_id,
            model_version=prediction.model_version,
            market=prediction.market,
            selection=prediction.selection,
            market_line=prediction.market_line,
            raw_probability=prediction.raw_probability,
            calibrated_probability=calibration.calibrated_probability,
            decimal_odds=prediction.decimal_odds,
            expected_value=prediction.expected_value,
            confidence=prediction.confidence,
            prediction_timestamp=prediction.prediction_timestamp,
            kickoff_timestamp=prediction.kickoff_timestamp,
            evaluation_timestamp=request.evaluation_timestamp,
            odds_observed_at=prediction.odds_timestamp,
            core_data_observed_at=prediction.core_data_timestamp,
            supporting_data_status=prediction.supporting_data_status,
            market_availability=prediction.market_availability,
            calibration=CalibrationQualityFacts(
                brier_score=calibration.metric_summary.brier_score,
                log_loss=calibration.metric_summary.log_loss,
                expected_calibration_error=(
                    calibration.metric_summary.expected_calibration_error
                ),
                maximum_calibration_error=(
                    calibration.metric_summary.maximum_calibration_error
                ),
                sample_size=calibration.metric_summary.observation_count,
                model_version=calibration.model_version,
            ),
            model_health=ModelHealthFacts(
                status=health.status,
                model_version=health.model_version,
                checked_at=health.checked_at,
            ),
            risk_result=risk.decision,
            exposure_result=exposure.decision,
            bankroll_scope=bankroll.product_scope,
            publication_state=self._gate_publication_state(publication.state),
            lineup_status=prediction.lineup_status,
            injury_status=prediction.injury_status,
        )
        normalized = self._normalized(
            request,
            publication,
            calibration,
            health,
            risk,
            exposure,
            verified_ev,
        )
        return OfficialCandidateAssembly(
            prediction_id=prediction.prediction_id,
            match_id=prediction.match_id,
            gate_candidate=gate_candidate,
            calibration_run_id=calibration.calibration_run_id,
            calibration_method=calibration.calibration_method.value,
            calibration_timestamp=calibration.timestamp,
            risk_evaluation_id=risk.evaluation_id,
            risk_evaluated_at=risk.evaluated_at,
            exposure_evaluation_id=exposure.evaluation_id,
            exposure_evaluated_at=exposure.evaluated_at,
            bankroll_reference_id=bankroll.reference_id,
            bankroll_snapshot_timestamp=bankroll.snapshot_timestamp,
            publication_state=publication.state,
            publication_attempt_reference=publication.attempt_reference,
            verified_expected_value=verified_ev,
            normalized_input=normalized,
        )

    def _validate_prediction(
        self,
        prediction: OfficialPredictionFacts,
        evaluation_timestamp: datetime,
    ) -> None:
        if not prediction.prediction_id.strip():
            self._fail(
                AssemblyReason.INVALID_PREDICTION_IDENTITY,
                "Prediction ID must not be empty.",
            )
        if not prediction.match_id.strip():
            self._fail(
                AssemblyReason.INVALID_MATCH_IDENTITY,
                "Match ID must not be empty.",
            )
        if not prediction.model_version.strip():
            self._fail(
                AssemblyReason.INVALID_MODEL_VERSION,
                "Model version must not be empty.",
            )
        self._valid_timestamp(evaluation_timestamp, "Evaluation timestamp")
        for value, label in (
            (prediction.prediction_timestamp, "Prediction timestamp"),
            (prediction.kickoff_timestamp, "Kickoff timestamp"),
            (prediction.odds_timestamp, "Odds timestamp"),
            (prediction.core_data_timestamp, "Core-data timestamp"),
        ):
            self._valid_timestamp(value, label)
        if prediction.prediction_timestamp >= prediction.kickoff_timestamp:
            self._fail(
                AssemblyReason.INVALID_TIMESTAMP,
                "Prediction timestamp must precede kickoff.",
            )
        for value, label in (
            (prediction.prediction_timestamp, "Prediction timestamp"),
            (prediction.odds_timestamp, "Odds timestamp"),
            (prediction.core_data_timestamp, "Core-data timestamp"),
        ):
            if value > evaluation_timestamp:
                self._fail(
                    AssemblyReason.INVALID_TIMESTAMP,
                    f"{label} cannot be after orchestration evaluation time.",
                )
        if not self._finite(prediction.raw_probability) or not (
            Decimal("0") <= prediction.raw_probability <= Decimal("1")
        ):
            self._fail(
                AssemblyReason.INVALID_PROBABILITY,
                "Raw probability must be a finite Decimal in [0, 1].",
            )
        if not self._finite(prediction.decimal_odds) or prediction.decimal_odds <= 1:
            self._fail(
                AssemblyReason.INVALID_ODDS,
                "Decimal odds must be a finite Decimal greater than one.",
            )
        if not self._finite(prediction.expected_value):
            self._fail(
                AssemblyReason.INVALID_EXPECTED_VALUE,
                "Supplied expected value must be a finite Decimal.",
            )
        market = self._normalize(prediction.market)
        selection = self._normalize(prediction.selection)
        if not self._valid_market_facts(
            market,
            selection,
            prediction.market_line,
        ):
            self._fail(
                AssemblyReason.UNSUPPORTED_MARKET_FACTS,
                "Market and selection facts must use supported Official semantics.",
            )

    def _select_calibration(
        self,
        request: OfficialCandidateAssemblyRequest,
    ) -> ProbabilityCalibrationReport:
        prediction = request.prediction
        matching_model = tuple(
            item
            for item in request.calibration_records
            if item.model_version == prediction.model_version
            and item.timestamp <= request.evaluation_timestamp
        )
        if not matching_model:
            reason = (
                AssemblyReason.CALIBRATION_MODEL_VERSION_MISMATCH
                if any(
                    item.timestamp <= request.evaluation_timestamp
                    and item.model_version != prediction.model_version
                    for item in request.calibration_records
                )
                else AssemblyReason.NO_VALID_CALIBRATION_RECORD
            )
            self._fail(
                reason,
                "No persisted calibration record matches the model and cutoff.",
            )
        matching_probability = tuple(
            item
            for item in matching_model
            if item.raw_probability == prediction.raw_probability
        )
        if not matching_probability:
            self._fail(
                AssemblyReason.CALIBRATION_RAW_PROBABILITY_MISMATCH,
                "Calibration records do not transform this raw probability.",
            )
        return max(
            matching_probability,
            key=lambda item: (item.timestamp, item.calibration_run_id),
        )

    def _select_health(
        self,
        request: OfficialCandidateAssemblyRequest,
    ) -> ModelHealthRecord:
        matching = tuple(
            item
            for item in request.model_health_records
            if item.model_version == request.prediction.model_version
            and item.checked_at <= request.evaluation_timestamp
        )
        if not matching:
            reason = (
                AssemblyReason.MODEL_HEALTH_VERSION_MISMATCH
                if request.model_health_records
                else AssemblyReason.NO_VALID_MODEL_HEALTH_RECORD
            )
            self._fail(reason, "No model-health record matches the model and cutoff.")
        selected = max(matching, key=lambda item: (item.checked_at, item.record_id))
        if not selected.record_id.strip():
            self._fail(
                AssemblyReason.NO_VALID_MODEL_HEALTH_RECORD,
                "Selected model-health record identity must not be empty.",
            )
        return selected

    def _select_risk(
        self,
        request: OfficialCandidateAssemblyRequest,
    ) -> RiskEvaluationRecord:
        matching = tuple(
            item
            for item in request.risk_evaluations
            if self._evaluation_matches(item, request)
            and item.evaluated_at <= request.evaluation_timestamp
        )
        if not matching:
            reason = (
                AssemblyReason.RISK_IDENTITY_MISMATCH
                if request.risk_evaluations
                else AssemblyReason.NO_VALID_RISK_EVALUATION
            )
            self._fail(reason, "No risk evaluation matches all candidate facts.")
        selected = max(matching, key=lambda item: (item.evaluated_at, item.evaluation_id))
        if not selected.evaluation_id.strip():
            self._fail(
                AssemblyReason.NO_VALID_RISK_EVALUATION,
                "Selected risk evaluation identity must not be empty.",
            )
        return selected

    def _select_exposure(
        self,
        request: OfficialCandidateAssemblyRequest,
    ) -> ExposureEvaluationRecord:
        matching = tuple(
            item
            for item in request.exposure_evaluations
            if self._evaluation_matches(item, request)
            and item.evaluated_at <= request.evaluation_timestamp
        )
        if not matching:
            reason = (
                AssemblyReason.EXPOSURE_IDENTITY_MISMATCH
                if request.exposure_evaluations
                else AssemblyReason.NO_VALID_EXPOSURE_EVALUATION
            )
            self._fail(reason, "No exposure evaluation matches all candidate facts.")
        selected = max(matching, key=lambda item: (item.evaluated_at, item.evaluation_id))
        if not selected.evaluation_id.strip():
            self._fail(
                AssemblyReason.NO_VALID_EXPOSURE_EVALUATION,
                "Selected exposure evaluation identity must not be empty.",
            )
        return selected

    def _evaluation_matches(
        self,
        item: RiskEvaluationRecord | ExposureEvaluationRecord,
        request: OfficialCandidateAssemblyRequest,
    ) -> bool:
        prediction = request.prediction
        return (
            item.prediction_id == prediction.prediction_id
            and item.match_id == prediction.match_id
            and item.model_version == prediction.model_version
            and self._normalize(item.market) == self._normalize(prediction.market)
            and self._normalize(item.selection) == self._normalize(prediction.selection)
            and item.market_line == prediction.market_line
            and item.bankroll_scope is RiskProductScope.OFFICIAL
        )

    def _normalized(
        self,
        request: OfficialCandidateAssemblyRequest,
        publication: PublicationStateRecord,
        calibration: ProbabilityCalibrationReport,
        health: ModelHealthRecord,
        risk: RiskEvaluationRecord,
        exposure: ExposureEvaluationRecord,
        verified_ev: Decimal,
    ) -> tuple[tuple[str, str], ...]:
        prediction = request.prediction
        bankroll = request.bankroll
        assert bankroll is not None
        return canonical_items({
            "bankroll_reference_id": bankroll.reference_id,
            "bankroll_scope": bankroll.product_scope,
            "bankroll_snapshot_timestamp": bankroll.snapshot_timestamp,
            "calibrated_probability": calibration.calibrated_probability,
            "calibration_brier_score": calibration.metric_summary.brier_score,
            "calibration_ece": calibration.metric_summary.expected_calibration_error,
            "calibration_log_loss": calibration.metric_summary.log_loss,
            "calibration_mce": calibration.metric_summary.maximum_calibration_error,
            "calibration_method": calibration.calibration_method,
            "calibration_run_id": calibration.calibration_run_id,
            "calibration_sample_size": calibration.metric_summary.observation_count,
            "calibration_timestamp": calibration.timestamp,
            "calibration_version": calibration.calibration_version,
            "confidence": prediction.confidence,
            "core_data_timestamp": prediction.core_data_timestamp,
            "decimal_odds": prediction.decimal_odds,
            "evaluation_timestamp": request.evaluation_timestamp,
            "expected_value_supplied": prediction.expected_value,
            "expected_value_verified": verified_ev,
            "exposure_decision": exposure.decision,
            "exposure_evaluated_at": exposure.evaluated_at,
            "exposure_evaluation_id": exposure.evaluation_id,
            "injury_status": prediction.injury_status,
            "kickoff_timestamp": prediction.kickoff_timestamp,
            "lineup_status": prediction.lineup_status,
            "market": self._normalize(prediction.market),
            "market_availability": prediction.market_availability,
            "market_line": prediction.market_line,
            "match_id": prediction.match_id,
            "model_health_checked_at": health.checked_at,
            "model_health_record_id": health.record_id,
            "model_health_status": health.status,
            "model_version": prediction.model_version,
            "odds_timestamp": prediction.odds_timestamp,
            "prediction_id": prediction.prediction_id,
            "prediction_timestamp": prediction.prediction_timestamp,
            "publication_attempt_reference": publication.attempt_reference,
            "publication_state": publication.state,
            "publication_state_observed_at": publication.observed_at,
            "raw_probability": prediction.raw_probability,
            "risk_decision": risk.decision,
            "risk_evaluated_at": risk.evaluated_at,
            "risk_evaluation_id": risk.evaluation_id,
            "selection": self._normalize(prediction.selection),
            "supporting_data_status": prediction.supporting_data_status,
        })

    @staticmethod
    def _gate_publication_state(state: PublicationDeliveryState) -> PublicationState:
        return {
            PublicationDeliveryState.NEVER_ATTEMPTED: PublicationState.UNPUBLISHED,
            PublicationDeliveryState.CLAIMED: PublicationState.CLAIMED,
            PublicationDeliveryState.ATTEMPTING: PublicationState.ATTEMPTING,
            PublicationDeliveryState.PUBLISHED: PublicationState.PUBLISHED,
            PublicationDeliveryState.CONFIRMED_FAILED_RETRYABLE: PublicationState.FAILED,
            PublicationDeliveryState.INDETERMINATE_FAILURE: PublicationState.CLAIMED,
        }[state]

    @staticmethod
    def _valid_timestamp(value: datetime, label: str) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            OfficialPredictionCandidateAssembler._fail(
                AssemblyReason.INVALID_TIMESTAMP,
                f"{label} must be timezone-aware.",
            )

    @classmethod
    def _valid_past_timestamp(
        cls,
        value: datetime,
        cutoff: datetime,
        label: str,
    ) -> None:
        cls._valid_timestamp(value, label)
        if value > cutoff:
            cls._fail(
                AssemblyReason.INVALID_TIMESTAMP,
                f"{label} cannot be after orchestration evaluation time.",
            )

    @staticmethod
    def _finite(value: object) -> bool:
        return isinstance(value, Decimal) and value.is_finite()

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.strip().upper().replace("_", " ").replace("/", " ").split())

    @staticmethod
    def _valid_market_facts(
        market: str,
        selection: str,
        line: Decimal | None,
    ) -> bool:
        if market not in _SUPPORTED_MARKETS or not selection:
            return False
        if market in {"MATCH WINNER", "MONEYLINE", "1X2"}:
            return line is None and selection in {"HOME", "DRAW", "AWAY", "1", "X", "2"}
        if market == "DOUBLE CHANCE":
            return line is None and selection in {
                "HOME OR DRAW",
                "AWAY OR DRAW",
                "HOME OR AWAY",
                "1X",
                "X2",
                "12",
            }
        if market in {"TOTALS", "OVER UNDER"}:
            return (
                (selection.startswith("OVER") or selection.startswith("UNDER"))
                and isinstance(line, Decimal)
                and line.is_finite()
                and line > 0
            )
        return line is None and selection in {"YES", "NO"}

    @staticmethod
    def _fail(reason: AssemblyReason, explanation: str) -> None:
        raise CandidateAssemblyError((reason,), (explanation,))
