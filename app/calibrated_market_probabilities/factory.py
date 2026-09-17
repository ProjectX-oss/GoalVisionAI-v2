from app.probability_calibration import ProbabilityCalibrationConfig, ProbabilityCalibrationEngine

from .calibration_registry import CalibrationRegistry
from .policy import CalibratedMarketProbabilityPolicy
from .ports import (
    CalibratedAssemblyRepository,
    CalibrationSetRepository,
    ProbabilityCalibrationEngineFactory,
    RawInferenceReader,
)
from .service import CalibratedMarketProbabilityService


class ExistingProbabilityCalibrationEngineFactory:
    """Explicit construction adapter for the existing deterministic engine."""

    def build(self, config: ProbabilityCalibrationConfig) -> ProbabilityCalibrationEngine:
        return ProbabilityCalibrationEngine(config)


def build_calibrated_market_probability_service(
    inference_reader: RawInferenceReader,
    registry: CalibrationRegistry,
    calibration_set_repository: CalibrationSetRepository,
    assembly_repository: CalibratedAssemblyRepository,
    engine_factory: ProbabilityCalibrationEngineFactory,
    policy: CalibratedMarketProbabilityPolicy,
) -> CalibratedMarketProbabilityService:
    if registry.policy != policy:
        raise ValueError("Registry and service policies must match.")
    return CalibratedMarketProbabilityService(
        inference_reader, registry, calibration_set_repository,
        assembly_repository, engine_factory, policy,
    )
