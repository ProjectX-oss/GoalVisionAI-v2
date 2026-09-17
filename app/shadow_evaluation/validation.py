"""Strict command, chronology, input, and odds validation."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal

from .exceptions import ShadowSourceError, ShadowValidationError
from .fingerprint import sha256_fingerprint

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")


def utc(value: datetime | str, name: str) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ShadowValidationError(f"{name} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise ShadowValidationError(f"{name} must be timezone-aware.")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_command(command, policy) -> None:
    for name, value in vars_from_slots(command):
        if name.endswith("_id") and value is not None and (not isinstance(value, str) or not _IDENTIFIER.fullmatch(value)):
            raise ShadowValidationError(f"{name} is invalid.")
    if command.champion_model_artifact_id == command.challenger_model_artifact_id:
        raise ShadowValidationError("Champion and challenger must be distinct model artifacts.")
    pinned = {
        "shadow_policy_version": policy.version,
        "probability_contract_version": policy.probability_contract_version,
        "market_value_policy_version": policy.market_value_policy_version,
        "selection_policy_version": policy.selection_policy_version,
        "comparison_policy_version": policy.comparison_policy_version,
        "settlement_policy_version": policy.settlement_policy_version,
        "metric_policy_version": policy.metric_policy_version,
        "odds_policy_version": policy.odds_policy_version,
    }
    for field, expected in pinned.items():
        if getattr(command, field) != expected:
            raise ShadowValidationError(f"{field} is unsupported.")
    kickoff = utc(command.kickoff_utc, "kickoff_utc")
    snapshot = utc(command.input_snapshot_timestamp_utc, "input_snapshot_timestamp_utc")
    evaluated = utc(command.evaluation_timestamp_utc, "evaluation_timestamp_utc")
    if not snapshot < kickoff or not evaluated < kickoff:
        raise ShadowValidationError("Input and evaluation timestamps must be strictly pre-kickoff.")


def validate_input(command, snapshot) -> None:
    expected = (
        snapshot.model_input_vector_id == command.model_input_vector_id
        and snapshot.model_input_fingerprint == command.model_input_fingerprint
        and snapshot.match_id == command.match_id
        and snapshot.competition == command.competition
        and utc(snapshot.kickoff_utc, "input kickoff") == utc(command.kickoff_utc, "command kickoff")
        and snapshot.feature_schema_version == command.feature_schema_version
        and snapshot.feature_schema_fingerprint == command.feature_schema_fingerprint
        and snapshot.feature_provenance_fingerprint == command.feature_provenance_fingerprint
    )
    if not expected:
        raise ShadowSourceError("Model-input identity or provenance differs from the command.")
    count = len(snapshot.ordered_feature_names)
    if count == 0 or len(snapshot.ordered_feature_values) != count or len(snapshot.missingness_mask) != count:
        raise ShadowSourceError("Model-input ordered vectors are incomplete.")
    if len(set(snapshot.ordered_feature_names)) != count:
        raise ShadowSourceError("Model-input feature names are not unique.")
    missing = tuple(name for name, masked in zip(snapshot.ordered_feature_names, snapshot.missingness_mask) if masked)
    if missing != snapshot.ordered_missing_features:
        raise ShadowSourceError("Model-input missingness evidence differs.")
    if not Decimal(0) <= snapshot.completeness_score <= Decimal(1):
        raise ShadowSourceError("Model-input completeness is outside [0,1].")
    if utc(snapshot.snapshot_timestamp_utc, "input snapshot") >= utc(snapshot.kickoff_utc, "input kickoff"):
        raise ShadowSourceError("Model input is not strictly pre-kickoff.")
    if any(utc(item, "source timestamp") >= utc(snapshot.kickoff_utc, "input kickoff") for item in snapshot.ordered_source_timestamps):
        raise ShadowSourceError("Feature provenance contains target-time or future evidence.")
    core = {
        "vector_id": snapshot.model_input_vector_id,
        "vector_fingerprint": snapshot.model_input_fingerprint,
        "match_id": snapshot.match_id,
        "feature_schema_version": snapshot.feature_schema_version,
        "feature_schema_fingerprint": snapshot.feature_schema_fingerprint,
        "feature_provenance_fingerprint": snapshot.feature_provenance_fingerprint,
        "ordered_feature_names": snapshot.ordered_feature_names,
        "ordered_feature_values": snapshot.ordered_feature_values,
        "missingness_mask": snapshot.missingness_mask,
        "ordered_missing_features": snapshot.ordered_missing_features,
        "completeness_score": snapshot.completeness_score,
    }
    if snapshot.input_snapshot_fingerprint != sha256_fingerprint(core):
        raise ShadowSourceError("Model-input snapshot fingerprint mismatch.")


def validate_odds(command, odds_set) -> None:
    if (odds_set.odds_snapshot_set_id, odds_set.odds_snapshot_set_fingerprint) != (
        command.odds_snapshot_set_id, command.odds_snapshot_set_fingerprint,
    ):
        raise ShadowSourceError("Odds snapshot-set identity differs.")
    supported = {
        "HOME_WIN", "DRAW", "AWAY_WIN", "OVER_1_5", "UNDER_1_5", "OVER_2_5",
        "UNDER_2_5", "OVER_3_5", "UNDER_3_5", "BTTS_YES", "BTTS_NO",
    }
    identities = set()
    for item in odds_set.snapshots:
        if item.match_id != command.match_id or item.market_identity not in supported:
            raise ShadowSourceError("Odds contain a different match or unsupported market.")
        if item.decimal_odds <= Decimal(1):
            raise ShadowSourceError("Decimal odds must be greater than 1.")
        if utc(item.snapshot_timestamp_utc, "odds timestamp") >= utc(item.kickoff_utc, "odds kickoff"):
            raise ShadowSourceError("Odds are not strictly pre-kickoff.")
        identity = (item.source_identity, item.source_record_identity, item.market_identity)
        if identity in identities:
            raise ShadowSourceError("Duplicate supplied odds identity.")
        identities.add(identity)
        expected = sha256_fingerprint({
            "source_identity": item.source_identity, "source_version": item.source_version,
            "source_record_identity": item.source_record_identity, "match_id": item.match_id,
            "market_identity": item.market_identity, "selection_identity": item.selection_identity,
            "bookmaker_identity": item.bookmaker_identity, "decimal_odds": item.decimal_odds,
            "market_status": item.market_status, "snapshot_timestamp_utc": utc(item.snapshot_timestamp_utc, "odds"),
            "kickoff_utc": utc(item.kickoff_utc, "kickoff"),
        })
        if item.source_fingerprint != expected:
            raise ShadowSourceError("Odds source fingerprint mismatch.")
    expected_set = sha256_fingerprint(tuple(item.source_fingerprint for item in odds_set.snapshots))
    if expected_set != odds_set.odds_snapshot_set_fingerprint:
        raise ShadowSourceError("Odds snapshot-set fingerprint mismatch.")


def vars_from_slots(value):
    return tuple((name, getattr(value, name)) for name in value.__slots__)
