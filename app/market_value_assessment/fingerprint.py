"""Canonical SHA-256 content identities."""

from __future__ import annotations

import hashlib
import json

from app.match_data_snapshot import canonical_data

from .models import MarketOddsSnapshot, MarketValueAssessment


def _digest(value: object) -> str:
    payload = json.dumps(
        canonical_data(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def odds_fingerprint(value: MarketOddsSnapshot) -> str:
    """Fingerprint material odds content, excluding registration execution time."""

    return _digest(
        {
            "version": "market-odds-fingerprint-v1",
            "snapshot_id": value.supplied_snapshot_id,
            "provider": value.source_provider,
            "bookmaker": value.bookmaker_id,
            "event": value.source_event_id,
            "match": value.match_id,
            "market": value.market_type.value,
            "selection": value.selection.value,
            "line": value.market_line,
            "odds": value.decimal_odds,
            "effective": value.odds_effective_timestamp,
            "updated": value.source_updated_timestamp,
            "kickoff": value.kickoff_timestamp,
            "status": value.market_status.value,
            "suspended": value.suspended,
            "available": value.available,
            "data_version": value.source_data_version,
            "metadata_version": value.metadata_version,
        }
    )


def assessment_fingerprint(value: MarketValueAssessment) -> str:
    return _digest(
        {
            "version": "market-value-assessment-fingerprint-v1",
            "assembly_id": value.calibrated_assembly_id,
            "assembly_fingerprint": value.calibrated_assembly_fingerprint,
            "model": (
                value.source_model_artifact_id,
                value.source_model_version,
            ),
            "calibration": (
                value.calibration_set_id,
                value.calibration_set_fingerprint,
            ),
            "odds_fingerprint": value.odds_fingerprint,
            "market": (
                value.market_type.value,
                value.selection.value,
                value.market_line,
            ),
            "targets": tuple(
                target.value for target in value.source_calibrated_targets
            ),
            "derivation": (
                value.probability_derivation_type.value,
                value.derivation_version,
            ),
            "fair_probability": value.fair_probability,
            "bookmaker_odds": value.bookmaker_decimal_odds,
            "implied_probability": value.implied_probability,
            "fair_odds": value.fair_decimal_odds,
            "edges": (
                value.absolute_probability_edge,
                value.relative_probability_edge,
            ),
            "ev": value.expected_value,
            "freshness": (
                value.odds_freshness.value,
                value.calibrated_freshness.value,
                value.overall_freshness.value,
            ),
            "actionability": value.actionability_status.value,
            "timestamp": value.assessment_timestamp,
            "policy": value.value_policy_version,
        }
    )
