"""Dependency-free Pi ratings for match-result-only LAB shadow evidence.

The update equations follow the Pi system described by Constantinou & Fenton
(2012) and the MIT-licensed ``penaltyblog.ratings.PiRatingSystem`` public API.
This is an independent Decimal implementation, not copied package code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from enum import StrEnum
from math import erf, sqrt
from typing import Iterable


class PiAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    LOW_SAMPLE = "LOW_SAMPLE"
    INSUFFICIENT = "INSUFFICIENT"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class MatchResult:
    league_id: int
    season: int
    fixture_id: int
    kickoff_utc: datetime
    home_team_id: int
    away_team_id: int
    home_goals: int
    away_goals: int


@dataclass(frozen=True, slots=True)
class TeamPiRating:
    home: Decimal = Decimal("0")
    away: Decimal = Decimal("0")

    @property
    def average(self) -> Decimal:
        return (self.home + self.away) / Decimal(2)


@dataclass(frozen=True, slots=True)
class PiSignal:
    state: PiAvailability
    league_id: int
    home_team_id: int
    away_team_id: int
    home_pi_rating: Decimal | None
    away_pi_rating: Decimal | None
    rating_difference: Decimal | None
    expected_relative_strength: str | None
    home_team_home_strength: Decimal | None
    home_team_away_strength: Decimal | None
    away_team_home_strength: Decimal | None
    away_team_away_strength: Decimal | None
    home_observations: int
    away_observations: int
    home_venue_observations: int
    away_venue_observations: int
    probabilities: dict[str, Decimal]


class PiRatingAdapter:
    """One-league rating namespace; it cannot compare ratings across leagues."""

    def __init__(
        self,
        league_id: int,
        *,
        alpha: Decimal = Decimal("0.15"),
        beta: Decimal = Decimal("0.10"),
        diminishing_factor: Decimal = Decimal("0.75"),
        sigma: Decimal = Decimal("1.0"),
        minimum_observations: int = 8,
        low_sample_observations: int = 4,
        minimum_venue_observations: int = 3,
    ) -> None:
        if minimum_observations < low_sample_observations or low_sample_observations < 1:
            raise ValueError("INVALID_PI_SUFFICIENCY_POLICY")
        self.league_id = int(league_id)
        self.alpha, self.beta = alpha, beta
        self.diminishing_factor, self.sigma = diminishing_factor, sigma
        self.minimum_observations = minimum_observations
        self.low_sample_observations = low_sample_observations
        self.minimum_venue_observations = minimum_venue_observations
        self._ratings: dict[int, TeamPiRating] = {}
        self._observations: dict[int, int] = {}
        self._home_observations: dict[int, int] = {}
        self._away_observations: dict[int, int] = {}
        self._seen: set[int] = set()

    def replay(self, matches: Iterable[MatchResult], *, before: datetime | None = None) -> None:
        """Replay unique completed matches in chronological provider-ID order."""
        cutoff = _utc(before) if before is not None else None
        ordered = sorted(matches, key=lambda item: (_utc(item.kickoff_utc), item.fixture_id))
        for match in ordered:
            if match.league_id != self.league_id or match.fixture_id in self._seen:
                continue
            if cutoff is not None and _utc(match.kickoff_utc) >= cutoff:
                continue
            self.update(match)

    def update(self, match: MatchResult) -> None:
        if match.league_id != self.league_id:
            raise ValueError("PI_CROSS_LEAGUE_UPDATE_REJECTED")
        if match.fixture_id in self._seen:
            return
        home = self._ratings.get(match.home_team_id, TeamPiRating())
        away = self._ratings.get(match.away_team_id, TeamPiRating())
        with localcontext() as context:
            context.prec = 28
            expected = home.home - away.away
            error = Decimal(match.home_goals - match.away_goals) - expected
            adjusted = error / (Decimal(1) + self.diminishing_factor * abs(error))
            self._ratings[match.home_team_id] = TeamPiRating(
                home.home + self.alpha * adjusted,
                home.away + self.beta * adjusted,
            )
            self._ratings[match.away_team_id] = TeamPiRating(
                away.home - self.beta * adjusted,
                away.away - self.alpha * adjusted,
            )
        self._seen.add(match.fixture_id)
        for team in (match.home_team_id, match.away_team_id):
            self._observations[team] = self._observations.get(team, 0) + 1
        self._home_observations[match.home_team_id] = self._home_observations.get(match.home_team_id, 0) + 1
        self._away_observations[match.away_team_id] = self._away_observations.get(match.away_team_id, 0) + 1

    def rating(self, team_id: int) -> TeamPiRating:
        return self._ratings.get(int(team_id), TeamPiRating())

    def signal(self, home_team_id: int, away_team_id: int) -> PiSignal:
        home_team_id, away_team_id = int(home_team_id), int(away_team_id)
        home_count = self._observations.get(home_team_id, 0)
        away_count = self._observations.get(away_team_id, 0)
        home_venue = self._home_observations.get(home_team_id, 0)
        away_venue = self._away_observations.get(away_team_id, 0)
        state = self._availability(home_count, away_count, home_venue, away_venue)
        if state in {PiAvailability.UNAVAILABLE, PiAvailability.INSUFFICIENT}:
            return PiSignal(
                state, self.league_id, home_team_id, away_team_id,
                None, None, None, None, None, None, None, None,
                home_count, away_count, home_venue, away_venue, {},
            )
        home, away = self.rating(home_team_id), self.rating(away_team_id)
        difference = home.home - away.away
        probabilities = _normal_outcome_probabilities(difference, self.sigma)
        relative = "HOME_STRONGER" if difference > Decimal("0.05") else (
            "AWAY_STRONGER" if difference < Decimal("-0.05") else "BALANCED"
        )
        return PiSignal(
            state, self.league_id, home_team_id, away_team_id,
            home.average, away.average, difference, relative,
            home.home, home.away, away.home, away.away,
            home_count, away_count, home_venue, away_venue, probabilities,
        )

    def _availability(self, home: int, away: int, home_venue: int, away_venue: int) -> PiAvailability:
        if home == 0 and away == 0:
            return PiAvailability.UNAVAILABLE
        if min(home, away) < self.low_sample_observations:
            return PiAvailability.INSUFFICIENT
        if min(home, away) < self.minimum_observations or min(home_venue, away_venue) < self.minimum_venue_observations:
            return PiAvailability.LOW_SAMPLE
        return PiAvailability.AVAILABLE


def parse_api_fixture_results(payloads: Iterable[object]) -> tuple[MatchResult, ...]:
    """Normalize only finished fixture identity and goals; ignore every odds field."""
    matches: dict[int, MatchResult] = {}
    conflicting: set[int] = set()
    for payload in payloads:
        rows = payload if isinstance(payload, list) else payload.get("response") if isinstance(payload, dict) else ()
        for row in rows if isinstance(rows, list) else ():
            if not isinstance(row, dict):
                continue
            fixture = row.get("fixture") if isinstance(row.get("fixture"), dict) else {}
            league = row.get("league") if isinstance(row.get("league"), dict) else {}
            teams = row.get("teams") if isinstance(row.get("teams"), dict) else {}
            home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
            away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
            goals = row.get("goals") if isinstance(row.get("goals"), dict) else {}
            status = fixture.get("status") if isinstance(fixture.get("status"), dict) else {}
            if status.get("short") not in {"FT", "AET", "PEN"}:
                continue
            fulltime=(row.get('score') or {}).get('fulltime') or {}
            if status.get('short') in {'AET','PEN'}:
                goals=fulltime
            elif fulltime.get('home') is not None and fulltime.get('away') is not None:
                goals=fulltime
            if not all(type(goals.get(side)) is int and 0<=goals[side]<=30 for side in ('home','away')):
                continue
            try:
                item = MatchResult(
                    league_id=int(league["id"]), season=int(league["season"]),
                    fixture_id=int(fixture["id"]), kickoff_utc=_parse_time(fixture["date"]),
                    home_team_id=int(home["id"]), away_team_id=int(away["id"]),
                    home_goals=int(goals["home"]), away_goals=int(goals["away"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
            if item.home_team_id==item.away_team_id or min(item.fixture_id,item.league_id,item.home_team_id,item.away_team_id)<=0:
                continue
            if item.fixture_id in matches and matches[item.fixture_id]!=item:
                conflicting.add(item.fixture_id)
            matches[item.fixture_id] = item
    return tuple(matches[key] for key in sorted(matches, key=lambda key: (matches[key].kickoff_utc, key)) if key not in conflicting)


def _normal_outcome_probabilities(expected_difference: Decimal, sigma: Decimal) -> dict[str, Decimal]:
    mean, scale = float(expected_difference), float(sigma)
    if scale <= 0:
        raise ValueError("PI_SIGMA_MUST_BE_POSITIVE")
    cdf_low = 0.5 * (1 + erf((-0.5 - mean) / (scale * sqrt(2))))
    cdf_high = 0.5 * (1 + erf((0.5 - mean) / (scale * sqrt(2))))
    home = Decimal(str(1 - cdf_high))
    draw = Decimal(str(cdf_high - cdf_low))
    # erf is evaluated in binary float. Close the Decimal simplex explicitly
    # instead of retaining a small conversion residual in the away class.
    away = Decimal(1) - home - draw
    values = (home, draw, away)
    return dict(zip(("HOME_WIN", "DRAW", "AWAY_WIN"), values, strict=True))


def _parse_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return _utc(parsed)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("PI_MATCH_TIME_REQUIRES_OFFSET")
    return value.astimezone(timezone.utc)
