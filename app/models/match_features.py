from dataclasses import dataclass

from .feature_vector import FeatureVector


@dataclass(slots=True)
class MatchFeatures:

    home: FeatureVector

    away: FeatureVector

    standings_difference: float

    goal_difference: float

    form_difference: float

    momentum_difference: float

    home_advantage: float
