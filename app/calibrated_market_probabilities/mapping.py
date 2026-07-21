from .models import CalibratedMarketProbabilityAssembly, FutureMarketProbabilityInput


def to_future_market_probability_input(value: CalibratedMarketProbabilityAssembly) -> FutureMarketProbabilityInput:
    return FutureMarketProbabilityInput(
        value.calibrated_assembly_id, value.inference_id, value.match_id,
        value.source_model_artifact_id, value.source_model_version,
        value.calibration_set_id, value.raw_inference_fingerprint,
        value.calibrated_assembly_fingerprint, value.ordered_target_results,
    )
