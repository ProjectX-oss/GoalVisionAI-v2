from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from app.presentation import TelegramPredictionPresenter

from .callbacks import CallbackCodec
from .models import InteractionAction, InteractionResponse, InteractionStatus
from .repository import AssessmentExplanationLookup


class TelegramPredictionInteractionHandler:
    """Resolves callbacks without sending messages or recalculating analysis."""

    def __init__(
        self,
        lookup: AssessmentExplanationLookup,
        presenter: TelegramPredictionPresenter,
        callback_codec: CallbackCodec,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._lookup = lookup
        self._presenter = presenter
        self._callback_codec = callback_codec
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._successful_responses: dict[
            str,
            tuple[InteractionResponse, datetime],
        ] = {}

    def handle(self, callback_data: str) -> InteractionResponse:
        now = self._now()
        cached = self._successful_responses.get(callback_data)
        if cached is not None:
            response, expires_at = cached
            if expires_at > now:
                return replace(response, duplicate=True)
            del self._successful_responses[callback_data]

        try:
            reference = self._callback_codec.decode(callback_data)
        except (TypeError, ValueError):
            return self._response(
                InteractionStatus.MALFORMED,
                "This action is invalid.",
            )

        if reference.action is not InteractionAction.WHY_THIS_PICK:
            return self._response(
                InteractionStatus.PLACEHOLDER,
                "This action is not available yet.",
            )

        stored = self._lookup.get(reference.assessment_id)
        if stored is None:
            return self._response(
                InteractionStatus.UNKNOWN,
                "This prediction analysis could not be found.",
            )

        if stored.expires_at <= now:
            return self._response(
                InteractionStatus.EXPIRED,
                "This prediction analysis has expired.",
            )
        if stored.explanation is None:
            return self._response(
                InteractionStatus.MISSING_EXPLANATION,
                "No explanation is available for this prediction.",
            )

        message = self._presenter.detailed_explanation(stored.explanation)
        response = InteractionResponse(
            status=InteractionStatus.OK,
            text=message.text,
            parse_mode=message.parse_mode,
        )
        self._successful_responses[callback_data] = (
            response,
            stored.expires_at,
        )
        return response

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("Interaction clock must return a timezone-aware time.")
        return now

    @staticmethod
    def _response(
        status: InteractionStatus,
        text: str,
    ) -> InteractionResponse:
        return InteractionResponse(status=status, text=text)
