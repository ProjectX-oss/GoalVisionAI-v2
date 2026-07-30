"""Leakage-safe projection through the canonical live 78-feature extractor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.feature_store import (
    DEFAULT_FEATURE_STORE_POLICY,
    OfficialPrematchFeatureExtractor,
)
from app.match_data_snapshot import (
    FormRecord,
    HeadToHeadRecord,
    MatchContextRecord,
    SeasonAggregateRecord,
    VenueSplitRecord,
)
from app.model_input_builder import LIVE_MODEL_INPUT_CONTRACT

from .feature_projection import ProjectedFeatures, project_features
from .models import HistoricalSourceMatch
from .policy import HistoricalTrainingDatasetPolicy


LIVE_FEATURE_DATASET_POLICY_VERSION = "historical_live_model_input_dataset_policy_v1"


@dataclass(frozen=True, slots=True)
class FeatureCoverage:
    feature_name: str
    classification: str
    explanation: str


def live_feature_coverage() -> tuple[FeatureCoverage, ...]:
    """Return deterministic coverage in canonical schema order."""
    unavailable_prefixes = (
        "home_confirmed_lineup",
        "away_confirmed_lineup",
        "home_probable_lineup",
        "away_probable_lineup",
        "home_injuries",
        "away_injuries",
        "home_suspensions",
        "away_suspensions",
        "home_missing_key_players",
        "away_missing_key_players",
        "home_goalkeeper",
        "away_goalkeeper",
    )
    unavailable_exact = {
        "normalized_league_position_difference",
        "missing_player_difference",
        "derby_indicator",
        "competition_stage_encoding",
    }
    direct = {
        "neutral_venue_indicator",
        "snapshot_completeness_score",
        "home_recent_form_sample_size",
        "away_recent_form_sample_size",
        "home_venue_sample_size",
        "away_venue_sample_size",
        "home_season_sample_size",
        "away_season_sample_size",
        "xg_availability_indicator",
        "lineup_availability_indicator",
        "injury_data_availability_indicator",
        "head_to_head_availability_indicator",
    }
    rows = []
    for name in LIVE_MODEL_INPUT_CONTRACT.ordered_feature_names:
        if name in unavailable_exact or name.startswith(unavailable_prefixes):
            classification = "OPTIONAL_LEGITIMATELY_MISSING"
            explanation = "The historical import has no pre-kickoff source for this optional field."
        elif name in direct:
            classification = "DIRECTLY_DERIVED"
            explanation = "Derived deterministically from source availability or fixture identity."
        else:
            classification = "HISTORICALLY_AGGREGATED"
            explanation = "Calculated only from source matches strictly before target kickoff."
        rows.append(FeatureCoverage(name, classification, explanation))
    return tuple(rows)


def project_live_features(
    target: HistoricalSourceMatch,
    prior_matches: tuple[HistoricalSourceMatch, ...],
    policy: HistoricalTrainingDatasetPolicy,
) -> ProjectedFeatures:
    """Build the exact live vector without a duplicated feature list."""
    if policy.neutral_venue_indicator is None:
        raise ValueError(
            "Live-contract historical projection requires explicit neutral-venue provenance."
        )
    # Reuse the established chronology/source collector. Its vector is discarded.
    legacy = project_features(target, prior_matches, policy)
    home_history = tuple(
        item for item in prior_matches if _involves(item, target.home_team_identity)
    )
    away_history = tuple(
        item for item in prior_matches if _involves(item, target.away_team_identity)
    )
    command = SimpleNamespace(
        home_recent_form=_form(home_history[-10:], target.home_team_identity),
        away_recent_form=_form(away_history[-10:], target.away_team_identity),
        home_venue_split=_venue(
            tuple(
                item
                for item in home_history
                if item.home_team_identity == target.home_team_identity
            )[-10:],
            target.home_team_identity,
        ),
        away_venue_split=_venue(
            tuple(
                item
                for item in away_history
                if item.away_team_identity == target.away_team_identity
            )[-10:],
            target.away_team_identity,
        ),
        home_season_aggregate=_season(target, home_history, target.home_team_identity),
        away_season_aggregate=_season(target, away_history, target.away_team_identity),
        head_to_head=_head_to_head(target, prior_matches),
        home_availability=None,
        away_availability=None,
        context=MatchContextRecord(
            home_rest_days=_rest_days(target, home_history),
            away_rest_days=_rest_days(target, away_history),
            home_fixture_congestion_count=_congestion(target, home_history),
            away_fixture_congestion_count=_congestion(target, away_history),
        ),
        neutral_venue_indicator=policy.neutral_venue_indicator,
    )
    values, missingness, quality = OfficialPrematchFeatureExtractor(
        DEFAULT_FEATURE_STORE_POLICY
    ).extract(SimpleNamespace(prepared=SimpleNamespace(command=command)))
    names = tuple(item.name for item in values)
    if names != LIVE_MODEL_INPUT_CONTRACT.ordered_feature_names:
        raise ValueError("Canonical live feature order changed during historical projection.")
    vector = tuple(item.value for item in values)
    mask = tuple(item[1] for item in missingness)
    for required in LIVE_MODEL_INPUT_CONTRACT.required_feature_names:
        index = names.index(required)
        if mask[index]:
            raise ValueError(f"Required live feature is unavailable: {required}")
    provenance = tuple(
        (
            item.name,
            (
                "HISTORICAL_SOURCE_STRICTLY_BEFORE_KICKOFF"
                if not missing
                else "OPTIONAL_SOURCE_UNAVAILABLE"
            ),
        )
        for item, (_, missing) in zip(values, missingness, strict=True)
    )
    return ProjectedFeatures(
        vector,
        mask,
        (
            Decimal(sum(not item for item in mask))
            / Decimal(LIVE_MODEL_INPUT_CONTRACT.feature_count)
        ).quantize(DEFAULT_FEATURE_STORE_POLICY.decimal_quantum),
        provenance,
        legacy.sources,
    )


def _aggregate(matches, team):
    wins = draws = losses = goals_for = goals_against = clean = failed = 0
    xg_for = Decimal(0)
    xg_against = Decimal(0)
    xg_complete = bool(matches)
    for match in matches:
        gf, ga = _score(match, team)
        wins += int(gf > ga)
        draws += int(gf == ga)
        losses += int(gf < ga)
        goals_for += gf
        goals_against += ga
        clean += int(ga == 0)
        failed += int(gf == 0)
        own = match.home_statistics if match.home_team_identity == team else match.away_statistics
        other = match.away_statistics if match.home_team_identity == team else match.home_statistics
        if own is None or other is None or own.expected_goals is None or other.expected_goals is None:
            xg_complete = False
        else:
            xg_for += own.expected_goals
            xg_against += other.expected_goals
    return {
        "count": len(matches),
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "clean": clean,
        "failed": failed,
        "xg_for": xg_for if xg_complete else None,
        "xg_against": xg_against if xg_complete else None,
    }


def _form(matches, team):
    value = _aggregate(matches, team)
    return FormRecord(
        value["count"], value["wins"], value["draws"], value["losses"],
        value["goals_for"], value["goals_against"], value["clean"], value["failed"],
        value["xg_for"], value["xg_against"],
    )


def _venue(matches, team):
    value = _aggregate(matches, team)
    return VenueSplitRecord(
        value["count"], value["wins"], value["draws"], value["losses"],
        value["goals_for"], value["goals_against"], value["clean"], value["failed"],
        value["xg_for"], value["xg_against"],
    )


def _season(target, history, team):
    selected = tuple(
        item
        for item in history
        if item.competition_identity == target.competition_identity
        and item.season == target.season
    )
    value = _aggregate(selected, team)
    return SeasonAggregateRecord(
        matches_played=value["count"],
        points=value["wins"] * 3 + value["draws"],
        goals_scored=value["goals_for"],
        goals_conceded=value["goals_against"],
        expected_goals_for=value["xg_for"],
        expected_goals_against=value["xg_against"],
    )


def _head_to_head(target, prior):
    selected = tuple(
        item
        for item in prior
        if {item.home_team_identity, item.away_team_identity}
        == {target.home_team_identity, target.away_team_identity}
    )[-5:]
    if not selected:
        return None
    home_wins = draws = away_wins = total = btts = over = 0
    for item in selected:
        home, away = _score(item, target.home_team_identity)
        home_wins += int(home > away)
        draws += int(home == away)
        away_wins += int(home < away)
        total += home + away
        btts += int(home > 0 and away > 0)
        over += int(home + away >= 3)
    return HeadToHeadRecord(
        len(selected), home_wins, draws, away_wins, total, btts, over,
        datetime.fromisoformat(selected[-1].kickoff_utc.replace("Z", "+00:00")),
    )


def _rest_days(target, history):
    if not history:
        return None
    target_time = datetime.fromisoformat(target.kickoff_utc.replace("Z", "+00:00"))
    previous = datetime.fromisoformat(history[-1].kickoff_utc.replace("Z", "+00:00"))
    return int((target_time - previous).total_seconds() // 86400)


def _congestion(target, history):
    target_time = datetime.fromisoformat(target.kickoff_utc.replace("Z", "+00:00"))
    return sum(
        target_time - datetime.fromisoformat(item.kickoff_utc.replace("Z", "+00:00"))
        <= timedelta(days=7)
        for item in history
    )


def _score(match, team):
    if match.home_team_identity == team:
        return match.full_time_home_score, match.full_time_away_score
    return match.full_time_away_score, match.full_time_home_score


def _involves(match, team):
    return team in (match.home_team_identity, match.away_team_identity)
