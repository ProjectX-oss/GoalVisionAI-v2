from app.features.base import Feature
from app.models import TeamStrength


class DefenseFeature(Feature):

    def calculate(self, strength: TeamStrength) -> float:

        return strength.defense
