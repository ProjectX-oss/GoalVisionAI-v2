"""LIVE_CONTEXT_AWARE_POISSON_V2: offline venue/competition ablation.

No fitted red-card/xG coefficient is available. Such inputs are never imputed.
Red-card states abstain, rather than applying a literature coefficient to a
different population. Zero-card forecasts use observed venue-specific attack
and defence rates and the existing score/remaining-time Poisson evaluator.
This is an uncalibrated development model, never a runtime replacement.
"""
from __future__ import annotations

from datetime import datetime
from collections import Counter
from statistics import mean

from app.adaptive_lab.contracts import digest, utc
from .engine import remaining_goal_probabilities
from .policy import POLICY

VERSION = "LIVE_CONTEXT_AWARE_POISSON_V2"


def context_reasons(state: dict, *, at: datetime) -> list[str]:
    """Validate the frozen score/minute/events, including goals and dismissals."""
    reasons = set()
    if state.get("state_fingerprint") != digest({k:v for k,v in state.items() if k != "state_fingerprint"}):
        reasons.add("STATE_INTEGRITY_FAILURE")
    minute = state.get("minute")
    if type(minute) is not int or not 0 <= minute < 90:
        reasons.add("REMAINING_REGULATION_TIME_UNSUPPORTED")
    if state.get("status") not in POLICY.active_statuses:
        reasons.add("FIXTURE_NOT_CONFIRMED_LIVE")
    for field in ("retrieved_at", "score_retrieved_at", "minute_retrieved_at", "event_retrieved_at"):
        try:
            if not 0 <= (utc(at)-utc(state[field])).total_seconds() <= POLICY.state_age_seconds:
                reasons.add("CONTEXT_CLOCK_INVALID")
        except (KeyError, ValueError, TypeError, AttributeError):
            reasons.add("CONTEXT_CLOCK_INVALID")
    teams = [state.get("home_team_id"), state.get("away_team_id")]
    if any(type(t) is not int for t in teams) or teams[0] == teams[1]:
        return sorted(reasons | {"TEAM_IDENTITY_UNAVAILABLE"})
    goals, reds = dict.fromkeys(teams, 0), dict.fromkeys(teams, 0)
    events = state.get("events")
    if not isinstance(events, list):
        return sorted(reasons | {"EVENTS_UNAVAILABLE"})
    for event in events:
        elapsed = (event.get("time") or {}).get("elapsed")
        if type(elapsed) is not int or elapsed < 0 or type(minute) is not int or elapsed > minute:
            reasons.add("EVENT_MINUTE_CONFLICT")
            continue
        team = (event.get("team") or {}).get("id")
        if event.get("type") == "Goal":
            if event.get("detail") not in {"Normal Goal", "Penalty"}:
                # Own-goal attribution/VAR reversals need a verified provider contract.
                reasons.add("GOAL_EVENT_SEMANTICS_UNSUPPORTED")
            elif team not in goals:
                reasons.add("EVENT_TEAM_CONFLICT")
            else:
                goals[team] += 1
        if event.get("type") == "Card" and event.get("detail") in {"Red Card", "Second Yellow card"}:
            if team not in reds:
                reasons.add("EVENT_TEAM_CONFLICT")
            else:
                reds[team] += 1
    for side, team in zip(("home", "away"), teams):
        score, cards = state.get(side+"_score"), state.get("red_cards_"+side)
        if type(score) is not int or not 0 <= score <= 30 or score != goals[team]:
            reasons.add("GOAL_EVENT_SCORE_MISMATCH")
        if type(cards) is not int or cards != reds[team]:
            reasons.add("RED_CARD_EVENT_COUNT_MISMATCH")
    return sorted(reasons)


def forecast(candidate: dict, *, at: datetime) -> dict:
    """Pure, deterministic as-of inference. Labels and future inputs are rejected."""
    base = {"version": VERSION, "mode": "OFFLINE_RESEARCH_ONLY",
            "candidate_id": candidate.get("prediction_id"), "as_of": utc(at).isoformat(),
            "source_fingerprint": digest(candidate), "calibrated": False,
            "publication_effect": "NONE", "probabilities": None}
    reasons = set()
    if any(k in candidate for k in ("target", "outcome", "settlement", "result_label")):
        reasons.add("LABEL_IN_MODEL_INPUT")
    try:
        state, rates = candidate["state"], candidate["rates"]
        if utc(candidate["prepared_at_utc"]) > utc(at):
            reasons.add("FUTURE_CANDIDATE")
        if utc(state["kickoff_utc"]) > utc(state["retrieved_at"]):
            reasons.add("FUTURE_KICKOFF")
        reasons.update(context_reasons(state, at=at))
        payloads = rates["frozen_history_payloads"]
        if len(payloads) != 2 or digest(payloads) != rates["source_fingerprint"]:
            reasons.add("HISTORY_INTEGRITY_FAILURE")
        if utc(rates["available_at"]) > utc(at):
            reasons.add("FUTURE_HISTORY")
        if any(state.get("red_cards_"+side) for side in ("home", "away")):
            reasons.add("RED_CARD_EFFECT_NOT_ESTIMATED")
        samples, source_ids, excluded = [], [], Counter()
        for side, payload in zip(("home", "away"), payloads):
            scores, seen = [], set()
            if payload.get("errors") or not isinstance(payload.get("response"), list):
                reasons.add("HISTORY_UNAVAILABLE")
                continue
            for row in payload["response"]:
                fixture = row.get("fixture") or {}
                fid = fixture.get("id")
                if type(fid) is not int or fid in seen:
                    reasons.add("DUPLICATE_OR_INVALID_HISTORY_ID")
                    continue
                seen.add(fid)
                if fid == state["fixture_id"] or utc(fixture["date"]) >= utc(state["kickoff_utc"]):
                    excluded["FUTURE_OR_TARGET_HISTORY"] += 1
                    continue
                if (fixture.get("status") or {}).get("short") != "FT":
                    continue
                if state.get("league_id") is None or (row.get("league") or {}).get("id") != state["league_id"]:
                    continue
                if ((row.get("teams") or {}).get(side) or {}).get("id") != state[side+"_team_id"]:
                    continue
                score = (row.get("score") or {}).get("fulltime") or {}
                gf, ga = score.get(side), score.get("away" if side == "home" else "home")
                if not all(type(v) is int and 0 <= v <= 30 for v in (gf, ga)):
                    reasons.add("HISTORY_SCORE_INVALID")
                    continue
                scores.append((gf, ga)); source_ids.append(fid)
            samples.append(scores)
        counts = [len(s) for s in samples]
        base["venue_competition_sample_counts"] = counts
        base["history_excluded_counts"] = dict(excluded)
        base["history_fixture_ids"] = sorted(set(source_ids))
        base["optional_features_used"] = []
        base["optional_features_status"] = "NO_VERIFIED_XG_SHOTS_OR_EFFECT_ARTIFACT"
        if len(samples) != 2 or min(counts, default=0) < POLICY.minimum_history:
            reasons.add("VENUE_COMPETITION_HISTORY_INSUFFICIENT")
        if not reasons:
            home, away = samples
            hr = (mean(s[0] for s in home)+mean(s[1] for s in away))/2
            ar = (mean(s[0] for s in away)+mean(s[1] for s in home))/2
            if not all(.01 <= rate <= 6 for rate in (hr, ar)):
                reasons.add("OBSERVED_RATE_OUTSIDE_SUPPORTED_DOMAIN")
            else:
                derived = {"home_goal_rate": hr, "away_goal_rate": ar,
                           "home_sample": len(home), "away_sample": len(away),
                           "available_at": rates["available_at"],
                           "source_fingerprint": digest([VERSION, payloads, state["league_id"]])}
                base["rates"] = derived
                base["probabilities"] = remaining_goal_probabilities(state, derived, as_of=at)
    except (KeyError, TypeError, ValueError, AttributeError):
        reasons.add("MISSING_OR_INVALID_CONTEXT_INPUT")
    base.update(status="NO_FORECAST" if reasons else "RESEARCH_FORECAST", blockers=sorted(reasons))
    base["fingerprint"] = digest(base)
    return base
