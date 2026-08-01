"""Forward-test observation, result, and statistical-only settlement services."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from app.real_match_lab_analysis.fingerprint import fingerprint

from .models import (
    EVIDENCE_TIER, OBSERVATION_SCHEMA_VERSION, RESULT_SCHEMA_VERSION,
    CurrentOddsSnapshot, ForwardTestObservation, ForwardTestResult,
    ForwardTestSettlement, ObservationStatus, SettlementOutcome,
)
from .repository import ForwardTestConflictError, SQLiteForwardTestRepository


COMPLETED_RESULT_STATUSES = frozenset({"FT", "AET", "PEN", "COMPLETED"})


class ForwardTestValidationError(ValueError): pass


class ForwardTestService:
    def __init__(self, repository: SQLiteForwardTestRepository) -> None: self.repository = repository

    def capture_odds(self, snapshot: CurrentOddsSnapshot):
        return self.repository.append_odds_snapshot(snapshot)

    def create_observation(self, request_id: str, analysis_id: str, odds_snapshot_id: str) -> ForwardTestObservation:
        analysis = self.repository.connection.execute("SELECT * FROM real_match_lab_analyses WHERE analysis_id=?", (analysis_id,)).fetchone()
        odds_row = self.repository.load_odds(odds_snapshot_id)
        if analysis is None: raise ForwardTestValidationError("Real Match Lab analysis not found.")
        if odds_row is None: raise ForwardTestValidationError("Sealed current-odds snapshot not found.")
        request = json.loads(analysis["request_snapshot"]); result = json.loads(analysis["result_snapshot"])
        odds = json.loads(odds_row["snapshot_json"])
        inference_at = _time(analysis["created_at"]); kickoff = _time(request["kickoff_utc"])
        captured = _time(odds["captured_at_utc"]); selected_at = _time(odds["source_selected_at_utc"]); sealed = _time(odds["sealed_at_utc"])
        if request["match_id"] != odds["canonical_fixture_id"]: raise ForwardTestValidationError("Fixture identity conflict.")
        if captured >= kickoff: raise ForwardTestValidationError("ODDS_CAPTURE_AFTER_KICKOFF")
        if captured > inference_at or sealed > inference_at: raise ForwardTestValidationError("ODDS_CAPTURED_AFTER_INFERENCE")
        if selected_at > captured: raise ForwardTestValidationError("ODDS_SOURCE_CHANGED_AFTER_INFERENCE")
        if int((inference_at - captured).total_seconds()) > 900: raise ForwardTestValidationError("STALE_CURRENT_ODDS")
        _match_analysis_odds(request.get("odds", []), odds)
        evidence = result.get("evidence") or {}; evaluations = tuple(evidence.get("evaluations") or ())
        quality = evidence.get("calibration_quality_report") or {"status": "CALIBRATION_QUALITY_NOT_EVALUATED"}
        shift = quality.get("distribution_shift") or {"status": "DISTRIBUTION_SHIFT_NOT_EVALUATED"}
        status = ObservationStatus.ANALYSIS_COMPLETED if analysis["status"] == "COMPLETED" else ObservationStatus.NO_SELECTION if analysis["status"] == "NO_SELECTION" else ObservationStatus.BLOCKED
        selected_market = analysis["selected_market"]
        selected_eval = next((item for item in evaluations if item.get("market") == selected_market), None)
        actionable = bool(selected_eval and selected_eval.get("actionable") is True)
        rejection = tuple(result.get("rejection_reasons") or ())
        request_material = {"request_id": request_id, "analysis_id": analysis_id, "odds_snapshot_id": odds_snapshot_id, "analysis_result_fingerprint": analysis["result_fingerprint"], "odds_snapshot_fingerprint": odds_row["snapshot_fingerprint"]}
        request_fp = fingerprint(request_material)
        material = dict(
            schema_version=OBSERVATION_SCHEMA_VERSION, evidence_tier=EVIDENCE_TIER,
            request_id=request_id, request_fingerprint=request_fp, analysis_id=analysis_id,
            analysis_result_fingerprint=analysis["result_fingerprint"], odds_snapshot_id=odds_snapshot_id,
            odds_snapshot_fingerprint=odds_row["snapshot_fingerprint"], canonical_fixture_id=request["match_id"],
            fixture_snapshot_fingerprint=fingerprint(request.get("match_snapshot")),
            feature_snapshot_fingerprint=evidence.get("feature_fingerprint"), model_input_fingerprint=evidence.get("model_input_fingerprint"),
            model_artifact_id=evidence.get("model_artifact_id"), model_artifact_fingerprint=evidence.get("model_artifact_fingerprint"),
            calibration_id=evidence.get("calibration_set_id"), calibration_fingerprint=evidence.get("calibration_fingerprint"),
            calibration_quality=quality, distribution_shift=shift,
            raw_probability_fingerprint=fingerprint(tuple((item.get("market"), item.get("raw_probability")) for item in evaluations)) if evaluations else None,
            calibrated_probability_fingerprint=fingerprint(tuple((item.get("market"), item.get("calibrated_probability")) for item in evaluations)) if evaluations else None,
            market_evaluations=evaluations, mathematical_top_market=evidence.get("mathematically_top_ranked_market"),
            actionable_market=selected_market if actionable else None, status=status,
            analysis_completed=analysis["status"] in {"COMPLETED", "NO_SELECTION"}, actionable=actionable,
            forward_test_recorded=True, preview_available=bool(analysis["message_html"]),
            lab_send_eligible=False, official_eligible=False, message_preview=analysis["message_html"],
            message_fingerprint=analysis["message_fingerprint"], rejection_reasons=rejection,
            inference_at_utc=inference_at, created_at_utc=inference_at,
        )
        observation_fp = fingerprint(material)
        observation = ForwardTestObservation(observation_id="forward-test-observation-" + observation_fp, **material, observation_fingerprint=observation_fp)
        self.repository.append_observation(observation)
        return observation

    def record_result(self, observation_id: str, raw: object) -> ForwardTestResult:
        observation = self.repository.load_observation(observation_id)
        if observation is None: raise ForwardTestValidationError("Forward-test observation not found.")
        if not isinstance(raw, dict) or raw.get("schema_version") != RESULT_SCHEMA_VERSION: raise ForwardTestValidationError("Unsupported result schema.")
        fixture = _text(raw.get("fixture_id"), "fixture_id"); status = _text(raw.get("final_status"), "final_status").upper()
        retrieved = _time(raw.get("result_retrieval_timestamp_utc")); kickoff = _fixture_kickoff(self.repository.connection, observation["analysis_id"])
        if fixture != observation["canonical_fixture_id"]: raise ForwardTestValidationError("Result fixture identity conflict.")
        if retrieved <= kickoff: raise ForwardTestValidationError("Result cannot be recorded before kickoff.")
        if status not in COMPLETED_RESULT_STATUSES: raise ForwardTestValidationError("Result status is not completed.")
        home, away = raw.get("final_home_score"), raw.get("final_away_score")
        if type(home) is not int or type(away) is not int or not 0 <= home <= 30 or not 0 <= away <= 30: raise ForwardTestValidationError("Final score is invalid.")
        material = {"schema_version": RESULT_SCHEMA_VERSION, "observation_id": observation_id, "fixture": fixture, "home": home, "away": away, "status": status, "source": _text(raw.get("result_source"), "result_source"), "retrieved": retrieved, "provenance": _text(raw.get("provenance"), "provenance", 2000)}
        fp = fingerprint(material)
        value = ForwardTestResult("forward-test-result-" + fp, RESULT_SCHEMA_VERSION, observation_id, fixture, home, away, status, material["source"], retrieved, material["provenance"], fp)
        self.repository.append_result(value); return value

    def settle(self, observation_id: str, *, settled_at_utc: datetime | None = None) -> ForwardTestSettlement:
        observation = self.repository.load_observation(observation_id); result_row = self.repository.load_result(observation_id)
        if observation is None or result_row is None: raise ForwardTestValidationError("Observation and final result are required.")
        obs = json.loads(observation["observation_json"]); result = json.loads(result_row["result_json"])
        market = obs.get("actionable_market")
        evaluation = next((item for item in obs.get("market_evaluations", []) if item.get("market") == market), None)
        if market is None or evaluation is None: outcome = SettlementOutcome.NOT_APPLICABLE; odds = None; net = Decimal("0"); reason = "NO_ACTIONABLE_SELECTION"
        else:
            won = _won(market, result["final_home_score"], result["final_away_score"])
            outcome = SettlementOutcome.WON if won else SettlementOutcome.LOST; odds = Decimal(str(evaluation["bookmaker_odds"])); net = odds - 1 if won else Decimal("-1"); reason = f"{market}_{outcome.value}"
        settled = _time(settled_at_utc or datetime.now(timezone.utc)); material = {"observation_id": observation_id, "result_id": result_row["result_id"], "market": market, "outcome": outcome, "odds": odds, "flat_stake": Decimal("1"), "net": net, "reason": reason, "settled": settled}
        fp = fingerprint(material)
        value = ForwardTestSettlement("forward-test-settlement-" + fp, observation_id, result_row["result_id"], market, outcome, odds, Decimal("1"), net, reason, settled, fp)
        self.repository.append_settlement(value); return value


def _match_analysis_odds(analysis_odds, snapshot):
    current = {item["market"]: item for item in snapshot["quotes"]}
    if set(current) != {item.get("market") for item in analysis_odds}: raise ForwardTestValidationError("ODDS_QUOTE_REPLACEMENT_CONFLICT")
    for old in analysis_odds:
        new = current[old["market"]]
        if old.get("source_provider") != new["provider_source_id"] or old.get("bookmaker_id") != new["bookmaker_name"] or old.get("source_event_id") != new["provider_event_id"]: raise ForwardTestValidationError("ODDS_SOURCE_CHANGED_AFTER_INFERENCE")
        if Decimal(str(old.get("decimal_odds"))) != Decimal(str(new["decimal_odds"])) or _time(old.get("captured_at")) != _time(new["captured_at_utc"]): raise ForwardTestValidationError("ODDS_QUOTE_REPLACEMENT_CONFLICT")


def _fixture_kickoff(connection, analysis_id): return _time(connection.execute("SELECT kickoff_utc FROM real_match_lab_analyses WHERE analysis_id=?", (analysis_id,)).fetchone()[0])
def _time(value):
    if isinstance(value, datetime): parsed = value
    else: parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None: raise ForwardTestValidationError("Timestamp offset is required.")
    return parsed.astimezone(timezone.utc)
def _text(value, label, maximum=512):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum: raise ForwardTestValidationError(f"{label} is required text.")
    return " ".join(value.strip().split())
def _won(market, home, away):
    total = home + away
    return {"HOME_WIN": home > away, "DRAW": home == away, "AWAY_WIN": away > home, "OVER_1_5": total > 1, "UNDER_1_5": total < 2, "OVER_2_5": total > 2, "UNDER_2_5": total < 3, "OVER_3_5": total > 3, "UNDER_3_5": total < 4, "BTTS_YES": home > 0 and away > 0, "BTTS_NO": home == 0 or away == 0}[market]
