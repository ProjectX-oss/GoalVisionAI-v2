from decimal import Decimal

from .models import FeatureDefinition, FeatureValueType


SCHEMA_NAME = "official_prematch_features"
SCHEMA_VERSION = "v1"
SCHEMA_IDENTIFIER = "official_prematch_features_v1"


def _d(
    name: str,
    description: str,
    sources: tuple[str, ...],
    formula: str,
    missing: str = "Missing when any required source is absent or its denominator is zero.",
    valid: tuple[Decimal | None, Decimal | None] | None = None,
    value_type: FeatureValueType = FeatureValueType.DECIMAL,
) -> FeatureDefinition:
    return FeatureDefinition(name, value_type, description, sources, formula, missing, valid, SCHEMA_IDENTIFIER)


RATE = (Decimal("0"), Decimal("1"))
NONNEGATIVE = (Decimal("0"), None)
SIGNED = (None, None)


FEATURE_DEFINITIONS = (
    _d("home_recent_points_per_match", "Home team recent points per match.", ("home_recent_form.wins", "home_recent_form.draws", "home_recent_form.match_count"), "(3*wins + draws) / match_count", valid=(Decimal(0), Decimal(3))),
    _d("away_recent_points_per_match", "Away team recent points per match.", ("away_recent_form.wins", "away_recent_form.draws", "away_recent_form.match_count"), "(3*wins + draws) / match_count", valid=(Decimal(0), Decimal(3))),
    *tuple(_d(f"{side}_recent_{metric}_per_match", f"{side.title()} recent {metric.replace('_', ' ')} per match.", (f"{side}_recent_form.{source}", f"{side}_recent_form.match_count"), f"{source} / match_count", valid=NONNEGATIVE) for side in ("home", "away") for metric, source in (("goals_scored", "goals_scored"), ("goals_conceded", "goals_conceded"), ("xg_for", "expected_goals_for"), ("xg_against", "expected_goals_against"))),
    *tuple(_d(f"{side}_recent_{metric}_rate", f"{side.title()} recent {metric.replace('_', ' ')} rate.", (f"{side}_recent_form.{source}", f"{side}_recent_form.match_count"), f"{source} / match_count", valid=RATE) for side in ("home", "away") for metric, source in (("clean_sheet", "clean_sheets"), ("failed_to_score", "failed_to_score"))),
    _d("home_team_home_points_per_match", "Home team points per home match.", ("home_venue_split.wins", "home_venue_split.draws", "home_venue_split.match_count"), "(3*wins + draws) / match_count", valid=(Decimal(0), Decimal(3))),
    _d("away_team_away_points_per_match", "Away team points per away match.", ("away_venue_split.wins", "away_venue_split.draws", "away_venue_split.match_count"), "(3*wins + draws) / match_count", valid=(Decimal(0), Decimal(3))),
    *tuple(_d(name, description, sources, formula, valid=NONNEGATIVE) for name, description, sources, formula in (
        ("home_goals_scored_at_home_per_match", "Home scoring at home.", ("home_venue_split.goals_scored", "home_venue_split.match_count"), "goals_scored / match_count"),
        ("away_goals_scored_away_per_match", "Away scoring away.", ("away_venue_split.goals_scored", "away_venue_split.match_count"), "goals_scored / match_count"),
        ("home_goals_conceded_at_home_per_match", "Home concessions at home.", ("home_venue_split.goals_conceded", "home_venue_split.match_count"), "goals_conceded / match_count"),
        ("away_goals_conceded_away_per_match", "Away concessions away.", ("away_venue_split.goals_conceded", "away_venue_split.match_count"), "goals_conceded / match_count"),
        ("home_venue_xg_for_per_match", "Home venue xG for.", ("home_venue_split.expected_goals_for", "home_venue_split.match_count"), "xG for / match_count"),
        ("away_venue_xg_for_per_match", "Away venue xG for.", ("away_venue_split.expected_goals_for", "away_venue_split.match_count"), "xG for / match_count"),
        ("home_venue_xg_against_per_match", "Home venue xG against.", ("home_venue_split.expected_goals_against", "home_venue_split.match_count"), "xG against / match_count"),
        ("away_venue_xg_against_per_match", "Away venue xG against.", ("away_venue_split.expected_goals_against", "away_venue_split.match_count"), "xG against / match_count"),
    )),
    *tuple(_d(f"{side}_season_{metric}", f"{side.title()} season {metric.replace('_', ' ')}.", sources, formula, valid=valid) for side in ("home", "away") for metric, sources, formula, valid in (
        ("points_per_match", ("season.points", "season.matches_played"), "points / matches_played", (Decimal(0), Decimal(3))),
        ("goal_difference_per_match", ("season.goals_scored", "season.goals_conceded", "season.matches_played"), "(goals_scored - goals_conceded) / matches_played", SIGNED),
        ("xg_difference_per_match", ("season.expected_goals_for", "season.expected_goals_against", "season.matches_played"), "(xG for - xG against) / matches_played", SIGNED),
    )),
    _d("normalized_league_position_difference", "Positive means the home team has the stronger supplied position.", ("home_season_aggregate.league_position", "away_season_aggregate.league_position"), "(away_position - home_position) / max(position)", valid=(Decimal(-1), Decimal(1))),
    *tuple(_d(f"{side}_season_matches_played", f"{side.title()} season sample size.", (f"{side}_season_aggregate.matches_played",), "matches_played", "Missing when season aggregate is absent.", NONNEGATIVE, FeatureValueType.INTEGER) for side in ("home", "away")),
    *tuple(_d(name, description, sources, formula, valid=SIGNED) for name, description, sources, formula in (
        ("recent_form_difference", "Home minus away recent points rate.", ("home_recent_points_per_match", "away_recent_points_per_match"), "home - away"),
        ("attacking_strength_difference", "Home minus away recent scoring rate.", ("home_recent_goals_scored_per_match", "away_recent_goals_scored_per_match"), "home - away"),
        ("defensive_strength_difference", "Away minus home recent concession rate; positive favors home.", ("home_recent_goals_conceded_per_match", "away_recent_goals_conceded_per_match"), "away - home"),
        ("recent_xg_difference", "Home minus away recent net xG.", ("recent xG fields",), "(home xGF-home xGA) - (away xGF-away xGA)"),
        ("venue_strength_difference", "Home-at-home minus away-away points rate.", ("home_team_home_points_per_match", "away_team_away_points_per_match"), "home - away"),
        ("rest_days_difference", "Home minus away rest days.", ("context.home_rest_days", "context.away_rest_days"), "home - away"),
        ("missing_player_difference", "Away minus home key absences; positive favors home.", ("availability.missing_key_players_count",), "away - home"),
        ("fixture_congestion_difference", "Away minus home congestion; positive favors home.", ("context fixture congestion",), "away - home"),
    )),
    *tuple(_d(name, description, sources, formula, valid=valid) for name, description, sources, formula, valid in (
        ("combined_recent_goals_per_match", "Combined recent scoring rate.", ("recent goals scored rates",), "home + away", NONNEGATIVE),
        ("combined_recent_xg_per_match", "Combined recent xG-for rate.", ("recent xG-for rates",), "home + away", NONNEGATIVE),
        ("combined_goal_concession_rate", "Combined recent concession rate.", ("recent goals conceded rates",), "home + away", NONNEGATIVE),
        ("combined_clean_sheet_rate", "Mean recent clean-sheet rate.", ("recent clean-sheet rates",), "(home + away) / 2", RATE),
        ("combined_failed_to_score_rate", "Mean recent failed-to-score rate.", ("recent failed-to-score rates",), "(home + away) / 2", RATE),
        ("head_to_head_btts_rate", "Historical supplied BTTS rate.", ("head_to_head.both_teams_to_score_count", "head_to_head.match_count"), "count / match_count", RATE),
        ("head_to_head_over_2_5_rate", "Historical supplied over-2.5 rate.", ("head_to_head.over_2_5_count", "head_to_head.match_count"), "count / match_count", RATE),
    )),
    *tuple(_d(f"{side}_{name}", f"{side.title()} {description}", (f"{side}_availability.{source}",), source, "Missing when availability facts are absent.", valid, value_type) for side in ("home", "away") for name, description, source, valid, value_type in (
        ("confirmed_lineup_indicator", "confirmed lineup indicator.", "confirmed_lineup", RATE, FeatureValueType.BOOLEAN),
        ("probable_lineup_indicator", "probable lineup indicator.", "probable_lineup", RATE, FeatureValueType.BOOLEAN),
        ("injuries_count", "injury count.", "injuries_count", NONNEGATIVE, FeatureValueType.INTEGER),
        ("suspensions_count", "suspension count.", "suspensions_count", NONNEGATIVE, FeatureValueType.INTEGER),
        ("missing_key_players_count", "missing key-player count.", "missing_key_players_count", NONNEGATIVE, FeatureValueType.INTEGER),
        ("goalkeeper_available_indicator", "goalkeeper availability indicator.", "goalkeeper_availability_status", RATE, FeatureValueType.BOOLEAN),
    )),
    _d("neutral_venue_indicator", "Neutral venue flag.", ("neutral_venue_indicator",), "boolean", "Never missing.", RATE, FeatureValueType.BOOLEAN),
    _d("derby_indicator", "Supplied derby flag.", ("context.derby_indicator",), "boolean", "Missing when not supplied.", RATE, FeatureValueType.BOOLEAN),
    *tuple(_d(f"{side}_{name}", f"{side.title()} {description}", (f"context.{side}_{source}",), source, "Missing when context or field is absent.", NONNEGATIVE, FeatureValueType.INTEGER) for side in ("home", "away") for name, description, source in (("fixture_congestion_count", "fixture congestion count.", "fixture_congestion_count"), ("rest_days", "rest days.", "rest_days"))),
    _d("competition_stage_encoding", "Controlled pre-match competition-stage code.", ("context.competition_stage",), "controlled vocabulary integer", "Missing when stage is absent or outside the controlled vocabulary.", NONNEGATIVE, FeatureValueType.INTEGER),
    _d("snapshot_completeness_score", "Share of v1 source groups supplied.", ("snapshot optional groups",), "available source groups / total source groups", "Never missing.", RATE),
    *tuple(_d(name, description, sources, formula, "Never missing; zero is a genuine supplied sample size or absent group.", NONNEGATIVE, FeatureValueType.INTEGER) for name, description, sources, formula in (
        ("home_recent_form_sample_size", "Home recent-form sample size.", ("home_recent_form.match_count",), "match_count or 0 when group absent"),
        ("away_recent_form_sample_size", "Away recent-form sample size.", ("away_recent_form.match_count",), "match_count or 0 when group absent"),
        ("home_venue_sample_size", "Home venue sample size.", ("home_venue_split.match_count",), "match_count or 0 when group absent"),
        ("away_venue_sample_size", "Away venue sample size.", ("away_venue_split.match_count",), "match_count or 0 when group absent"),
        ("home_season_sample_size", "Home season sample size.", ("home_season_aggregate.matches_played",), "matches_played or 0 when group absent"),
        ("away_season_sample_size", "Away season sample size.", ("away_season_aggregate.matches_played",), "matches_played or 0 when group absent"),
    )),
    *tuple(_d(name, description, sources, "1 when source facts are supplied, else 0", "Never missing.", RATE, FeatureValueType.BOOLEAN) for name, description, sources in (
        ("xg_availability_indicator", "Both teams have recent xG for and against.", ("recent xG fields",)),
        ("lineup_availability_indicator", "Both teams have a supplied lineup status.", ("availability lineup fields",)),
        ("injury_data_availability_indicator", "Both teams have supplied injury counts.", ("availability injury fields",)),
        ("head_to_head_availability_indicator", "A head-to-head sample is supplied.", ("head_to_head",)),
    )),
)


FEATURE_DEFINITION_BY_NAME = {definition.name: definition for definition in FEATURE_DEFINITIONS}

if len(FEATURE_DEFINITION_BY_NAME) != len(FEATURE_DEFINITIONS):
    raise RuntimeError("Feature definitions contain duplicate names.")
