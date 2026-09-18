"""Versioned safe features derived exclusively from each frozen opportunity."""
from __future__ import annotations
from .contracts import number

FEATURE_SCHEMA = 'LAB_FROZEN_FEATURES_V1'
BASE_FEATURES = ('prior_probability','implied_probability','uncertainty','family_count')
CONTEXT_FEATURES = ('signal_cmi_probability','signal_pi_probability','signal_api_probability','home_goal_rate','away_goal_rate','recent_form','goals_scored','goals_conceded','home_form','away_form','strength',
                    'rest_days','congestion','lineup_strength','injury_impact','xg','neutral_venue','knockout')
LIVE_FEATURES = ('minute','time_remaining','score_difference','total_goals','red_card_difference',
                 'shots','shots_on_target','possession','corners','dangerous_attacks','live_xg','substitutions')
SAFE_FEATURES = frozenset((*BASE_FEATURES,*CONTEXT_FEATURES,*LIVE_FEATURES))


def features(row: dict) -> dict[str, float | None]:
    """Missing optional context stays None; fitted preprocessing adds missing indicators."""
    result = {k: None for k in SAFE_FEATURES}
    result.update(prior_probability=number(row.get('frozen_features',{}).get('baseline_probability',row['frozen_model_probability']),low=0,high=1),
                  implied_probability=number(row['implied_probability'],low=0,high=1),
                  uncertainty=number(row['uncertainty']) if row.get('uncertainty') is not None else None,
                  family_count=number(row.get('evidence_family_count',0)))
    for key,value in row.get('frozen_features',{}).items():
        if key in SAFE_FEATURES and key not in BASE_FEATURES and value is not None:
            result[key] = number(value,low=-1000,high=1000)
    if row['stream'] == 'LIVE':
        result.update(minute=number(row['live_minute']),time_remaining=max(0,90-row['live_minute']),
                      score_difference=row['live_score_home']-row['live_score_away'],
                      total_goals=row['live_score_home']+row['live_score_away'])
    else:
        for key in LIVE_FEATURES:
            result[key] = None
    return result


def captured_features(prediction: dict) -> dict:
    """Project only explicit pre-outcome values, preserving provenance in the source record."""
    result = dict(prediction.get('adaptive_features', {}))
    if prediction.get('baseline_probability') is not None:
        result['baseline_probability'] = number(prediction['baseline_probability'], low=0, high=1)
    names = {'CURRENT_MATCH_INTELLIGENCE': 'signal_cmi_probability',
             'PI_RATINGS': 'signal_pi_probability',
             'API_FOOTBALL_PREDICTION': 'signal_api_probability'}
    for name, key in names.items():
        matches = [s for s in prediction.get('signals', []) if s.get('name') == name
                   and s.get('market') == prediction.get('market') and s.get('provenance')
                   and s.get('probability') is not None]
        if len(matches) == 1:
            result.setdefault(key, number(matches[0]['probability'], low=0, high=1))
    return result
