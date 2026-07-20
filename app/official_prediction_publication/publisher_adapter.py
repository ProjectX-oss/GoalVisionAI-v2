from collections.abc import Callable
from datetime import datetime

from app.official_prediction_orchestration import (
    ApprovedOfficialPredictionPublication,
    OfficialCandidateFingerprint,
    OfficialPredictionPublicationResult,
    PublicationDeliveryState,
    PublisherResultStatus,
)
from app.quality_gate import QualityGateStatus
from app.risk_management import RiskProductScope

from .exceptions import (
    ConfirmedTelegramDeliveryError,
    OfficialPredictionPublicationValidationError,
)
from .mapping import published_prediction_reference
from .message_builder import OfficialPredictionMessageBuilder
from .models import (
    OfficialPredictionDestination,
    OfficialPredictionMessageInput,
    PredictionPublicationEventStatus,
    PredictionPublicationFailureReason,
)
from .ports import (
    AtomicPredictionPublicationRepository,
    OfficialPredictionPublicFactsProvider,
    PublishedPredictionWriter,
    TelegramPredictionSender,
)


class OfficialPredictionPublisherAdapter:
    """Concrete claim/send/finalize adapter for approved Official predictions."""

    def __init__(
        self,
        messages: OfficialPredictionMessageBuilder,
        facts: OfficialPredictionPublicFactsProvider,
        publications: AtomicPredictionPublicationRepository,
        telegram: TelegramPredictionSender,
        published_predictions: PublishedPredictionWriter,
        destination: OfficialPredictionDestination,
        clock: Callable[[], datetime],
        *,
        enabled: bool = True,
    ) -> None:
        self._messages = messages
        self._facts = facts
        self._publications = publications
        self._telegram = telegram
        self._published_predictions = published_predictions
        self._destination = destination
        self._clock = clock
        self._enabled = enabled
        self._fingerprint = OfficialCandidateFingerprint()

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def publish(
        self,
        approved: ApprovedOfficialPredictionPublication,
    ) -> OfficialPredictionPublicationResult:
        if not self.enabled:
            return self._retryable(
                "PUBLISHER_DISABLED",
                "Official prediction publisher is disabled.",
            )
        try:
            self._validate_approval(approved)
            facts = self._facts.get(approved)
            if facts is None:
                raise OfficialPredictionPublicationValidationError(
                    "Approved public message facts are unavailable."
                )
            payload = self._messages.build(OfficialPredictionMessageInput(
                approved=approved,
                facts=facts,
                destination=self._destination,
            ))
        except (OfficialPredictionPublicationValidationError, ValueError, TypeError) as exc:
            return self._retryable(
                "PUBLICATION_VALIDATION_FAILED",
                f"Official publication validation failed: {type(exc).__name__}.",
            )

        try:
            attempted_at = self._now()
            claim = self._publications.begin_attempt(payload, attempted_at)
        except Exception as exc:
            return self._retryable(
                "PUBLICATION_CLAIM_FAILED",
                f"Publication claim failed before send: {type(exc).__name__}.",
            )
        if not claim.acquired:
            if claim.event.status is PredictionPublicationEventStatus.INDETERMINATE:
                return OfficialPredictionPublicationResult(
                    PublisherResultStatus.INDETERMINATE_FAILURE,
                    claim.event.attempt_reference,
                    ("INDETERMINATE_PUBLICATION_STATE",),
                    ("Existing delivery state is indeterminate; resend is blocked.",),
                )
            return OfficialPredictionPublicationResult(
                PublisherResultStatus.DUPLICATE_BLOCKED,
                claim.event.attempt_reference,
                ("ATOMIC_DUPLICATE_CLAIM",),
                ("An existing publication or active claim blocks duplicate send.",),
            )

        reference = claim.event.attempt_reference
        try:
            message_id = await self._telegram.send_message(
                chat_id=self._destination.channel_id,
                text=payload.rendered_text,
                parse_mode=payload.parse_mode,
            )
        except ConfirmedTelegramDeliveryError:
            try:
                self._publications.append_terminal(
                    reference,
                    PredictionPublicationEventStatus.FAILED,
                    self._now(),
                    failure_reason=(
                        PredictionPublicationFailureReason.TELEGRAM_CONFIRMED_FAILED
                    ),
                )
            except Exception:
                return self._indeterminate(reference, "FAILURE_AUDIT_PERSISTENCE_FAILED")
            return OfficialPredictionPublicationResult(
                PublisherResultStatus.RETRYABLE_FAILURE,
                reference,
                ("TELEGRAM_CONFIRMED_FAILED",),
                ("Telegram confirmed that the prediction message was not delivered.",),
            )
        except Exception:
            self._record_indeterminate(
                reference,
                PredictionPublicationFailureReason.TELEGRAM_DELIVERY_UNKNOWN,
            )
            return self._indeterminate(reference, "TELEGRAM_DELIVERY_UNKNOWN")

        if message_id is not None and (
            isinstance(message_id, bool)
            or not isinstance(message_id, int)
            or message_id <= 0
        ):
            self._record_indeterminate(
                reference,
                PredictionPublicationFailureReason.FINALIZATION_FAILED,
            )
            return self._indeterminate(reference, "INVALID_TELEGRAM_MESSAGE_ID")
        try:
            published_at = self._now()
        except Exception:
            self._record_indeterminate(
                reference,
                PredictionPublicationFailureReason.FINALIZATION_FAILED,
                message_id,
            )
            return self._indeterminate(reference, "PUBLICATION_CLOCK_FAILED")
        try:
            published = published_prediction_reference(
                payload,
                approved.assembly.gate_candidate.market,
                approved.assembly.gate_candidate.selection,
                published_at,
            )
            self._published_predictions.save_published(published)
        except Exception:
            self._record_indeterminate(
                reference,
                PredictionPublicationFailureReason.PUBLISHED_REFERENCE_FAILED,
                message_id,
            )
            return self._indeterminate(reference, "PUBLISHED_REFERENCE_FAILED")

        try:
            self._publications.append_terminal(
                reference,
                PredictionPublicationEventStatus.PUBLISHED,
                published_at,
                telegram_message_id=message_id,
            )
        except Exception:
            self._record_indeterminate(
                reference,
                PredictionPublicationFailureReason.FINALIZATION_FAILED,
                message_id,
            )
            return self._indeterminate(reference, "PUBLICATION_FINALIZATION_FAILED")
        return OfficialPredictionPublicationResult(
            PublisherResultStatus.PUBLISHED,
            reference,
        )

    def _validate_approval(
        self,
        approved: ApprovedOfficialPredictionPublication,
    ) -> None:
        assembly = approved.assembly
        candidate = assembly.gate_candidate
        gate = approved.quality_gate_evaluation
        if approved.dry_run:
            raise OfficialPredictionPublicationValidationError(
                "Dry-run approval cannot invoke the publisher adapter."
            )
        if (
            approved.approval_status is not QualityGateStatus.APPROVED
            or gate.final_decision is not QualityGateStatus.APPROVED
        ):
            raise OfficialPredictionPublicationValidationError(
                "Only persisted APPROVED Quality Gate evaluations may publish."
            )
        if (
            gate.prediction_id != assembly.prediction_id
            or candidate.prediction_id != assembly.prediction_id
            or gate.model_version != candidate.model_version
            or not gate.policy_version.strip()
        ):
            raise OfficialPredictionPublicationValidationError(
                "Approval identity, model, or policy facts are inconsistent."
            )
        if approved.candidate_fingerprint != self._fingerprint.generate(assembly):
            raise OfficialPredictionPublicationValidationError(
                "Candidate fingerprint does not match the approved assembly."
            )
        if not approved.orchestration_id.strip() or not gate.evaluation_id.strip():
            raise OfficialPredictionPublicationValidationError(
                "Approval audit identifiers are required."
            )
        if candidate.bankroll_scope is not RiskProductScope.OFFICIAL:
            raise OfficialPredictionPublicationValidationError(
                "Only the Official bankroll scope may publish."
            )
        if assembly.publication_state not in {
            PublicationDeliveryState.NEVER_ATTEMPTED,
            PublicationDeliveryState.CONFIRMED_FAILED_RETRYABLE,
        }:
            raise OfficialPredictionPublicationValidationError(
                "Duplicate-risk publication state cannot send."
            )
        try:
            if int(assembly.match_id) <= 0:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise OfficialPredictionPublicationValidationError(
                "Official match ID must be a positive integer."
            ) from exc

    def _record_indeterminate(
        self,
        reference: str,
        reason: PredictionPublicationFailureReason,
        message_id: int | None = None,
    ) -> None:
        try:
            self._publications.append_terminal(
                reference,
                PredictionPublicationEventStatus.INDETERMINATE,
                self._now(),
                telegram_message_id=message_id,
                failure_reason=reason,
            )
        except Exception:
            return None

    @staticmethod
    def _retryable(
        reason: str,
        explanation: str,
    ) -> OfficialPredictionPublicationResult:
        return OfficialPredictionPublicationResult(
            PublisherResultStatus.RETRYABLE_FAILURE,
            None,
            (reason,),
            (explanation,),
        )

    @staticmethod
    def _indeterminate(
        reference: str,
        reason: str,
    ) -> OfficialPredictionPublicationResult:
        return OfficialPredictionPublicationResult(
            PublisherResultStatus.INDETERMINATE_FAILURE,
            reference,
            (reason,),
            ("Delivery may have occurred; automatic resend is blocked.",),
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Official publication clock must be timezone-aware.")
        return value
