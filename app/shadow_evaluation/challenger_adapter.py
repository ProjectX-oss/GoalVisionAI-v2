"""Challenger adapter: persisted artifact inference only."""

from .inference import infer
from .models import ModelRole


def infer_challenger(artifact, calibration, snapshot):
    return infer(ModelRole.CHALLENGER, artifact, calibration, snapshot)
