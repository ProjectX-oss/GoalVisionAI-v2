"""Explicit bounded First-Lab dry-run orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Awaitable, Callable
from types import SimpleNamespace

from app.real_match_lab_analysis.input import parse_input

from .input import parse_current_odds
from .operations import FirstLabOperationsRepository, build_lab_preview
from .repository import SQLiteForwardTestRepository
from .service import ForwardTestService


class FirstLabDryRunWorkflow:
    """Coordinate existing services and stop unconditionally before Telegram."""

    def __init__(
        self,
        operations: FirstLabOperationsRepository,
        forward_tests: SQLiteForwardTestRepository,
        analyze: Callable[[object], object],
    ) -> None:
        self.operations = operations
        self.forward_tests = forward_tests
        self.forward_service = ForwardTestService(forward_tests)
        self.analyze = analyze

    async def run(
        self, *, run_id: str, readiness: dict,
        discover: Callable[[], Awaitable[dict]], parameters: dict,
        now: datetime | None = None, mode: str = "GENUINE",
    ) -> dict:
        clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self.operations.begin(run_id, parameters, mode=mode, occurred_at=clock)
        prior = {item["stage_name"]: item for item in self.operations.stages(run_id)}
        if "TERMINAL_COMPLETED" in prior:
            observation_id = prior["TERMINAL_COMPLETED"]["artifact_snapshot"]["observation_id"]
            preview = prior["PREVIEW_CREATED"]["artifact_snapshot"]
            analysis_id = prior["ANALYSIS_COMPLETED"]["artifact_snapshot"]["analysis_id"]
            return {**self._summary(run_id, "FIRST_LAB_DRY_RUN_COMPLETED"), "analysis_id": analysis_id, "observation_id": observation_id, "preview": preview, "recovered": True}
        if "READINESS_CHECKED" not in prior:
            self.operations.stage(run_id, "READINESS_CHECKED", "PASSED" if readiness.get("ready_for_genuine_forward_test") else "BLOCKED", readiness, occurred_at=clock, artifact_type="PRO_READINESS")
        if not readiness.get("ready_for_genuine_forward_test"):
            self.operations.stage(run_id, "TERMINAL_BLOCKED", "BLOCKED", {"reason": readiness.get("status")}, occurred_at=clock)
            return self._summary(run_id, readiness.get("status", "PRO_PLAN_REQUIRED"))
        if "CAPABILITIES_RESOLVED" not in prior:
            self.operations.stage(run_id, "CAPABILITIES_RESOLVED", "PASSED", readiness.get("capability_cache"), occurred_at=clock, artifact_type="CAPABILITY_CACHE")
        if "CANDIDATE_SELECTED" in prior:
            selected = prior["CANDIDATE_SELECTED"]["artifact_snapshot"]
            discovery = None
        else:
            discovery = await discover()
            self.operations.stage(run_id, "FIXTURES_DISCOVERED", "PASSED", {"terminal_result": discovery.get("terminal_result"), "candidate_count": discovery.get("candidate_fixture_count"), "request_count": discovery.get("api_call_count")}, occurred_at=clock, artifact_type="DISCOVERY")
            selected = discovery.get("selected_fixture")
        if selected is None:
            assert discovery is not None
            self.operations.stage(run_id, "TERMINAL_BLOCKED", "BLOCKED", {"reason": discovery.get("terminal_result", "NO_ELIGIBLE_CURRENT_FIXTURE")}, occurred_at=clock)
            return self._summary(run_id, discovery.get("terminal_result", "NO_ELIGIBLE_CURRENT_FIXTURE"))
        if "CANDIDATE_SELECTED" not in prior:
            self.operations.stage(run_id, "CANDIDATE_SELECTED", "PASSED", selected, occurred_at=clock, artifact_type="FIXTURE", artifact_id=str(selected["provider_fixture_id"]))
        baseline = selected.get("feature_baseline") or {}
        self.operations.stage(run_id, "BASELINES_CAPTURED", "PASSED", baseline, occurred_at=clock, artifact_type="FEATURE_BASELINE")
        # Revalidate freshness at this execution/recovery boundary.  A prior
        # immutable snapshot may be reused only while its quote remains fresh.
        odds = parse_current_odds(selected["odds_contract"], now=clock)
        self.forward_service.capture_odds(odds)
        self.operations.stage(run_id, "ODDS_CAPTURED", "PASSED", {"snapshot_id": odds.snapshot_id, "fingerprint": odds.snapshot_fingerprint, "freshness": odds.freshness_status}, occurred_at=clock, artifact_type="ODDS_SNAPSHOT", artifact_id=odds.snapshot_id)
        raw = _analysis_input(run_id, selected, odds)
        command = parse_input(raw, now=clock)
        self.operations.stage(run_id, "INPUT_SEALED", "PASSED", raw, occurred_at=clock, artifact_type="REAL_MATCH_LAB_INPUT", artifact_id=command.request_id)
        if "ANALYSIS_COMPLETED" in prior:
            saved = prior["ANALYSIS_COMPLETED"]["artifact_snapshot"]
            analysis = SimpleNamespace(analysis_id=saved["analysis_id"], status=SimpleNamespace(value=saved["status"]), result_fingerprint=saved["result_fingerprint"])
        else:
            analysis = self.analyze(command)
            self.operations.stage(run_id, "ANALYSIS_COMPLETED", "PASSED" if analysis.status.value in {"COMPLETED", "NO_SELECTION"} else "BLOCKED", {"analysis_id": analysis.analysis_id, "status": analysis.status.value, "result_fingerprint": analysis.result_fingerprint}, occurred_at=clock, artifact_type="REAL_MATCH_LAB_ANALYSIS", artifact_id=analysis.analysis_id)
        observation = self.forward_service.create_observation("forward-test-" + run_id, analysis.analysis_id, odds.snapshot_id)
        self.operations.stage(run_id, "OBSERVATION_CREATED", "PASSED", {"observation_id": observation.observation_id, "fingerprint": observation.observation_fingerprint}, occurred_at=clock, artifact_type="FORWARD_TEST_OBSERVATION", artifact_id=observation.observation_id)
        preview = build_lab_preview(_asdict(observation), raw, _asdict(odds))
        self.operations.stage(run_id, "PREVIEW_CREATED", "PASSED", preview, occurred_at=clock, artifact_type="LAB_PREVIEW", artifact_id=preview["preview_fingerprint"])
        self.operations.stage(run_id, "TERMINAL_COMPLETED", "COMPLETED", {"observation_id": observation.observation_id, "telegram_send_executed": False}, occurred_at=clock)
        return {**self._summary(run_id, "FIRST_LAB_DRY_RUN_COMPLETED"), "analysis_id": analysis.analysis_id, "observation_id": observation.observation_id, "preview": preview}

    def _summary(self, run_id: str, status: str) -> dict:
        return {"schema_version": "goalvision-first-lab-dry-run-output-v1", "status": status, "run_id": run_id, "stages": self.operations.stages(run_id), "telegram_send_executed": False, "delivery_records_created": 0, "official_publications_created": 0, "scheduling_enabled": False}


def _analysis_input(run_id, selected, odds) -> dict:
    baseline = selected["feature_baseline"]
    collected = odds.sealed_at_utc.isoformat()
    return {
        "schema_version": "goalvision-real-match-lab-input-v1", "request_id": "real-match-lab-" + run_id,
        "environment": "LAB", "scope": "OFFICIAL_GLOBAL", "operator_identity": "FIRST_LAB_OPERATOR",
        "match_id": str(selected["provider_fixture_id"]), "competition_id": str(selected["competition_id"]),
        "competition": selected["competition"], "season": str(selected["season"]),
        "home_team_id": str(selected["home_team_id"]), "home_team": selected["home_team"],
        "away_team_id": str(selected["away_team_id"]), "away_team": selected["away_team"],
        "kickoff_utc": selected["kickoff_utc"], "collected_at": collected,
        "source_updated_at": selected.get("provider_update_timestamp_utc") or collected,
        "source_provider": "API_FOOTBALL", "source_event_id": str(selected["provider_fixture_id"]),
        "source_snapshot_id": "fixture-" + str(selected["provider_fixture_id"]),
        "data": {"home_recent_form": baseline["home_recent_form"], "away_recent_form": baseline["away_recent_form"], "venue": selected.get("venue_name")},
        "odds": [{"snapshot_id": quote.quote_id, "market": quote.market, "decimal_odds": str(quote.decimal_odds), "source_provider": quote.provider_source_id, "bookmaker_id": quote.bookmaker_name, "source_event_id": quote.provider_event_id, "captured_at": quote.captured_at_utc.isoformat()} for quote in odds.quotes],
        "operator_notes": "Explicit bounded First Lab dry-run; no Telegram send authorized.",
    }


def _asdict(value):
    from app.real_match_lab_analysis.fingerprint import canonical_json
    import json
    return json.loads(canonical_json(value))


def _time(value):
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)
