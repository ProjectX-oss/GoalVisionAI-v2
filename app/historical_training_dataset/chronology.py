"""Independent strict temporal-cutoff enforcement."""

from __future__ import annotations

from datetime import datetime

from .exceptions import TemporalLeakageError
from .models import HistoricalSourceMatch, LeakageReason, TrainingExampleSource


def strictly_prior_matches(
    target: HistoricalSourceMatch,
    matches: tuple[HistoricalSourceMatch, ...],
) -> tuple[HistoricalSourceMatch, ...]:
    target_time = _timestamp(target.kickoff_utc, LeakageReason.SOURCE_TIMESTAMP_MISSING)
    eligible = []
    for source in matches:
        if source.historical_match_id == target.historical_match_id:
            continue
        source_time = _timestamp(source.kickoff_utc, LeakageReason.SOURCE_TIMESTAMP_MISSING)
        if source_time < target_time:
            eligible.append(source)
    return tuple(sorted(eligible, key=match_order_key))


def assert_source_precedes_target(source_id: str, source_kickoff: str, target_id: str, target_kickoff: str) -> None:
    if source_id == target_id:
        raise TemporalLeakageError(LeakageReason.TARGET_AS_SOURCE.value)
    source_time = _timestamp(source_kickoff, LeakageReason.SOURCE_TIMESTAMP_MISSING)
    target_time = _timestamp(target_kickoff, LeakageReason.SOURCE_TIMESTAMP_MISSING)
    if source_time == target_time:
        raise TemporalLeakageError(LeakageReason.SOURCE_EQUALS_TARGET_KICKOFF.value)
    if source_time > target_time:
        raise TemporalLeakageError(LeakageReason.SOURCE_AFTER_TARGET.value)


def verify_sources_strictly_prior(target_id: str, target_kickoff: str, sources: tuple[TrainingExampleSource, ...]) -> tuple[str, ...]:
    reasons: list[str] = []
    for source in sources:
        try:
            assert_source_precedes_target(
                source.source_historical_match_id,
                source.source_kickoff,
                target_id,
                target_kickoff,
            )
        except TemporalLeakageError as exc:
            reasons.append(str(exc))
    return tuple(sorted(set(reasons)))


def match_order_key(match: HistoricalSourceMatch) -> tuple[str, str, str]:
    return (match.kickoff_utc, match.competition_identity, match.historical_match_id)


def _timestamp(value: str, reason: LeakageReason) -> datetime:
    if not isinstance(value, str) or not value:
        raise TemporalLeakageError(reason.value)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TemporalLeakageError(reason.value) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TemporalLeakageError(reason.value)
    return parsed
