from datetime import datetime

from .models import (
    FinishedMatchResult,
    PublishedPredictionReference,
    ResolvedPredictionResult,
    ResolutionStatus,
    SettlementReasonCode,
)
from .policy import FixtureStatusPolicy
from .rules import MarketSettlementRegistry


class PredictionResultResolver:
    FRAMEWORK_VERSION = "result-resolution-v1"

    def __init__(
        self,
        status_policy: FixtureStatusPolicy,
        market_registry: MarketSettlementRegistry,
    ) -> None:
        self._status_policy = status_policy
        self._market_registry = market_registry

    def resolve(
        self,
        prediction: PublishedPredictionReference,
        match: FinishedMatchResult | None,
        evaluated_at: datetime,
    ) -> ResolvedPredictionResult:
        if evaluated_at.tzinfo is None:
            raise ValueError("Resolution timestamp must be timezone-aware.")
        if match is None:
            return self._result(
                prediction,
                None,
                ResolutionStatus.UNRESOLVED,
                None,
                self.FRAMEWORK_VERSION,
                (SettlementReasonCode.MATCH_DATA_MISSING,),
            )
        if prediction.fixture_id != match.fixture_id:
            return self._result(
                prediction,
                match,
                ResolutionStatus.UNRESOLVED,
                None,
                self.FRAMEWORK_VERSION,
                (SettlementReasonCode.FIXTURE_MISMATCH,),
            )

        fixture_status = match.status.strip().upper()
        if fixture_status in self._status_policy.pending_statuses:
            return self._result(
                prediction,
                match,
                ResolutionStatus.PENDING,
                None,
                self.FRAMEWORK_VERSION,
                (SettlementReasonCode.MATCH_PENDING,),
            )

        non_playable = self._status_policy.classify_non_playable(fixture_status)
        if non_playable is not None:
            status, reason = non_playable
            return self._result(
                prediction,
                match,
                status,
                evaluated_at if status is ResolutionStatus.VOID else None,
                self.FRAMEWORK_VERSION,
                (reason,),
            )

        if fixture_status not in self._status_policy.finished_statuses:
            return self._result(
                prediction,
                match,
                ResolutionStatus.UNRESOLVED,
                None,
                self.FRAMEWORK_VERSION,
                (SettlementReasonCode.UNSUPPORTED_FIXTURE_STATUS,),
            )

        if match.home_score is None or match.away_score is None:
            return self._result(
                prediction,
                match,
                ResolutionStatus.UNRESOLVED,
                None,
                self.FRAMEWORK_VERSION,
                (SettlementReasonCode.FINAL_SCORE_MISSING,),
            )

        rule = self._market_registry.find(prediction.market)
        if rule is None:
            reason = (
                SettlementReasonCode.MALFORMED_PREDICTION
                if not prediction.market.strip()
                else SettlementReasonCode.UNSUPPORTED_MARKET
            )
            return self._result(
                prediction,
                match,
                ResolutionStatus.UNRESOLVED,
                None,
                self.FRAMEWORK_VERSION,
                (reason,),
            )

        settlement = rule.settle(prediction, match)
        resolved_at = evaluated_at if settlement.status in {
            ResolutionStatus.WON,
            ResolutionStatus.LOST,
            ResolutionStatus.VOID,
        } else None
        return self._result(
            prediction,
            match,
            settlement.status,
            resolved_at,
            settlement.rule_version,
            settlement.reason_codes,
        )

    @staticmethod
    def _result(
        prediction: PublishedPredictionReference,
        match: FinishedMatchResult | None,
        status: ResolutionStatus,
        resolved_at: datetime | None,
        rule_version: str,
        reason_codes: tuple[SettlementReasonCode, ...],
    ) -> ResolvedPredictionResult:
        return ResolvedPredictionResult(
            prediction_id=prediction.prediction_id,
            fixture_id=prediction.fixture_id,
            status=status,
            resolved_at=resolved_at,
            home_score=match.home_score if match is not None else None,
            away_score=match.away_score if match is not None else None,
            settlement_rule_version=rule_version,
            reason_codes=reason_codes,
        )
