"""First-Lab manual operations, durable checkpoints, and publication safety.

This module is deliberately inert: importing it performs no network, database,
Telegram, scheduling, or model work.  All state changes require an explicit
operator command and remain confined to the forward-test database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Awaitable, Callable

from app.database import Database, MigrationManager
from app.football.configuration import api_football_credential_status
from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint
from app.real_match_lab_analysis.models import LAB_BOT_USERNAME, LAB_CHAT_ID, SEND_CONFIRMATION

from .audit import audit_observation
from .efficiency import CapabilityCacheError, CompetitionCapabilityCache
from .repository import ForwardTestConflictError, SQLiteForwardTestRepository
from .statistics import build_statistics


REQUIRED_COMPLETE_RUN_CALLS = 12
MAX_TRUSTED_PRESENTED_PROBABILITY = 0.95
READINESS_SCHEMA = "goalvision-api-football-pro-readiness-v1"
REVIEW_SCHEMA = "goalvision-lab-publication-review-v1"
RUN_SCHEMA = "goalvision-first-lab-run-v1"


class ProReadinessOutcome(str, Enum):
    FREE_PLAN_CURRENT_SEASON_BLOCKED = "FREE_PLAN_CURRENT_SEASON_BLOCKED"
    PRO_PLAN_REQUIRED = "PRO_PLAN_REQUIRED"
    PRO_PLAN_READY = "PRO_PLAN_READY"
    CREDENTIAL_INVALID = "CREDENTIAL_INVALID"
    QUOTA_INSUFFICIENT = "QUOTA_INSUFFICIENT"
    CONFIGURATION_INCOMPLETE = "CONFIGURATION_INCOMPLETE"


class PublicationReviewOutcome(str, Enum):
    PASSED = "LAB_PUBLICATION_REVIEW_PASSED"
    BLOCKED = "LAB_PUBLICATION_REVIEW_BLOCKED"
    REQUIRED = "LAB_PUBLICATION_REVIEW_REQUIRED"


STAGES = (
    "READINESS_CHECKED", "CAPABILITIES_RESOLVED", "FIXTURES_DISCOVERED",
    "CANDIDATE_SELECTED", "BASELINES_CAPTURED", "ODDS_CAPTURED",
    "INPUT_SEALED", "ANALYSIS_COMPLETED", "OBSERVATION_CREATED",
    "PREVIEW_CREATED", "TERMINAL_BLOCKED", "TERMINAL_COMPLETED",
)


def build_pro_readiness(
    *, env_file: Path = Path(".env"), cache_path: Path = Path("var/api_football_capabilities.json"),
    now: datetime | None = None, network_verified: bool = False,
    authenticated: bool | None = None, detected_plan: str | None = None,
    quota: dict | None = None,
) -> dict:
    """Build a secret-free readiness report from config, cache and bounded facts."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    credential = api_football_credential_status(env_file=env_file)
    cache = None
    cache_error = None
    try:
        cache = CompetitionCapabilityCache.load(cache_path, now=now)
    except (CapabilityCacheError, OSError, ValueError, json.JSONDecodeError) as exc:
        cache_error = type(exc).__name__
    records = cache.records if cache else ()
    seasons = sorted({item.season for item in records})
    plan = (detected_plan or "NOT_VERIFIED").upper()
    quota = dict(quota or {})
    daily_remaining = quota.get("daily_remaining")
    minute_remaining = quota.get("minute_remaining")
    minimum_quota_available = (
        isinstance(daily_remaining, int) and daily_remaining >= REQUIRED_COMPLETE_RUN_CALLS
        and (minute_remaining is None or minute_remaining >= 1)
    )
    current_history = network_verified and authenticated is True and plan not in {"FREE", "NOT_VERIFIED", "UNKNOWN"}
    if credential == "NOT_CONFIGURED":
        outcome = ProReadinessOutcome.CONFIGURATION_INCOMPLETE
    elif credential != "CONFIGURED" or authenticated is False:
        outcome = ProReadinessOutcome.CREDENTIAL_INVALID
    elif not network_verified:
        outcome = ProReadinessOutcome.PRO_PLAN_REQUIRED
    elif plan == "FREE":
        outcome = ProReadinessOutcome.FREE_PLAN_CURRENT_SEASON_BLOCKED
    elif not current_history:
        outcome = ProReadinessOutcome.PRO_PLAN_REQUIRED
    elif not minimum_quota_available:
        outcome = ProReadinessOutcome.QUOTA_INSUFFICIENT
    else:
        outcome = ProReadinessOutcome.PRO_PLAN_READY
    capabilities = {
        "fixture_endpoint_available": any(item.fixtures for item in records),
        "standings_available": any(item.standings for item in records),
        "injuries_available": any(item.injuries for item in records),
        "lineups_available": any(item.lineups for item in records),
        "current_odds_available": any(item.odds for item in records),
    }
    document = {
        "schema_version": READINESS_SCHEMA,
        "status": outcome.value,
        "credential_configured": credential == "CONFIGURED",
        "credential_status": credential,
        "authentication_status": "AUTHENTICATED" if authenticated is True else "INVALID" if authenticated is False else "NOT_EXECUTED",
        "detected_api_plan": plan,
        "network_verification": "BOUNDED" if network_verified else "NOT_EXECUTED",
        "accessible_season_range": {"minimum": seasons[0] if seasons and current_history else None, "maximum": seasons[-1] if seasons and current_history else None},
        "provider_capability_season_range": {"minimum": seasons[0] if seasons else None, "maximum": seasons[-1] if seasons else None},
        "current_season_team_history_available": current_history,
        **capabilities,
        "daily_limit": quota.get("daily_limit"), "daily_remaining": daily_remaining,
        "per_minute_limit": quota.get("minute_limit"), "per_minute_remaining": minute_remaining,
        "required_minimum_quota": REQUIRED_COMPLETE_RUN_CALLS,
        "capability_cache": {
            "status": "VALID" if cache else "MISSING_OR_EXPIRED" if cache_error is None else "INVALID",
            "record_count": len(records), "fingerprint": cache.cache_fingerprint if cache else None,
            "error_type": cache_error,
        },
        "ready_for_genuine_forward_test": outcome is ProReadinessOutcome.PRO_PLAN_READY,
        "secret_fields_present": False,
    }
    document["readiness_fingerprint"] = fingerprint(document)
    return document


class FirstLabOperationsRepository:
    """Append-only, replay-safe repository for operator workflow evidence."""

    def __init__(self, database: Database, *, migrate: bool = True) -> None:
        self.connection = database.connection
        if migrate:
            MigrationManager(self.connection).migrate()

    def begin(self, run_id: str, request: dict, *, mode: str, occurred_at: datetime) -> dict:
        material = {"schema_version": RUN_SCHEMA, "run_id": run_id, "request": request, "mode": mode}
        request_fp = fingerprint({"run_id": run_id, "request": request}); run_fp = fingerprint(material)
        existing = self.connection.execute("SELECT * FROM first_lab_run_executions WHERE run_id=?", (run_id,)).fetchone()
        if existing:
            if existing["request_fingerprint"] != request_fp or existing["run_fingerprint"] != run_fp:
                raise ForwardTestConflictError("Conflicting First Lab run replay rejected.")
            return json.loads(existing["run_snapshot"])
        snapshot = {**material, "request_fingerprint": request_fp, "run_fingerprint": run_fp, "initial_status": "RUNNING", "created_at_utc": occurred_at.isoformat()}
        with self.connection:
            self.connection.execute(
                "INSERT INTO first_lab_run_executions VALUES (?,?,?,?,?,?,?)",
                (run_id, request_fp, mode, "STARTED", occurred_at.isoformat(), run_fp, canonical_json(snapshot)),
            )
        return snapshot

    def stage(self, run_id: str, name: str, status: str, artifact: object, *, occurred_at: datetime, artifact_type: str | None = None, artifact_id: str | None = None) -> dict:
        if name not in STAGES:
            raise ValueError("Unknown First Lab stage.")
        artifact_fp = fingerprint(artifact) if artifact is not None else None
        material = {"run_id": run_id, "stage_name": name, "stage_status": status, "artifact_type": artifact_type, "artifact_id": artifact_id, "artifact_fingerprint": artifact_fp}
        event_fp = fingerprint(material)
        existing = self.connection.execute("SELECT * FROM first_lab_run_stage_events WHERE run_id=? AND stage_name=?", (run_id, name)).fetchone()
        if existing:
            if existing["event_fingerprint"] != event_fp:
                raise ForwardTestConflictError(f"Conflicting First Lab stage replay: {name}.")
            return json.loads(existing["event_snapshot"])
        order = STAGES.index(name)
        snapshot = {**material, "artifact_snapshot": artifact, "stage_order": order, "occurred_at_utc": occurred_at.isoformat(), "event_fingerprint": event_fp}
        with self.connection:
            self.connection.execute(
                "INSERT INTO first_lab_run_stage_events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("first-lab-stage-" + event_fp, run_id, order, name, status, artifact_type, artifact_id, artifact_fp, occurred_at.isoformat(), event_fp, canonical_json(snapshot)),
            )
        return snapshot

    def stages(self, run_id: str) -> tuple[dict, ...]:
        rows = self.connection.execute("SELECT event_snapshot FROM first_lab_run_stage_events WHERE run_id=? ORDER BY stage_order", (run_id,)).fetchall()
        return tuple(json.loads(row[0]) for row in rows)

    def append_review(self, report: dict) -> dict:
        existing = self.connection.execute("SELECT review_snapshot FROM forward_test_publication_reviews WHERE review_fingerprint=?", (report["review_fingerprint"],)).fetchone()
        if existing:
            return json.loads(existing[0])
        with self.connection:
            self.connection.execute(
                "INSERT INTO forward_test_publication_reviews VALUES (?,?,?,?,?,?,?)",
                (report["review_id"], report["observation_id"], report["status"], report.get("message_fingerprint"), report["reviewed_at_utc"], report["review_fingerprint"], canonical_json(report)),
            )
        return report

    def append_result_preview(self, preview: dict) -> dict:
        existing = self.connection.execute("SELECT preview_snapshot FROM forward_test_result_previews WHERE observation_id=?", (preview["observation_id"],)).fetchone()
        if existing:
            prior = json.loads(existing[0])
            if prior["preview_fingerprint"] != preview["preview_fingerprint"]:
                raise ForwardTestConflictError("Conflicting result preview rejected.")
            return prior
        with self.connection:
            self.connection.execute(
                "INSERT INTO forward_test_result_previews VALUES (?,?,?,?,?,?)",
                (preview["preview_id"], preview["observation_id"], preview["settlement_id"], preview["preview_fingerprint"], canonical_json(preview), preview["created_at_utc"]),
            )
        return preview


def build_lab_preview(observation: dict, request: dict, odds: dict) -> dict:
    """Create either a publishable candidate or an honest internal diagnostic."""
    market = observation.get("actionable_market") or observation.get("mathematical_top_market")
    evaluation = next((item for item in observation.get("market_evaluations", ()) if item.get("market") == market), {})
    quality = observation.get("calibration_quality") or {}
    shift = observation.get("distribution_shift") or {}
    controlled = bool(quality.get("controlled_synthetic"))
    calibrated = _float(evaluation.get("calibrated_probability"))
    extreme = calibrated is not None and calibrated > MAX_TRUSTED_PRESENTED_PROBABILITY
    publishable = bool(
        observation.get("actionable") and market and not controlled and not extreme
        and quality.get("lab_outcome") == "CALIBRATION_QUALITY_ACCEPTABLE"
        and shift.get("status") == "DISTRIBUTION_SHIFT_ACCEPTABLE"
    )
    kickoff = _time(request["kickoff_utc"])
    captured = _time(odds["captured_at_utc"])
    from app.real_match_lab_analysis.message import _riga_time
    latvian = _riga_time(kickoff)
    source = f"{odds.get('provider_source_id')}/{odds.get('bookmaker_name')}"
    probability = evaluation.get("calibrated_probability") if publishable else "WITHHELD_OR_DIAGNOSTIC"
    lines = [
        "🧪 <b>GoalVision AI Lab</b>",
        f"⚽ {request.get('home_team', 'Home')} vs {request.get('away_team', 'Away')}",
        f"🏆 {request.get('competition', 'Unknown competition')}",
        f"🕒 {latvian:%Y-%m-%d %H:%M} Europe/Riga · {kickoff:%Y-%m-%d %H:%M} UTC",
        f"<b>Market:</b> {market or 'No actionable selection'}",
        f"<b>Source:</b> {source}",
        f"<b>Captured odds:</b> {evaluation.get('bookmaker_odds', 'N/A')} at {captured.isoformat()}",
        f"<b>Calibrated probability:</b> {probability}",
        f"<b>Fair odds:</b> {evaluation.get('fair_odds', 'WITHHELD')}" if publishable else "<b>Fair odds / EV:</b> withheld because quality gates did not pass",
        f"<b>EV:</b> {evaluation.get('expected_value')}" if publishable else "<b>Status:</b> internal diagnostic only",
        f"<b>Confidence:</b> {evaluation.get('confidence', 'NOT_ACTIONABLE')}",
        f"<b>Feature completeness:</b> {shift.get('completeness', 'NOT_RECORDED')}",
        f"<b>Lineups:</b> {evaluation.get('lineup_freshness_status', 'NOT_RECORDED')}",
        f"<b>Calibration quality:</b> {quality.get('lab_outcome', 'NOT_EVALUATED')}",
        f"<b>Distribution shift:</b> {shift.get('status', 'NOT_EVALUATED')}",
        f"<b>Reasoning:</b> {'; '.join(observation.get('rejection_reasons') or ('model ranking and immutable current odds',))}",
        f"<b>Trace:</b> {observation.get('observation_id', '')[-16:]}",
        "⚠️ Experimental forward-test evidence only. No guarantee.",
        "Excluded from Official bankroll and Official statistics.",
    ]
    body = "\n".join(lines)
    material = {"version": "goalvision-first-lab-preview-v1", "observation_id": observation.get("observation_id"), "publishable": publishable, "body": body}
    return {"status": "LAB_PREVIEW_PUBLISHABLE" if publishable else "LAB_PREVIEW_INTERNAL_DIAGNOSTIC", "publishable": publishable, "message_html": body, "message_fingerprint": fingerprint(material), "quality_blockers_visible": not publishable, "preview_fingerprint": fingerprint(material)}


def build_publication_review(repository: SQLiteForwardTestRepository, observation_id: str, *, reviewed_at: datetime | None = None, persist: FirstLabOperationsRepository | None = None) -> dict:
    reviewed = (reviewed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    row = repository.load_observation(observation_id)
    if row is None:
        material = {"schema_version": REVIEW_SCHEMA, "observation_id": observation_id, "status": PublicationReviewOutcome.REQUIRED.value, "checks": [], "blocker_codes": ["OBSERVATION_NOT_FOUND"], "reviewed_at_utc": reviewed.isoformat(), "message_fingerprint": None}
    else:
        observation = json.loads(row["observation_json"])
        analysis = repository.connection.execute("SELECT * FROM real_match_lab_analyses WHERE analysis_id=?", (observation["analysis_id"],)).fetchone()
        request = json.loads(analysis["request_snapshot"])
        odds = json.loads(repository.load_odds(observation["odds_snapshot_id"])["snapshot_json"])
        kickoff, captured, inference = _time(request["kickoff_utc"]), _time(odds["captured_at_utc"]), _time(observation["inference_at_utc"])
        quality = observation.get("calibration_quality") or {}; shift = observation.get("distribution_shift") or {}
        evaluations = observation.get("market_evaluations") or []
        selected = next((item for item in evaluations if item.get("market") == observation.get("actionable_market")), {})
        probability = _float(selected.get("calibrated_probability"))
        checks = [
            ("REAL_UPCOMING_FIXTURE", request.get("match_snapshot") is not None and reviewed < kickoff),
            ("ODDS_BEFORE_INFERENCE", captured <= inference), ("ODDS_BEFORE_KICKOFF", captured < kickoff),
            ("ODDS_FRESH_AT_REVIEW", 0 <= (reviewed-captured).total_seconds() <= 900),
            ("BOOKMAKER_SOURCE_PROVENANCE", bool(odds.get("provider_source_id") and odds.get("bookmaker_name"))),
            ("REQUIRED_BASELINE_COMPLETE", bool(observation.get("feature_snapshot_fingerprint"))),
            ("LIVE_78_COMPATIBLE", bool(observation.get("model_input_fingerprint"))),
            ("MODEL_PROVENANCE", bool(observation.get("model_artifact_id") and observation.get("model_artifact_fingerprint"))),
            ("CALIBRATION_PROVENANCE", bool(observation.get("calibration_id") and observation.get("calibration_fingerprint"))),
            ("CALIBRATION_EVIDENCE_PRODUCTION", quality.get("controlled_synthetic") is False),
            ("CALIBRATION_QUALITY", quality.get("lab_outcome") == "CALIBRATION_QUALITY_ACCEPTABLE" and quality.get("send_eligible") is True),
            ("DISTRIBUTION_SHIFT", shift.get("status") == "DISTRIBUTION_SHIFT_ACCEPTABLE"),
            ("MARKET_ACTIONABLE", bool(observation.get("actionable") and selected.get("actionable"))),
            ("NO_UNSUPPORTED_EXTREME", probability is not None and probability <= MAX_TRUSTED_PRESENTED_PROBABILITY),
            ("NO_CORRECT_SCORE", "CORRECT_SCORE" not in str(observation.get("actionable_market"))),
            ("NO_COMBO", "COMBO" not in str(observation.get("actionable_market"))),
            ("MESSAGE_FINGERPRINT", bool(observation.get("message_fingerprint"))),
            ("EXACT_LAB_DESTINATION", analysis["destination_chat_id"] == LAB_CHAT_ID and analysis["destination_bot"] == LAB_BOT_USERNAME),
            ("OFFICIAL_SEPARATION", observation.get("official_eligible") is False),
            ("FORWARD_TEST_LINKAGE", observation.get("forward_test_recorded") is True),
            ("RESULT_TRACKING_READY", repository.load_result(observation_id) is None),
            ("AUDIT_INTEGRITY", audit_observation(repository, observation_id).status.value != "FORWARD_TEST_INTEGRITY_BLOCKED"),
        ]
        blockers = [name for name, passed in checks if not passed]
        status = PublicationReviewOutcome.PASSED.value if not blockers else PublicationReviewOutcome.BLOCKED.value
        material = {"schema_version": REVIEW_SCHEMA, "observation_id": observation_id, "status": status, "checks": [{"name": name, "passed": passed} for name, passed in checks], "blocker_codes": blockers, "reviewed_at_utc": reviewed.isoformat(), "message_fingerprint": observation.get("message_fingerprint")}
    review_fp = fingerprint(material)
    report = {**material, "review_id": "lab-publication-review-" + review_fp, "review_fingerprint": review_fp, "telegram_send_executed": False}
    return persist.append_review(report) if persist and row is not None else report


def validate_manual_send_authorization(
    repository: SQLiteForwardTestRepository, *, observation_id: str,
    review_fingerprint: str, message_fingerprint: str, confirmation: str,
    environment: str, chat_id: str, bot: str, now: datetime | None = None,
) -> dict:
    """Validate a future manual send without constructing a transport."""
    row = repository.load_observation(observation_id)
    if row is None:
        raise ForwardTestConflictError("Observation not found.")
    observation = json.loads(row["observation_json"])
    review_row = repository.connection.execute("SELECT * FROM forward_test_publication_reviews WHERE review_fingerprint=? AND observation_id=?", (review_fingerprint, observation_id)).fetchone()
    blockers = []
    if environment != "LAB": blockers.append("WRONG_ENVIRONMENT")
    if chat_id != LAB_CHAT_ID: blockers.append("WRONG_DESTINATION")
    if bot != LAB_BOT_USERNAME: blockers.append("WRONG_BOT")
    if confirmation != SEND_CONFIRMATION: blockers.append("WRONG_CONFIRMATION")
    if review_row is None or review_row["review_status"] != PublicationReviewOutcome.PASSED.value: blockers.append("PUBLICATION_REVIEW_NOT_PASSED")
    if observation.get("message_fingerprint") != message_fingerprint: blockers.append("MESSAGE_FINGERPRINT_CONFLICT")
    if not observation.get("actionable"): blockers.append("NON_ACTIONABLE_OBSERVATION")
    if (observation.get("calibration_quality") or {}).get("controlled_synthetic") is not False: blockers.append("SYNTHETIC_OR_UNKNOWN_EVIDENCE")
    analysis_id = observation["analysis_id"]
    if repository.connection.execute("SELECT 1 FROM real_match_lab_deliveries WHERE analysis_id=? LIMIT 1", (analysis_id,)).fetchone(): blockers.append("DELIVERY_ALREADY_EXISTS")
    latest_review = build_publication_review(repository, observation_id, reviewed_at=now)
    if latest_review["status"] != PublicationReviewOutcome.PASSED.value: blockers.extend(latest_review["blocker_codes"])
    return {"status": "LAB_MANUAL_SEND_AUTHORIZED" if not blockers else "LAB_MANUAL_SEND_REJECTED", "analysis_id": analysis_id, "observation_id": observation_id, "message_fingerprint": message_fingerprint, "publication_review_fingerprint": review_fingerprint, "blocker_codes": sorted(set(blockers)), "transport_constructed": False, "telegram_send_executed": False}


def build_result_preview(repository: SQLiteForwardTestRepository, observation_id: str, *, created_at: datetime | None = None, persist: FirstLabOperationsRepository | None = None) -> dict:
    observation_row = repository.load_observation(observation_id); result_row = repository.load_result(observation_id); settlement_row = repository.load_settlement(observation_id)
    if not observation_row or not result_row or not settlement_row:
        raise ValueError("Observation, final result, and settlement are required.")
    observation, result, settlement = (json.loads(observation_row["observation_json"]), json.loads(result_row["result_json"]), json.loads(settlement_row["settlement_json"]))
    request = json.loads(repository.connection.execute("SELECT request_snapshot FROM real_match_lab_analyses WHERE analysis_id=?", (observation["analysis_id"],)).fetchone()[0])
    statistics = build_statistics(repository)
    created = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    body = "\n".join((
        "🧪 GoalVision AI Lab — forward-test result",
        f"{request.get('home_team', 'Home')} {result['final_home_score']}–{result['final_away_score']} {request.get('away_team', 'Away')}",
        f"Selection: {observation.get('actionable_market') or 'No selection'} @ {settlement.get('quoted_odds') or 'N/A'}",
        f"Result: {settlement['outcome']}",
        f"Cumulative: {statistics.wins} WON / {statistics.losses} LOST / {statistics.voids} VOID ({statistics.settled} settled)",
        "Forward-test simulation only; no Official bankroll claim.",
        "Losses remain included in the public evidence history.",
    ))
    material = {"observation_id": observation_id, "settlement_id": settlement["settlement_id"], "message": body}
    preview_fp = fingerprint(material)
    preview = {"schema_version": "goalvision-forward-test-result-preview-v1", "preview_id": "forward-test-result-preview-" + preview_fp, **material, "preview_fingerprint": preview_fp, "created_at_utc": created.isoformat(), "publish_authorized": False}
    return persist.append_result_preview(preview) if persist else preview


def _time(value) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp offset required.")
    return parsed.astimezone(timezone.utc)


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
