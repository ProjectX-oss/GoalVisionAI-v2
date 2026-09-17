"""Domain-specific errors used at validation and persistence boundaries."""


class MarketValueAssessmentError(Exception):
    """Base error for the package."""


class InvalidCalibrationError(MarketValueAssessmentError, ValueError):
    """The calibrated input is incomplete, invalid, or unverifiable."""


class InvalidOddsError(MarketValueAssessmentError, ValueError):
    """The supplied odds command is structurally invalid."""


class IncompatibleMarketError(MarketValueAssessmentError, ValueError):
    """The normalized market has no v1 calibrated target mapping."""


class ProvenanceMismatchError(MarketValueAssessmentError, ValueError):
    """The odds and calibrated inputs do not describe the same event state."""


class MarketValueConflictError(MarketValueAssessmentError):
    """A supposedly identical immutable fingerprint has conflicting content."""


class MarketValuePersistenceError(MarketValueAssessmentError):
    """SQLite could not complete an assessment persistence operation."""


class NonActionableMappingError(MarketValueAssessmentError, ValueError):
    """A non-actionable assessment cannot cross the selection boundary."""
