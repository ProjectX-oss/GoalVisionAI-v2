"""Fail-closed request, source, feature, and example validation."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal

from .exceptions import DatasetRequestValidationError, SourceProvenanceError
from .models import (
    DatasetBuildCommand,
    HistoricalTrainingExample,
    NormalizedDatasetBuildCommand,
)
from .policy import HistoricalTrainingDatasetPolicy, METADATA_VERSION


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")


def normalize_build_command(
    command: DatasetBuildCommand,
    policy: HistoricalTrainingDatasetPolicy,
) -> NormalizedDatasetBuildCommand:
    if not isinstance(command, DatasetBuildCommand):
        raise DatasetRequestValidationError("A typed DatasetBuildCommand is required.")
    request_id = _identifier(command.request_id, "request ID")
    dataset_name = _text(command.dataset_name, "dataset name")
    if not command.source_import_ids:
        raise DatasetRequestValidationError("At least one explicit source import ID is required.")
    source_ids = tuple(sorted(_identifier(value, "source import ID") for value in command.source_import_ids))
    if len(source_ids) != len(set(source_ids)):
        raise DatasetRequestValidationError("Source import IDs must be unique.")
    competitions = tuple(sorted({_identity(value, "competition filter") for value in command.competition_filters}))
    seasons = tuple(sorted({_text(value, "season filter") for value in command.season_filters}))
    lower = normalize_utc(command.kickoff_lower_bound, optional=True)
    upper = normalize_utc(command.kickoff_upper_bound, optional=True)
    if lower is not None and upper is not None and lower >= upper:
        raise DatasetRequestValidationError("Kickoff lower bound must precede upper bound.")
    if command.cutoff_policy != policy.cutoff_policy:
        raise DatasetRequestValidationError("Unsupported cutoff policy.")
    if command.feature_schema_version != policy.feature_schema_version:
        raise DatasetRequestValidationError("Unsupported feature schema.")
    if command.label_schema_version != policy.label_schema_version:
        raise DatasetRequestValidationError("Unsupported label schema.")
    if command.dataset_policy_version != policy.version:
        raise DatasetRequestValidationError("Unsupported dataset policy.")
    if command.metadata_version != METADATA_VERSION:
        raise DatasetRequestValidationError("Unsupported metadata version.")
    build_timestamp = normalize_utc(command.build_timestamp)
    return NormalizedDatasetBuildCommand(
        request_id=request_id,
        dataset_name=dataset_name,
        source_import_ids=source_ids,
        competition_filters=competitions,
        season_filters=seasons,
        kickoff_lower_bound=lower,
        kickoff_upper_bound=upper,
        cutoff_policy=command.cutoff_policy,
        feature_schema_version=command.feature_schema_version,
        label_schema_version=command.label_schema_version,
        dataset_policy_version=command.dataset_policy_version,
        build_timestamp=build_timestamp,
        metadata_version=command.metadata_version,
    )


def validate_source_matches(matches: tuple[object, ...]) -> None:
    identities: dict[str, str] = {}
    for match in matches:
        match_id = getattr(match, "historical_match_id", None)
        fingerprint = getattr(match, "match_fingerprint", None)
        kickoff = getattr(match, "kickoff_utc", None)
        home = getattr(match, "home_team_identity", None)
        away = getattr(match, "away_team_identity", None)
        if not all(isinstance(value, str) and value for value in (match_id, fingerprint, kickoff, home, away)):
            raise SourceProvenanceError("Historical match provenance is incomplete.")
        if len(fingerprint) != 64 or any(char not in "0123456789abcdef" for char in fingerprint):
            raise SourceProvenanceError("Historical match fingerprint is malformed.")
        normalized_kickoff = normalize_utc(kickoff)
        if normalized_kickoff != kickoff:
            raise SourceProvenanceError("Historical source kickoff is not canonical UTC.")
        if home != _canonical_identity(home) or away != _canonical_identity(away):
            raise SourceProvenanceError("Historical source team identity is not normalized.")
        if home == away:
            raise SourceProvenanceError("Historical match team identities conflict.")
        previous = identities.get(match_id)
        if previous is not None and previous != fingerprint:
            raise SourceProvenanceError("A historical match ID has conflicting fingerprints.")
        if previous is not None:
            raise SourceProvenanceError("A historical match is duplicated in the selected source set.")
        identities[match_id] = fingerprint


def validate_example(example: HistoricalTrainingExample, expected_features: int) -> None:
    if len(example.ordered_feature_vector) != expected_features:
        raise SourceProvenanceError("Feature vector length differs from its schema.")
    if len(example.missingness_mask) != expected_features:
        raise SourceProvenanceError("Missingness mask length differs from its schema.")
    for value, missing in zip(example.ordered_feature_vector, example.missingness_mask):
        if missing != (value is None):
            raise SourceProvenanceError("Feature missingness contradicts the feature value.")
        if isinstance(value, Decimal) and not value.is_finite():
            raise SourceProvenanceError("Feature values must be finite.")
    available = sum(not item for item in example.missingness_mask)
    expected = (Decimal(available) / Decimal(expected_features)).quantize(Decimal("0.000001"))
    if example.completeness_score != expected:
        raise SourceProvenanceError("Feature completeness is inconsistent.")


def normalize_utc(value: datetime | str | None, *, optional: bool = False) -> str | None:
    if value is None:
        if optional:
            return None
        raise DatasetRequestValidationError("An explicit timezone-aware timestamp is required.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    except (TypeError, ValueError) as exc:
        raise DatasetRequestValidationError("Timestamp is malformed.") from exc
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DatasetRequestValidationError("Timestamp must include an explicit timezone.")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise DatasetRequestValidationError(f"{label.title()} must be text.")
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    if not normalized or len(normalized) > 200:
        raise DatasetRequestValidationError(f"{label.title()} is empty or too long.")
    return normalized


def _identifier(value: object, label: str) -> str:
    normalized = _text(value, label)
    if not _IDENTIFIER.fullmatch(normalized):
        raise DatasetRequestValidationError(f"{label.title()} is malformed.")
    return normalized


def _identity(value: object, label: str) -> str:
    return _text(value, label).casefold()


def _canonical_identity(value: str) -> str:
    display = unicodedata.normalize("NFKC", value).casefold()
    return " ".join("".join(character if character.isalnum() else " " for character in display).split())
