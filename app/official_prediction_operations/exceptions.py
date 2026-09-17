"""Fail-closed errors raised by the manual Official operations boundary."""


class OfficialPredictionOperationsError(Exception):
    """Base class for expected operator-facing failures."""


class FixtureValidationError(OfficialPredictionOperationsError):
    """A fixture is not a valid ``goalvision_official_fixture_v1`` document."""


class DatabaseSafetyError(OfficialPredictionOperationsError):
    """A database path or requested database operation is unsafe."""


class ConfirmationError(OfficialPredictionOperationsError):
    """An exact, explicit operator confirmation is missing or mismatched."""


class DestinationVerificationError(OfficialPredictionOperationsError):
    """The configured publication destination could not be verified safely."""


class RecoveryError(OfficialPredictionOperationsError):
    """A requested recovery action is not demonstrably safe."""


class MaterializationError(OfficialPredictionOperationsError):
    """A deterministic fixture could not traverse an upstream domain boundary."""
