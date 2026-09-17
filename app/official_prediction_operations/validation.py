"""Strict validation for versioned, JSON-only Official pipeline fixtures."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

from .exceptions import FixtureValidationError
from .fixture_models import FIXTURE_SCHEMA, OfficialPredictionFixture
from .serialization import sha256_fingerprint


REQUIRED_SECTIONS = (
    "metadata", "match", "model_input", "inference", "calibration", "odds",
    "value_assessment", "selection", "bankroll", "exposure", "risk",
    "candidate", "publication",
)
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_KEY_PARTS = ("token", "secret", "password", "api_key", "bot_key", "credential")
_URL = re.compile(r"(?:https?|ftp)://", re.IGNORECASE)

_FIELDS: dict[str, tuple[str, ...]] = {
    "metadata": ("fixture_id", "schema_version", "description", "expected_outcome", "metadata_version", "non_production", "fixture_fingerprint"),
    "match": ("match_id", "competition_id", "competition_name", "home_team_id", "home_team_name", "away_team_id", "away_team_name", "kickoff_utc", "snapshot_effective_time", "source_provider", "source_event_id", "source_snapshot_identity"),
    "model_input": ("model_input_id", "feature_set_id", "snapshot_id", "completeness", "schema_version", "provenance_reference"),
    "inference": ("inference_id", "model_artifact_id", "model_name", "model_version", "raw_probabilities", "raw_probability_fingerprint"),
    "calibration": ("calibrated_assembly_id", "calibration_set_id", "calibrated_probabilities", "calibrated_assembly_fingerprint", "sample_size", "brier_score", "log_loss", "expected_calibration_error", "maximum_calibration_error"),
    "odds": ("odds_snapshot_identity", "provider", "bookmaker", "source_event_id", "market", "selection", "line", "decimal_odds", "odds_effective_timestamp", "odds_fingerprint", "available", "is_live"),
    "value_assessment": ("assessment_id", "fair_probability", "fair_odds", "implied_probability", "expected_value", "absolute_probability_edge", "relative_probability_edge", "freshness", "actionability", "assessment_fingerprint"),
    "selection": ("selection_decision_id", "selection_fingerprint", "selected_market", "selected_assessment_identity", "expected_rank", "expected_eligible_count"),
    "bankroll": ("snapshot_id", "scope", "currency", "current_bankroll", "available_bankroll", "effective_timestamp", "fingerprint"),
    "exposure": ("snapshot_id", "current_match_exposure", "current_market_exposure", "correlated_exposure_facts", "effective_timestamp", "fingerprint"),
    "risk": ("expected_risk_outcome", "expected_stake_percentage", "expected_stake_amount", "expected_risk_fingerprint", "confidence_level", "lineup_status", "injury_status", "supporting_data_status", "market_availability", "model_health_status"),
    "candidate": ("expected_candidate_id", "expected_version", "expected_lifecycle", "expected_candidate_fingerprint"),
    "publication": ("expected_destination_identity", "destination_type", "expected_message_fingerprint", "expected_dry_run_outcome", "expected_publish_outcome", "initial_state"),
}

_DECIMAL_FIELDS = {
    "decimal_odds", "fair_probability", "fair_odds", "implied_probability",
    "expected_value", "absolute_probability_edge", "relative_probability_edge",
    "current_bankroll", "available_bankroll", "current_match_exposure",
    "current_market_exposure", "expected_stake_percentage", "expected_stake_amount",
    "brier_score", "log_loss", "expected_calibration_error", "maximum_calibration_error",
}
_TIMESTAMP_FIELDS = {
    "kickoff_utc", "snapshot_effective_time", "odds_effective_timestamp", "effective_timestamp",
}
_TARGETS = {
    "HOME_WIN", "DRAW", "AWAY_WIN", "OVER_1_5", "UNDER_1_5",
    "OVER_2_5", "UNDER_2_5", "OVER_3_5", "UNDER_3_5",
    "BTTS_YES", "BTTS_NO",
}


def load_official_fixture(path: str | Path) -> OfficialPredictionFixture:
    fixture_path = Path(path).expanduser().resolve()
    if not fixture_path.is_file():
        raise FixtureValidationError(f"Fixture file does not exist: {fixture_path}")
    try:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FixtureValidationError("Fixture must be a readable UTF-8 JSON document.") from exc
    return validate_official_fixture(payload)


def validate_official_fixture(payload: object) -> OfficialPredictionFixture:
    if type(payload) is not dict:
        raise FixtureValidationError("Fixture root must be a JSON object.")
    _reject_unsafe_content(payload)
    if set(payload) != set(REQUIRED_SECTIONS):
        missing = sorted(set(REQUIRED_SECTIONS) - set(payload))
        extra = sorted(set(payload) - set(REQUIRED_SECTIONS))
        raise FixtureValidationError(f"Fixture sections mismatch; missing={missing}, extra={extra}.")
    for section, fields in _FIELDS.items():
        value = payload[section]
        if type(value) is not dict or set(value) != set(fields):
            raise FixtureValidationError(f"Section '{section}' has missing or unsupported fields.")
    metadata = payload["metadata"]
    if metadata["schema_version"] != FIXTURE_SCHEMA:
        raise FixtureValidationError(f"Unsupported fixture schema: {metadata['schema_version']!r}.")
    if metadata["metadata_version"] != "v1" or type(metadata["non_production"]) is not bool:
        raise FixtureValidationError("Fixtures must be metadata v1 and explicitly classify non-production status.")
    _validate_strings(payload)
    _validate_decimals(payload)
    _validate_timestamps(payload)
    _validate_fingerprints(payload)
    if payload["bankroll"]["scope"] != "OFFICIAL" or payload["bankroll"]["currency"] != "EUR":
        raise FixtureValidationError("Fixture bankroll scope/currency must be OFFICIAL/EUR.")
    if payload["odds"]["is_live"] is not False:
        raise FixtureValidationError("Live odds are forbidden in Official fixtures.")
    if payload["candidate"]["expected_lifecycle"] != "READY":
        raise FixtureValidationError("Expected candidate lifecycle must be READY.")
    _validate_market_and_derived_values(payload)
    expected = metadata["fixture_fingerprint"]
    unsigned = {key: dict(value) for key, value in payload.items()}
    unsigned["metadata"].pop("fixture_fingerprint")
    actual = sha256_fingerprint(unsigned)
    if expected != actual:
        raise FixtureValidationError("Fixture fingerprint does not match canonical content.")
    return OfficialPredictionFixture(payload=payload, fixture_fingerprint=actual)


def parse_utc_timestamp(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise FixtureValidationError(f"{label} must be an explicit UTC timestamp ending in Z.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FixtureValidationError(f"{label} is not a valid timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise FixtureValidationError(f"{label} must be UTC.")
    return parsed


def parse_decimal(value: object, label: str) -> Decimal:
    if not isinstance(value, str) or not value.strip():
        raise FixtureValidationError(f"{label} must be a Decimal-safe JSON string.")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise FixtureValidationError(f"{label} is not a valid Decimal.") from exc
    if not parsed.is_finite():
        raise FixtureValidationError(f"{label} must be finite.")
    return parsed


def _validate_strings(payload: Mapping[str, Any]) -> None:
    for section, values in payload.items():
        for key, value in values.items():
            if key in {"line", "expected_message_fingerprint"} and value is None:
                continue
            if key in {"raw_probabilities", "calibrated_probabilities", "correlated_exposure_facts"}:
                continue
            if isinstance(value, str) and not value.strip():
                raise FixtureValidationError(f"{section}.{key} cannot be empty.")


def _validate_decimals(payload: Mapping[str, Any]) -> None:
    for section, values in payload.items():
        for key, value in values.items():
            if key in _DECIMAL_FIELDS:
                parse_decimal(value, f"{section}.{key}")
    for group in ("raw_probabilities", "calibrated_probabilities"):
        values = payload["inference" if group == "raw_probabilities" else "calibration"][group]
        if type(values) is not dict or not values:
            raise FixtureValidationError(f"{group} must be a non-empty JSON object.")
        if set(values) != _TARGETS:
            raise FixtureValidationError(f"{group} must contain the exact Official target set.")
        for target, value in values.items():
            probability = parse_decimal(value, f"{group}.{target}")
            if probability < 0 or probability > 1:
                raise FixtureValidationError(f"{group}.{target} must be in [0,1].")


def _validate_timestamps(payload: Mapping[str, Any]) -> None:
    for section, values in payload.items():
        for key, value in values.items():
            if key in _TIMESTAMP_FIELDS:
                parse_utc_timestamp(value, f"{section}.{key}")
    kickoff = parse_utc_timestamp(payload["match"]["kickoff_utc"], "match.kickoff_utc")
    snapshot = parse_utc_timestamp(payload["match"]["snapshot_effective_time"], "match.snapshot_effective_time")
    odds = parse_utc_timestamp(payload["odds"]["odds_effective_timestamp"], "odds.odds_effective_timestamp")
    if not snapshot <= odds < kickoff:
        raise FixtureValidationError("Fixture timestamps must preserve snapshot <= odds < kickoff.")


def _validate_fingerprints(payload: Mapping[str, Any]) -> None:
    for section, values in payload.items():
        for key, value in values.items():
            if "fingerprint" in key and value is not None and not _FINGERPRINT.fullmatch(str(value)):
                raise FixtureValidationError(f"{section}.{key} must be a lowercase SHA-256 value.")


def _validate_market_and_derived_values(payload: Mapping[str, Any]) -> None:
    odds = payload["odds"]
    market = odds["market"]
    selection = odds["selection"]
    supported = {
        "MATCH_WINNER": {"HOME", "DRAW", "AWAY"},
        "DOUBLE_CHANCE": {"HOME_DRAW", "HOME_AWAY", "DRAW_AWAY"},
        "TOTALS": {"OVER", "UNDER"},
        "BTTS": {"YES", "NO"},
    }
    if market not in supported or selection not in supported[market]:
        raise FixtureValidationError("Fixture market/selection is unsupported by Official policy.")
    line = odds["line"]
    if market == "TOTALS":
        if parse_decimal(line, "odds.line") not in {Decimal("1.5"), Decimal("2.5"), Decimal("3.5")}:
            raise FixtureValidationError("Totals line is unsupported.")
    elif line is not None:
        raise FixtureValidationError("A market line is only valid for totals.")
    if odds["source_event_id"] != payload["match"]["source_event_id"]:
        raise FixtureValidationError("Odds and match source-event provenance conflict.")
    if payload["selection"]["selected_assessment_identity"] != payload["value_assessment"]["assessment_id"]:
        raise FixtureValidationError("Selection and value-assessment identities conflict.")
    price = parse_decimal(odds["decimal_odds"], "odds.decimal_odds")
    fair = parse_decimal(payload["value_assessment"]["fair_probability"], "value_assessment.fair_probability")
    implied = parse_decimal(payload["value_assessment"]["implied_probability"], "value_assessment.implied_probability")
    expected_value = parse_decimal(payload["value_assessment"]["expected_value"], "value_assessment.expected_value")
    tolerance = Decimal("0.000000001")
    if price <= 1 or fair <= 0 or fair >= 1:
        raise FixtureValidationError("Odds and fair probability are outside supported bounds.")
    if abs(implied - (Decimal("1") / price)) > tolerance:
        raise FixtureValidationError("Implied probability does not match decimal odds.")
    if abs(expected_value - (fair * price - Decimal("1"))) > tolerance:
        raise FixtureValidationError("Expected value does not match probability and odds.")
    for name in ("raw_probabilities", "calibrated_probabilities"):
        source = payload["inference" if name == "raw_probabilities" else "calibration"][name]
        values = {key: Decimal(value) for key, value in source.items()}
        if values["HOME_WIN"] + values["DRAW"] + values["AWAY_WIN"] != Decimal("1"):
            raise FixtureValidationError(f"{name} match-result probabilities must sum to one.")
        for over, under in (("OVER_1_5", "UNDER_1_5"), ("OVER_2_5", "UNDER_2_5"), ("OVER_3_5", "UNDER_3_5"), ("BTTS_YES", "BTTS_NO")):
            if values[over] + values[under] != Decimal("1"):
                raise FixtureValidationError(f"{name} complement probabilities must sum to one.")
        if not values["OVER_1_5"] >= values["OVER_2_5"] >= values["OVER_3_5"]:
            raise FixtureValidationError(f"{name} totals probabilities are not monotonic.")


def _reject_unsafe_content(value: Any, path: str = "fixture") -> None:
    if value is None or type(value) in {str, int, bool}:
        if isinstance(value, str) and _URL.search(value):
            raise FixtureValidationError(f"URLs are forbidden in fixtures ({path}).")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _reject_unsafe_content(item, f"{path}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise FixtureValidationError(f"Fixture keys must be strings ({path}).")
            normalized = key.lower().replace("-", "_")
            if any(fragment in normalized for fragment in _FORBIDDEN_KEY_PARTS):
                raise FixtureValidationError(f"Credentials/secrets are forbidden ({path}.{key}).")
            _reject_unsafe_content(item, f"{path}.{key}")
        return
    raise FixtureValidationError(f"Arbitrary JSON-incompatible object is forbidden ({path}).")
