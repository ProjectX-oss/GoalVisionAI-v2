from app.features.base import Feature
from app.models import TeamStrength


class FormFeature(Feature):

    def calculate(self, strength: TeamStrength) -> float:

        return strength.form
