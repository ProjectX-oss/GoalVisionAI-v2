from app.features.base import Feature
from app.models import TeamStrength


class AwayFeature(Feature):

    def calculate(self, strength: TeamStrength) -> float:

        return strength.away
