from collections.abc import Callable
from datetime import datetime, timezone

from app.bankroll import (
    BankrollConfig,
    BankrollProduct,
    BankrollRepository,
)
from app.presentation import (
    ResultPresentationData,
    ResultStatus,
    TelegramPredictionPresenter,
)
from app.results import (
    PredictionResultRepository,
    ResolvedPredictionResult,
    ResolutionStatus,
)

from .models import (
    ResultPublicationBatchReport,
    ResultPublicationCandidate,
    ResultPublicationFailureReason,
    ResultPublicationMessage,
    ResultPublicationOutcome,
    ResultPublicationStatus,
)
from .ports import ResultPresentationMetadataProvider, TelegramResultPublisher
from .repository import ResultPublicationRepository


class OfficialResultPublicationService:
    """Publishes settled Official results through a durable delivery claim."""

    FORMAT_VERSION = "official-result-v1"

    def __init__(
        self,
        results: PredictionResultRepository,
        bankroll: BankrollRepository,
        publications: ResultPublicationRepository,
        metadata: ResultPresentationMetadataProvider,
        presenter: TelegramPredictionPresenter,
        telegram: TelegramResultPublisher,
        bankroll_config: BankrollConfig,
        destination: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not destination.strip():
            raise ValueError("Official Telegram destination must not be empty.")
        if bankroll_config.product_id is not BankrollProduct.OFFICIAL:
            raise ValueError("Only the Official bankroll may be published.")
        self._results = results
        self._bankroll = bankroll
        self._publications = publications
        self._metadata = metadata
        self._presenter = presenter
        self._telegram = telegram
        self._bankroll_config = bankroll_config
        self._destination = destination
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def publish_resolved(self) -> ResultPublicationBatchReport:
        started_at = self._now()
        outcomes: list[ResultPublicationOutcome] = []
        seen: set[str] = set()
        statuses: dict[str, ResolutionStatus] = {}

        try:
            results = self._results.load_history()
        except Exception:
            completed_at = self._now()
            return self._report(outcomes, statuses, started_at, completed_at)

        for result in results:
            if result.prediction_id in seen:
                outcomes.append(self._outcome(
                    result.prediction_id,
                    result.fixture_id,
                    ResultPublicationStatus.SKIPPED,
                    ResultPublicationFailureReason.DUPLICATE_CANDIDATE,
                ))
                continue
            seen.add(result.prediction_id)
            statuses[result.prediction_id] = result.status

            if not result.is_terminal:
                outcomes.append(self._outcome(
                    result.prediction_id,
                    result.fixture_id,
                    ResultPublicationStatus.SKIPPED,
                    ResultPublicationFailureReason.NON_TERMINAL_RESULT,
                ))
                continue

            try:
                outcome = await self._publish_one(result)
            except Exception:
                outcome = self._outcome(
                    result.prediction_id,
                    result.fixture_id,
                    ResultPublicationStatus.FAILED,
                    ResultPublicationFailureReason.DATABASE_FAILED,
                )
            outcomes.append(outcome)

        return self._report(outcomes, statuses, started_at, self._now())

    async def _publish_one(
        self,
        result: ResolvedPredictionResult,
    ) -> ResultPublicationOutcome:
        try:
            existing = self._publications.get(
                result.prediction_id,
                BankrollProduct.OFFICIAL,
                self._destination,
            )
        except Exception:
            return self._outcome(
                result.prediction_id,
                result.fixture_id,
                ResultPublicationStatus.FAILED,
                ResultPublicationFailureReason.DATABASE_FAILED,
            )
        if existing is not None:
            if existing.status is ResultPublicationStatus.PUBLISHED:
                return self._outcome(
                    result.prediction_id,
                    result.fixture_id,
                    ResultPublicationStatus.SKIPPED,
                    ResultPublicationFailureReason.ALREADY_PUBLISHED,
                    existing.telegram_message_id,
                )
            if existing.status is ResultPublicationStatus.ATTEMPTING:
                return self._outcome(
                    result.prediction_id,
                    result.fixture_id,
                    ResultPublicationStatus.SKIPPED,
                    ResultPublicationFailureReason.PUBLICATION_IN_PROGRESS,
                )

        try:
            prediction = self._results.get_published(result.prediction_id)
        except Exception:
            return self._outcome(
                result.prediction_id,
                result.fixture_id,
                ResultPublicationStatus.FAILED,
                ResultPublicationFailureReason.DATABASE_FAILED,
            )
        if prediction is None:
            return self._outcome(
                result.prediction_id,
                result.fixture_id,
                ResultPublicationStatus.FAILED,
                ResultPublicationFailureReason.PUBLISHED_PREDICTION_MISSING,
            )
        try:
            transaction = self._bankroll.get_transaction(
                BankrollProduct.OFFICIAL,
                result.prediction_id,
            )
        except Exception:
            return self._outcome(
                result.prediction_id,
                result.fixture_id,
                ResultPublicationStatus.FAILED,
                ResultPublicationFailureReason.DATABASE_FAILED,
            )
        if transaction is None:
            return self._outcome(
                result.prediction_id,
                result.fixture_id,
                ResultPublicationStatus.FAILED,
                ResultPublicationFailureReason.BANKROLL_TRANSACTION_MISSING,
            )
        if (
            transaction.fixture_id != result.fixture_id
            or transaction.settlement_status is not result.status
        ):
            return self._outcome(
                result.prediction_id,
                result.fixture_id,
                ResultPublicationStatus.FAILED,
                ResultPublicationFailureReason.BANKROLL_TRANSACTION_MISSING,
            )

        try:
            presentation_metadata = self._metadata.get(result.prediction_id)
        except Exception:
            return self._outcome(
                result.prediction_id,
                result.fixture_id,
                ResultPublicationStatus.FAILED,
                ResultPublicationFailureReason.PRESENTATION_FAILED,
            )
        candidate = ResultPublicationCandidate(
            result=result,
            prediction=prediction,
            transaction=transaction,
            destination=self._destination,
            metadata=presentation_metadata,
        )
        try:
            message = self._message(candidate)
        except Exception:
            return self._outcome(
                result.prediction_id,
                result.fixture_id,
                ResultPublicationStatus.FAILED,
                ResultPublicationFailureReason.PRESENTATION_FAILED,
            )

        attempted_at = self._now()
        try:
            claim = self._publications.begin_attempt(
                result.prediction_id,
                BankrollProduct.OFFICIAL,
                self._destination,
                attempted_at,
                self.FORMAT_VERSION,
            )
        except Exception:
            return self._outcome(
                result.prediction_id,
                result.fixture_id,
                ResultPublicationStatus.FAILED,
                ResultPublicationFailureReason.DATABASE_FAILED,
            )
        if not claim.acquired:
            record = claim.record
            reason = (
                ResultPublicationFailureReason.ALREADY_PUBLISHED
                if record.status is ResultPublicationStatus.PUBLISHED
                else ResultPublicationFailureReason.PUBLICATION_IN_PROGRESS
            )
            return self._outcome(
                result.prediction_id,
                result.fixture_id,
                ResultPublicationStatus.SKIPPED,
                reason,
                record.telegram_message_id,
            )

        try:
            message_id = await self._telegram.send_message(
                chat_id=self._destination,
                text=message.text,
                parse_mode=message.parse_mode,
            )
        except Exception:
            reasons = [ResultPublicationFailureReason.TELEGRAM_FAILED]
            try:
                self._publications.mark_failed(
                    result.prediction_id,
                    BankrollProduct.OFFICIAL,
                    self._destination,
                    ResultPublicationFailureReason.TELEGRAM_FAILED,
                )
            except Exception:
                reasons.append(ResultPublicationFailureReason.DATABASE_FAILED)
            return ResultPublicationOutcome(
                prediction_id=result.prediction_id,
                fixture_id=result.fixture_id,
                status=ResultPublicationStatus.FAILED,
                reasons=tuple(reasons),
            )

        try:
            published = self._publications.mark_published(
                result.prediction_id,
                BankrollProduct.OFFICIAL,
                self._destination,
                message_id,
                self._now(),
            )
        except Exception:
            return self._outcome(
                result.prediction_id,
                result.fixture_id,
                ResultPublicationStatus.FAILED,
                ResultPublicationFailureReason.DATABASE_FAILED,
                message_id,
            )

        reasons = (
            ()
            if presentation_metadata is not None
            else (ResultPublicationFailureReason.PRESENTATION_METADATA_MISSING,)
        )
        return ResultPublicationOutcome(
            prediction_id=result.prediction_id,
            fixture_id=result.fixture_id,
            status=ResultPublicationStatus.PUBLISHED,
            reasons=reasons,
            telegram_message_id=published.telegram_message_id,
        )

    def _message(
        self,
        candidate: ResultPublicationCandidate,
    ) -> ResultPublicationMessage:
        metadata = candidate.metadata
        transaction = candidate.transaction
        presentation = self._presenter.result(ResultPresentationData(
            league=metadata.league if metadata else None,
            home_team=metadata.home_team if metadata else None,
            away_team=metadata.away_team if metadata else None,
            market=candidate.prediction.market,
            pick=candidate.prediction.selection,
            status=ResultStatus(candidate.result.status.value),
            odds=candidate.prediction.odds,
            home_score=candidate.result.home_score,
            away_score=candidate.result.away_score,
            stake_stars=self._bankroll_config.stars_for(transaction.stake_tier),
            stake_amount=transaction.stake,
            profit_loss=transaction.profit_loss,
            bankroll_balance=transaction.closing_balance,
            currency=transaction.currency,
        ))
        return ResultPublicationMessage(
            text=presentation.text,
            parse_mode=presentation.parse_mode,
            format_version=self.FORMAT_VERSION,
        )

    @staticmethod
    def _outcome(
        prediction_id: str,
        fixture_id: int,
        status: ResultPublicationStatus,
        reason: ResultPublicationFailureReason,
        message_id: int | None = None,
    ) -> ResultPublicationOutcome:
        return ResultPublicationOutcome(
            prediction_id=prediction_id,
            fixture_id=fixture_id,
            status=status,
            reasons=(reason,),
            telegram_message_id=message_id,
        )

    def _report(
        self,
        outcomes: list[ResultPublicationOutcome],
        statuses: dict[str, ResolutionStatus],
        started_at: datetime,
        completed_at: datetime,
    ) -> ResultPublicationBatchReport:
        published = tuple(
            outcome
            for outcome in outcomes
            if outcome.status is ResultPublicationStatus.PUBLISHED
        )
        return ResultPublicationBatchReport(
            outcomes=tuple(outcomes),
            processed_count=len(outcomes),
            published_count=len(published),
            failed_count=sum(
                outcome.status is ResultPublicationStatus.FAILED
                for outcome in outcomes
            ),
            skipped_count=sum(
                outcome.status is ResultPublicationStatus.SKIPPED
                for outcome in outcomes
            ),
            won_count=sum(
                statuses[outcome.prediction_id] is ResolutionStatus.WON
                for outcome in published
            ),
            lost_count=sum(
                statuses[outcome.prediction_id] is ResolutionStatus.LOST
                for outcome in published
            ),
            void_count=sum(
                statuses[outcome.prediction_id] is ResolutionStatus.VOID
                for outcome in published
            ),
            started_at=started_at,
            completed_at=completed_at,
            format_version=self.FORMAT_VERSION,
        )

    def _now(self) -> datetime:
        timestamp = self._clock()
        if timestamp.tzinfo is None:
            raise ValueError("Publication clock must be timezone-aware.")
        return timestamp
