from app.presentation import InlineActionMetadata

from .callbacks import CallbackCodec
from .models import InteractionAction


class InteractionButtonFactory:
    def __init__(self, callback_codec: CallbackCodec) -> None:
        self._callback_codec = callback_codec

    def why_this_pick(self, assessment_id: str) -> InlineActionMetadata:
        return self._button(
            "Why this pick?",
            InteractionAction.WHY_THIS_PICK,
            assessment_id,
        )

    def view_statistics(self, assessment_id: str) -> InlineActionMetadata:
        return self._button(
            "View statistics",
            InteractionAction.VIEW_STATISTICS,
            assessment_id,
        )

    def view_bankroll(self, assessment_id: str) -> InlineActionMetadata:
        return self._button(
            "View bankroll",
            InteractionAction.VIEW_BANKROLL,
            assessment_id,
        )

    def all(self, assessment_id: str) -> tuple[InlineActionMetadata, ...]:
        return (
            self.why_this_pick(assessment_id),
            self.view_statistics(assessment_id),
            self.view_bankroll(assessment_id),
        )

    def _button(
        self,
        label: str,
        action: InteractionAction,
        assessment_id: str,
    ) -> InlineActionMetadata:
        return InlineActionMetadata(
            label=label,
            callback_data=self._callback_codec.encode(action, assessment_id),
        )
