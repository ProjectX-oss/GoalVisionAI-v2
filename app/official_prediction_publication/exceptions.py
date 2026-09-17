class OfficialPredictionPublicationError(RuntimeError):
    pass


class OfficialPredictionPublicationValidationError(
    OfficialPredictionPublicationError,
    ValueError,
):
    pass


class ConfirmedTelegramDeliveryError(OfficialPredictionPublicationError):
    """Telegram confirms that no message was delivered."""


class PredictionPublicationPersistenceError(OfficialPredictionPublicationError):
    pass
