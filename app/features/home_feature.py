from app.features.base import Feature
from app.models import TeamStrength


class HomeFeature(Feature):

    def calculate(self, strength: TeamStrength) -> float:

        return strength.home
