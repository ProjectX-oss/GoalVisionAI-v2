"""Deterministic fixture builders for controlled local and integration runs.

Only the model adapter represents an external boundary. Every generated fixture
is fictional, fixed-time, non-production data and contains no transport config.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .serialization import sha256_fingerprint
from .validation import validate_official_fixture


VALID_PROBABILITIES = {
    "HOME_WIN": "0.600000", "DRAW": "0.200000", "AWAY_WIN": "0.200000",
    "OVER_1_5": "0.800000", "UNDER_1_5": "0.200000",
    "OVER_2_5": "0.550000", "UNDER_2_5": "0.450000",
    "OVER_3_5": "0.300000", "UNDER_3_5": "0.700000",
    "BTTS_YES": "0.580000", "BTTS_NO": "0.420000",
}

_EXPECTED_CANDIDATES = {
    "fictional-official-valid-v1": ("official-registry-candidate-c60edfb5fe7690b9-v000001-45841781e60e7d01", "45841781e60e7d013e772c413648f62220857d03dc71eec7afb076b8bf720592"),
    "fictional-official-quality-gate-rejected-v1": ("official-registry-candidate-0476641ec2e39573-v000001-87e9749552878110", "87e9749552878110da3cee616adbb5bc33554e64cac97795da8b093038cd2a9a"),
    "fictional-official-review-required-v1": ("official-registry-candidate-d8aa63cc59c29ee0-v000001-6fdc6339d15fa133", "6fdc6339d15fa1334f77c3eb8c30cf68a6f325ced9693662c9b3807b5148d09c"),
    "fictional-official-retryable-send-failure-v1": ("official-registry-candidate-9fcb37450ea6d768-v000001-e4a395bafa257ce7", "e4a395bafa257ce719699dd48e21bc7eed3716f2f5eacdc5120b7904908e8f34"),
    "fictional-official-active-claim-v1": ("official-registry-candidate-2bc5b53cab555756-v000001-2dbda9c45fb13cd2", "2dbda9c45fb13cd29a1b51a5b5037d9f35505d32018c9dc08e4e68dcd8ff0551"),
    "fictional-official-indeterminate-post-send-v1": ("official-registry-candidate-e94a4cfb4566b7ef-v000001-a0a5b68a880ac9db", "a0a5b68a880ac9db2812210e0bf1d7cfa8a1495ded1a2cf1990d7d721df152f0"),
}


def build_valid_official_fixture(*, fixture_id: str = "fictional-official-valid-v1") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "metadata": {
            "fixture_id": fixture_id,
            "schema_version": "goalvision_official_fixture_v1",
            "description": "Fictional deterministic Official single-bet fixture for controlled operations.",
            "expected_outcome": "APPROVED",
            "metadata_version": "v1",
            "non_production": True,
        },
        "match": {
            "match_id": "500100",
            "competition_id": "fictional-league-1",
            "competition_name": "Fictional Premier Division",
            "home_team_id": "fictional-home-1",
            "home_team_name": "Northbridge FC",
            "away_team_id": "fictional-away-1",
            "away_team_name": "Southport Athletic",
            "kickoff_utc": "2026-08-01T15:00:00Z",
            "snapshot_effective_time": "2026-08-01T12:00:00Z",
            "source_provider": "fictional-fixture-provider",
            "source_event_id": "fictional-event-500100",
            "source_snapshot_identity": "fictional-snapshot-500100-v1",
        },
        "model_input": {
            "model_input_id": "expected-derived-model-input",
            "feature_set_id": "expected-derived-feature-set",
            "snapshot_id": "expected-derived-snapshot",
            "completeness": "COMPLETE",
            "schema_version": "goalvision_model_input_v1",
            "provenance_reference": "fixture-controlled-source-v1",
        },
        "inference": {
            "inference_id": "expected-derived-inference",
            "model_artifact_id": "fixture-reference-artifact-v1",
            "model_name": "fixture-deterministic-reference-model",
            "model_version": "1.0.0",
            "raw_probabilities": dict(VALID_PROBABILITIES),
            "raw_probability_fingerprint": _fp("raw-probabilities-v1"),
        },
        "calibration": {
            "calibrated_assembly_id": "expected-derived-calibrated-assembly",
            "calibration_set_id": "fixture-official-identity-set-v1",
            "calibrated_probabilities": dict(VALID_PROBABILITIES),
            "calibrated_assembly_fingerprint": _fp("calibrated-assembly-v1"),
            "sample_size": 200,
            "brier_score": "0.15",
            "log_loss": "0.50",
            "expected_calibration_error": "0.03",
            "maximum_calibration_error": "0.08",
        },
        "odds": {
            "odds_snapshot_identity": "fictional-odds-500100-v1",
            "provider": "Fictional Odds Provider",
            "bookmaker": "Fictional Book A",
            "source_event_id": "fictional-event-500100",
            "market": "MATCH_WINNER",
            "selection": "HOME",
            "line": None,
            "decimal_odds": "1.80",
            "odds_effective_timestamp": "2026-08-01T12:05:00Z",
            "odds_fingerprint": _fp("odds-v1"),
            "available": True,
            "is_live": False,
        },
        "value_assessment": {
            "assessment_id": "expected-derived-assessment",
            "fair_probability": "0.600000",
            "fair_odds": "1.6666666667",
            "implied_probability": "0.5555555556",
            "expected_value": "0.080000",
            "absolute_probability_edge": "0.0444444444",
            "relative_probability_edge": "0.0800000000",
            "freshness": "FRESH",
            "actionability": "ACTIONABLE",
            "assessment_fingerprint": _fp("assessment-v1"),
        },
        "selection": {
            "selection_decision_id": "expected-derived-selection",
            "selection_fingerprint": _fp("selection-v1"),
            "selected_market": "MATCH_WINNER:HOME",
            "selected_assessment_identity": "expected-derived-assessment",
            "expected_rank": 1,
            "expected_eligible_count": 1,
        },
        "bankroll": {
            "snapshot_id": "fixture-bankroll-500100-v1",
            "scope": "OFFICIAL",
            "currency": "EUR",
            "current_bankroll": "10000.00",
            "available_bankroll": "10000.00",
            "effective_timestamp": "2026-08-01T12:05:00Z",
            "fingerprint": _fp("bankroll-v1"),
        },
        "exposure": {
            "snapshot_id": "fixture-exposure-500100-v1",
            "current_match_exposure": "0.00",
            "current_market_exposure": "0.00",
            "correlated_exposure_facts": [],
            "effective_timestamp": "2026-08-01T12:05:00Z",
            "fingerprint": _fp("exposure-v1"),
        },
        "risk": {
            "expected_risk_outcome": "ELIGIBLE",
            "expected_stake_percentage": "0.01",
            "expected_stake_amount": "100.00",
            "expected_risk_fingerprint": _fp("risk-v1"),
            "confidence_level": "HIGH",
            "lineup_status": "CONFIRMED",
            "injury_status": "AVAILABLE",
            "supporting_data_status": "AVAILABLE",
            "market_availability": "AVAILABLE",
            "model_health_status": "HEALTHY",
        },
        "candidate": {
            "expected_candidate_id": "expected-derived-candidate",
            "expected_version": 1,
            "expected_lifecycle": "READY",
            "expected_candidate_fingerprint": _fp("candidate-v1"),
        },
        "publication": {
            "expected_destination_identity": "fixture-official-channel",
            "destination_type": "TELEGRAM_CHANNEL",
            "expected_message_fingerprint": None,
            "expected_dry_run_outcome": "DRY_RUN_COMPLETED",
            "expected_publish_outcome": "PUBLISHED",
            "initial_state": "NOT_PUBLISHED",
        },
    }
    return _sign(payload)


def build_quality_gate_rejected_fixture(**changes: Any) -> dict[str, Any]:
    value = _variant("quality-gate-rejected", **changes)
    value["metadata"]["expected_outcome"] = "QUALITY_GATE_REJECTED"
    value["risk"]["confidence_level"] = "LOW"
    return _resign(value)


def build_review_required_fixture(**changes: Any) -> dict[str, Any]:
    value = _variant("review-required", **changes)
    value["metadata"]["expected_outcome"] = "REVIEW_REQUIRED"
    value["risk"]["lineup_status"] = "MISSING"
    return _resign(value)


def build_stale_odds_fixture(**changes: Any) -> dict[str, Any]:
    value = _variant("stale-odds", **changes)
    value["metadata"]["expected_outcome"] = "STALE_ODDS_REJECTED"
    value["match"]["snapshot_effective_time"] = "2026-08-01T11:00:00Z"
    value["odds"]["odds_effective_timestamp"] = "2026-08-01T11:30:00Z"
    return _resign(value)


def build_below_minimum_odds_fixture(**changes: Any) -> dict[str, Any]:
    value = _variant("below-minimum-odds", **changes)
    value["metadata"]["expected_outcome"] = "NO_SELECTION_BELOW_MINIMUM_ODDS"
    value["odds"]["decimal_odds"] = "1.59"
    value["value_assessment"]["implied_probability"] = "0.6289308176"
    value["value_assessment"]["expected_value"] = "-0.046000"
    value["value_assessment"]["absolute_probability_edge"] = "-0.0289308176"
    value["value_assessment"]["relative_probability_edge"] = "-0.0460000000"
    return _resign(value)


def build_below_minimum_ev_fixture(**changes: Any) -> dict[str, Any]:
    value = _variant("below-minimum-ev", **changes)
    value["metadata"]["expected_outcome"] = "NO_SELECTION_BELOW_MINIMUM_EV"
    value["odds"]["decimal_odds"] = "1.68"
    value["value_assessment"]["implied_probability"] = "0.5952380952"
    value["value_assessment"]["expected_value"] = "0.008000"
    value["value_assessment"]["absolute_probability_edge"] = "0.0047619048"
    value["value_assessment"]["relative_probability_edge"] = "0.0080000000"
    return _resign(value)


def build_superseded_candidate_fixture(**changes: Any) -> dict[str, Any]:
    value = _variant("superseded-candidate", **changes)
    value["metadata"]["expected_outcome"] = "SUPERSEDED_CANDIDATE_REJECTED"
    value["publication"]["initial_state"] = "SUPERSEDED_CANDIDATE"
    return _resign(value)


def build_retryable_publication_failure_fixture(**changes: Any) -> dict[str, Any]:
    value = _variant("retryable-send-failure", **changes)
    value["metadata"]["expected_outcome"] = "RETRYABLE_SEND_FAILURE"
    value["publication"]["initial_state"] = "RETRYABLE_SEND_FAILURE"
    value["publication"]["expected_publish_outcome"] = "RETRY_REQUIRED"
    return _resign(value)


def build_active_claim_fixture(**changes: Any) -> dict[str, Any]:
    value = _variant("active-claim", **changes)
    value["metadata"]["expected_outcome"] = "ACTIVE_CLAIM"
    value["publication"]["initial_state"] = "ACTIVE_CLAIM"
    value["publication"]["expected_publish_outcome"] = "PUBLICATION_IN_PROGRESS"
    return _resign(value)


def build_indeterminate_publication_fixture(**changes: Any) -> dict[str, Any]:
    value = _variant("indeterminate-post-send", **changes)
    value["metadata"]["expected_outcome"] = "INDETERMINATE_POST_SEND"
    value["publication"]["initial_state"] = "INDETERMINATE_POST_SEND"
    value["publication"]["expected_publish_outcome"] = "RETRY_REQUIRED"
    return _resign(value)


def _variant(label: str, **changes: Any) -> dict[str, Any]:
    value = deepcopy(build_valid_official_fixture(fixture_id=f"fictional-official-{label}-v1"))
    for section, section_changes in changes.items():
        if section not in value or not isinstance(section_changes, dict):
            raise ValueError(f"Fixture override must target a section mapping: {section}")
        value[section].update(section_changes)
    return value


def _fp(label: str) -> str:
    return sha256_fingerprint({"fixture_reference": label})


def _sign(payload: dict[str, Any]) -> dict[str, Any]:
    expected = _EXPECTED_CANDIDATES.get(str(payload["metadata"]["fixture_id"]))
    if expected is not None:
        payload["candidate"]["expected_candidate_id"] = expected[0]
        payload["candidate"]["expected_candidate_fingerprint"] = expected[1]
    if payload["metadata"]["fixture_id"] == "fictional-official-valid-v1":
        payload["publication"]["expected_message_fingerprint"] = "10f3967a2cefbd5729b306cb4152eca77a5b97aa1451fd9511b7c3245335b1d5"
    payload["metadata"]["fixture_fingerprint"] = sha256_fingerprint(payload)
    validate_official_fixture(payload)
    return payload


def _resign(payload: dict[str, Any]) -> dict[str, Any]:
    payload["metadata"].pop("fixture_fingerprint", None)
    return _sign(payload)
