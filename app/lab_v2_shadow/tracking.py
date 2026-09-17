"""Durable fixture/market review identity, independent of changing quote hashes."""

from __future__ import annotations

from datetime import datetime

from .capability import CapabilityTier, LeagueCapabilityCache
from .repository import ShadowEvidenceRepository
from .profiles import fallback_capability, classify


TERMINAL_STATES = frozenset({"REJECTED", "FIXTURE_INVALID", "EXPIRED"})


def load_reviews(repository: ShadowEvidenceRepository, now: datetime) -> dict[tuple[int, str], dict]:
    """Recover existing EARLY evidence on upgrade; never reopen a terminal review."""
    records = {(row["fixture_id"], row["market"]): row for row in repository.tracked_reviews()}
    for candidate in repository.early_candidates(now=now):
        key = (int(candidate["fixture_id"]), candidate["market"])
        if key not in records:
            records[key] = new_review(candidate, now)
    return {key: row for key, row in records.items() if row["state"] not in TERMINAL_STATES}


def new_review(candidate: dict, now: datetime) -> dict:
    """Retain identity and fixture context only; old quotes cannot become new inputs."""
    fields = ("fixture_id", "market", "kickoff_utc", "home_team_id", "away_team_id",
              "home_team", "away_team", "league_id", "league", "season", "competition_profile",
              "classifier_version", "classification_reason", "classification_fingerprint", "country",
              "age_category", "flags", "provider_metadata")
    return {
        **{key: candidate[key] for key in fields if key in candidate},
        "origin_candidate_id": candidate["candidate_id"],
        "state": "EARLY_CANDIDATE", "reasons": ["FINAL_REVIEW_WINDOW_NOT_OPEN"],
        "evaluated_at_utc": now.isoformat(),
    }


def restore_fixture(record: dict, capabilities: LeagueCapabilityCache) -> dict | None:
    """Restore by provider IDs; current capabilities must still cover the fixture."""
    kickoff = datetime.fromisoformat(record["kickoff_utc"])
    matches = [item for item in capabilities.records
               if item.league_id == record["league_id"] and item.covers(kickoff.date())
               and (record.get("season") is None or item.season == record["season"])]
    metadata = record.get("provider_metadata") or {}
    league = metadata.get("league") or {"id": record["league_id"], "season": record.get("season", kickoff.year),
                                        "name": record.get("league", "UNKNOWN")}
    capability = matches[0] if len(matches) == 1 else fallback_capability(league)
    classification = classify(league, metadata.get("teams", {}), metadata.get("fixture", {}), capability)
    return {
        **classification.document(), "country": capability.country, "provider_metadata": metadata,
        **{key: record[key] for key in ("fixture_id", "league_id", "home_team_id",
                                      "away_team_id", "home_team", "away_team")},
        "kickoff_utc": kickoff, "league_name": record["league"], "season": capability.season,
        "capability": capability, "capability_tier": capability.tier,
    }
