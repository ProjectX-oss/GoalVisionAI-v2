import re

from .models import CallbackReference, InteractionAction


class CallbackCodec:
    """Encodes opaque assessment keys into Telegram-safe callback data."""

    MAX_CALLBACK_BYTES = 64
    MAX_ASSESSMENT_ID_LENGTH = 48
    _PATTERN = re.compile(r"^gv1:([wsb]):([A-Za-z0-9_-]{1,48})$")

    def encode(
        self,
        action: InteractionAction,
        assessment_id: str,
    ) -> str:
        self._validate_assessment_id(assessment_id)
        callback_data = f"gv1:{action.value}:{assessment_id}"
        if len(callback_data.encode("utf-8")) > self.MAX_CALLBACK_BYTES:
            raise ValueError("Callback data exceeds Telegram's 64-byte limit.")
        return callback_data

    def decode(self, callback_data: str) -> CallbackReference:
        if not isinstance(callback_data, str):
            raise ValueError("Callback data must be text.")
        if len(callback_data.encode("utf-8")) > self.MAX_CALLBACK_BYTES:
            raise ValueError("Callback data exceeds Telegram's 64-byte limit.")
        match = self._PATTERN.fullmatch(callback_data)
        if match is None:
            raise ValueError("Malformed interaction callback data.")
        return CallbackReference(
            action=InteractionAction(match.group(1)),
            assessment_id=match.group(2),
        )

    @classmethod
    def _validate_assessment_id(cls, assessment_id: str) -> None:
        if not re.fullmatch(
            rf"[A-Za-z0-9_-]{{1,{cls.MAX_ASSESSMENT_ID_LENGTH}}}",
            assessment_id,
        ):
            raise ValueError(
                "Assessment ID must contain only ASCII letters, digits, "
                "underscores, or hyphens."
            )
