"""Champion adapter: persisted artifact inference only."""

from .inference import infer
from .models import ModelRole


def infer_champion(artifact, calibration, snapshot):
    return infer(ModelRole.CHAMPION, artifact, calibration, snapshot)
