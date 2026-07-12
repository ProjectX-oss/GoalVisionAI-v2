from dataclasses import dataclass

from .feature_vector import FeatureVector
from .form_snapshot import FormSnapshot
from .team_rating import TeamRating
from .team_strength import TeamStrength


@dataclass(slots=True)
class TeamContext:

    team_id: int

    snapshot: FormSnapshot

    features: FeatureVector

    strength: TeamStrength

    rating: TeamRating
