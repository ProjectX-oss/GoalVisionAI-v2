from dataclasses import replace
from datetime import datetime, timezone

from app.risk_management import RiskProductScope

from .models import (
    CandidateDiscoveryStatus,
    DiscoveredOfficialPredictionCandidate,
    OfficialPredictionCandidateReference,
    OfficialPredictionDiscoveryResult,
    OfficialPredictionRunRequest,
)
from .policy import OfficialPredictionRunPolicy
from .ports import (
    OfficialCandidateHistoricalStateReader,
    PersistedOfficialPredictionCandidateSource,
)


class DeterministicOfficialPredictionCandidateDiscovery:
    """Classifies and orders persisted Official candidate references."""

    def __init__(
        self,
        candidates: PersistedOfficialPredictionCandidateSource,
        states: OfficialCandidateHistoricalStateReader,
    ) -> None:
        self._candidates = candidates
        self._states = states

    def discover(
        self,
        request: OfficialPredictionRunRequest,
        policy: OfficialPredictionRunPolicy,
    ) -> OfficialPredictionDiscoveryResult:
        values = self._candidates.load_candidates(
            request.evaluation_timestamp,
            request.normalized_discovery_filters,
        )
        ordered = sorted(values, key=_order_key)
        discovered: list[DiscoveredOfficialPredictionCandidate] = []
        seen: set[str] = set()
        eligible_slots = 0
        for candidate in ordered:
            result = self._classify(candidate, request.evaluation_timestamp, policy)
            if candidate.prediction_id in seen:
                result = replace(
                    result,
                    status=CandidateDiscoveryStatus.MALFORMED,
                    ordered_reason_codes=("DUPLICATE_PREDICTION_REFERENCE",),
                )
            else:
                seen.add(candidate.prediction_id)
            if _potentially_eligible(result, request, policy):
                if eligible_slots >= policy.maximum_batch_size:
                    result = replace(
                        result,
                        status=CandidateDiscoveryStatus.NOT_YET_ELIGIBLE,
                        ordered_reason_codes=("BATCH_LIMIT_REACHED",),
                    )
                else:
                    eligible_slots += 1
            discovered.append(result)
        return OfficialPredictionDiscoveryResult(
            evaluated_at=request.evaluation_timestamp,
            normalized_filters=request.normalized_discovery_filters,
            ordered_candidates=tuple(discovered),
        )

    def _classify(
        self,
        candidate: OfficialPredictionCandidateReference,
        evaluated_at: datetime,
        policy: OfficialPredictionRunPolicy,
    ) -> DiscoveredOfficialPredictionCandidate:
        malformed = _malformed_reason(candidate)
        if malformed is not None:
            return _discovered(
                candidate,
                CandidateDiscoveryStatus.MALFORMED,
                malformed,
            )
        if (
            candidate.bankroll_scope is not RiskProductScope.OFFICIAL
            or candidate.destination_scope is not RiskProductScope.OFFICIAL
        ):
            return _discovered(
                candidate,
                CandidateDiscoveryStatus.NON_OFFICIAL,
                "NON_OFFICIAL_SCOPE",
            )
        remaining = candidate.kickoff_timestamp - evaluated_at
        if remaining < policy.minimum_time_remaining_before_kickoff:
            return _discovered(
                candidate,
                CandidateDiscoveryStatus.EXPIRED,
                "KICKOFF_TOO_CLOSE_OR_PASSED",
            )
        if remaining > policy.kickoff_lookahead_window:
            return _discovered(
                candidate,
                CandidateDiscoveryStatus.NOT_YET_ELIGIBLE,
                "OUTSIDE_KICKOFF_LOOKAHEAD",
            )
        state = self._states.get(candidate, evaluated_at)
        return DiscoveredOfficialPredictionCandidate(
            reference=candidate,
            status=state.status,
            attempt_count=state.attempt_count,
            last_attempt_timestamp=state.last_attempt_timestamp,
            ordered_reason_codes=(f"DISCOVERY_{state.status.value}",),
        )


def _malformed_reason(candidate: OfficialPredictionCandidateReference) -> str | None:
    prediction = candidate.request.prediction
    if any(
        not value.strip()
        for value in (
            candidate.prediction_id,
            candidate.match_id,
            candidate.immutable_fingerprint,
        )
    ):
        return "MISSING_CANDIDATE_IDENTITY"
    if (
        candidate.kickoff_timestamp.tzinfo is None
        or candidate.kickoff_timestamp.utcoffset() is None
        or candidate.prediction_created_timestamp.tzinfo is None
        or candidate.prediction_created_timestamp.utcoffset() is None
    ):
        return "NAIVE_CANDIDATE_TIMESTAMP"
    if (
        prediction.prediction_id != candidate.prediction_id
        or prediction.match_id != candidate.match_id
        or prediction.kickoff_timestamp != candidate.kickoff_timestamp
        or prediction.prediction_timestamp != candidate.prediction_created_timestamp
    ):
        return "CANDIDATE_REQUEST_IDENTITY_MISMATCH"
    bankroll = candidate.request.bankroll
    if bankroll is None or bankroll.product_scope is not candidate.bankroll_scope:
        return "CANDIDATE_BANKROLL_IDENTITY_MISMATCH"
    return None


def _potentially_eligible(
    candidate: DiscoveredOfficialPredictionCandidate,
    request: OfficialPredictionRunRequest,
    policy: OfficialPredictionRunPolicy,
) -> bool:
    status = candidate.status
    if status in policy.retryable_states:
        if candidate.attempt_count >= policy.maximum_retry_attempts_per_candidate:
            return False
        last = candidate.last_attempt_timestamp
        return not (
            last is not None
            and last + policy.retry_cooldown > request.evaluation_timestamp
        )
    if status in {
        CandidateDiscoveryStatus.READY,
    }:
        return True
    return bool(
        request.force_review
        and request.dry_run
        and status
        in {
            CandidateDiscoveryStatus.REJECTED_IMMUTABLE,
            CandidateDiscoveryStatus.REVIEW_REQUIRED_IMMUTABLE,
        }
    )


def _discovered(
    candidate: OfficialPredictionCandidateReference,
    status: CandidateDiscoveryStatus,
    reason: str,
) -> DiscoveredOfficialPredictionCandidate:
    return DiscoveredOfficialPredictionCandidate(
        reference=candidate,
        status=status,
        ordered_reason_codes=(reason,),
    )


def _order_key(
    candidate: OfficialPredictionCandidateReference,
) -> tuple[datetime, datetime, str, str, str]:
    return (
        _sortable_timestamp(candidate.kickoff_timestamp),
        _sortable_timestamp(candidate.prediction_created_timestamp),
        candidate.prediction_id,
        candidate.match_id,
        candidate.immutable_fingerprint,
    )


def _sortable_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return datetime.max.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
