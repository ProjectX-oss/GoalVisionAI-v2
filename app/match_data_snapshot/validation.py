from dataclasses import fields
from datetime import datetime
from decimal import Decimal

from .exceptions import SnapshotValidationError
from .fingerprint import MatchDataSnapshotFingerprint
from .models import (
    AggregateRecord,
    FormRecord,
    HeadToHeadRecord,
    MatchDataSnapshotRegistrationCommand,
    MatchSnapshotStatus,
    OddsContextRecord,
    PreparedMatchDataSnapshot,
    SeasonAggregateRecord,
    TeamAvailabilityRecord,
    VenueSplitRecord,
)
from .normalization import normalize_command
from .normalization import normalize_timestamp
from .policy import MatchDataSnapshotPolicy


class MatchDataSnapshotValidator:
    def __init__(
        self,
        policy: MatchDataSnapshotPolicy,
        fingerprints: MatchDataSnapshotFingerprint | None = None,
    ) -> None:
        self.policy = policy
        self._fingerprints = fingerprints or MatchDataSnapshotFingerprint()

    def prepare(
        self,
        command: MatchDataSnapshotRegistrationCommand,
    ) -> PreparedMatchDataSnapshot:
        normalized = normalize_command(command, self.policy)
        self._validate_identity(normalized)
        self._validate_timing(normalized)
        self._validate_status(normalized)
        for record in (normalized.home_recent_form, normalized.away_recent_form):
            if record is not None:
                self._form(record)
        for record in (normalized.home_venue_split, normalized.away_venue_split):
            if record is not None:
                self._venue(record)
        for record in (
            normalized.home_season_aggregate,
            normalized.away_season_aggregate,
        ):
            if record is not None:
                self._season(record)
        if normalized.head_to_head is not None:
            self._head_to_head(normalized.head_to_head, normalized.snapshot_effective_timestamp)
        for record in (normalized.home_availability, normalized.away_availability):
            if record is not None:
                self._availability(record, normalized.snapshot_effective_timestamp)
        if normalized.context is not None:
            self._nonnegative_fields(normalized.context)
            self._decimal_nonnegative(normalized.context.home_travel_distance)
            self._decimal_nonnegative(normalized.context.away_travel_distance)
        if normalized.odds_snapshot is not None:
            self._odds(normalized.odds_snapshot, normalized)
        return PreparedMatchDataSnapshot(
            logical_identity_fingerprint=self._fingerprints.logical_identity(normalized),
            content_fingerprint=self._fingerprints.content(normalized),
            command=normalized,
            deterministic_snapshot=self._fingerprints.serialize(normalized),
        )

    def normalize_reason_code(self, reason_code: str) -> str:
        if not isinstance(reason_code, str):
            self._invalid("INVALID_REASON_CODE", "Lifecycle reason must be text.")
        value = "_".join(reason_code.strip().upper().split())
        if not value or len(value) > self.policy.maximum_reason_code_length:
            self._invalid("INVALID_REASON_CODE", "Lifecycle reason is missing or too long.")
        return value

    @staticmethod
    def normalize_event_timestamp(value: datetime) -> datetime:
        return normalize_timestamp(value, "event_timestamp")

    @staticmethod
    def _validate_identity(command: MatchDataSnapshotRegistrationCommand) -> None:
        if command.home_team_id and command.away_team_id and command.home_team_id == command.away_team_id:
            MatchDataSnapshotValidator._invalid("IDENTICAL_TEAMS", "Home and away team IDs are identical.")
        if command.home_team_name.casefold() == command.away_team_name.casefold():
            MatchDataSnapshotValidator._invalid("IDENTICAL_TEAMS", "Home and away team names are identical.")

    @staticmethod
    def _validate_timing(command: MatchDataSnapshotRegistrationCommand) -> None:
        if command.kickoff_timestamp <= command.snapshot_effective_timestamp:
            MatchDataSnapshotValidator._invalid(
                "NOT_PREMATCH", "Kickoff must be after the snapshot effective time."
            )
        if command.source_updated_timestamp > command.snapshot_effective_timestamp:
            MatchDataSnapshotValidator._invalid(
                "SOURCE_AFTER_EFFECTIVE", "Source update cannot follow snapshot effective time."
            )
        if command.registration_timestamp < command.source_updated_timestamp:
            MatchDataSnapshotValidator._invalid(
                "REGISTRATION_BEFORE_SOURCE_UPDATE",
                "Registration cannot precede the supplied source update.",
            )
        if command.registration_timestamp >= command.kickoff_timestamp:
            MatchDataSnapshotValidator._invalid(
                "REGISTRATION_AT_OR_AFTER_KICKOFF",
                "A pre-match snapshot must be registered before kickoff.",
            )

    @staticmethod
    def _validate_status(command: MatchDataSnapshotRegistrationCommand) -> None:
        if command.is_live or command.scheduled_status is MatchSnapshotStatus.LIVE:
            MatchDataSnapshotValidator._invalid("LIVE_DATA_FORBIDDEN", "Live/in-play data is unsupported.")
        if command.cancelled_indicator or command.scheduled_status is MatchSnapshotStatus.CANCELLED:
            MatchDataSnapshotValidator._invalid("CANCELLED_MATCH", "Cancelled matches are not valid pre-match snapshots.")
        if command.scheduled_status is MatchSnapshotStatus.COMPLETED:
            MatchDataSnapshotValidator._invalid("COMPLETED_MATCH", "Completed matches are not valid pre-match snapshots.")
        if command.postponed_indicator != (command.scheduled_status is MatchSnapshotStatus.POSTPONED):
            MatchDataSnapshotValidator._invalid(
                "CONTRADICTORY_MATCH_STATUS", "Postponed status and indicator disagree."
            )

    @classmethod
    def _form(cls, record: FormRecord) -> None:
        cls._record(record)
        for value in (record.expected_goals_for, record.expected_goals_against):
            cls._decimal_nonnegative(value)
        if record.shots is not None and record.shots < 0:
            cls._invalid("NEGATIVE_COUNT", "Shots cannot be negative.")
        if record.shots_on_target is not None:
            if record.shots_on_target < 0:
                cls._invalid("NEGATIVE_COUNT", "Shots on target cannot be negative.")
            if record.shots is not None and record.shots_on_target > record.shots:
                cls._invalid("INCONSISTENT_SHOTS", "Shots on target exceed shots.")
        if record.possession is not None:
            if not isinstance(record.possession, Decimal) or not record.possession.is_finite():
                cls._invalid("INVALID_DECIMAL", "Possession must be a finite Decimal.")
            if not Decimal(0) <= record.possession <= Decimal(100):
                cls._invalid("INVALID_POSSESSION", "Possession must be in [0, 100].")

    @classmethod
    def _venue(cls, record: VenueSplitRecord) -> None:
        cls._record(record)
        cls._decimal_nonnegative(record.expected_goals_for)
        cls._decimal_nonnegative(record.expected_goals_against)

    @classmethod
    def _record(cls, record: FormRecord | VenueSplitRecord) -> None:
        cls._nonnegative_fields(record)
        if record.wins + record.draws + record.losses > record.match_count:
            cls._invalid("INCONSISTENT_RESULTS", "Wins, draws, and losses exceed match count.")
        if record.clean_sheets > record.match_count:
            cls._invalid("INVALID_CLEAN_SHEETS", "Clean sheets exceed match count.")
        if record.failed_to_score > record.match_count:
            cls._invalid("INVALID_FAILED_TO_SCORE", "Failed-to-score count exceeds match count.")

    @classmethod
    def _season(cls, record: SeasonAggregateRecord) -> None:
        cls._nonnegative_fields(record)
        if record.points > record.matches_played * 3:
            cls._invalid("INVALID_POINTS_TOTAL", "Season points exceed three per match.")
        if record.league_position is not None and record.league_position <= 0:
            cls._invalid("INVALID_LEAGUE_POSITION", "League position must be positive.")
        cls._decimal_nonnegative(record.expected_goals_for)
        cls._decimal_nonnegative(record.expected_goals_against)
        for split in (record.home_record, record.away_record):
            if split is not None:
                cls._aggregate(split)

    @classmethod
    def _aggregate(cls, record: AggregateRecord) -> None:
        cls._nonnegative_fields(record)
        if record.wins + record.draws + record.losses > record.match_count:
            cls._invalid("INCONSISTENT_RESULTS", "Aggregate results exceed match count.")

    @classmethod
    def _head_to_head(cls, record: HeadToHeadRecord, effective: datetime) -> None:
        cls._nonnegative_fields(record)
        if record.home_team_wins + record.draws + record.away_team_wins > record.match_count:
            cls._invalid("INCONSISTENT_H2H", "Head-to-head results exceed match count.")
        if record.both_teams_to_score_count > record.match_count or record.over_2_5_count > record.match_count:
            cls._invalid("INVALID_H2H_RATE", "Head-to-head counts exceed match count.")
        if record.most_recent_match_timestamp is not None and record.most_recent_match_timestamp >= effective:
            cls._invalid("FUTURE_DATA", "Head-to-head evidence must precede the snapshot.")

    @classmethod
    def _availability(cls, record: TeamAvailabilityRecord, effective: datetime) -> None:
        cls._nonnegative_fields(record)
        for timestamp in (record.lineup_source_timestamp, record.injury_source_timestamp):
            if timestamp is not None and timestamp > effective:
                cls._invalid("FUTURE_DATA", "Availability evidence cannot follow the snapshot.")

    @classmethod
    def _odds(
        cls,
        record: OddsContextRecord,
        command: MatchDataSnapshotRegistrationCommand,
    ) -> None:
        if not record.source_identifier.strip() or not record.market_type.strip() or not record.selection.strip():
            cls._invalid("INVALID_ODDS_CONTEXT", "Odds identity fields are required when odds are supplied.")
        if record.decimal_odds <= Decimal(1):
            cls._invalid("INVALID_DECIMAL_ODDS", "Decimal odds must exceed 1.00.")
        if record.market_line is not None and (
            not isinstance(record.market_line, Decimal)
            or not record.market_line.is_finite()
        ):
            cls._invalid("INVALID_DECIMAL", "Market line must be a finite Decimal.")
        if record.odds_timestamp > command.snapshot_effective_timestamp:
            cls._invalid("FUTURE_ODDS", "Odds timestamp cannot follow snapshot effective time.")

    @classmethod
    def _nonnegative_fields(cls, record: object) -> None:
        boolean_fields = {
            "confirmed_lineup", "probable_lineup", "derby_indicator",
        }
        for item in fields(record):
            value = getattr(record, item.name)
            if value is None or isinstance(value, (datetime, str, Decimal)):
                continue
            if item.name in boolean_fields:
                if not isinstance(value, bool):
                    cls._invalid("MALFORMED_BOOLEAN", f"{item.name} must be boolean.")
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                cls._invalid("MALFORMED_COUNT", f"{item.name} must be an integer count.")
            if value < 0:
                cls._invalid("NEGATIVE_COUNT", f"{item.name} cannot be negative.")

    @classmethod
    def _decimal_nonnegative(cls, value: Decimal | None) -> None:
        if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
            cls._invalid("INVALID_DECIMAL", "Decimal facts must be finite Decimal values.")
        if value is not None and value < 0:
            cls._invalid("NEGATIVE_VALUE", "Decimal facts cannot be negative.")

    @staticmethod
    def _invalid(code: str, explanation: str) -> None:
        raise SnapshotValidationError(code, explanation)
