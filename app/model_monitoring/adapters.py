from datetime import datetime
from decimal import Decimal

from app.backtesting import HistoricalEvaluationRecord
from app.quality_gate_shadow import ShadowEvaluationRecord, ShadowEvaluationStage
from app.results import (
    PublishedPredictionReference,
    ResolvedPredictionResult,
    ResolutionStatus,
)

from .models import MonitoringObservation


SHADOW_STAGE_PRIORITY = (
    ShadowEvaluationStage.FINAL_PRE_KICKOFF,
    ShadowEvaluationStage.PRE_PUBLICATION,
    ShadowEvaluationStage.INITIAL_CANDIDATE,
)
SOURCE_PRIORITY = {
    "OFFICIAL": 0,
    "SHADOW": 1,
    "BACKTEST": 2,
}


class OfficialMonitoringAdapter:
    @staticmethod
    def convert(
        prediction: PublishedPredictionReference,
        settlement: ResolvedPredictionResult,
        *,
        competition: str,
        model_version: str,
        raw_probability: Decimal,
        profit_loss_units: Decimal,
        calibrated_probability: Decimal | None = None,
        calibration_artifact_id: str | None = None,
        closing_odds: Decimal | None = None,
    ) -> MonitoringObservation:
        if prediction.prediction_id != settlement.prediction_id:
            raise ValueError("Official prediction and settlement identities differ.")
        if not settlement.is_terminal or settlement.resolved_at is None:
            raise ValueError("Official monitoring requires authoritative settlement.")
        if prediction.odds is None:
            raise ValueError("Official monitoring requires recorded offered odds.")
        return MonitoringObservation(
            prediction_id=prediction.prediction_id,
            fixture_id=prediction.fixture_id,
            competition=competition,
            market=prediction.market,
            model_version=model_version,
            calibration_artifact_id=calibration_artifact_id,
            prediction_timestamp=prediction.published_at,
            raw_probability=raw_probability,
            calibrated_probability=calibrated_probability,
            offered_odds=Decimal(str(prediction.odds)),
            closing_odds=closing_odds,
            authoritative_outcome=settlement.status,
            profit_loss_units=profit_loss_units,
            settlement_timestamp=settlement.resolved_at,
            source="OFFICIAL",
            actually_published=True,
        )


class ShadowMonitoringAdapter:
    def convert(
        self,
        records: tuple[ShadowEvaluationRecord, ...],
        *,
        closing_odds_by_prediction: dict[str, Decimal] | None = None,
        calibration_artifact_by_prediction: dict[str, str] | None = None,
    ) -> tuple[MonitoringObservation, ...]:
        selected: dict[str, ShadowEvaluationRecord] = {}
        for record in sorted(
            records,
            key=lambda item: (
                item.prediction_id,
                SHADOW_STAGE_PRIORITY.index(item.stage),
                item.evaluation_timestamp,
                item.shadow_evaluation_id,
            ),
        ):
            selected.setdefault(record.prediction_id, record)
        closing = closing_odds_by_prediction or {}
        artifacts = calibration_artifact_by_prediction or {}
        return tuple(
            self._convert(item, closing.get(item.prediction_id), artifacts.get(item.prediction_id))
            for item in sorted(
                selected.values(),
                key=lambda value: (
                    value.evaluation_timestamp,
                    value.prediction_id,
                ),
            )
        )

    @staticmethod
    def _convert(
        record: ShadowEvaluationRecord,
        closing_odds: Decimal | None,
        artifact_id: str | None,
    ) -> MonitoringObservation:
        candidate = record.candidate_snapshot
        if record.settled_at is not None and record.settled_at < record.evaluation_timestamp:
            raise ValueError("Shadow settlement cannot predate its original evaluation.")
        return MonitoringObservation(
            prediction_id=record.prediction_id,
            fixture_id=record.fixture_id,
            competition=candidate.competition,
            market=candidate.market,
            model_version=candidate.model_version or "UNKNOWN",
            calibration_artifact_id=artifact_id,
            prediction_timestamp=candidate.prediction_timestamp,
            raw_probability=candidate.raw_probability,
            calibrated_probability=candidate.calibrated_probability,
            offered_odds=record.actual_offered_odds or candidate.offered_odds,
            closing_odds=closing_odds,
            authoritative_outcome=record.settlement_outcome,
            profit_loss_units=record.eventual_profit_loss_units,
            settlement_timestamp=record.settled_at,
            source="SHADOW",
            source_stage=record.stage.value,
            actually_published=record.actually_published,
            gate_status=record.gate_status.value,
        )


class BacktestingMonitoringAdapter:
    @staticmethod
    def convert(
        records: tuple[HistoricalEvaluationRecord, ...],
        *,
        model_version: str,
        settlement_timestamp_by_fixture: dict[int, datetime],
        prediction_id_by_fixture: dict[int, str] | None = None,
    ) -> tuple[MonitoringObservation, ...]:
        identities = prediction_id_by_fixture or {}
        converted = []
        for item in records:
            settlement = settlement_timestamp_by_fixture[item.fixture_id]
            converted.append(
                MonitoringObservation(
                    prediction_id=identities.get(
                        item.fixture_id,
                        f"backtest:{item.fixture_id}:{item.market}:{item.selection}",
                    ),
                    fixture_id=item.fixture_id,
                    competition=item.competition,
                    market=item.market,
                    model_version=model_version,
                    calibration_artifact_id=None,
                    prediction_timestamp=item.prediction_timestamp,
                    raw_probability=item.model_probability,
                    calibrated_probability=None,
                    offered_odds=item.offered_odds,
                    closing_odds=item.closing_odds,
                    authoritative_outcome=ResolutionStatus(item.outcome.value),
                    profit_loss_units=item.profit_loss,
                    settlement_timestamp=settlement,
                    source="BACKTEST",
                )
            )
        return tuple(
            sorted(
                converted,
                key=lambda item: (
                    item.prediction_timestamp,
                    item.prediction_id,
                    item.fixture_id,
                ),
            )
        )


def deduplicate_monitoring_sources(
    observations: tuple[MonitoringObservation, ...],
) -> tuple[MonitoringObservation, ...]:
    selected: dict[tuple[str, int, str], MonitoringObservation] = {}
    for item in sorted(
        observations,
        key=lambda value: (
            value.deduplication_identity,
            SOURCE_PRIORITY.get(value.source, 99),
            value.prediction_timestamp,
        ),
    ):
        selected.setdefault(item.deduplication_identity, item)
    return tuple(
        sorted(
            selected.values(),
            key=lambda item: (
                item.prediction_timestamp,
                item.prediction_id,
                item.fixture_id,
                item.market,
            ),
        )
    )
