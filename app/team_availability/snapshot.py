from collections import defaultdict
from datetime import datetime, timedelta

from .models import (
    AvailabilityConflict,
    AvailabilityEvidenceStatus,
    AvailabilityReason,
    AvailabilityReliability,
    AvailabilitySource,
    LineupObservation,
    LineupStatus,
    LineupType,
    PlayerAvailabilityObservation,
    PlayerAvailabilityStatus,
    PlayerIdentity,
    TeamAvailabilitySnapshot,
    TeamIdentity,
)
from .policy import AvailabilityFreshnessPolicy


class TeamAvailabilitySnapshotBuilder:
    def __init__(
        self,
        freshness: AvailabilityFreshnessPolicy | None = None,
    ) -> None:
        self._freshness = freshness or AvailabilityFreshnessPolicy()

    def build(
        self,
        *,
        fixture_id: str,
        team: TeamIdentity,
        evaluation_timestamp: datetime,
        kickoff: datetime,
        player_observations: tuple[PlayerAvailabilityObservation, ...],
        lineup_observations: tuple[LineupObservation, ...],
        sources: tuple[AvailabilitySource, ...],
    ) -> TeamAvailabilitySnapshot:
        self._aware(evaluation_timestamp)
        self._aware(kickoff)
        players = tuple(
            item
            for item in player_observations
            if item.fixture_id == fixture_id
            and item.team.team_id == team.team_id
            and item.observed_at <= evaluation_timestamp
        )
        lineups = tuple(
            item
            for item in lineup_observations
            if item.fixture_id == fixture_id
            and item.team.team_id == team.team_id
            and item.observed_at <= evaluation_timestamp
            and (
                item.lineup_status is not LineupStatus.CONFIRMED
                or item.observed_at <= kickoff
            )
        )
        starting_lineups = tuple(
            item for item in lineups if item.lineup_type is LineupType.STARTING
        )
        latest_lineup = max(
            starting_lineups,
            key=lambda item: (
                item.observed_at,
                self._lineup_rank(item.lineup_status),
                item.source_name,
                item.lineup_observation_id,
            ),
            default=None,
        )
        latest_substitutes = max(
            (
                item
                for item in lineups
                if item.lineup_type is LineupType.SUBSTITUTE
            ),
            key=lambda item: (
                item.observed_at,
                self._lineup_rank(item.lineup_status),
                item.source_name,
                item.lineup_observation_id,
            ),
            default=None,
        )
        latest_by_player: dict[str, list[PlayerAvailabilityObservation]] = (
            defaultdict(list)
        )
        for item in players:
            latest_by_player[item.player.identity_key].append(item)
        latest_sets: list[tuple[PlayerAvailabilityObservation, ...]] = []
        conflicts: list[AvailabilityConflict] = []
        chosen: list[PlayerAvailabilityObservation] = []
        source_map = {item.source_name: item for item in sources}
        for key in sorted(latest_by_player):
            observations = latest_by_player[key]
            latest_at = max(item.observed_at for item in observations)
            current = tuple(
                sorted(
                    (item for item in observations if item.observed_at == latest_at),
                    key=lambda item: (
                        item.availability_status.value,
                        item.source_name,
                        item.observation_id,
                    ),
                )
            )
            latest_sets.append(current)
            reliable_statuses = {
                item.availability_status
                for item in current
                if source_map.get(item.source_name) is not None
                and source_map[item.source_name].reliability
                is AvailabilityReliability.RELIABLE
            }
            if len(reliable_statuses) > 1:
                conflicts.append(
                    AvailabilityConflict(
                        player=current[0].player,
                        statuses=tuple(sorted(reliable_statuses, key=lambda x: x.value)),
                        observation_ids=tuple(
                            sorted(item.observation_id for item in current)
                        ),
                    )
                )
            chosen.extend(current)
        status_players = self._status_players(chosen)
        freshness = self._freshness_status(
            evaluation_timestamp,
            latest_lineup,
            tuple(item for group in latest_sets for item in group),
        )
        completeness = self._completeness(
            latest_lineup,
            tuple(item for group in latest_sets for item in group),
            bool(conflicts),
        )
        lineup_evidence = self._lineup_evidence(
            evaluation_timestamp,
            latest_lineup,
        )
        injury_evidence = self._injury_evidence(
            evaluation_timestamp,
            tuple(item for group in latest_sets for item in group),
            bool(conflicts),
        )
        confirmed = ()
        predicted = ()
        substitutes = ()
        formation = None
        if latest_lineup is not None:
            formation = latest_lineup.formation
            if latest_lineup.lineup_status is LineupStatus.CONFIRMED:
                confirmed = tuple(
                    item for item in latest_lineup.players if item.is_starting
                )
            elif latest_lineup.lineup_status in {
                LineupStatus.PREDICTED,
                LineupStatus.PARTIAL,
            }:
                predicted = tuple(
                    item for item in latest_lineup.players if item.is_starting
                )
        if latest_substitutes is not None:
            substitutes = latest_substitutes.players
        used_sources = {
            item.source_name for item in players
        } | {item.source_name for item in lineups}
        return TeamAvailabilitySnapshot(
            fixture_id=fixture_id,
            team=team,
            evaluation_timestamp=evaluation_timestamp,
            kickoff=kickoff,
            latest_lineup_status=(
                latest_lineup.lineup_status
                if latest_lineup
                else LineupStatus.NOT_AVAILABLE
            ),
            lineup_observed_at=(
                latest_lineup.observed_at if latest_lineup else None
            ),
            formation=formation,
            confirmed_starters=confirmed,
            predicted_starters=predicted,
            substitutes=substitutes,
            unavailable_players=status_players["unavailable"],
            injured_players=status_players["injured"],
            suspended_players=status_players["suspended"],
            doubtful_players=status_players["doubtful"],
            unknown_status_players=status_players["unknown"],
            lineup_evidence_status=lineup_evidence,
            injury_evidence_status=injury_evidence,
            data_freshness=freshness,
            data_completeness=completeness,
            source_count=len(used_sources),
            conflicts=tuple(conflicts),
            snapshot_timestamp=evaluation_timestamp,
        )

    def _lineup_evidence(
        self,
        evaluation: datetime,
        lineup: LineupObservation | None,
    ) -> AvailabilityEvidenceStatus:
        if lineup is None or lineup.lineup_status is LineupStatus.NOT_AVAILABLE:
            return AvailabilityEvidenceStatus.MISSING
        maximum = (
            self._freshness.confirmed_lineup_max_age
            if lineup.lineup_status is LineupStatus.CONFIRMED
            else self._freshness.predicted_lineup_max_age
        )
        if evaluation - lineup.observed_at > maximum:
            return AvailabilityEvidenceStatus.STALE
        if lineup.lineup_status in {LineupStatus.PREDICTED, LineupStatus.PARTIAL}:
            return AvailabilityEvidenceStatus.PARTIAL
        return AvailabilityEvidenceStatus.AVAILABLE

    def _injury_evidence(
        self,
        evaluation: datetime,
        players: tuple[PlayerAvailabilityObservation, ...],
        conflicting: bool,
    ) -> AvailabilityEvidenceStatus:
        if not players:
            return AvailabilityEvidenceStatus.MISSING
        if conflicting:
            return AvailabilityEvidenceStatus.PARTIAL
        for item in players:
            maximum = (
                self._freshness.suspension_max_age
                if item.reason is AvailabilityReason.SUSPENSION
                else self._freshness.injury_max_age
            )
            if evaluation - item.observed_at > maximum:
                return AvailabilityEvidenceStatus.STALE
        return AvailabilityEvidenceStatus.AVAILABLE

    def _freshness_status(
        self,
        evaluation: datetime,
        lineup: LineupObservation | None,
        players: tuple[PlayerAvailabilityObservation, ...],
    ) -> AvailabilityEvidenceStatus:
        if lineup is None and not players:
            return AvailabilityEvidenceStatus.MISSING
        stale = False
        if lineup is not None:
            maximum = (
                self._freshness.confirmed_lineup_max_age
                if lineup.lineup_status is LineupStatus.CONFIRMED
                else self._freshness.predicted_lineup_max_age
                if lineup.lineup_type is LineupType.STARTING
                else self._freshness.squad_max_age
            )
            stale = evaluation - lineup.observed_at > maximum
        for item in players:
            maximum = (
                self._freshness.suspension_max_age
                if item.reason is AvailabilityReason.SUSPENSION
                else self._freshness.injury_max_age
            )
            stale = stale or evaluation - item.observed_at > maximum
        return (
            AvailabilityEvidenceStatus.STALE
            if stale
            else AvailabilityEvidenceStatus.AVAILABLE
        )

    @staticmethod
    def _completeness(
        lineup: LineupObservation | None,
        players: tuple[PlayerAvailabilityObservation, ...],
        conflicting: bool,
    ) -> AvailabilityEvidenceStatus:
        if lineup is None and not players:
            return AvailabilityEvidenceStatus.MISSING
        if conflicting:
            return AvailabilityEvidenceStatus.PARTIAL
        if not players or lineup is None or lineup.lineup_status in {
            LineupStatus.NOT_AVAILABLE,
            LineupStatus.PARTIAL,
            LineupStatus.PREDICTED,
        }:
            return AvailabilityEvidenceStatus.PARTIAL
        return AvailabilityEvidenceStatus.AVAILABLE

    @staticmethod
    def _status_players(
        items: list[PlayerAvailabilityObservation],
    ) -> dict[str, tuple[PlayerIdentity, ...]]:
        def select(statuses: set[PlayerAvailabilityStatus]) -> tuple[PlayerIdentity, ...]:
            values = {
                item.player.identity_key: item.player
                for item in items
                if item.availability_status in statuses
            }
            return tuple(values[key] for key in sorted(values))

        return {
            "unavailable": select({
                PlayerAvailabilityStatus.UNAVAILABLE,
                PlayerAvailabilityStatus.INJURED,
                PlayerAvailabilityStatus.SUSPENDED,
                PlayerAvailabilityStatus.ILL,
                PlayerAvailabilityStatus.RESTED,
                PlayerAvailabilityStatus.NOT_SELECTED,
            }),
            "injured": select({PlayerAvailabilityStatus.INJURED}),
            "suspended": select({PlayerAvailabilityStatus.SUSPENDED}),
            "doubtful": select({PlayerAvailabilityStatus.DOUBTFUL}),
            "unknown": select({PlayerAvailabilityStatus.UNKNOWN}),
        }

    @staticmethod
    def _lineup_rank(status: LineupStatus) -> int:
        return {
            LineupStatus.NOT_AVAILABLE: 0,
            LineupStatus.PREDICTED: 1,
            LineupStatus.PARTIAL: 2,
            LineupStatus.CONFIRMED: 3,
        }[status]

    @staticmethod
    def _aware(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Snapshot timestamps must be timezone-aware.")
