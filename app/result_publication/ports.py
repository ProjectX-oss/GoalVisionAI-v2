from typing import Protocol

from .models import ResultPresentationMetadata


class TelegramResultPublisher(Protocol):
    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str | None = None,
    ) -> int | None:
        ...


class ResultPresentationMetadataProvider(Protocol):
    def get(self, prediction_id: str) -> ResultPresentationMetadata | None:
        ...


class InMemoryResultPresentationMetadataProvider:
    def __init__(
        self,
        values: dict[str, ResultPresentationMetadata] | None = None,
    ) -> None:
        self._values = dict(values or {})

    def get(self, prediction_id: str) -> ResultPresentationMetadata | None:
        return self._values.get(prediction_id)
