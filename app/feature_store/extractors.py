from decimal import Decimal

from app.match_data_snapshot import MatchDataSnapshotVersion

from .definitions import FEATURE_DEFINITIONS
from .models import DataQualitySummary, FeatureValue
from .policy import FeatureStorePolicy


_STAGE_ENCODING = {
    "LEAGUE": 1,
    "REGULAR_SEASON": 1,
    "GROUP": 2,
    "GROUP_STAGE": 2,
    "ROUND_OF_32": 3,
    "ROUND_OF_16": 4,
    "QUARTER_FINAL": 5,
    "SEMI_FINAL": 6,
    "FINAL": 7,
    "PLAYOFF": 8,
}


class OfficialPrematchFeatureExtractor:
    """Pure Decimal feature extraction from one immutable snapshot."""

    def __init__(self, policy: FeatureStorePolicy) -> None:
        self.policy = policy

    def extract(
        self,
        snapshot: MatchDataSnapshotVersion,
    ) -> tuple[
        tuple[FeatureValue, ...],
        tuple[tuple[str, bool], ...],
        DataQualitySummary,
    ]:
        command = snapshot.prepared.command
        home = command.home_recent_form
        away = command.away_recent_form
        hv = command.home_venue_split
        av = command.away_venue_split
        hs = command.home_season_aggregate
        aws = command.away_season_aggregate
        ha = command.home_availability
        aa = command.away_availability
        context = command.context
        h2h = command.head_to_head
        values: dict[str, Decimal | int | bool | None] = {}

        def ratio(numerator: int | Decimal | None, denominator: int | Decimal | None) -> Decimal | None:
            if numerator is None or denominator is None or Decimal(denominator) == 0:
                return None
            return Decimal(numerator) / Decimal(denominator)

        def points(record):
            return None if record is None else ratio(3 * record.wins + record.draws, record.match_count)

        values["home_recent_points_per_match"] = points(home)
        values["away_recent_points_per_match"] = points(away)
        for side, record in (("home", home), ("away", away)):
            for feature, field in (
                ("goals_scored", "goals_scored"),
                ("goals_conceded", "goals_conceded"),
                ("xg_for", "expected_goals_for"),
                ("xg_against", "expected_goals_against"),
            ):
                values[f"{side}_recent_{feature}_per_match"] = (
                    None if record is None else ratio(getattr(record, field), record.match_count)
                )
            values[f"{side}_recent_clean_sheet_rate"] = None if record is None else ratio(record.clean_sheets, record.match_count)
            values[f"{side}_recent_failed_to_score_rate"] = None if record is None else ratio(record.failed_to_score, record.match_count)

        values["home_team_home_points_per_match"] = points(hv)
        values["away_team_away_points_per_match"] = points(av)
        for name, record, field in (
            ("home_goals_scored_at_home_per_match", hv, "goals_scored"),
            ("away_goals_scored_away_per_match", av, "goals_scored"),
            ("home_goals_conceded_at_home_per_match", hv, "goals_conceded"),
            ("away_goals_conceded_away_per_match", av, "goals_conceded"),
            ("home_venue_xg_for_per_match", hv, "expected_goals_for"),
            ("away_venue_xg_for_per_match", av, "expected_goals_for"),
            ("home_venue_xg_against_per_match", hv, "expected_goals_against"),
            ("away_venue_xg_against_per_match", av, "expected_goals_against"),
        ):
            values[name] = None if record is None else ratio(getattr(record, field), record.match_count)

        for side, record in (("home", hs), ("away", aws)):
            values[f"{side}_season_points_per_match"] = None if record is None else ratio(record.points, record.matches_played)
            values[f"{side}_season_goal_difference_per_match"] = None if record is None else ratio(record.goals_scored - record.goals_conceded, record.matches_played)
            values[f"{side}_season_xg_difference_per_match"] = (
                None if record is None or record.expected_goals_for is None or record.expected_goals_against is None
                else ratio(record.expected_goals_for - record.expected_goals_against, record.matches_played)
            )
            values[f"{side}_season_matches_played"] = None if record is None else record.matches_played
        if hs is None or aws is None or hs.league_position is None or aws.league_position is None:
            values["normalized_league_position_difference"] = None
        else:
            values["normalized_league_position_difference"] = ratio(
                aws.league_position - hs.league_position,
                max(hs.league_position, aws.league_position),
            )

        def difference(left: str, right: str, reverse: bool = False) -> Decimal | None:
            first, second = values[left], values[right]
            if first is None or second is None:
                return None
            return Decimal(second) - Decimal(first) if reverse else Decimal(first) - Decimal(second)

        values["recent_form_difference"] = difference("home_recent_points_per_match", "away_recent_points_per_match")
        values["attacking_strength_difference"] = difference("home_recent_goals_scored_per_match", "away_recent_goals_scored_per_match")
        values["defensive_strength_difference"] = difference("home_recent_goals_conceded_per_match", "away_recent_goals_conceded_per_match", True)
        home_xg_net = _subtract(values["home_recent_xg_for_per_match"], values["home_recent_xg_against_per_match"])
        away_xg_net = _subtract(values["away_recent_xg_for_per_match"], values["away_recent_xg_against_per_match"])
        values["recent_xg_difference"] = _subtract(home_xg_net, away_xg_net)
        values["venue_strength_difference"] = difference("home_team_home_points_per_match", "away_team_away_points_per_match")
        values["rest_days_difference"] = _context_difference(context, "home_rest_days", "away_rest_days")
        values["missing_player_difference"] = _availability_difference(ha, aa, "missing_key_players_count", reverse=True)
        values["fixture_congestion_difference"] = _context_difference(context, "home_fixture_congestion_count", "away_fixture_congestion_count", reverse=True)

        for name, left, right, mean in (
            ("combined_recent_goals_per_match", "home_recent_goals_scored_per_match", "away_recent_goals_scored_per_match", False),
            ("combined_recent_xg_per_match", "home_recent_xg_for_per_match", "away_recent_xg_for_per_match", False),
            ("combined_goal_concession_rate", "home_recent_goals_conceded_per_match", "away_recent_goals_conceded_per_match", False),
            ("combined_clean_sheet_rate", "home_recent_clean_sheet_rate", "away_recent_clean_sheet_rate", True),
            ("combined_failed_to_score_rate", "home_recent_failed_to_score_rate", "away_recent_failed_to_score_rate", True),
        ):
            values[name] = _combine(values[left], values[right], mean)
        values["head_to_head_btts_rate"] = None if h2h is None else ratio(h2h.both_teams_to_score_count, h2h.match_count)
        values["head_to_head_over_2_5_rate"] = None if h2h is None else ratio(h2h.over_2_5_count, h2h.match_count)

        for side, record in (("home", ha), ("away", aa)):
            values[f"{side}_confirmed_lineup_indicator"] = None if record is None else record.confirmed_lineup
            values[f"{side}_probable_lineup_indicator"] = None if record is None else record.probable_lineup
            for field in ("injuries_count", "suspensions_count", "missing_key_players_count"):
                values[f"{side}_{field}"] = None if record is None else getattr(record, field)
            status = None if record is None else record.goalkeeper_availability_status
            values[f"{side}_goalkeeper_available_indicator"] = None if status is None else status == "AVAILABLE"

        values["neutral_venue_indicator"] = command.neutral_venue_indicator
        values["derby_indicator"] = None if context is None else context.derby_indicator
        for side in ("home", "away"):
            values[f"{side}_fixture_congestion_count"] = None if context is None else getattr(context, f"{side}_fixture_congestion_count")
            values[f"{side}_rest_days"] = None if context is None else getattr(context, f"{side}_rest_days")
        stage = None if context is None or context.competition_stage is None else context.competition_stage.upper().replace(" ", "_").replace("-", "_")
        values["competition_stage_encoding"] = None if stage is None else _STAGE_ENCODING.get(stage)

        groups = (
            ("home_recent_form", home is not None), ("away_recent_form", away is not None),
            ("home_venue_split", hv is not None), ("away_venue_split", av is not None),
            ("home_season", hs is not None), ("away_season", aws is not None),
            ("home_availability", ha is not None), ("away_availability", aa is not None),
            ("head_to_head", h2h is not None), ("context", context is not None),
        )
        completeness = Decimal(sum(1 for _, present in groups if present)) / Decimal(len(groups))
        values["snapshot_completeness_score"] = completeness
        for name, record, field in (
            ("home_recent_form_sample_size", home, "match_count"),
            ("away_recent_form_sample_size", away, "match_count"),
            ("home_venue_sample_size", hv, "match_count"),
            ("away_venue_sample_size", av, "match_count"),
            ("home_season_sample_size", hs, "matches_played"),
            ("away_season_sample_size", aws, "matches_played"),
        ):
            values[name] = 0 if record is None else getattr(record, field)
        values["xg_availability_indicator"] = all(
            value is not None for value in (
                values["home_recent_xg_for_per_match"], values["home_recent_xg_against_per_match"],
                values["away_recent_xg_for_per_match"], values["away_recent_xg_against_per_match"],
            )
        )
        values["lineup_availability_indicator"] = ha is not None and aa is not None and ha.confirmed_lineup is not None and aa.confirmed_lineup is not None
        values["injury_data_availability_indicator"] = ha is not None and aa is not None and ha.injuries_count is not None and aa.injuries_count is not None
        values["head_to_head_availability_indicator"] = h2h is not None and h2h.match_count > 0

        ordered = tuple(
            FeatureValue(definition.name, self._quantize(values[definition.name]))
            for definition in FEATURE_DEFINITIONS
        )
        missingness = tuple((item.name, item.value is None) for item in ordered)
        missing_count = sum(1 for _, missing in missingness if missing)
        quality = DataQualitySummary(
            self._quantize(completeness), len(ordered) - missing_count,
            missing_count, len(ordered), groups,
        )
        return ordered, missingness, quality

    def _quantize(self, value):
        if isinstance(value, Decimal):
            return value.quantize(self.policy.decimal_quantum, rounding=self.policy.rounding)
        return value


def _subtract(left, right):
    return None if left is None or right is None else Decimal(left) - Decimal(right)


def _combine(left, right, mean: bool):
    if left is None or right is None:
        return None
    result = Decimal(left) + Decimal(right)
    return result / Decimal(2) if mean else result


def _context_difference(context, home_field: str, away_field: str, reverse: bool = False):
    if context is None:
        return None
    home, away = getattr(context, home_field), getattr(context, away_field)
    if home is None or away is None:
        return None
    return Decimal(away - home) if reverse else Decimal(home - away)


def _availability_difference(home, away, field: str, reverse: bool = False):
    if home is None or away is None:
        return None
    left, right = getattr(home, field), getattr(away, field)
    if left is None or right is None:
        return None
    return Decimal(right - left) if reverse else Decimal(left - right)
