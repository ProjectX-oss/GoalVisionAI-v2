"""Canonical SHA-256 identities for requests, evaluations, and decisions."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from app.match_data_snapshot import canonical_data
from app.market_value_assessment import MarketSelection, MarketType

from .models import (
    AssessmentEligibilityEvaluation,
    AssessmentEligibilityStatus,
    AssessmentFreshnessSummary,
    OfficialPredictionSelectionCommand,
    SelectionReason,
)
from .policy import (
    OfficialPredictionRankingPolicy,
    OfficialPredictionSelectionPolicy,
)


def digest(value: object) -> str:
    payload = json.dumps(
        canonical_data(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def policy_fingerprint(
    selection_policy: OfficialPredictionSelectionPolicy,
    ranking_policy: OfficialPredictionRankingPolicy,
) -> str:
    return digest(
        {
            "version": "official-selection-policy-fingerprint-v1",
            "selection_policy": selection_policy,
            "ranking_policy": ranking_policy,
        }
    )


def logical_market_identity(
    match_id: str,
    market_type: MarketType,
    selection: MarketSelection,
    market_line: Decimal | None,
) -> str:
    line = "-" if market_line is None else format(market_line.normalize(), "f")
    return "|".join(
        (match_id, market_type.value, selection.value, line)
    )


def logical_prediction_identity(logical_identity: str) -> str:
    return "official-logical-prediction-" + hashlib.sha256(
        f"official-logical-prediction-v1|{logical_identity}".encode("utf-8")
    ).hexdigest()


def request_fingerprint(
    command: OfficialPredictionSelectionCommand,
    ranking_policy_version: str,
) -> str:
    return digest(
        {
            "version": "official-selection-request-fingerprint-v1",
            "request_identity": command.selection_request_identity,
            "match_id": command.match_id,
            "kickoff": command.kickoff_timestamp,
            "selection_timestamp": command.selection_timestamp,
            "bankroll_scope": command.bankroll_scope.value,
            "destination_scope": command.destination_scope.value,
            "assessment_fingerprints": tuple(
                sorted(item.assessment_fingerprint for item in command.assessments)
            ),
            "selection_policy_version": command.selection_policy_version,
            "ranking_policy_version": ranking_policy_version,
            "metadata_version": command.metadata_version,
        }
    )


def evaluation_fingerprint(
    *,
    assessment_fingerprint: str,
    eligibility_status: AssessmentEligibilityStatus,
    ordered_rejection_reasons: tuple[SelectionReason, ...],
    logical_identity: str,
    verified_odds: Decimal,
    verified_fair_probability: Decimal,
    verified_expected_value: Decimal,
    freshness: AssessmentFreshnessSummary,
    policy_version: str,
) -> str:
    return digest(
        {
            "version": "official-selection-evaluation-fingerprint-v1",
            "assessment_fingerprint": assessment_fingerprint,
            "eligibility": eligibility_status.value,
            "reasons": tuple(item.value for item in ordered_rejection_reasons),
            "logical_market_identity": logical_identity,
            "odds": verified_odds,
            "fair_probability": verified_fair_probability,
            "expected_value": verified_expected_value,
            "freshness": freshness,
            "policy_version": policy_version,
        }
    )


def selected_fingerprint(
    *,
    request_identity_fingerprint: str,
    evaluation: AssessmentEligibilityEvaluation,
    ranking_values: tuple[object, ...],
    selected_rank: int,
    eligible_count: int,
    rejected_count: int,
    selection_policy_version: str,
    ranking_policy_version: str,
) -> str:
    return digest(
        {
            "version": "official-selected-decision-fingerprint-v1",
            "request_fingerprint": request_identity_fingerprint,
            "selected_assessment_fingerprint": evaluation.assessment_fingerprint,
            "logical_market_identity": evaluation.logical_market_identity,
            "ranking_values": ranking_values,
            "selected_rank": selected_rank,
            "eligible_count": eligible_count,
            "rejected_count": rejected_count,
            "selection_policy_version": selection_policy_version,
            "ranking_policy_version": ranking_policy_version,
        }
    )


def no_selection_fingerprint(
    *,
    request_identity_fingerprint: str,
    evaluations: tuple[AssessmentEligibilityEvaluation, ...],
    final_reason: SelectionReason,
    eligible_count: int,
    rejected_count: int,
    selection_policy_version: str,
    ranking_policy_version: str,
) -> str:
    return digest(
        {
            "version": "official-no-selection-decision-fingerprint-v1",
            "request_fingerprint": request_identity_fingerprint,
            "evaluation_fingerprints": tuple(
                item.evaluation_fingerprint for item in evaluations
            ),
            "final_reason": final_reason.value,
            "eligible_count": eligible_count,
            "rejected_count": rejected_count,
            "selection_policy_version": selection_policy_version,
            "ranking_policy_version": ranking_policy_version,
        }
    )


def selection_decision_id(decision_fingerprint: str) -> str:
    return "official-selection-decision-" + hashlib.sha256(
        f"official-selection-decision-id-v1|{decision_fingerprint}".encode(
            "utf-8"
        )
    ).hexdigest()


def selection_evaluation_id(
    request_identity_fingerprint: str,
    assessment_fingerprint: str,
) -> str:
    return "official-selection-evaluation-" + hashlib.sha256(
        "|".join(
            (
                "official-selection-evaluation-id-v1",
                request_identity_fingerprint,
                assessment_fingerprint,
            )
        ).encode("utf-8")
    ).hexdigest()
