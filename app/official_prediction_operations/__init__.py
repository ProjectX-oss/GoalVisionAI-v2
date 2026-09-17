"""Controlled manual Official prediction operations.

Importing this package performs no discovery, scheduling, database access,
Quality Gate execution, orchestration, publication claim, or Telegram send.
"""

from .commands import (
    PRODUCTION_TOKEN, PUBLISH_TOKEN, RETRY_TOKEN, execute_fixture,
    execute_fixture_sync, retry_persisted_execution,
    retry_persisted_execution_sync,
)
from .diagnostics import OfficialPipelineDiagnostics, run_official_pipeline_diagnostics
from .exceptions import (
    ConfirmationError, DatabaseSafetyError, DestinationVerificationError,
    FixtureValidationError, OfficialPredictionOperationsError,
)
from .factory import (
    DestinationVerification, DestinationVerificationPort,
    DestinationVerificationState, NoSendTelegramTransport,
    OperationsEnvironment, StaticDestinationVerifier,
)
from .fixture_models import FIXTURE_SCHEMA, OfficialPredictionFixture
from .fixtures import (
    build_active_claim_fixture, build_below_minimum_ev_fixture,
    build_below_minimum_odds_fixture, build_indeterminate_publication_fixture,
    build_quality_gate_rejected_fixture, build_retryable_publication_failure_fixture,
    build_review_required_fixture, build_stale_odds_fixture,
    build_superseded_candidate_fixture, build_valid_official_fixture,
)
from .recovery import RecoveryAnalysis, RecoveryClassification, analyze_execution_recovery
from .summaries import OperationsExitCode, OperationsResult, RESULT_SCHEMA
from .validation import load_official_fixture, validate_official_fixture

__all__ = (
    "ConfirmationError", "DatabaseSafetyError", "DestinationVerification",
    "DestinationVerificationError", "DestinationVerificationPort",
    "DestinationVerificationState", "FIXTURE_SCHEMA", "FixtureValidationError",
    "NoSendTelegramTransport", "OfficialPipelineDiagnostics",
    "OfficialPredictionFixture", "OfficialPredictionOperationsError",
    "OperationsEnvironment", "OperationsExitCode", "OperationsResult",
    "PRODUCTION_TOKEN", "PUBLISH_TOKEN", "RESULT_SCHEMA", "RETRY_TOKEN",
    "RecoveryAnalysis", "RecoveryClassification", "StaticDestinationVerifier",
    "analyze_execution_recovery", "build_active_claim_fixture",
    "build_below_minimum_ev_fixture", "build_below_minimum_odds_fixture",
    "build_indeterminate_publication_fixture", "build_quality_gate_rejected_fixture",
    "build_retryable_publication_failure_fixture", "build_review_required_fixture",
    "build_stale_odds_fixture", "build_superseded_candidate_fixture",
    "build_valid_official_fixture", "execute_fixture", "execute_fixture_sync",
    "retry_persisted_execution", "retry_persisted_execution_sync",
    "load_official_fixture", "run_official_pipeline_diagnostics",
    "validate_official_fixture",
)
