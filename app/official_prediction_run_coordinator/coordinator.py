import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.logger import logger

from .models import (
    CandidateDiscoveryStatus,
    DiscoveredOfficialPredictionCandidate,
    OfficialPredictionRunItemResult,
    OfficialPredictionRunItemStatus,
    OfficialPredictionRunRequest,
    OfficialPredictionRunResult,
    OfficialPredictionRunStart,
    OfficialPredictionRunStatus,
    derived_counts,
)
from .policy import OfficialPredictionRunPolicy
from .ports import (
    OfficialPredictionCandidateDiscovery,
    OfficialPredictionRunRepository,
    OfficialSinglePredictionOrchestrator,
)


_FAILURE_ITEM_STATUSES = frozenset({
    OfficialPredictionRunItemStatus.RETRYABLE_PUBLICATION_FAILURE,
    OfficialPredictionRunItemStatus.INDETERMINATE_PUBLICATION_FAILURE,
    OfficialPredictionRunItemStatus.ASSEMBLY_FAILED,
    OfficialPredictionRunItemStatus.INTERNAL_FAILURE,
})


class OfficialPredictionRunFingerprint:
    VERSION = "official-prediction-run-fingerprint-v1"

    def generate(
        self,
        request: OfficialPredictionRunRequest,
        policy: OfficialPredictionRunPolicy,
    ) -> str:
        material = {
            "version": self.VERSION,
            "idempotency_key": request.idempotency_key,
            "run_timestamp": _utc(request.evaluation_timestamp),
            "policy_version": policy.version,
            "dry_run": request.dry_run,
            "force_review": request.force_review,
            "bankroll_scope": policy.allowed_bankroll_scope.value,
            "destination_scope": policy.allowed_destination_scope.value,
            "lookahead_microseconds": _microseconds(
                policy.kickoff_lookahead_window
            ),
            "minimum_time_remaining_microseconds": _microseconds(
                policy.minimum_time_remaining_before_kickoff
            ),
            "batch_limit": policy.maximum_batch_size,
            "maximum_retry_attempts": policy.maximum_retry_attempts_per_candidate,
            "retryable_states": tuple(
                item.value for item in policy.retryable_states
            ),
            "retry_cooldown_microseconds": _microseconds(policy.retry_cooldown),
            "stop_batch_after_failure": policy.stop_batch_after_failure,
            "discovery_filters": request.normalized_discovery_filters,
        }
        payload = json.dumps(material, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class OfficialPredictionRunCoordinator:
    """Sequential manual batch boundary over single-prediction orchestration."""

    def __init__(
        self,
        discovery: OfficialPredictionCandidateDiscovery,
        orchestration: OfficialSinglePredictionOrchestrator,
        runs: OfficialPredictionRunRepository,
        policy: OfficialPredictionRunPolicy,
        fingerprint: OfficialPredictionRunFingerprint | None = None,
    ) -> None:
        self._discovery = discovery
        self._orchestration = orchestration
        self._runs = runs
        self.policy = policy
        self._fingerprint = fingerprint or OfficialPredictionRunFingerprint()

    async def run_official_prediction_batch(
        self,
        request: OfficialPredictionRunRequest,
    ) -> OfficialPredictionRunResult:
        fingerprint = self._fingerprint.generate(request, self.policy)
        run_id = f"official-prediction-run-{fingerprint}"
        start = OfficialPredictionRunStart(
            run_id=run_id,
            run_fingerprint=fingerprint,
            request=request,
            policy_version=self.policy.version,
            bankroll_scope=self.policy.allowed_bankroll_scope,
            destination_scope=self.policy.allowed_destination_scope,
            request_snapshot=_request_snapshot(request, self.policy),
        )
        logger.info(
            "Official prediction run start run_id=%s dry_run=%s policy=%s",
            run_id,
            request.dry_run,
            self.policy.version,
        )
        try:
            claim = self._runs.begin_run(start)
        except Exception as exc:
            logger.warning(
                "Official prediction run failed to start run_id=%s error=%s",
                run_id,
                type(exc).__name__,
            )
            return _result(
                start,
                OfficialPredictionRunStatus.FAILED_TO_START,
                (),
                ("RUN_START_PERSISTENCE_FAILED",),
            )
        if not claim.acquired:
            if claim.existing_result is not None:
                return claim.existing_result
            return _result(
                claim.start,
                OfficialPredictionRunStatus.INDETERMINATE,
                (),
                ("INCOMPLETE_PRIOR_RUN_REPLAY_BLOCKED",),
                "INCOMPLETE_PRIOR_RUN",
            )
        try:
            discovery = self._discovery.discover(request, self.policy)
        except Exception as exc:
            logger.warning(
                "Official prediction discovery failed run_id=%s error=%s",
                run_id,
                type(exc).__name__,
            )
            aborted = _result(
                start,
                OfficialPredictionRunStatus.ABORTED,
                (),
                ("CANDIDATE_DISCOVERY_FAILED",),
                "DISCOVERY_FAILED",
            )
            return self._finalize_or_indeterminate(aborted)

        logger.info(
            "Official prediction discovery run_id=%s discovered=%d",
            run_id,
            len(discovery.ordered_candidates),
        )
        items: list[OfficialPredictionRunItemResult] = []
        stopped = False
        stop_reason: str | None = None
        for candidate in discovery.ordered_candidates:
            item_index = len(items)
            if stopped:
                item = _skipped_item(
                    start,
                    candidate,
                    item_index,
                    OfficialPredictionRunItemStatus.SKIPPED_NOT_ELIGIBLE,
                    "BATCH_STOPPED_AFTER_FAILURE",
                )
            else:
                eligible, skipped_status, reason = _eligibility(
                    candidate,
                    request,
                    self.policy,
                )
                if not eligible:
                    assert skipped_status is not None
                    item = _skipped_item(
                        start,
                        candidate,
                        item_index,
                        skipped_status,
                        reason,
                    )
                else:
                    item = await self._process_candidate(
                        start,
                        candidate,
                        item_index,
                    )
                    if (
                        self.policy.stop_batch_after_failure
                        and item.status in _FAILURE_ITEM_STATUSES
                    ):
                        stopped = True
                        stop_reason = f"STOPPED_AFTER_{item.status.value}"
            try:
                self._runs.append_item(item)
            except Exception as exc:
                logger.error(
                    "Official prediction run item persistence uncertain "
                    "run_id=%s prediction_id=%s error=%s",
                    run_id,
                    item.prediction_id,
                    type(exc).__name__,
                )
                items.append(item)
                return _result(
                    start,
                    OfficialPredictionRunStatus.INDETERMINATE,
                    tuple(items),
                    ("RUN_ITEM_PERSISTENCE_FAILED",),
                    "ITEM_PERSISTENCE_UNCERTAIN",
                )
            items.append(item)
            logger.info(
                "Official prediction run item terminal run_id=%s "
                "prediction_id=%s status=%s",
                run_id,
                item.prediction_id,
                item.status.value,
            )

        eligible_count = sum(item.was_eligible for item in items)
        logger.info(
            "Official prediction run eligibility run_id=%s eligible=%d",
            run_id,
            eligible_count,
        )
        terminal_status = _terminal_status(
            tuple(items),
            request.dry_run,
            stopped,
        )
        result = _result(
            start,
            terminal_status,
            tuple(items),
            (),
            stop_reason,
        )
        return self._finalize_or_indeterminate(result)

    async def _process_candidate(
        self,
        start: OfficialPredictionRunStart,
        candidate: DiscoveredOfficialPredictionCandidate,
        item_index: int,
    ) -> OfficialPredictionRunItemResult:
        reference = candidate.reference
        logger.info(
            "Official prediction run item start run_id=%s prediction_id=%s",
            start.run_id,
            reference.prediction_id,
        )
        try:
            outcome = await self._orchestration.prepare_and_publish_official_prediction(
                replace(
                    reference.request,
                    evaluation_timestamp=start.request.evaluation_timestamp,
                    dry_run=start.request.dry_run,
                )
            )
            if outcome.prediction_id != reference.prediction_id:
                raise ValueError("Orchestration returned another prediction identity.")
            status = OfficialPredictionRunItemStatus(outcome.final_status.value)
            return OfficialPredictionRunItemResult(
                run_id=start.run_id,
                item_index=item_index,
                prediction_id=reference.prediction_id,
                match_id=reference.match_id,
                candidate_fingerprint=reference.immutable_fingerprint,
                kickoff_timestamp=reference.kickoff_timestamp,
                discovery_status=candidate.status,
                status=status,
                was_eligible=True,
                started_timestamp=start.request.evaluation_timestamp,
                completed_timestamp=start.request.evaluation_timestamp,
                orchestration_id=outcome.orchestration_id,
                publication_attempt_reference=(
                    outcome.publication_attempt_reference
                ),
                ordered_reason_codes=outcome.ordered_reason_codes,
            )
        except Exception as exc:
            return OfficialPredictionRunItemResult(
                run_id=start.run_id,
                item_index=item_index,
                prediction_id=reference.prediction_id,
                match_id=reference.match_id,
                candidate_fingerprint=reference.immutable_fingerprint,
                kickoff_timestamp=reference.kickoff_timestamp,
                discovery_status=candidate.status,
                status=OfficialPredictionRunItemStatus.INTERNAL_FAILURE,
                was_eligible=True,
                started_timestamp=start.request.evaluation_timestamp,
                completed_timestamp=start.request.evaluation_timestamp,
                ordered_reason_codes=(
                    f"ORCHESTRATION_DEPENDENCY_{type(exc).__name__.upper()}",
                ),
            )

    def _finalize_or_indeterminate(
        self,
        result: OfficialPredictionRunResult,
    ) -> OfficialPredictionRunResult:
        try:
            stored = self._runs.finalize_run(result)
        except Exception as exc:
            logger.error(
                "Official prediction run finalization uncertain run_id=%s error=%s",
                result.run_id,
                type(exc).__name__,
            )
            return replace(
                result,
                run_status=OfficialPredictionRunStatus.INDETERMINATE,
                ordered_internal_reasons=("RUN_FINALIZATION_FAILED",),
                stop_reason="FINALIZATION_UNCERTAIN",
            )
        logger.info(
            "Official prediction run terminal run_id=%s status=%s "
            "processed=%d published=%d skipped=%d",
            stored.run_id,
            stored.run_status.value,
            stored.processed_count,
            stored.published_count,
            stored.skipped_count,
        )
        return stored


async def run_official_prediction_batch(
    coordinator: OfficialPredictionRunCoordinator,
    *,
    evaluation_timestamp: datetime,
    idempotency_key: str,
    dry_run: bool | None = None,
    force_review: bool = False,
    discovery_filters: Mapping[str, str] | Iterable[tuple[str, str]] = (),
) -> OfficialPredictionRunResult:
    """CLI-safe explicit manual entry point; defaults to policy dry-run."""
    filters = (
        discovery_filters.items()
        if isinstance(discovery_filters, Mapping)
        else discovery_filters
    )
    normalized = tuple(sorted((str(key), str(value)) for key, value in filters))
    request = OfficialPredictionRunRequest(
        evaluation_timestamp=evaluation_timestamp,
        idempotency_key=idempotency_key,
        dry_run=(coordinator.policy.default_dry_run if dry_run is None else dry_run),
        force_review=force_review,
        normalized_discovery_filters=normalized,
    )
    return await coordinator.run_official_prediction_batch(request)


def _eligibility(
    candidate: DiscoveredOfficialPredictionCandidate,
    request: OfficialPredictionRunRequest,
    policy: OfficialPredictionRunPolicy,
) -> tuple[bool, OfficialPredictionRunItemStatus | None, str]:
    status = candidate.status
    if status is CandidateDiscoveryStatus.READY:
        return True, None, "READY"
    if status in policy.retryable_states:
        if candidate.attempt_count >= policy.maximum_retry_attempts_per_candidate:
            return (
                False,
                OfficialPredictionRunItemStatus.SKIPPED_RETRY_LIMIT,
                "RETRY_LIMIT_REACHED",
            )
        last = candidate.last_attempt_timestamp
        if last is not None and last + policy.retry_cooldown > request.evaluation_timestamp:
            return (
                False,
                OfficialPredictionRunItemStatus.SKIPPED_RETRY_COOLDOWN,
                "RETRY_COOLDOWN_ACTIVE",
            )
        return True, None, "CONFIRMED_FAILURE_RETRY_ALLOWED"
    if (
        request.force_review
        and request.dry_run
        and status
        in {
            CandidateDiscoveryStatus.REJECTED_IMMUTABLE,
            CandidateDiscoveryStatus.REVIEW_REQUIRED_IMMUTABLE,
        }
    ):
        return True, None, "MANUAL_DRY_RUN_FORCE_REVIEW"
    mapping = {
        CandidateDiscoveryStatus.ALREADY_PUBLISHED: (
            OfficialPredictionRunItemStatus.SKIPPED_ALREADY_PUBLISHED,
            "ALREADY_PUBLISHED",
        ),
        CandidateDiscoveryStatus.ACTIVE_DUPLICATE_CLAIM: (
            OfficialPredictionRunItemStatus.SKIPPED_ACTIVE_CLAIM,
            "ACTIVE_PUBLICATION_CLAIM",
        ),
        CandidateDiscoveryStatus.INDETERMINATE: (
            OfficialPredictionRunItemStatus.SKIPPED_INDETERMINATE,
            "INDETERMINATE_DELIVERY_STATE",
        ),
        CandidateDiscoveryStatus.EXPIRED: (
            OfficialPredictionRunItemStatus.SKIPPED_EXPIRED,
            "KICKOFF_EXPIRED",
        ),
    }
    skipped, reason = mapping.get(
        status,
        (
            OfficialPredictionRunItemStatus.SKIPPED_NOT_ELIGIBLE,
            f"DISCOVERY_{status.value}",
        ),
    )
    return False, skipped, reason


def _skipped_item(
    start: OfficialPredictionRunStart,
    candidate: DiscoveredOfficialPredictionCandidate,
    item_index: int,
    status: OfficialPredictionRunItemStatus,
    reason: str,
) -> OfficialPredictionRunItemResult:
    reference = candidate.reference
    timestamp = start.request.evaluation_timestamp
    return OfficialPredictionRunItemResult(
        run_id=start.run_id,
        item_index=item_index,
        prediction_id=reference.prediction_id,
        match_id=reference.match_id,
        candidate_fingerprint=reference.immutable_fingerprint,
        kickoff_timestamp=reference.kickoff_timestamp,
        discovery_status=candidate.status,
        status=status,
        was_eligible=False,
        started_timestamp=timestamp,
        completed_timestamp=timestamp,
        ordered_reason_codes=(reason,),
    )


def _terminal_status(
    items: tuple[OfficialPredictionRunItemResult, ...],
    dry_run: bool,
    stopped: bool,
) -> OfficialPredictionRunStatus:
    if stopped:
        return OfficialPredictionRunStatus.ABORTED
    processed = tuple(item for item in items if item.was_eligible)
    if not processed:
        return OfficialPredictionRunStatus.NO_ELIGIBLE_CANDIDATES
    statuses = {item.status for item in processed}
    if OfficialPredictionRunItemStatus.INDETERMINATE_PUBLICATION_FAILURE in statuses:
        return OfficialPredictionRunStatus.INDETERMINATE
    if statuses & _FAILURE_ITEM_STATUSES:
        return OfficialPredictionRunStatus.COMPLETED_WITH_FAILURES
    if dry_run:
        return OfficialPredictionRunStatus.DRY_RUN_COMPLETED
    return OfficialPredictionRunStatus.COMPLETED


def _result(
    start: OfficialPredictionRunStart,
    status: OfficialPredictionRunStatus,
    items: tuple[OfficialPredictionRunItemResult, ...],
    reasons: tuple[str, ...],
    stop_reason: str | None = None,
) -> OfficialPredictionRunResult:
    counts = derived_counts(items)
    return OfficialPredictionRunResult(
        run_id=start.run_id,
        run_fingerprint=start.run_fingerprint,
        started_timestamp=start.request.evaluation_timestamp,
        completed_timestamp=start.request.evaluation_timestamp,
        run_status=status,
        policy_version=start.policy_version,
        dry_run=start.request.dry_run,
        discovered_count=counts[0],
        eligible_count=counts[1],
        processed_count=counts[2],
        published_count=counts[3],
        approved_not_published_count=counts[4],
        rejected_count=counts[5],
        review_required_count=counts[6],
        duplicate_blocked_count=counts[7],
        retryable_failure_count=counts[8],
        indeterminate_failure_count=counts[9],
        assembly_failure_count=counts[10],
        skipped_count=counts[11],
        internal_failure_count=counts[12],
        ordered_items=items,
        ordered_internal_reasons=reasons,
        stop_reason=stop_reason,
    )


def _request_snapshot(
    request: OfficialPredictionRunRequest,
    policy: OfficialPredictionRunPolicy,
) -> tuple[tuple[str, str], ...]:
    return tuple(sorted({
        "evaluation_timestamp": _utc(request.evaluation_timestamp),
        "dry_run": str(int(request.dry_run)),
        "force_review": str(int(request.force_review)),
        "policy_version": policy.version,
        "maximum_batch_size": str(policy.maximum_batch_size),
        "lookahead_microseconds": str(_microseconds(policy.kickoff_lookahead_window)),
        "minimum_time_remaining_microseconds": str(
            _microseconds(policy.minimum_time_remaining_before_kickoff)
        ),
        "maximum_retry_attempts": str(
            policy.maximum_retry_attempts_per_candidate
        ),
        "retry_cooldown_microseconds": str(_microseconds(policy.retry_cooldown)),
        "retryable_states": ",".join(
            item.value for item in policy.retryable_states
        ),
        "stop_batch_after_failure": str(int(policy.stop_batch_after_failure)),
    }.items()))


def _microseconds(value: timedelta) -> int:
    return (
        value.days * 86_400_000_000
        + value.seconds * 1_000_000
        + value.microseconds
    )


def _utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()
