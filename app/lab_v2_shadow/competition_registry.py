"""Immutable, provider-scoped reviewed facts; names never serve as identity keys."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from app.real_match_lab_analysis.fingerprint import fingerprint

REGISTRY_VERSION = 'LAB_REVIEWED_COMPETITIONS_V1'


@dataclass(frozen=True)
class ReviewedCompetition:
    provider: str
    league_id: int
    country: str
    name: str
    profile: str
    gender: str
    age_group: str
    professional_status: str
    competition_type: str
    tier: str
    review_reason: str
    review_source: str
    registry_version: str


def _load() -> Mapping[tuple[str, int], ReviewedCompetition]:
    document = json.loads(Path(__file__).with_name('reviewed_competitions.json').read_text())
    if document['version'] != REGISTRY_VERSION:
        raise ValueError('COMPETITION_REGISTRY_VERSION_MISMATCH')
    rows = [ReviewedCompetition(**row) for row in document['records']]
    records = {(row.provider, row.league_id): row for row in rows}
    if len(records) != len(rows) or any(row.registry_version != REGISTRY_VERSION for row in rows):
        raise ValueError('COMPETITION_REGISTRY_INVALID')
    return MappingProxyType(records)


REVIEWED_COMPETITIONS = _load()
REGISTRY_FINGERPRINT = fingerprint(tuple(vars(row) for row in REVIEWED_COMPETITIONS.values()))


def reviewed_competition(provider: str, league_id: int, country: str) -> ReviewedCompetition | None:
    """Country conflicts fail closed; renaming a league does not change identity."""
    row = REVIEWED_COMPETITIONS.get((provider, league_id))
    return row if row and row.country.casefold() == country.casefold() else None
