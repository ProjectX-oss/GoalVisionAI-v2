from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.official_prediction_orchestration import OfficialCandidateAssemblyRequest
from app.risk_management import RiskProductScope

from .exceptions import OfficialPredictionRunValidationError


class CandidateDiscoveryStatus(str, Enum):
    READY = "READY"
    ALREADY_PUBLISHED = "ALREADY_PUBLISHED"
    ACTIVE_DUPLICATE_CLAIM = "ACTIVE_DUPLICATE_CLAIM"
    RETRYABLE_CONFIRMED_FAILURE = "RETRYABLE_CONFIRMED_FAILURE"
    INDETERMINATE = "INDETERMINATE"
    REJECTED_IMMUTABLE = "REJECTED_IMMUTABLE"
    REVIEW_REQUIRED_IMMUTABLE = "REVIEW_REQUIRED_IMMUTABLE"
    EXPIRED = "EXPIRED"
    MALFORMED = "MALFORMED"
    NOT_YET_ELIGIBLE = "NOT_YET_ELIGIBLE"
    NON_OFFICIAL = "NON_OFFICIAL"


class OfficialPredictionRunStatus(str, Enum):
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_FAILURES = "COMPLETED_WITH_FAILURES"
    DRY_RUN_COMPLETED = "DRY_RUN_COMPLETED"
    NO_ELIGIBLE_CANDIDATES = "NO_ELIGIBLE_CANDIDATES"
    ABORTED = "ABORTED"
    FAILED_TO_START = "FAILED_TO_START"
    INDETERMINATE = "INDETERMINATE"


class OfficialPredictionRunItemStatus(str, Enum):
    PUBLISHED = "PUBLISHED"
    APPROVED_NOT_PUBLISHED = "APPROVED_NOT_PUBLISHED"
    REJECTED = "REJECTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DUPLICATE_BLOCKED = "DUPLICATE_BLOCKED"
    RETRYABLE_PUBLICATION_FAILURE = "RETRYABLE_PUBLICATION_FAILURE"
    INDETERMINATE_PUBLICATION_FAILURE = "INDETERMINATE_PUBLICATION_FAILURE"
    ASSEMBLY_FAILED = "ASSEMBLY_FAILED"
    SKIPPED_ALREADY_PUBLISHED = "SKIPPED_ALREADY_PUBLISHED"
    SKIPPED_ACTIVE_CLAIM = "SKIPPED_ACTIVE_CLAIM"
    SKIPPED_INDETERMINATE = "SKIPPED_INDETERMINATE"
    SKIPPED_EXPIRED = "SKIPPED_EXPIRED"
    SKIPPED_NOT_ELIGIBLE = "SKIPPED_NOT_ELIGIBLE"
    SKIPPED_RETRY_LIMIT = "SKIPPED_RETRY_LIMIT"
    SKIPPED_RETRY_COOLDOWN = "SKIPPED_RETRY_COOLDOWN"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


_SKIPPED_ITEM_STATUSES = frozenset({
    OfficialPredictionRunItemStatus.SKIPPED_ALREADY_PUBLISHED,
    OfficialPredictionRunItemStatus.SKIPPED_ACTIVE_CLAIM,
    OfficialPredictionRunItemStatus.SKIPPED_INDETERMINATE,
    OfficialPredictionRunItemStatus.SKIPPED_EXPIRED,
    OfficialPredictionRunItemStatus.SKIPPED_NOT_ELIGIBLE,
    OfficialPredictionRunItemStatus.SKIPPED_RETRY_LIMIT,
    OfficialPredictionRunItemStatus.SKIPPED_RETRY_COOLDOWN,
})


@dataclass(frozen=True, slots=True)
class OfficialPredictionCandidateReference:
    prediction_id: str
    match_id: str
    immutable_fingerprint: str
    kickoff_timestamp: datetime
    prediction_created_timestamp: datetime
    bankroll_scope: RiskProductScope
    destination_scope: RiskProductScope
    request: OfficialCandidateAssemblyRequest


@dataclass(frozen=True, slots=True)
class CandidateHistoricalState:
    status: CandidateDiscoveryStatus
    attempt_count: int = 0
    last_attempt_timestamp: datetime | None = None
    unchanged_candidate_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if self.attempt_count < 0:
            raise OfficialPredictionRunValidationError(
                "Historical attempt count must not be negative."
            )
        if self.last_attempt_timestamp is not None:
            _aware(self.last_attempt_timestamp, "Last attempt timestamp")


@dataclass(frozen=True, slots=True)
class DiscoveredOfficialPredictionCandidate:
    reference: OfficialPredictionCandidateReference
    status: CandidateDiscoveryStatus
    attempt_count: int = 0
    last_attempt_timestamp: datetime | None = None
    ordered_reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.attempt_count < 0:
            raise OfficialPredictionRunValidationError(
                "Discovered attempt count must not be negative."
            )
        if self.last_attempt_timestamp is not None:
            _aware(self.last_attempt_timestamp, "Discovered attempt timestamp")


@dataclass(frozen=True, slots=True)
class OfficialPredictionDiscoveryResult:
    evaluated_at: datetime
    normalized_filters: tuple[tuple[str, str], ...]
    ordered_candidates: tuple[DiscoveredOfficialPredictionCandidate, ...]


@dataclass(frozen=True, slots=True)
class OfficialPredictionRunRequest:
    evaluation_timestamp: datetime
    idempotency_key: str
    dry_run: bool
    force_review: bool
    normalized_discovery_filters: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _aware(self.evaluation_timestamp, "Run evaluation timestamp")
        if not self.idempotency_key.strip() or len(self.idempotency_key) > 128:
            raise OfficialPredictionRunValidationError(
                "A bounded non-empty manual idempotency key is required."
            )
        if self.force_review and not self.dry_run:
            raise OfficialPredictionRunValidationError(
                "Force review is allowed only for manual dry-run execution."
            )
        if self.normalized_discovery_filters != tuple(
            sorted(self.normalized_discovery_filters)
        ):
            raise OfficialPredictionRunValidationError(
                "Discovery filters must use canonical sorted ordering."
            )
        keys = tuple(item[0] for item in self.normalized_discovery_filters)
        if any(not key.strip() for key in keys) or len(keys) != len(set(keys)):
            raise OfficialPredictionRunValidationError(
                "Discovery filter keys must be unique and non-empty."
            )


@dataclass(frozen=True, slots=True)
class OfficialPredictionRunStart:
    run_id: str
    run_fingerprint: str
    request: OfficialPredictionRunRequest
    policy_version: str
    bankroll_scope: RiskProductScope
    destination_scope: RiskProductScope
    request_snapshot: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class OfficialPredictionRunItemResult:
    run_id: str
    item_index: int
    prediction_id: str
    match_id: str
    candidate_fingerprint: str
    kickoff_timestamp: datetime
    discovery_status: CandidateDiscoveryStatus
    status: OfficialPredictionRunItemStatus
    was_eligible: bool
    started_timestamp: datetime
    completed_timestamp: datetime
    orchestration_id: str | None = None
    publication_attempt_reference: str | None = None
    ordered_reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.item_index < 0:
            raise OfficialPredictionRunValidationError(
                "Run item index must not be negative."
            )
        if any(
            not value.strip()
            for value in (
                self.run_id,
                self.prediction_id,
                self.match_id,
                self.candidate_fingerprint,
            )
        ):
            raise OfficialPredictionRunValidationError(
                "Run item identifiers must not be empty."
            )
        for value, label in (
            (self.kickoff_timestamp, "Kickoff timestamp"),
            (self.started_timestamp, "Item start timestamp"),
            (self.completed_timestamp, "Item completion timestamp"),
        ):
            _aware(value, label)
        if self.completed_timestamp < self.started_timestamp:
            raise OfficialPredictionRunValidationError(
                "Run item completion cannot precede its start."
            )
        if self.was_eligible == (self.status in _SKIPPED_ITEM_STATUSES):
            raise OfficialPredictionRunValidationError(
                "Run item eligibility and terminal status are inconsistent."
            )


@dataclass(frozen=True, slots=True)
class OfficialPredictionRunResult:
    run_id: str
    run_fingerprint: str
    started_timestamp: datetime
    completed_timestamp: datetime
    run_status: OfficialPredictionRunStatus
    policy_version: str
    dry_run: bool
    discovered_count: int
    eligible_count: int
    processed_count: int
    published_count: int
    approved_not_published_count: int
    rejected_count: int
    review_required_count: int
    duplicate_blocked_count: int
    retryable_failure_count: int
    indeterminate_failure_count: int
    assembly_failure_count: int
    skipped_count: int
    internal_failure_count: int
    ordered_items: tuple[OfficialPredictionRunItemResult, ...]
    ordered_internal_reasons: tuple[str, ...] = ()
    stop_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.run_fingerprint.strip():
            raise OfficialPredictionRunValidationError(
                "Run identifiers must not be empty."
            )
        _aware(self.started_timestamp, "Run start timestamp")
        _aware(self.completed_timestamp, "Run completion timestamp")
        if self.completed_timestamp < self.started_timestamp:
            raise OfficialPredictionRunValidationError(
                "Run completion cannot precede its start."
            )
        if tuple(item.item_index for item in self.ordered_items) != tuple(
            range(len(self.ordered_items))
        ):
            raise OfficialPredictionRunValidationError(
                "Run item ordering must be contiguous and deterministic."
            )
        if any(item.run_id != self.run_id for item in self.ordered_items):
            raise OfficialPredictionRunValidationError(
                "Run items belong to a different run."
            )
        expected = _derived_counts(self.ordered_items)
        supplied = (
            self.discovered_count,
            self.eligible_count,
            self.processed_count,
            self.published_count,
            self.approved_not_published_count,
            self.rejected_count,
            self.review_required_count,
            self.duplicate_blocked_count,
            self.retryable_failure_count,
            self.indeterminate_failure_count,
            self.assembly_failure_count,
            self.skipped_count,
            self.internal_failure_count,
        )
        if supplied != expected:
            raise OfficialPredictionRunValidationError(
                "Run counters do not match immutable item outcomes."
            )
        if (
            self.run_status is OfficialPredictionRunStatus.DRY_RUN_COMPLETED
            and not self.dry_run
        ):
            raise OfficialPredictionRunValidationError(
                "Dry-run completion requires a dry-run request."
            )
        if (
            self.run_status is OfficialPredictionRunStatus.NO_ELIGIBLE_CANDIDATES
            and self.eligible_count != 0
        ):
            raise OfficialPredictionRunValidationError(
                "No-eligible status cannot contain processed candidates."
            )
        if (
            self.run_status is OfficialPredictionRunStatus.FAILED_TO_START
            and self.ordered_items
        ):
            raise OfficialPredictionRunValidationError(
                "A failed-to-start run cannot contain item results."
            )


@dataclass(frozen=True, slots=True)
class OfficialPredictionRunClaim:
    acquired: bool
    start: OfficialPredictionRunStart
    existing_result: OfficialPredictionRunResult | None = None
    incomplete: bool = False


def derived_counts(
    items: tuple[OfficialPredictionRunItemResult, ...],
) -> tuple[int, ...]:
    return _derived_counts(items)


def _derived_counts(
    items: tuple[OfficialPredictionRunItemResult, ...],
) -> tuple[int, ...]:
    statuses = tuple(item.status for item in items)
    skipped = sum(status in _SKIPPED_ITEM_STATUSES for status in statuses)
    internal = statuses.count(OfficialPredictionRunItemStatus.INTERNAL_FAILURE)
    eligible = sum(item.was_eligible for item in items)
    processed = len(items) - skipped
    return (
        len(items),
        eligible,
        processed,
        statuses.count(OfficialPredictionRunItemStatus.PUBLISHED),
        statuses.count(OfficialPredictionRunItemStatus.APPROVED_NOT_PUBLISHED),
        statuses.count(OfficialPredictionRunItemStatus.REJECTED),
        statuses.count(OfficialPredictionRunItemStatus.REVIEW_REQUIRED),
        statuses.count(OfficialPredictionRunItemStatus.DUPLICATE_BLOCKED),
        statuses.count(
            OfficialPredictionRunItemStatus.RETRYABLE_PUBLICATION_FAILURE
        ),
        statuses.count(
            OfficialPredictionRunItemStatus.INDETERMINATE_PUBLICATION_FAILURE
        ),
        statuses.count(OfficialPredictionRunItemStatus.ASSEMBLY_FAILED),
        skipped,
        internal,
    )


def _aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise OfficialPredictionRunValidationError(f"{label} must be timezone-aware.")
