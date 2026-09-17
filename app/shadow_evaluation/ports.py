"""Dependency-injected source and persistence boundaries."""

from typing import Protocol


class ShadowInputSource(Protocol):
    def load_model_input(self, model_input_vector_id: str): ...
    def load_odds_snapshot_set(self, odds_snapshot_set_id: str): ...


class ShadowRepository(Protocol):
    def append_shadow_evaluation(self, execution): ...
    def find_by_request_id(self, request_id: str): ...
    def load_shadow_execution(self, execution_id: str): ...
    def append_shadow_settlement(self, settlement, metrics, aggregate_snapshots): ...


class StaticShadowInputSource:
    """Explicit in-memory loader useful for controlled Lab invocations."""

    def __init__(self, inputs=(), odds_sets=()) -> None:
        self._inputs = {item.model_input_vector_id: item for item in inputs}
        self._odds = {item.odds_snapshot_set_id: item for item in odds_sets}

    def load_model_input(self, model_input_vector_id):
        return self._inputs.get(model_input_vector_id)

    def load_odds_snapshot_set(self, odds_snapshot_set_id):
        return self._odds.get(odds_snapshot_set_id)
