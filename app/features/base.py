from abc import ABC, abstractmethod

from app.models import TeamStrength


class Feature(ABC):

    @abstractmethod
    def calculate(
        self,
        strength: TeamStrength,
    ) -> float:
        ...
