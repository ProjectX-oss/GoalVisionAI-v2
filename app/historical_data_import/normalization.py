"""Deterministic normalization of explicitly supplied provider history."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal

from .exceptions import HistoricalDatasetValidationError
from .fingerprint import canonical_json, sha256_fingerprint
from .models import (
    HistoricalDataset,
    HistoricalLineupInput,
    HistoricalMatchInput,
    HistoricalTeamStatisticsInput,
    NormalizedHistoricalLineup,
    NormalizedHistoricalMatch,
    NormalizedHistoricalStatistics,
    PreparedHistoricalDataset,
    PreparedHistoricalMatch,
)
from .policy import DEFAULT_HISTORICAL_IMPORT_POLICY, HistoricalImportPolicy
from .validation import (
    derive_result,
    normalize_supplied_result,
    optional_decimal,
    optional_integer,
    optional_text,
    require_integer,
    require_text,
    validate_dataset,
    validate_lineup_input,
    validate_statistics_input,
)


_WHITESPACE = re.compile(r"\s+")


def normalize_text(value: str, label: str) -> str:
    checked = require_text(value, label)
    normalized = unicodedata.normalize("NFKC", checked)
    return _WHITESPACE.sub(" ", normalized).strip()


def normalize_identity(value: str, label: str) -> str:
    display = normalize_text(value, label).casefold()
    identity = "".join(character if character.isalnum() else " " for character in display)
    identity = _WHITESPACE.sub(" ", identity).strip()
    if not identity:
        raise HistoricalDatasetValidationError(f"{label} has no usable identity characters.")
    return identity


def normalize_utc(value: datetime | str, label: str) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif type(value) is str and value.strip():
        source = value.strip()
        try:
            parsed = datetime.fromisoformat(source[:-1] + "+00:00" if source.endswith("Z") else source)
        except ValueError as exc:
            raise HistoricalDatasetValidationError(f"{label} is not a valid ISO-8601 timestamp.") from exc
    else:
        raise HistoricalDatasetValidationError(f"{label} must be an explicit timestamp.")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HistoricalDatasetValidationError(f"{label} must include an explicit UTC offset.")
    utc = parsed.astimezone(timezone.utc)
    timespec = "microseconds" if utc.microsecond else "seconds"
    return utc.isoformat(timespec=timespec).replace("+00:00", "Z")


def prepare_historical_dataset(
    dataset: HistoricalDataset,
    *,
    import_timestamp: datetime | str,
    policy: HistoricalImportPolicy = DEFAULT_HISTORICAL_IMPORT_POLICY,
) -> PreparedHistoricalDataset:
    validate_dataset(dataset, policy)
    provider = normalize_text(dataset.provider, "provider")
    provider_identity = normalize_identity(provider, "provider")
    dataset_id = normalize_text(dataset.dataset_id, "dataset_id")
    dataset_version = normalize_text(dataset.dataset_version, "dataset_version")
    imported_at = normalize_utc(import_timestamp, "import_timestamp")
    prepared = tuple(
        _prepare_match(match, provider, provider_identity, policy)
        for match in dataset.matches
    )
    _reject_dataset_duplicates(prepared)
    ordered = tuple(sorted(
        prepared,
        key=lambda item: (
            item.match.kickoff_utc,
            item.logical_identity_fingerprint,
            item.match_fingerprint,
        ),
    ))
    fingerprints = tuple(item.match_fingerprint for item in ordered)
    match_snapshot = canonical_json(fingerprints)
    content_fingerprint = sha256_fingerprint({"match_fingerprints": fingerprints})
    deterministic = {
        "schema_version": dataset.schema_version,
        "provider": provider,
        "provider_identity": provider_identity,
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "dataset_content_fingerprint": content_fingerprint,
        "match_fingerprints": fingerprints,
        "policy_version": policy.version,
        "metadata_version": policy.metadata_version,
    }
    dataset_fingerprint = sha256_fingerprint(deterministic)
    return PreparedHistoricalDataset(
        schema_version=dataset.schema_version,
        provider=provider,
        provider_identity=provider_identity,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        import_timestamp=imported_at,
        matches=ordered,
        dataset_content_fingerprint=content_fingerprint,
        dataset_fingerprint=dataset_fingerprint,
        match_fingerprint_snapshot=match_snapshot,
        deterministic_dataset_snapshot=canonical_json(deterministic),
        policy_version=policy.version,
        metadata_version=policy.metadata_version,
    )


def _prepare_match(
    value: HistoricalMatchInput,
    provider: str,
    provider_identity: str,
    policy: HistoricalImportPolicy,
) -> PreparedHistoricalMatch:
    if type(value) is not HistoricalMatchInput:
        raise HistoricalDatasetValidationError("Every dataset item must be a HistoricalMatchInput.")
    source_match_id = normalize_text(value.source_match_id, "source_match_id")
    competition = normalize_text(value.competition, "competition")
    competition_identity = normalize_identity(competition, "competition")
    season = normalize_text(value.season, "season")
    round_name = normalize_text(value.round, "round")
    kickoff = normalize_utc(value.kickoff_utc, "kickoff_utc")
    home_team = normalize_text(value.home_team, "home_team")
    away_team = normalize_text(value.away_team, "away_team")
    home_identity = normalize_identity(home_team, "home_team")
    away_identity = normalize_identity(away_team, "away_team")
    if home_identity == away_identity:
        raise HistoricalDatasetValidationError("Home and away team identities must differ.")
    home_score = require_integer(
        value.full_time_home_score,
        "full_time_home_score",
        maximum=policy.maximum_score,
    )
    away_score = require_integer(
        value.full_time_away_score,
        "full_time_away_score",
        maximum=policy.maximum_score,
    )
    half_home = optional_integer(
        value.half_time_home_score,
        "half_time_home_score",
        maximum=policy.maximum_score,
    )
    half_away = optional_integer(
        value.half_time_away_score,
        "half_time_away_score",
        maximum=policy.maximum_score,
    )
    if (half_home is None) != (half_away is None):
        raise HistoricalDatasetValidationError("Both half-time scores must be supplied together.")
    if half_home is not None and (half_home > home_score or half_away > away_score):
        raise HistoricalDatasetValidationError("Half-time scores cannot exceed full-time scores.")
    result = derive_result(home_score, away_score)
    supplied_result = normalize_supplied_result(value.full_time_result)
    if supplied_result is not None and supplied_result is not result:
        raise HistoricalDatasetValidationError("The supplied full-time result conflicts with the score.")
    venue = normalize_text(value.venue, "venue")
    referee_raw = optional_text(value.referee, "referee")
    referee = normalize_text(referee_raw, "referee") if referee_raw is not None else None
    attendance = optional_integer(value.attendance, "attendance")
    home_statistics = _normalize_statistics(value.home_statistics, "home_statistics", policy)
    away_statistics = _normalize_statistics(value.away_statistics, "away_statistics", policy)
    if (
        home_statistics is not None
        and away_statistics is not None
        and home_statistics.possession is not None
        and away_statistics.possession is not None
    ):
        possession_total = home_statistics.possession + away_statistics.possession
        if abs(possession_total - Decimal("100")) > policy.possession_total_tolerance:
            raise HistoricalDatasetValidationError("Home and away possession must total approximately 100.")
    home_lineup = _normalize_lineup(value.home_lineup, "home_lineup", policy)
    away_lineup = _normalize_lineup(value.away_lineup, "away_lineup", policy)
    normalized = NormalizedHistoricalMatch(
        source_provider=provider,
        provider_identity=provider_identity,
        source_match_id=source_match_id,
        competition=competition,
        competition_identity=competition_identity,
        season=season,
        round=round_name,
        kickoff_utc=kickoff,
        home_team=home_team,
        home_team_identity=home_identity,
        away_team=away_team,
        away_team_identity=away_identity,
        full_time_home_score=home_score,
        full_time_away_score=away_score,
        half_time_home_score=half_home,
        half_time_away_score=half_away,
        full_time_result=result,
        venue=venue,
        referee=referee,
        attendance=attendance,
        home_statistics=home_statistics,
        away_statistics=away_statistics,
        home_lineup=home_lineup,
        away_lineup=away_lineup,
    )
    logical = sha256_fingerprint({
        "provider_identity": provider_identity,
        "source_match_id": normalize_identity(source_match_id, "source_match_id"),
    })
    natural = sha256_fingerprint({
        "competition_identity": competition_identity,
        "season": normalize_identity(season, "season"),
        "kickoff_utc": kickoff,
        "home_team_identity": home_identity,
        "away_team_identity": away_identity,
    })
    snapshot = canonical_json(normalized)
    return PreparedHistoricalMatch(
        match=normalized,
        logical_identity_fingerprint=logical,
        natural_identity_fingerprint=natural,
        match_fingerprint=sha256_fingerprint(normalized),
        normalized_match_snapshot=snapshot,
    )


def _normalize_statistics(
    value: HistoricalTeamStatisticsInput | None,
    label: str,
    policy: HistoricalImportPolicy,
) -> NormalizedHistoricalStatistics | None:
    if value is None:
        return None
    validate_statistics_input(value, label, policy)
    return NormalizedHistoricalStatistics(
        possession=optional_decimal(value.possession, f"{label}.possession", minimum=Decimal("0"), maximum=Decimal("100")),
        shots=optional_integer(value.shots, f"{label}.shots", maximum=policy.maximum_shots),
        shots_on_target=optional_integer(value.shots_on_target, f"{label}.shots_on_target", maximum=policy.maximum_shots_on_target),
        expected_goals=optional_decimal(value.expected_goals, f"{label}.expected_goals", minimum=Decimal("0"), maximum=policy.maximum_expected_goals),
        corners=optional_integer(value.corners, f"{label}.corners", maximum=policy.maximum_corners),
        yellow_cards=optional_integer(value.yellow_cards, f"{label}.yellow_cards", maximum=policy.maximum_yellow_cards),
        red_cards=optional_integer(value.red_cards, f"{label}.red_cards", maximum=policy.maximum_red_cards),
        fouls=optional_integer(value.fouls, f"{label}.fouls", maximum=policy.maximum_fouls),
        offsides=optional_integer(value.offsides, f"{label}.offsides", maximum=policy.maximum_offsides),
    )


def _normalize_lineup(
    value: HistoricalLineupInput | None,
    label: str,
    policy: HistoricalImportPolicy,
) -> NormalizedHistoricalLineup | None:
    if value is None:
        return None
    validate_lineup_input(value, label, policy)
    starters = tuple(normalize_text(player, f"{label}.starting_xi") for player in value.starting_xi)
    substitutes = tuple(normalize_text(player, f"{label}.substitutes") for player in value.substitutes)
    identities = tuple(normalize_identity(player, f"{label}.player") for player in (*starters, *substitutes))
    if len(identities) != len(set(identities)):
        raise HistoricalDatasetValidationError(f"{label} contains duplicate players.")
    formation = value.formation.replace(" ", "") if value.formation is not None else None
    return NormalizedHistoricalLineup(starters, substitutes, formation)


def _reject_dataset_duplicates(matches: tuple[PreparedHistoricalMatch, ...]) -> None:
    logical: set[str] = set()
    natural: set[str] = set()
    fingerprints: set[str] = set()
    for match in matches:
        if match.logical_identity_fingerprint in logical:
            raise HistoricalDatasetValidationError("The dataset repeats a provider match identity.")
        if match.natural_identity_fingerprint in natural:
            raise HistoricalDatasetValidationError("The dataset repeats a normalized natural match identity.")
        if match.match_fingerprint in fingerprints:
            raise HistoricalDatasetValidationError("The dataset contains duplicate normalized match content.")
        logical.add(match.logical_identity_fingerprint)
        natural.add(match.natural_identity_fingerprint)
        fingerprints.add(match.match_fingerprint)
