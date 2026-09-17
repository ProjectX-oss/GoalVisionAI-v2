"""Deterministic non-public fixture for the recent champion rehearsal."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.real_match_lab_analysis.input import parse_input


def build_controlled_rehearsal_fixture(controlled_now: datetime):
    """Build one future Lab input covering every supported single market."""
    now_text = controlled_now.isoformat(timespec="seconds").replace("+00:00", "Z")
    source_text = (controlled_now - timedelta(minutes=1)).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    kickoff = controlled_now.replace(hour=14, minute=0).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    markets = (
        ("HOME_WIN", "2.10"), ("DRAW", "3.20"), ("AWAY_WIN", "3.50"),
        ("OVER_1_5", "1.55"), ("UNDER_1_5", "2.45"),
        ("OVER_2_5", "1.95"), ("UNDER_2_5", "1.90"),
        ("OVER_3_5", "2.70"), ("UNDER_3_5", "1.48"),
        ("BTTS_YES", "1.85"), ("BTTS_NO", "1.95"),
    )
    raw = {
        "schema_version": "goalvision-real-match-lab-input-v1",
        "request_id": "controlled-recent-live78-rehearsal-v1",
        "environment": "LAB",
        "scope": "OFFICIAL_GLOBAL",
        "operator_identity": "CONTROLLED_SYNTHETIC_RECENT_CALIBRATION_REHEARSAL",
        "match_id": "controlled-upcoming-fixture-20260731-v1",
        "competition_id": "controlled-rehearsal-league",
        "competition": "Controlled Rehearsal League",
        "season": "2026",
        "home_team_id": "controlled-home",
        "home_team": "Controlled Home",
        "away_team_id": "controlled-away",
        "away_team": "Controlled Away",
        "kickoff_utc": kickoff,
        "collected_at": now_text,
        "source_updated_at": source_text,
        "source_provider": "CONTROLLED_SYNTHETIC_RECENT_CALIBRATION_REHEARSAL",
        "source_event_id": "controlled-event-20260731-v1",
        "source_snapshot_id": "controlled-snapshot-20260731-v1",
        "operator_notes": "Non-public deterministic rehearsal; never send.",
        "data": {
            "venue": "Controlled Ground",
            "neutral_venue": False,
            "home_recent_form": {
                "match_count": 5, "wins": 3, "draws": 1, "losses": 1,
                "goals_scored": 9, "goals_conceded": 5,
                "clean_sheets": 2, "failed_to_score": 0,
                "expected_goals_for": "8.4", "expected_goals_against": "5.2",
            },
            "away_recent_form": {
                "match_count": 5, "wins": 2, "draws": 2, "losses": 1,
                "goals_scored": 7, "goals_conceded": 6,
                "clean_sheets": 1, "failed_to_score": 1,
                "expected_goals_for": "7.1", "expected_goals_against": "6.3",
            },
            "home_availability": {
                "confirmed_lineup": False, "probable_lineup": True,
                "injuries_count": 1, "suspensions_count": 0,
                "missing_key_players_count": 0,
                "lineup_source_timestamp": source_text,
            },
            "away_availability": {
                "confirmed_lineup": False, "probable_lineup": True,
                "injuries_count": 1, "suspensions_count": 0,
                "missing_key_players_count": 0,
                "lineup_source_timestamp": source_text,
            },
            "context": {
                "home_rest_days": 6, "away_rest_days": 5,
                "competition_stage": "CONTROLLED_REHEARSAL",
                "derby_indicator": False,
            },
        },
        "odds": [
            {
                "snapshot_id": f"controlled-odds-{market.lower()}",
                "market": market,
                "decimal_odds": odds,
                "source_provider": "CONTROLLED_IMMUTABLE_ODDS",
                "bookmaker_id": "CONTROLLED_BOOK",
                "source_event_id": "controlled-book-event-20260731-v1",
                "captured_at": source_text,
            }
            for market, odds in markets
        ],
    }
    return parse_input(raw, now=controlled_now)
