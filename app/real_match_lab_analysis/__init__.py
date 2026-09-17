"""Controlled manual Real Match Analysis to GoalVision AI Lab."""

from .factory import build_real_match_lab_analysis_service
from .input import InputValidationError, load_input, parse_input
from .models import (
    INPUT_SCHEMA_VERSION,
    LAB_BOT_USERNAME,
    LAB_CHAT_ID,
    OUTPUT_SCHEMA_VERSION,
    SEND_CONFIRMATION,
    AnalysisRecord,
    AnalysisStatus,
    DeliveryRecord,
    DeliveryStatus,
    EngineEvidence,
    ManualOdds,
    MarketEvaluation,
    RealMatchLabInput,
)
from .policy import LabSelectionPolicy, SUPPORTED_MARKETS
from .repository import (
    AnalysisConflictError,
    DeliveryConflictError,
    SQLiteRealMatchLabRepository,
)
from .service import RealMatchLabAnalysisService

__all__ = [
    "AnalysisConflictError", "AnalysisRecord", "AnalysisStatus",
    "DeliveryConflictError", "DeliveryRecord", "DeliveryStatus",
    "EngineEvidence", "INPUT_SCHEMA_VERSION", "InputValidationError",
    "LAB_BOT_USERNAME", "LAB_CHAT_ID", "LabSelectionPolicy", "ManualOdds",
    "MarketEvaluation", "OUTPUT_SCHEMA_VERSION", "RealMatchLabAnalysisService",
    "RealMatchLabInput", "SEND_CONFIRMATION", "SUPPORTED_MARKETS",
    "SQLiteRealMatchLabRepository", "build_real_match_lab_analysis_service",
    "load_input", "parse_input",
]
