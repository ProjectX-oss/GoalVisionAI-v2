"""Offline parser for explicitly acquired OpenLigaDB season snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.historical_data_import import (
    HISTORICAL_DATASET_SCHEMA,
    HistoricalDataset,
    HistoricalMatchInput,
)

from .models import MatchExclusionReason


PARSER_VERSION = "openligadb-offline-json-parser-v1"
NORMALIZATION_VERSION = "goalvision-historical-import-v1"


@dataclass(frozen=True, slots=True)
class ParseResult:
    dataset: HistoricalDataset
    supplied_record_count: int
    exclusions: tuple[tuple[str, MatchExclusionReason], ...]


def parse_openligadb_files(
    paths: Sequence[str | Path], *, dataset_id: str, dataset_version: str,
) -> ParseResult:
    matches: list[HistoricalMatchInput] = []
    exclusions: list[tuple[str, MatchExclusionReason]] = []
    supplied = 0
    natural_keys: set[tuple[str, str, str, str]] = set()
    for path in sorted((Path(item) for item in paths), key=lambda item: item.name):
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, list):
            raise ValueError(f"OpenLigaDB file must contain a JSON array: {path.name}")
        for index, raw in enumerate(payload):
            supplied += 1
            label = f"{path.name}:{index}"
            try:
                match = _parse_match(raw, label)
            except _Excluded as exc:
                exclusions.append((label, exc.reason))
                continue
            key = (match.competition, str(match.kickoff_utc), match.home_team, match.away_team)
            if key in natural_keys:
                exclusions.append((label, MatchExclusionReason.DUPLICATE))
                continue
            natural_keys.add(key)
            matches.append(match)
    return ParseResult(
        HistoricalDataset(
            schema_version=HISTORICAL_DATASET_SCHEMA,
            provider="OpenLigaDB",
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            matches=tuple(matches),
        ),
        supplied,
        tuple(exclusions),
    )


class _Excluded(Exception):
    def __init__(self, reason: MatchExclusionReason) -> None:
        self.reason = reason


def _parse_match(raw: Any, label: str) -> HistoricalMatchInput:
    if not isinstance(raw, Mapping):
        raise _Excluded(MatchExclusionReason.MALFORMED)
    if raw.get("matchIsFinished") is not True:
        raise _Excluded(MatchExclusionReason.NOT_FINISHED)
    kickoff = raw.get("matchDateTimeUTC")
    if not isinstance(kickoff, str) or not kickoff.strip():
        raise _Excluded(MatchExclusionReason.KICKOFF_MISSING)
    team1, team2 = raw.get("team1"), raw.get("team2")
    if not isinstance(team1, Mapping) or not isinstance(team2, Mapping):
        raise _Excluded(MatchExclusionReason.TEAM_IDENTITY_INVALID)
    home, away = team1.get("teamName"), team2.get("teamName")
    if not isinstance(home, str) or not home.strip() or not isinstance(away, str) or not away.strip():
        raise _Excluded(MatchExclusionReason.TEAM_IDENTITY_INVALID)
    score = _final_score(raw.get("matchResults"))
    if score is None:
        raise _Excluded(MatchExclusionReason.SCORE_MISSING)
    if any(type(item) is not int or item < 0 or item > 30 for item in score):
        raise _Excluded(MatchExclusionReason.SCORE_INVALID)
    group = raw.get("group") if isinstance(raw.get("group"), Mapping) else {}
    location = raw.get("location") if isinstance(raw.get("location"), Mapping) else {}
    match_id = raw.get("matchID")
    if type(match_id) not in (int, str):
        raise _Excluded(MatchExclusionReason.MALFORMED)
    season = str(raw.get("leagueSeason") or "").strip()
    competition = str(raw.get("leagueName") or raw.get("leagueShortcut") or "").strip()
    if not season or not competition:
        raise _Excluded(MatchExclusionReason.MALFORMED)
    round_name = str(group.get("groupName") or group.get("groupOrderID") or "UNSPECIFIED")
    venue = str(location.get("locationStadium") or "VENUE_NOT_SUPPLIED")
    return HistoricalMatchInput(
        source_match_id=str(match_id), competition=competition, season=season, round=round_name,
        kickoff_utc=kickoff, home_team=home, away_team=away,
        full_time_home_score=score[0], full_time_away_score=score[1], venue=venue,
    )


def _final_score(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, list):
        return None
    candidates = [item for item in value if isinstance(item, Mapping)]
    preferred = [item for item in candidates if item.get("resultTypeID") == 2 or item.get("resultName") in {"Endergebnis", "Final"}]
    for item in preferred or candidates:
        home, away = item.get("pointsTeam1"), item.get("pointsTeam2")
        if type(home) is int and type(away) is int:
            return home, away
    return None
