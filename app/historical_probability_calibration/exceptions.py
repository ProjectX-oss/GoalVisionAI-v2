"""Typed failures for historical probability calibration fitting."""


class HistoricalCalibrationError(Exception): pass
class CalibrationRequestValidationError(HistoricalCalibrationError): pass
class SourceTrainingRunError(HistoricalCalibrationError): pass
class SourceArtifactError(HistoricalCalibrationError): pass
class SourceSplitError(HistoricalCalibrationError): pass
class PartitionSafetyError(HistoricalCalibrationError): pass
class SchemaCompatibilityError(HistoricalCalibrationError): pass
class InsufficientExamplesError(HistoricalCalibrationError): pass
class InsufficientClassSupportError(HistoricalCalibrationError): pass
class RawPredictionError(HistoricalCalibrationError): pass
class CalibrationFitError(HistoricalCalibrationError): pass
class CalibrationConvergenceError(HistoricalCalibrationError): pass
class InvalidCalibratedProbabilityError(HistoricalCalibrationError): pass
class CalibrationConflictError(HistoricalCalibrationError): pass
class CalibrationPersistenceError(HistoricalCalibrationError): pass
