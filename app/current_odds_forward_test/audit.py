"""Read-only integrity audit for one forward-test observation chain."""

from __future__ import annotations

import json
from datetime import datetime

from app.real_match_lab_analysis.fingerprint import fingerprint

from .models import ForwardTestIntegrityReport, ForwardTestIntegrityStatus
from .repository import SQLiteForwardTestRepository
from .service import _won


def audit_observation(repository: SQLiteForwardTestRepository, observation_id: str) -> ForwardTestIntegrityReport:
    row = repository.load_observation(observation_id)
    if row is None: raise ValueError("Forward-test observation not found.")
    observation = json.loads(row["observation_json"]); odds = json.loads(repository.load_odds(row["odds_snapshot_id"])["snapshot_json"])
    analysis = repository.connection.execute("SELECT * FROM real_match_lab_analyses WHERE analysis_id=?", (row["analysis_id"],)).fetchone()
    result = repository.load_result(observation_id); settlement = repository.load_settlement(observation_id)
    checks = [
        ("FIXTURE_SELECTED_BEFORE_INFERENCE", datetime.fromisoformat(odds["source_selected_at_utc"]) <= datetime.fromisoformat(observation["inference_at_utc"])),
        ("ODDS_CAPTURED_BEFORE_INFERENCE", datetime.fromisoformat(odds["captured_at_utc"]) <= datetime.fromisoformat(observation["inference_at_utc"])),
        ("ODDS_CAPTURED_BEFORE_KICKOFF", datetime.fromisoformat(odds["captured_at_utc"]) < datetime.fromisoformat(odds["kickoff_utc"])),
        ("SOURCE_CHOSEN_BEFORE_CAPTURE", datetime.fromisoformat(odds["source_selected_at_utc"]) <= datetime.fromisoformat(odds["captured_at_utc"])),
        ("MODEL_PROVENANCE_COMPLETE", bool(observation.get("model_artifact_id") and observation.get("model_artifact_fingerprint"))),
        ("CALIBRATION_PROVENANCE_COMPLETE", bool(observation.get("calibration_id") and observation.get("calibration_fingerprint"))),
        ("CALIBRATION_QUALITY_RECORDED", bool(observation.get("calibration_quality"))),
        ("DISTRIBUTION_SHIFT_RECORDED", bool(observation.get("distribution_shift"))),
        ("LAB_SEND_NOT_AUTHORIZED", observation.get("lab_send_eligible") is False),
        ("OFFICIAL_NOT_AUTHORIZED", observation.get("official_eligible") is False),
        ("FORWARD_TEST_TIER_ISOLATED", observation.get("evidence_tier") == "FORWARD_TEST_REAL_TIME"),
        ("NO_TELEGRAM_DELIVERY", repository.connection.execute("SELECT COUNT(*) FROM real_match_lab_deliveries WHERE analysis_id=?", (row["analysis_id"],)).fetchone()[0] == 0),
    ]
    if result is not None:
        result_value = json.loads(result["result_json"])
        checks.append(("RESULT_APPENDED_AFTER_KICKOFF", datetime.fromisoformat(result_value["result_retrieval_timestamp_utc"]) > datetime.fromisoformat(odds["kickoff_utc"])))
    if settlement is not None:
        settlement_value = json.loads(settlement["settlement_json"]); market = settlement_value.get("market")
        expected = "NOT_APPLICABLE" if market is None else "WON" if _won(market, result_value["final_home_score"], result_value["final_away_score"]) else "LOST"
        checks.append(("DETERMINISTIC_SETTLEMENT", settlement_value["outcome"] == expected))
    blockers = tuple(name for name, passed in checks if not passed)
    if blockers: status = ForwardTestIntegrityStatus.FORWARD_TEST_INTEGRITY_BLOCKED
    elif result is None or settlement is None: status = ForwardTestIntegrityStatus.FORWARD_TEST_RESULT_PENDING
    else: status = ForwardTestIntegrityStatus.FORWARD_TEST_INTEGRITY_PASSED
    raw = {"status": status, "observation_id": observation_id, "checks": tuple(checks), "blocker_codes": blockers}
    return ForwardTestIntegrityReport(**raw, report_fingerprint=fingerprint(raw))
