"""Immutable contracts for deterministic manual Official fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


FIXTURE_SCHEMA = "goalvision_official_fixture_v1"


@dataclass(frozen=True, slots=True)
class OfficialPredictionFixture:
    """A validated fixture document with read-only section access."""

    payload: Mapping[str, Any]
    fixture_fingerprint: str

    @property
    def fixture_id(self) -> str:
        return str(self.payload["metadata"]["fixture_id"])

    @property
    def expected_outcome(self) -> str:
        return str(self.payload["metadata"]["expected_outcome"])

    @property
    def match_id(self) -> str:
        return str(self.payload["match"]["match_id"])

    @property
    def candidate_id(self) -> str:
        return str(self.payload["candidate"]["expected_candidate_id"])

    @property
    def destination_identity(self) -> str:
        return str(self.payload["publication"]["expected_destination_identity"])

    def section(self, name: str) -> Mapping[str, Any]:
        return self.payload[name]
