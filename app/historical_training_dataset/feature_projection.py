"""Versioned historical-only pre-match feature projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN

from .chronology import assert_source_precedes_target, match_order_key
from .models import (
    FeatureDataType,
    FeatureScalar,
    HistoricalFeatureDefinition,
    HistoricalSourceMatch,
    TrainingExampleSource,
)
from .policy import HistoricalTrainingDatasetPolicy


_FORM_METRICS = (
    ("matches_played", FeatureDataType.INTEGER, "Number of available matches in the window."),
    ("wins", FeatureDataType.INTEGER, "Wins in the window."),
    ("draws", FeatureDataType.INTEGER, "Draws in the window."),
    ("losses", FeatureDataType.INTEGER, "Losses in the window."),
    ("points_per_match", FeatureDataType.DECIMAL, "Points divided by matches played."),
    ("goals_scored_per_match", FeatureDataType.DECIMAL, "Goals scored divided by matches played."),
    ("goals_conceded_per_match", FeatureDataType.DECIMAL, "Goals conceded divided by matches played."),
    ("clean_sheet_rate", FeatureDataType.DECIMAL, "Share of matches conceding zero goals."),
    ("failed_to_score_rate", FeatureDataType.DECIMAL, "Share of matches scoring zero goals."),
    ("btts_rate", FeatureDataType.DECIMAL, "Share of matches where both teams scored."),
    ("over_1_5_rate", FeatureDataType.DECIMAL, "Share of matches with at least two total goals."),
    ("over_2_5_rate", FeatureDataType.DECIMAL, "Share of matches with at least three total goals."),
    ("over_3_5_rate", FeatureDataType.DECIMAL, "Share of matches with at least four total goals."),
)

_SPLIT_METRICS = (
    ("matches_played", FeatureDataType.INTEGER, "Prior matches in the requested venue split."),
    ("win_rate", FeatureDataType.DECIMAL, "Win rate in the venue split."),
    ("draw_rate", FeatureDataType.DECIMAL, "Draw rate in the venue split."),
    ("loss_rate", FeatureDataType.DECIMAL, "Loss rate in the venue split."),
    ("goals_scored_per_match", FeatureDataType.DECIMAL, "Split goals scored per match."),
    ("goals_conceded_per_match", FeatureDataType.DECIMAL, "Split goals conceded per match."),
)

_SEASON_METRICS = (
    ("matches_played", FeatureDataType.INTEGER, "Season-to-date matches played."),
    ("points", FeatureDataType.INTEGER, "Season-to-date points."),
    ("points_per_match", FeatureDataType.DECIMAL, "Season-to-date points per match."),
    ("goals_for", FeatureDataType.INTEGER, "Season-to-date goals for."),
    ("goals_against", FeatureDataType.INTEGER, "Season-to-date goals against."),
    ("goal_difference", FeatureDataType.INTEGER, "Season-to-date goal difference."),
)

_STATISTICS = (
    "shots", "shots_on_target", "possession", "expected_goals", "corners",
    "yellow_cards", "red_cards", "fouls", "offsides",
)


def build_feature_definitions(
    policy: HistoricalTrainingDatasetPolicy,
) -> tuple[HistoricalFeatureDefinition, ...]:
    definitions: list[HistoricalFeatureDefinition] = []

    def add(name: str, kind: FeatureDataType, semantic: str, window: str, missing: str) -> None:
        definitions.append(HistoricalFeatureDefinition(
            index=len(definitions),
            name=name,
            data_type=kind,
            semantic_definition=semantic,
            source_window=window,
            missingness_rule=missing,
            leakage_classification="PRE_MATCH_AGGREGATE_STRICTLY_BEFORE_TARGET_KICKOFF",
        ))

    for side in ("home", "away"):
        for window in policy.rolling_windows:
            for metric, kind, semantic in _FORM_METRICS:
                add(
                    f"{side}_last_{window}_{metric}", kind, semantic, f"LAST_{window}",
                    "Missing only when the prior-match denominator is zero; counts remain genuine zero.",
                )
        for metric, kind, semantic in _SPLIT_METRICS:
            add(
                f"{side}_venue_last_10_{metric}", kind, semantic, "VENUE_LAST_10",
                "Rates are missing when no prior venue-split match exists.",
            )
        for metric, kind, semantic in _SEASON_METRICS:
            add(
                f"{side}_season_{metric}", kind, semantic, "SEASON_TO_DATE",
                "Rate is missing when no earlier match exists; additive counts remain genuine zero.",
            )
        for metric, kind, semantic in _SEASON_METRICS:
            add(
                f"{side}_season_venue_{metric}", kind, f"Venue-split {semantic.lower()}", "SEASON_VENUE_TO_DATE",
                "Rate is missing when no earlier season venue match exists; counts remain genuine zero.",
            )
        add(f"{side}_days_since_previous_match", FeatureDataType.DECIMAL, "Days since the latest earlier match.", "PREVIOUS_MATCH", "Missing when no provably earlier match exists.")
        add(f"{side}_matches_previous_7_days", FeatureDataType.INTEGER, "Earlier matches inside the previous seven days.", "PREVIOUS_7_DAYS", "Never missing for an eligible chronology.")
        add(f"{side}_matches_previous_14_days", FeatureDataType.INTEGER, "Earlier matches inside the previous fourteen days.", "PREVIOUS_14_DAYS", "Never missing for an eligible chronology.")
        for statistic in _STATISTICS:
            add(
                f"{side}_last_10_average_{statistic}", FeatureDataType.DECIMAL,
                f"Average prior {statistic.replace('_', ' ')} where historically available.",
                "LAST_10_WITH_STATISTIC",
                "Missing when no earlier match in the last-ten window supplies this statistic; no imputation.",
            )
    for name, kind, semantic in (
        ("meetings_count", FeatureDataType.INTEGER, "Number of prior eligible meetings, capped at five."),
        ("home_side_wins", FeatureDataType.INTEGER, "Meetings won by the target match's home team."),
        ("draws", FeatureDataType.INTEGER, "Drawn prior meetings."),
        ("away_side_wins", FeatureDataType.INTEGER, "Meetings won by the target match's away team."),
        ("average_total_goals", FeatureDataType.DECIMAL, "Average total goals in prior meetings."),
        ("btts_rate", FeatureDataType.DECIMAL, "BTTS rate in prior meetings."),
        ("over_2_5_rate", FeatureDataType.DECIMAL, "Over-2.5 rate in prior meetings."),
    ):
        add(f"head_to_head_{name}", kind, semantic, "HEAD_TO_HEAD_LAST_5", "Rates are missing when there is no earlier meeting; count remains zero.")
    return tuple(definitions)


@dataclass(frozen=True, slots=True)
class ProjectedFeatures:
    values: tuple[FeatureScalar, ...]
    missingness_mask: tuple[bool, ...]
    completeness_score: Decimal
    provenance: tuple[tuple[str, str], ...]
    sources: tuple[TrainingExampleSource, ...]


def project_features(
    target: HistoricalSourceMatch,
    prior_matches: tuple[HistoricalSourceMatch, ...],
    policy: HistoricalTrainingDatasetPolicy,
) -> ProjectedFeatures:
    definitions = build_feature_definitions(policy)
    values: dict[str, FeatureScalar] = {}
    source_roles: dict[str, tuple[HistoricalSourceMatch, set[str], set[str]]] = {}
    target_time = _time(target.kickoff_utc)

    def mark(matches: tuple[HistoricalSourceMatch, ...], role: str, window: str) -> None:
        for match in matches:
            assert_source_precedes_target(match.historical_match_id, match.kickoff_utc, target.historical_match_id, target.kickoff_utc)
            record = source_roles.setdefault(match.historical_match_id, (match, set(), set()))
            record[1].add(role)
            record[2].add(window)

    for label, team, venue in (
        ("home", target.home_team_identity, "HOME"),
        ("away", target.away_team_identity, "AWAY"),
    ):
        team_history = tuple(match for match in prior_matches if _involves(match, team))
        for window in policy.rolling_windows:
            sample = team_history[-window:]
            mark(sample, f"{label.upper()}_RECENT_FORM", f"LAST_{window}")
            aggregate = _aggregate_team(sample, team)
            for metric, _, _ in _FORM_METRICS:
                values[f"{label}_last_{window}_{metric}"] = aggregate[metric]

        venue_history = tuple(match for match in team_history if _team_venue(match, team) == venue)[-10:]
        mark(venue_history, f"{label.upper()}_VENUE_FORM", "VENUE_LAST_10")
        split = _aggregate_team(venue_history, team)
        for metric, _, _ in _SPLIT_METRICS:
            values[f"{label}_venue_last_10_{metric}"] = split[metric]

        season_history = tuple(
            match for match in team_history
            if match.competition_identity == target.competition_identity and match.season == target.season
        )
        mark(season_history, f"{label.upper()}_SEASON", "SEASON_TO_DATE")
        season = _aggregate_team(season_history, team)
        for metric, _, _ in _SEASON_METRICS:
            values[f"{label}_season_{metric}"] = season[metric]
        season_venue = tuple(match for match in season_history if _team_venue(match, team) == venue)
        mark(season_venue, f"{label.upper()}_SEASON_VENUE", "SEASON_VENUE_TO_DATE")
        season_split = _aggregate_team(season_venue, team)
        for metric, _, _ in _SEASON_METRICS:
            values[f"{label}_season_venue_{metric}"] = season_split[metric]

        previous = team_history[-1:]
        mark(previous, f"{label.upper()}_REST", "PREVIOUS_MATCH")
        values[f"{label}_days_since_previous_match"] = (
            _q(Decimal(str((target_time - _time(previous[0].kickoff_utc)).total_seconds())) / Decimal("86400"))
            if previous else None
        )
        previous_7 = tuple(match for match in team_history if target_time - _time(match.kickoff_utc) <= timedelta(days=7))
        previous_14 = tuple(match for match in team_history if target_time - _time(match.kickoff_utc) <= timedelta(days=14))
        mark(previous_7, f"{label.upper()}_CONGESTION", "PREVIOUS_7_DAYS")
        mark(previous_14, f"{label.upper()}_CONGESTION", "PREVIOUS_14_DAYS")
        values[f"{label}_matches_previous_7_days"] = len(previous_7)
        values[f"{label}_matches_previous_14_days"] = len(previous_14)

        recent_ten = team_history[-10:]
        for statistic in _STATISTICS:
            supplied: list[Decimal] = []
            used: list[HistoricalSourceMatch] = []
            for match in recent_ten:
                stats = match.home_statistics if match.home_team_identity == team else match.away_statistics
                value = getattr(stats, statistic) if stats is not None else None
                if value is not None:
                    supplied.append(Decimal(value))
                    used.append(match)
            mark(tuple(used), f"{label.upper()}_STATISTICS", "LAST_10_WITH_STATISTIC")
            values[f"{label}_last_10_average_{statistic}"] = _average(supplied)

    h2h_all = tuple(
        match for match in prior_matches
        if {match.home_team_identity, match.away_team_identity}
        == {target.home_team_identity, target.away_team_identity}
    )[-policy.head_to_head_window:]
    mark(h2h_all, "HEAD_TO_HEAD", "HEAD_TO_HEAD_LAST_5")
    h2h = _head_to_head(h2h_all, target.home_team_identity)
    for key, value in h2h.items():
        values[f"head_to_head_{key}"] = value

    ordered = tuple(values[definition.name] for definition in definitions)
    mask = tuple(value is None for value in ordered)
    completeness = _q(Decimal(sum(not item for item in mask)) / Decimal(len(mask)))
    provenance = tuple((definition.name, definition.source_window) for definition in definitions)
    ordered_sources = sorted((entry[0] for entry in source_roles.values()), key=match_order_key)
    sources = tuple(
        TrainingExampleSource(
            source_historical_match_id=match.historical_match_id,
            source_match_fingerprint=match.match_fingerprint,
            source_kickoff=match.kickoff_utc,
            source_role="|".join(sorted(source_roles[match.historical_match_id][1])),
            deterministic_order_index=index,
            lookback_window_identity="|".join(sorted(source_roles[match.historical_match_id][2])),
        )
        for index, match in enumerate(ordered_sources)
    )
    return ProjectedFeatures(ordered, mask, completeness, provenance, sources)


def _aggregate_team(matches: tuple[HistoricalSourceMatch, ...], team: str) -> dict[str, FeatureScalar]:
    count = len(matches)
    wins = draws = losses = goals_for = goals_against = 0
    clean = failed = btts = over15 = over25 = over35 = 0
    for match in matches:
        gf, ga = _score_for(match, team)
        goals_for += gf
        goals_against += ga
        wins += int(gf > ga)
        draws += int(gf == ga)
        losses += int(gf < ga)
        clean += int(ga == 0)
        failed += int(gf == 0)
        btts += int(gf > 0 and ga > 0)
        over15 += int(gf + ga >= 2)
        over25 += int(gf + ga >= 3)
        over35 += int(gf + ga >= 4)
    rate = lambda value: _q(Decimal(value) / Decimal(count)) if count else None
    return {
        "matches_played": count, "wins": wins, "draws": draws, "losses": losses,
        "points": wins * 3 + draws,
        "points_per_match": rate(wins * 3 + draws),
        "goals_scored_per_match": rate(goals_for), "goals_conceded_per_match": rate(goals_against),
        "clean_sheet_rate": rate(clean), "failed_to_score_rate": rate(failed), "btts_rate": rate(btts),
        "over_1_5_rate": rate(over15), "over_2_5_rate": rate(over25), "over_3_5_rate": rate(over35),
        "win_rate": rate(wins), "draw_rate": rate(draws), "loss_rate": rate(losses),
        "goals_for": goals_for, "goals_against": goals_against,
        "goal_difference": goals_for - goals_against,
    }


def _head_to_head(matches: tuple[HistoricalSourceMatch, ...], target_home: str) -> dict[str, FeatureScalar]:
    count = len(matches)
    home_wins = draws = away_wins = total_goals = btts = over25 = 0
    for match in matches:
        gf, ga = _score_for(match, target_home)
        home_wins += int(gf > ga)
        draws += int(gf == ga)
        away_wins += int(gf < ga)
        total_goals += gf + ga
        btts += int(gf > 0 and ga > 0)
        over25 += int(gf + ga >= 3)
    rate = lambda value: _q(Decimal(value) / Decimal(count)) if count else None
    return {
        "meetings_count": count, "home_side_wins": home_wins, "draws": draws,
        "away_side_wins": away_wins, "average_total_goals": rate(total_goals),
        "btts_rate": rate(btts), "over_2_5_rate": rate(over25),
    }


def _score_for(match: HistoricalSourceMatch, team: str) -> tuple[int, int]:
    if match.home_team_identity == team:
        return match.full_time_home_score, match.full_time_away_score
    if match.away_team_identity == team:
        return match.full_time_away_score, match.full_time_home_score
    raise ValueError("Team is absent from source match.")


def _team_venue(match: HistoricalSourceMatch, team: str) -> str:
    return "HOME" if match.home_team_identity == team else "AWAY"


def _involves(match: HistoricalSourceMatch, team: str) -> bool:
    return team in (match.home_team_identity, match.away_team_identity)


def _average(values: list[Decimal]) -> Decimal | None:
    return _q(sum(values, Decimal(0)) / Decimal(len(values))) if values else None


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


HISTORICAL_TRAINING_FEATURES_V1 = build_feature_definitions(HistoricalTrainingDatasetPolicy())
