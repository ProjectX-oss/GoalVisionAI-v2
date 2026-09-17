from dataclasses import dataclass
from datetime import timedelta

from app.risk_management import RiskProductScope

from .models import CandidateDiscoveryStatus


@dataclass(frozen=True, slots=True)
class OfficialPredictionRunPolicy:
    """Central deterministic policy for one manual Official batch."""

    version: str = "official-prediction-run-policy-v1"
    maximum_batch_size: int = 25
    maximum_supported_batch_size: int = 100
    kickoff_lookahead_window: timedelta = timedelta(hours=24)
    minimum_time_remaining_before_kickoff: timedelta = timedelta(minutes=15)
    retryable_states: tuple[CandidateDiscoveryStatus, ...] = (
        CandidateDiscoveryStatus.RETRYABLE_CONFIRMED_FAILURE,
    )
    maximum_retry_attempts_per_candidate: int = 3
    retry_cooldown: timedelta = timedelta(minutes=5)
    stop_batch_after_failure: bool = False
    allow_second_attempt_within_run: bool = False
    default_dry_run: bool = True
    allowed_bankroll_scope: RiskProductScope = RiskProductScope.OFFICIAL
    allowed_destination_scope: RiskProductScope = RiskProductScope.OFFICIAL

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("Official run policy version is required.")
        if not 0 < self.maximum_batch_size <= self.maximum_supported_batch_size:
            raise ValueError("Official batch size is outside its bounded range.")
        if self.maximum_supported_batch_size <= 0:
            raise ValueError("Maximum supported batch size must be positive.")
        if self.kickoff_lookahead_window <= timedelta(0):
            raise ValueError("Kickoff lookahead must be positive.")
        if self.minimum_time_remaining_before_kickoff < timedelta(0):
            raise ValueError("Minimum pre-kickoff time must not be negative.")
        if (
            self.minimum_time_remaining_before_kickoff
            >= self.kickoff_lookahead_window
        ):
            raise ValueError("Minimum pre-kickoff time must be below lookahead.")
        if self.maximum_retry_attempts_per_candidate <= 0:
            raise ValueError("Retry attempts must be positively bounded.")
        if self.retry_cooldown < timedelta(0):
            raise ValueError("Retry cooldown must not be negative.")
        if self.retryable_states != (
            CandidateDiscoveryStatus.RETRYABLE_CONFIRMED_FAILURE,
        ):
            raise ValueError(
                "Only explicitly confirmed publication failures are retryable."
            )
        if self.allow_second_attempt_within_run:
            raise ValueError("Automatic second attempts within one run are unsupported.")
        if (
            self.allowed_bankroll_scope is not RiskProductScope.OFFICIAL
            or self.allowed_destination_scope is not RiskProductScope.OFFICIAL
        ):
            raise ValueError("The batch coordinator is restricted to Official scope.")


DEFAULT_OFFICIAL_PREDICTION_RUN_POLICY = OfficialPredictionRunPolicy()
