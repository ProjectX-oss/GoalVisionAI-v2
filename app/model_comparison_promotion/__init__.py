"""Immutable model comparison and promotion-recommendation foundation."""

from .betting_comparison import compare_betting_metrics
from .calibration_comparison import compare_calibration_metrics
from .decision import rank_challengers, recommend_challenger
from .eligibility import evaluate_eligibility_gates
from .exceptions import *
from .factory import build_model_comparison_promotion_service
from .fingerprint import *
from .inspection import *
from .models import *
from .normalization import derive_comparison_scope, verify_scope_compatibility
from .policy import *
from .predictive_comparison import build_metric_evaluation, compare_predictive_metrics
from .repository import SQLiteModelComparisonRepository
from .risk_comparison import compare_risk_metrics
from .scoring import calculate_promotion_score
from .service import ModelComparisonPromotionService, compare_models_for_promotion
from .significance import calculate_statistical_evidence
from .source_verification import (
    verify_challenger_source_integrity,
    verify_champion_source_integrity,
    verify_source_bundle,
)
from .stability import calculate_stability, reproduce_stability, summarize_stability
from .validation import validate_comparison_command

__all__ = [name for name in globals() if not name.startswith("_")]
