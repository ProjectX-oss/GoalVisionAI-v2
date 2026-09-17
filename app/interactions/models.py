from dataclasses import dataclass
from enum import Enum


class InteractionAction(str, Enum):
    WHY_THIS_PICK = "w"
    VIEW_STATISTICS = "s"
    VIEW_BANKROLL = "b"


class InteractionStatus(str, Enum):
    OK = "ok"
    MALFORMED = "malformed"
    UNKNOWN = "unknown"
    EXPIRED = "expired"
    MISSING_EXPLANATION = "missing_explanation"
    PLACEHOLDER = "placeholder"


@dataclass(frozen=True, slots=True)
class CallbackReference:
    action: InteractionAction
    assessment_id: str


@dataclass(frozen=True, slots=True)
class InteractionResponse:
    status: InteractionStatus
    text: str
    parse_mode: str = "HTML"
    duplicate: bool = False
