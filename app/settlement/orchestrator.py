from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

from app.bankroll import (
    BankrollProduct,
    BankrollRepository,
    OfficialResultBankrollSettlementService,
)
from app.results import (
    FinishedMatchResult,
    PredictionResultRepository,
    PredictionResultResolutionService,
    PublishedPredictionReference,
    ResolvedPredictionResult,
    ResolutionStatus,
)

from .models import (
    PredictionSettlementOutcome,
    SettlementBatchReport,
    SettlementBatchRequest,
    SettlementCandidate,
    SettlementFailureReasonCode,
    SettlementOutcomeState,
)
from .provider import FixtureResultProvider


class AutomaticPredictionSettlementOrchestrator:
    RULE_VERSION = "automatic-settlement-v1"

    def __init__(
        self,
        result_repository: PredictionResultRepository,
        result_resolution: PredictionResultResolutionService,
        bankroll_repository: BankrollRepository,
        bankroll_settlement: OfficialResultBankrollSettlementService,
        fixture_results: FixtureResultProvider,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._result_repository = result_repository
        self._result_resolution = result_resolution
        self._bankroll_repository = bankroll_repository
        self._bankroll_settlement = bankroll_settlement
        self._fixture_results = fixture_results
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def settle_pending(
        self,
        request: SettlementBatchRequest,
    ) -> SettlementBatchReport:
        outcomes: list[PredictionSettlementOutcome] = []
        candidates: list[SettlementCandidate] = []
        seen_predictions: set[str] = set()
        skipped_duplicates = 0

        for prediction in self._result_repository.load_pending():
            if prediction.prediction_id in seen_predictions:
                skipped_duplicates += 1
                outcomes.append(self._outcome(
                    prediction.prediction_id,
                    prediction.fixture_id,
                    SettlementOutcomeState.SKIPPED,
                    None,
                    (SettlementFailureReasonCode.DUPLICATE_PREDICTION,),
                    request.requested_at,
                ))
                continue
            seen_predictions.add(prediction.prediction_id)
            candidates.append(self._candidate(prediction, request, None))

        for result in self._result_repository.load_history():
            if self._bankroll_repository.has_settlement(
                BankrollProduct.OFFICIAL,
                result.prediction_id,
            ):
                continue
            if result.prediction_id in seen_predictions:
                skipped_duplicates += 1
                continue
            prediction = self._result_repository.get_published(result.prediction_id)
            if prediction is None:
                outcomes.append(self._outcome(
                    result.prediction_id,
                    result.fixture_id,
                    SettlementOutcomeState.FAILED,
                    result.status,
                    (SettlementFailureReasonCode.PUBLISHED_PREDICTION_MISSING,),
                    request.requested_at,
                    result.settlement_rule_version,
                ))
                continue
            seen_predictions.add(result.prediction_id)
            candidates.append(self._candidate(prediction, request, result))

        new_candidates = tuple(
            candidate for candidate in candidates if not candidate.is_recovery
        )
        fixture_results, fixture_failures, fixture_duplicates = (
            self._load_fixtures(new_candidates)
        )
        skipped_duplicates += fixture_duplicates

        for candidate in candidates:
            metadata_failure = self._metadata_failure(candidate)
            if metadata_failure is not None:
                outcomes.append(self._failure_outcome(
                    candidate,
                    metadata_failure,
                    request.requested_at,
                ))
                continue
            if candidate.persisted_result is not None:
                outcomes.append(self._settle_bankroll(
                    candidate,
                    candidate.persisted_result,
                    request.requested_at,
                ))
                continue

            fixture_failure = fixture_failures.get(candidate.prediction.fixture_id)
            if fixture_failure is not None:
                outcomes.append(self._failure_outcome(
                    candidate,
                    fixture_failure,
                    request.requested_at,
                ))
                continue
            fixture = fixture_results.get(candidate.prediction.fixture_id)
            if fixture is None:
                outcomes.append(self._outcome(
                    candidate.prediction.prediction_id,
                    candidate.prediction.fixture_id,
                    SettlementOutcomeState.UNRESOLVED,
                    ResolutionStatus.UNRESOLVED,
                    (SettlementFailureReasonCode.FIXTURE_RESULT_MISSING,),
                    request.requested_at,
                ))
                continue
            outcome = self._resolve_and_settle(
                candidate,
                fixture,
                request.requested_at,
            )
            if candidate.prediction.fixture_id in fixture_results.duplicates:
                outcome = self._with_reason(
                    outcome,
                    SettlementFailureReasonCode.DUPLICATE_FIXTURE_RESPONSE,
                )
            outcomes.append(outcome)

        return self._report(
            tuple(outcomes),
            skipped_duplicates,
            request.requested_at,
            self._now(),
        )

    def _candidate(
        self,
        prediction: PublishedPredictionReference,
        request: SettlementBatchRequest,
        result: ResolvedPredictionResult | None,
    ) -> SettlementCandidate:
        odds = (
            Decimal(str(prediction.odds))
            if prediction.odds is not None
            else None
        )
        return SettlementCandidate(
            prediction=prediction,
            stake_tier=request.tier_for(prediction.prediction_id),
            odds=odds,
            persisted_result=result,
        )

    def _load_fixtures(
        self,
        candidates: tuple[SettlementCandidate, ...],
    ) -> tuple[
        "_FixtureLookup",
        dict[int, SettlementFailureReasonCode],
        int,
    ]:
        results: dict[int, FinishedMatchResult] = {}
        failures: dict[int, SettlementFailureReasonCode] = {}
        duplicate_fixture_ids: set[int] = set()
        fixture_ids = tuple(dict.fromkeys(
            candidate.prediction.fixture_id for candidate in candidates
        ))
        for fixture_id in fixture_ids:
            try:
                responses = self._fixture_results.load_fixture(fixture_id)
            except Exception:
                failures[fixture_id] = (
                    SettlementFailureReasonCode.FIXTURE_PROVIDER_FAILED
                )
                continue
            if not responses:
                continue
            if any(response.fixture_id != fixture_id for response in responses):
                failures[fixture_id] = (
                    SettlementFailureReasonCode.FIXTURE_PROVIDER_FAILED
                )
                continue
            unique = tuple(dict.fromkeys(responses))
            if len(unique) > 1:
                failures[fixture_id] = (
                    SettlementFailureReasonCode.CONFLICTING_FIXTURE_RESPONSES
                )
                continue
            if len(responses) > 1:
                duplicate_fixture_ids.add(fixture_id)
            results[fixture_id] = unique[0]
        return _FixtureLookup(results, duplicate_fixture_ids), failures, sum(
            1 for fixture_id in duplicate_fixture_ids
        )

    def _resolve_and_settle(
        self,
        candidate: SettlementCandidate,
        fixture: FinishedMatchResult,
        processed_at: datetime,
    ) -> PredictionSettlementOutcome:
        try:
            result = self._result_resolution.resolve_one(
                candidate.prediction,
                fixture,
            )
        except Exception:
            return self._failure_outcome(
                candidate,
                SettlementFailureReasonCode.RESULT_PERSISTENCE_FAILED,
                processed_at,
            )
        if result.status is ResolutionStatus.PENDING:
            return self._outcome(
                result.prediction_id,
                result.fixture_id,
                SettlementOutcomeState.PENDING,
                result.status,
                (),
                processed_at,
                result.settlement_rule_version,
            )
        if result.status is ResolutionStatus.UNRESOLVED:
            return self._outcome(
                result.prediction_id,
                result.fixture_id,
                SettlementOutcomeState.UNRESOLVED,
                result.status,
                (),
                processed_at,
                result.settlement_rule_version,
            )
        persisted = self._result_repository.get_resolved(result.prediction_id)
        if persisted is None or persisted != result:
            return self._failure_outcome(
                candidate,
                SettlementFailureReasonCode.RESULT_PERSISTENCE_FAILED,
                processed_at,
                result.status,
                result.settlement_rule_version,
            )
        return self._settle_bankroll(candidate, persisted, processed_at)

    def _settle_bankroll(
        self,
        candidate: SettlementCandidate,
        result: ResolvedPredictionResult,
        processed_at: datetime,
    ) -> PredictionSettlementOutcome:
        try:
            bankroll_result = self._bankroll_settlement.settle_result(
                result,
                candidate.stake_tier,
                candidate.odds,
                processed_at,
            )
        except Exception:
            return self._failure_outcome(
                candidate,
                SettlementFailureReasonCode.BANKROLL_SETTLEMENT_FAILED,
                processed_at,
                result.status,
                result.settlement_rule_version,
            )
        reason_codes = (
            ()
            if bankroll_result.applied
            else (SettlementFailureReasonCode.BANKROLL_ALREADY_SETTLED,)
        )
        return self._outcome(
            result.prediction_id,
            result.fixture_id,
            SettlementOutcomeState.SETTLED,
            result.status,
            reason_codes,
            processed_at,
            result.settlement_rule_version,
            (
                bankroll_result.transaction.rule_version
                if bankroll_result.transaction is not None
                else None
            ),
        )

    @staticmethod
    def _metadata_failure(
        candidate: SettlementCandidate,
    ) -> SettlementFailureReasonCode | None:
        if candidate.stake_tier is None:
            return SettlementFailureReasonCode.MISSING_STAKE_TIER
        if candidate.odds is None:
            return SettlementFailureReasonCode.MISSING_ODDS
        if not candidate.odds.is_finite() or candidate.odds <= Decimal("1"):
            return SettlementFailureReasonCode.INVALID_ODDS
        return None

    @staticmethod
    def _failure_outcome(
        candidate: SettlementCandidate,
        reason: SettlementFailureReasonCode,
        processed_at: datetime,
        status: ResolutionStatus | None = None,
        result_rule_version: str | None = None,
    ) -> PredictionSettlementOutcome:
        return AutomaticPredictionSettlementOrchestrator._outcome(
            candidate.prediction.prediction_id,
            candidate.prediction.fixture_id,
            SettlementOutcomeState.FAILED,
            status,
            (reason,),
            processed_at,
            result_rule_version,
        )

    @staticmethod
    def _outcome(
        prediction_id: str,
        fixture_id: int,
        state: SettlementOutcomeState,
        status: ResolutionStatus | None,
        reasons: tuple[SettlementFailureReasonCode, ...],
        processed_at: datetime,
        result_rule_version: str | None = None,
        bankroll_rule_version: str | None = None,
    ) -> PredictionSettlementOutcome:
        return PredictionSettlementOutcome(
            prediction_id=prediction_id,
            fixture_id=fixture_id,
            state=state,
            resolution_status=status,
            reason_codes=reasons,
            processed_at=processed_at,
            result_rule_version=result_rule_version,
            bankroll_rule_version=bankroll_rule_version,
        )

    @staticmethod
    def _with_reason(
        outcome: PredictionSettlementOutcome,
        reason: SettlementFailureReasonCode,
    ) -> PredictionSettlementOutcome:
        return PredictionSettlementOutcome(
            prediction_id=outcome.prediction_id,
            fixture_id=outcome.fixture_id,
            state=outcome.state,
            resolution_status=outcome.resolution_status,
            reason_codes=outcome.reason_codes + (reason,),
            processed_at=outcome.processed_at,
            result_rule_version=outcome.result_rule_version,
            bankroll_rule_version=outcome.bankroll_rule_version,
        )

    def _report(
        self,
        outcomes: tuple[PredictionSettlementOutcome, ...],
        skipped_duplicates: int,
        started_at: datetime,
        completed_at: datetime,
    ) -> SettlementBatchReport:
        settled = tuple(
            outcome for outcome in outcomes
            if outcome.state is SettlementOutcomeState.SETTLED
        )
        return SettlementBatchReport(
            outcomes=outcomes,
            processed_count=len(outcomes),
            settled_count=len(settled),
            won_count=sum(
                outcome.resolution_status is ResolutionStatus.WON
                for outcome in settled
            ),
            lost_count=sum(
                outcome.resolution_status is ResolutionStatus.LOST
                for outcome in settled
            ),
            void_count=sum(
                outcome.resolution_status is ResolutionStatus.VOID
                for outcome in settled
            ),
            pending_count=sum(
                outcome.state is SettlementOutcomeState.PENDING
                for outcome in outcomes
            ),
            unresolved_count=sum(
                outcome.state is SettlementOutcomeState.UNRESOLVED
                for outcome in outcomes
            ),
            skipped_duplicates=skipped_duplicates,
            failed_count=sum(
                outcome.state is SettlementOutcomeState.FAILED
                for outcome in outcomes
            ),
            started_at=started_at,
            completed_at=completed_at,
            rule_version=self.RULE_VERSION,
        )

    def _now(self) -> datetime:
        timestamp = self._clock()
        if timestamp.tzinfo is None:
            raise ValueError("Orchestrator clock must be timezone-aware.")
        return timestamp


class _FixtureLookup(dict[int, FinishedMatchResult]):
    def __init__(
        self,
        values: dict[int, FinishedMatchResult],
        duplicates: set[int],
    ) -> None:
        super().__init__(values)
        self.duplicates = frozenset(duplicates)
