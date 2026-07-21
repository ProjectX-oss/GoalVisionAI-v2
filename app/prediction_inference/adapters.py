from .models import PredictionInferenceResult, RawInferenceCalibrationInput, PredictionTarget


def to_calibration_input(
    result: PredictionInferenceResult,
    target: PredictionTarget,
) -> RawInferenceCalibrationInput:
    """Map one immutable raw target downstream without running calibration."""
    return RawInferenceCalibrationInput(
        inference_id=result.inference_id,
        target=target,
        raw_probability=result.raw_probabilities.probability_for(target),
        model_artifact_id=result.model_artifact_id,
        model_name=result.model_name,
        model_version=result.model_version,
        inference_timestamp=result.inference_timestamp,
        inference_fingerprint=result.inference_fingerprint,
    )
