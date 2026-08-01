"""Deterministic, read-only calculations and explicit append operations."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from typing import Any, Iterable

from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint

from .models import Finding
from .policy import DEFAULT_POLICY, ForwardTestReportingPolicy
from .repository import SQLiteMonitoringRepository

_UTC = timezone.utc
_CANONICAL_MARKETS = frozenset({"HOME_WIN", "DRAW", "AWAY_WIN", "OVER_1_5", "UNDER_1_5", "OVER_2_5", "UNDER_2_5", "OVER_3_5", "UNDER_3_5", "BTTS_YES", "BTTS_NO"})


def _dt(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("UTC timestamp must be timezone-aware.")
    return parsed.astimezone(_UTC)


def _d(value: Any, default: str = "0") -> Decimal:
    return Decimal(default) if value is None else Decimal(str(value))


def _avg(values: Iterable[Decimal]) -> Decimal | None:
    items = tuple(values)
    return sum(items, Decimal(0)) / Decimal(len(items)) if items else None


def _median(values: Iterable[Decimal]) -> Decimal | None:
    items = sorted(values)
    if not items:
        return None
    middle = len(items) // 2
    return items[middle] if len(items) % 2 else (items[middle - 1] + items[middle]) / Decimal(2)


def _safe_ratio(numerator: Decimal | int, denominator: Decimal | int) -> Decimal | None:
    return Decimal(numerator) / Decimal(denominator) if denominator else None


def _event_time(table: str) -> str:
    return {"forward_test_results": "result_retrieval_timestamp_utc", "forward_test_settlements": "settled_at_utc"}.get(table, "created_at_utc")


class MonitoringService:
    """Builds evidence without networking, scheduling, Telegram, or Official writes."""

    def __init__(self, repository: SQLiteMonitoringRepository, policy: ForwardTestReportingPolicy = DEFAULT_POLICY) -> None:
        self.repository = repository
        self.connection = repository.connection
        self.policy = policy

    def lifecycle_audit(self, observation_id: str, cutoff_utc: datetime, *, persist: bool = False) -> dict[str, Any]:
        cutoff = _dt(cutoff_utc)
        row = self.connection.execute("SELECT * FROM forward_test_observations WHERE observation_id=?", (observation_id,)).fetchone()
        if row is None:
            raise ValueError("Forward-test observation not found.")
        observation = json.loads(row["observation_json"])
        odds_row = self.connection.execute("SELECT * FROM forward_test_odds_snapshots WHERE odds_snapshot_id=?", (row["odds_snapshot_id"],)).fetchone()
        analysis = self.connection.execute("SELECT * FROM real_match_lab_analyses WHERE analysis_id=?", (row["analysis_id"],)).fetchone()
        result = self.connection.execute("SELECT * FROM forward_test_results WHERE observation_id=?", (observation_id,)).fetchone()
        settlement = self.connection.execute("SELECT * FROM forward_test_settlements WHERE observation_id=?", (observation_id,)).fetchone()
        findings: list[Finding] = []

        def add(code: str, severity: str, detail: str, provenance: str = "FORWARD_TEST_CHAIN") -> None:
            findings.append(Finding(code, severity, observation_id, provenance, detail))

        if analysis is None: add("ORPHAN_OBSERVATION", "CORRUPT", "Linked Real Match Lab analysis is absent.")
        if odds_row is None: add("ORPHAN_ODDS_SNAPSHOT", "CORRUPT", "Linked immutable odds snapshot is absent.")
        if odds_row is not None:
            odds = json.loads(odds_row["snapshot_json"])
            kickoff, captured, inference = _dt(odds["kickoff_utc"]), _dt(odds["captured_at_utc"]), _dt(observation["inference_at_utc"])
            selected = observation.get("actionable_market")
            quotes = [q for q in odds.get("quotes", ()) if q.get("market") == selected]
            evaluations = [e for e in observation.get("market_evaluations", ()) if e.get("market") == selected]
            if not _dt(odds["source_selected_at_utc"]) <= captured: add("SOURCE_SELECTED_AFTER_CAPTURE", "BLOCKING", "Odds source selection occurred after capture.")
            if not captured <= inference: add("ODDS_CAPTURED_AFTER_INFERENCE", "CORRUPT", "Odds did not predate inference.")
            if not inference < kickoff: add("FIXTURE_NOT_UPCOMING_AT_OBSERVATION", "BLOCKING", "Inference was not before kickoff.")
            if not captured < kickoff: add("ODDS_CAPTURED_AFTER_KICKOFF", "CORRUPT", "Odds did not predate kickoff.")
            if (inference - captured).total_seconds() > self.policy.odds_fresh_seconds: add("ODDS_CAPTURE_STALE", "BLOCKING", "Capture exceeded the policy freshness window.")
            if odds.get("canonical_fixture_id") != row["canonical_fixture_id"]: add("FIXTURE_IDENTITY_CONFLICT", "CORRUPT", "Observation and odds fixture identities differ.")
            if not odds.get("bookmaker_name"): add("BOOKMAKER_IDENTITY_MISSING", "BLOCKING", "Bookmaker identity is absent.")
            if selected and not quotes: add("SELECTED_MARKET_NOT_IN_ODDS", "CORRUPT", "Selected market is absent from the sealed snapshot.")
            if selected and evaluations and quotes and _d(evaluations[0].get("bookmaker_odds")) != _d(quotes[0].get("decimal_odds")): add("SELECTED_PRICE_MISMATCH", "CORRUPT", "Evaluation price differs from sealed quote.")
            if selected not in _CANONICAL_MARKETS and selected is not None: add("NON_CANONICAL_MARKET", "BLOCKING", "Selected market is not an allowed single market.")
            if selected and ("SCORE" in selected or "COMBO" in selected): add("PROHIBITED_MARKET", "CORRUPT", "Correct-score and combo markets are prohibited.")
            if any(q.get("provider_origin_timestamp_utc") is None for q in odds.get("quotes", ())): add("ODDS_TIMESTAMP_PROVIDER_MISSING", "WARNING", "At least one quote has no provider-origin timestamp.", odds.get("provider_source_id", "UNKNOWN"))
        if observation.get("evidence_tier") not in self.policy.accepted_evidence_tiers: add("FORWARD_TEST_SOURCE_UNSUPPORTED", "BLOCKING", "Evidence tier is not accepted by reporting policy.")
        feature_fingerprint = observation.get("feature_snapshot_fingerprint")
        if not feature_fingerprint: add("FEATURE_FINGERPRINT_MISSING", "BLOCKING", "Feature fingerprint is absent.")
        else:
            feature_row = self.connection.execute("SELECT deterministic_feature_snapshot,feature_fingerprint FROM match_feature_sets WHERE feature_fingerprint=?", (feature_fingerprint,)).fetchone()
            if feature_row is None: add("FEATURE_VECTOR_UNVERIFIABLE", "WARNING", "The Real Match Lab fingerprint is retained, but its feature-set row is unavailable to recount.", "REAL_MATCH_LAB")
            else:
                feature_value = json.loads(feature_row["deterministic_feature_snapshot"])
                features = feature_value.get("features", feature_value) if isinstance(feature_value, dict) else feature_value
                if not isinstance(features, (dict, list)) or len(features) != 78: add("FEATURE_SCHEMA_COUNT_MISMATCH", "CORRUPT", f"Expected 78 features, found {len(features) if isinstance(features,(dict,list)) else 'invalid'}.", feature_fingerprint)
        if not observation.get("model_artifact_id") or not observation.get("model_artifact_fingerprint"): add("MODEL_ARTIFACT_MISMATCH", "BLOCKING", "Model provenance is incomplete.")
        if not observation.get("calibration_id") or not observation.get("calibration_fingerprint"): add("CALIBRATION_ARTIFACT_MISMATCH", "BLOCKING", "Calibration provenance is incomplete.")
        if not observation.get("calibration_quality"): add("CALIBRATION_QUALITY_MISSING", "BLOCKING", "Calibration-quality evidence is absent.")
        shift = observation.get("distribution_shift") or {}
        if not shift: add("DISTRIBUTION_SHIFT_MISSING", "BLOCKING", "Distribution-shift evidence is absent.")
        elif "BLOCK" in str(shift.get("status", "")): add("DISTRIBUTION_SHIFT_BLOCKING", "BLOCKING", "Distribution shift is blocking.")
        for evaluation in observation.get("market_evaluations", ()):
            probability = _d(evaluation.get("calibrated_probability"), "-1")
            if not self.policy.probability_minimum <= probability <= self.policy.probability_maximum: add("PROBABILITY_CONTRACT_INVALID", "CORRUPT", f"Invalid calibrated probability for {evaluation.get('market')}.")
        deliveries = self.connection.execute("SELECT * FROM real_match_lab_deliveries WHERE analysis_id=? ORDER BY occurred_at", (row["analysis_id"],)).fetchall()
        reviews = self.connection.execute("SELECT * FROM forward_test_publication_reviews WHERE observation_id=? ORDER BY reviewed_at_utc", (observation_id,)).fetchall()
        sent = [delivery for delivery in deliveries if delivery["status"] == "SENT"]
        if sent and not reviews: add("PUBLISHED_WITHOUT_REVIEW", "CORRUPT", "A Lab delivery exists without publication review.")
        for delivery in sent:
            if delivery["destination_chat_id"] != "-1003510920417": add("PUBLICATION_DESTINATION_NOT_LAB", "CORRUPT", "Delivery destination is not the fixed Lab channel.")
            if delivery["message_fingerprint"] != observation.get("message_fingerprint"): add("TELEGRAM_MESSAGE_FINGERPRINT_MISMATCH", "CORRUPT", "Delivery and observation message fingerprints differ.")
        if observation.get("official_eligible") or observation.get("lab_send_eligible"): add("PUBLICATION_BOUNDARY_VIOLATION", "CORRUPT", "Forward-test record claims publication eligibility.")
        if result is None and odds_row is not None and cutoff > _dt(odds["kickoff_utc"]) + self._hours(self.policy.missing_result_hours):
            add("RESULT_OVERDUE", "WARNING", "No final result exists after the policy grace period.")
        if result is not None:
            result_json = json.loads(result["result_json"])
            if result["canonical_fixture_id"] != row["canonical_fixture_id"]: add("RESULT_IDENTITY_CONFLICT", "CORRUPT", "Result fixture identity differs.")
            if odds_row is not None and _dt(result["result_retrieval_timestamp_utc"]) <= _dt(odds["kickoff_utc"]): add("RESULT_CAPTURED_BEFORE_COMPLETION", "CORRUPT", "Result was captured before kickoff.")
            if settlement is None and cutoff - _dt(result["result_retrieval_timestamp_utc"]) > self._hours(self.policy.delayed_settlement_hours): add("SETTLEMENT_OVERDUE", "WARNING", "Completed result remains unsettled.")
            if settlement is not None:
                settlement_json = json.loads(settlement["settlement_json"])
                expected = self._expected_outcome(settlement_json.get("market"), int(result_json["final_home_score"]), int(result_json["final_away_score"]))
                if settlement_json.get("outcome") != expected: add("SETTLEMENT_RULE_MISMATCH", "CORRUPT", f"Expected {expected}, found {settlement_json.get('outcome')}.")
                if settlement["result_id"] != result["result_id"]: add("SETTLEMENT_RESULT_CONFLICT", "CORRUPT", "Settlement links another result.")
        duplicate = self.connection.execute("SELECT COUNT(*) FROM forward_test_observations WHERE canonical_fixture_id=?", (row["canonical_fixture_id"],)).fetchone()[0]
        if duplicate > 1: add("DUPLICATE_OBSERVATION", "BLOCKING", f"Fixture has {duplicate} observations.")
        severities = {item.severity for item in findings}
        status = "LIFECYCLE_AUDIT_CORRUPT" if "CORRUPT" in severities else "LIFECYCLE_AUDIT_BLOCKED" if "BLOCKING" in severities else "LIFECYCLE_AUDIT_WARNING" if "WARNING" in severities else "LIFECYCLE_AUDIT_PASSED"
        raw = {"schema_version": "goalvision-forward-test-lifecycle-audit-v1", "observation_id": observation_id, "cutoff_utc": cutoff.isoformat(), "status": status, "findings": [self._finding(item) for item in findings], "checks_defined": 35, "official_bankroll_mutations": 0, "official_statistics_mutations": 0, "created_at_utc": cutoff.isoformat()}
        raw["audit_fingerprint"] = fingerprint(raw)
        raw["audit_id"] = "forward-test-audit-" + raw["audit_fingerprint"]
        if persist: self.repository.append_audit(raw)
        return raw

    def data_quality(self, cutoff_utc: datetime, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        cutoff = _dt(cutoff_utc); bundle = rows or self._source_rows(cutoff, None)
        findings: list[Finding] = []
        observations = bundle["observations"]
        for item in observations:
            observation, odds = item["observation"], item["odds"]
            identifier = observation["observation_id"]
            def add(code, severity, detail, provenance="OBSERVATION"): findings.append(Finding(code, severity, identifier, provenance, detail))
            evaluations = observation.get("market_evaluations", ())
            if not observation.get("feature_snapshot_fingerprint"): add("REQUIRED_FEATURE_MISSING", "BLOCKING", "Feature snapshot fingerprint is missing.")
            if len(evaluations) < 11: add("OPTIONAL_FEATURES_LOW_COMPLETENESS", "WARNING", f"Only {len(evaluations)} of 11 market evaluations exist.")
            if odds:
                quote_markets = [q.get("market") for q in odds.get("quotes", ())]
                if len(quote_markets) != len(set(quote_markets)): add("DUPLICATE_ODDS", "WARNING", "Sealed snapshot repeats a market.", odds.get("snapshot_id", "ODDS"))
                if len(set(quote_markets)) < 11: add("BOOKMAKER_MARKETS_INCOMPLETE", "WARNING", f"Bookmaker covers {len(set(quote_markets))} of 11 markets.", odds.get("bookmaker_name", "UNKNOWN"))
            for evaluation in evaluations:
                probability, ev = _d(evaluation.get("calibrated_probability")), _d(evaluation.get("expected_value"))
                if probability <= self.policy.extreme_probability_low or probability >= self.policy.extreme_probability_high: add("EXTREME_CALIBRATED_PROBABILITY", "WARNING", f"{evaluation.get('market')}={probability}.")
                if abs(ev) >= self.policy.extreme_ev_absolute: add("EXTREME_EXPECTED_VALUE", "WARNING", f"{evaluation.get('market')} EV={ev}.")
            result_probs = [_d(e.get("calibrated_probability")) for e in evaluations if e.get("market") in {"HOME_WIN", "DRAW", "AWAY_WIN"}]
            if len(result_probs) == 3 and abs(sum(result_probs) - Decimal(1)) > Decimal("0.000001"): add("MATCH_RESULT_SIMPLEX_INCONSISTENT", "BLOCKING", f"1X2 sum={sum(result_probs)}.")
            totals = {e.get("market"): _d(e.get("calibrated_probability")) for e in evaluations}
            if all(k in totals for k in ("OVER_1_5", "OVER_2_5", "OVER_3_5")) and not totals["OVER_1_5"] >= totals["OVER_2_5"] >= totals["OVER_3_5"]: add("TOTALS_MONOTONICITY_INCONSISTENT", "BLOCKING", "Over probabilities are not monotone.")
        counts = Counter(item.severity for item in findings)
        return {"schema_version": "goalvision-forward-test-data-quality-v1", "cutoff_utc": cutoff.isoformat(), "status": "DATA_QUALITY_BLOCKED" if counts["CORRUPT"] or counts["BLOCKING"] else "DATA_QUALITY_WARNING" if counts["WARNING"] else "DATA_QUALITY_PASSED", "finding_counts": dict(sorted(counts.items())), "findings": [self._finding(item) for item in sorted(findings, key=lambda x: (x.severity, x.code, x.affected_identifier))], "finding_fingerprint": fingerprint([self._finding(item) for item in findings])}

    def snapshot(self, cutoff_utc: datetime, *, generated_at_utc: datetime | None = None, persist: bool = True) -> dict[str, Any]:
        cutoff = _dt(cutoff_utc); generated = _dt(generated_at_utc or cutoff)
        rows = self._source_rows(cutoff, None); quality = self.data_quality(cutoff, rows)
        audits = [self.lifecycle_audit(item["observation"]["observation_id"], cutoff) for item in rows["observations"]]
        observations = [item["observation"] for item in rows["observations"]]
        settlements = rows["settlements"]
        source_fingerprints = sorted(set(
            [item["observation"].get("observation_fingerprint", "") for item in rows["observations"]]
            + [item["odds"].get("snapshot_fingerprint", "") for item in rows["observations"] if item["odds"]]
            + [item.get("result_fingerprint", "") for item in rows["results"]]
            + [item.get("settlement_fingerprint", "") for item in settlements]
        ))
        source_fingerprints = [item for item in source_fingerprints if item]
        source_fp = fingerprint(source_fingerprints)
        db_identity = self._database_identity()
        raw = {
            "schema_version": "goalvision-forward-test-monitoring-snapshot-v1", "requested_cutoff_utc": cutoff.isoformat(), "generated_at_utc": generated.isoformat(),
            "reporting_timezone": self.policy.timezone, "policy_id": self.policy.policy_id, "policy_version": self.policy.version,
            "source_database_identity": db_identity, "source_fingerprint": source_fp,
            "counts": {"observations": len(observations), "analyses": len(observations), "previews": sum(bool(o.get("preview_available")) for o in observations), "publication_reviews": len(rows["reviews"]), "published": rows["published_count"], "unpublished": len(observations) - rows["published_count"], "results": len(rows["results"]), "settled": len(settlements), "pending_results": len(observations) - len(rows["results"]), "blocked": sum(o.get("status") == "BLOCKED" for o in observations), "no_selection": sum(o.get("status") == "NO_SELECTION" for o in observations), "actionable": sum(bool(o.get("actionable")) for o in observations), "void": sum(s.get("outcome") == "VOID" for s in settlements), "won": sum(s.get("outcome") == "WON" for s in settlements), "lost": sum(s.get("outcome") == "LOST" for s in settlements), "conflicts": sum(a["status"] == "LIFECYCLE_AUDIT_CORRUPT" for a in audits), "orphans": sum(any("ORPHAN" in f["code"] for f in a["findings"]) for a in audits), "data_quality_warnings": len(quality["findings"])},
            "source_fingerprints": source_fingerprints, "audit_fingerprints": [a["audit_fingerprint"] for a in audits], "data_quality_fingerprint": quality["finding_fingerprint"],
        }
        raw["snapshot_fingerprint"] = fingerprint(raw); raw["snapshot_id"] = "forward-test-snapshot-" + raw["snapshot_fingerprint"]
        if persist: self.repository.append_snapshot(raw)
        return raw

    def report(self, kind: str, cutoff_utc: datetime, *, period_start_utc: datetime | None = None, generated_at_utc: datetime | None = None, persist: bool = True) -> dict[str, Any]:
        kind = kind.upper()
        if kind not in {"WEEKLY", "CUMULATIVE"}: raise ValueError("Report kind must be WEEKLY or CUMULATIVE.")
        cutoff = _dt(cutoff_utc)
        generated = _dt(generated_at_utc or cutoff)
        start = _dt(period_start_utc) if period_start_utc else (self._week_start(cutoff) if kind == "WEEKLY" else None)
        snapshot = self.snapshot(cutoff, generated_at_utc=generated, persist=persist)
        bundle = self._source_rows(cutoff, start); metrics = self._metrics(bundle); quality = self.data_quality(cutoff, bundle)
        comparisons = self._comparisons(kind, start, cutoff)
        request = {"report_kind": kind, "period_start_utc": start.isoformat() if start else None, "period_end_utc": cutoff.isoformat(), "generated_at_utc": generated.isoformat(), "policy_fingerprint": self.policy.fingerprint, "source_fingerprint": snapshot["source_fingerprint"]}
        request_fp = fingerprint(request)
        audits = [self.lifecycle_audit(item["observation"]["observation_id"], cutoff) for item in bundle["observations"]]
        raw = {"schema_version": "goalvision-forward-test-monitoring-report-v1", "report_kind": kind, "period_start_utc": request["period_start_utc"], "period_end_utc": cutoff.isoformat(), "generated_at_utc": generated.isoformat(), "reporting_timezone": self.policy.timezone, "policy_id": self.policy.policy_id, "policy_version": self.policy.version, "policy_fingerprint": self.policy.fingerprint, "snapshot_id": snapshot["snapshot_id"], "snapshot_fingerprint": snapshot["snapshot_fingerprint"], "request_fingerprint": request_fp, "metrics": metrics, "segments": self._segments(bundle), "records": self._report_records(bundle), "lifecycle_audits": audits, "data_quality": quality, "comparisons": comparisons, "unresolved": self.unresolved(cutoff, bundle), "limitations": ["HYPOTHETICAL_FLAT_STAKE only; no bet or bankroll transaction occurred.", "Forward-test evidence is not proof of profitability or statistical significance.", "Closing-line value is unavailable without an immutable closing quote.", "This report is manual-only and cannot publish or schedule itself."], "telegram_send_executed": False, "official_state_mutations": 0, "bankroll_mutations": 0}
        raw["report_fingerprint"] = fingerprint(raw); raw["report_id"] = "forward-test-report-" + raw["report_fingerprint"]
        if persist: self.repository.append_report(raw)
        return raw

    def reproduce(self, report_id: str) -> dict[str, Any]:
        existing = self.repository.report(report_id)
        rebuilt = self.report(existing["report_kind"], _dt(existing["period_end_utc"]), period_start_utc=_dt(existing["period_start_utc"]) if existing.get("period_start_utc") else None, generated_at_utc=_dt(existing["generated_at_utc"]), persist=False)
        return {"status": "REPORT_REPRODUCED" if rebuilt["report_fingerprint"] == existing["report_fingerprint"] else "REPORT_REPRODUCTION_CONFLICT", "report_id": report_id, "expected_fingerprint": existing["report_fingerprint"], "actual_fingerprint": rebuilt["report_fingerprint"], "matches": rebuilt["report_fingerprint"] == existing["report_fingerprint"]}

    def unresolved(self, cutoff_utc: datetime, bundle: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        cutoff = _dt(cutoff_utc); rows = bundle or self._source_rows(cutoff, None); output = []
        result_ids = {item["observation_id"] for item in rows["results"]}; settlement_ids = {item["observation_id"] for item in rows["settlements"]}
        for item in rows["observations"]:
            observation, odds = item["observation"], item["odds"] or {}; identifier = observation["observation_id"]
            if identifier not in result_ids:
                due = _dt(odds["kickoff_utc"]) + self._hours(self.policy.missing_result_hours) if odds.get("kickoff_utc") else None
                output.append({"observation_id": identifier, "state": "RESULT_PENDING", "overdue": bool(due and cutoff > due), "due_at_utc": due.isoformat() if due else None})
            elif identifier not in settlement_ids:
                output.append({"observation_id": identifier, "state": "SETTLEMENT_PENDING", "overdue": True, "due_at_utc": None})
        return sorted(output, key=lambda item: (not item["overdue"], item["observation_id"]))

    def health(self, cutoff_utc: datetime) -> dict[str, Any]:
        cutoff = _dt(cutoff_utc); fk = self.connection.execute("PRAGMA foreign_key_check").fetchall()
        required = {"ft_monitoring_snapshots_no_update", "ft_monitoring_reports_no_update", "ft_monitoring_audits_no_update", "ft_monitoring_incidents_no_update"}
        triggers = {row[0] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        schema = self.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        unresolved = self.unresolved(cutoff); corrupt = bool(fk) or schema < 38 or not required.issubset(triggers)
        observation_ids=[row[0] for row in self.connection.execute("SELECT observation_id FROM forward_test_observations WHERE created_at_utc<=? ORDER BY observation_id",(cutoff.isoformat(),))]
        audit_statuses=[self.lifecycle_audit(identifier,cutoff)["status"] for identifier in observation_ids]
        blocked=any(value=="LIFECYCLE_AUDIT_BLOCKED" for value in audit_statuses)
        audit_corrupt=any(value=="LIFECYCLE_AUDIT_CORRUPT" for value in audit_statuses)
        warning=any(value=="LIFECYCLE_AUDIT_WARNING" for value in audit_statuses) or any(item["overdue"] for item in unresolved)
        status = "FORWARD_TEST_CORRUPT" if corrupt or audit_corrupt else "FORWARD_TEST_BLOCKED" if blocked else "FORWARD_TEST_WARNING" if warning else "FORWARD_TEST_HEALTHY"
        return {"schema_version": "goalvision-forward-test-health-v1", "status": status, "checked_at_utc": cutoff.isoformat(), "database_schema_version": schema, "foreign_key_violations": len(fk), "immutable_trigger_contract": required.issubset(triggers), "audit_status_counts":dict(sorted(Counter(audit_statuses).items())), "unresolved_count": len(unresolved), "overdue_count": sum(item["overdue"] for item in unresolved), "provider_network_checked": False, "telegram_transport_constructed": False, "automatic_publication_enabled": False, "scheduling_enabled": False, "official_state_mutations": 0}

    def record_incidents(self, cutoff_utc: datetime) -> list[dict[str, Any]]:
        cutoff = _dt(cutoff_utc); incidents = []
        quality = self.data_quality(cutoff)
        for finding in quality["findings"]:
            if finding["severity"] not in {"WARNING", "BLOCKING", "CORRUPT"}: continue
            material = {"incident_code": finding["code"], "severity": finding["severity"], "affected_identifier": finding["affected_identifier"], "detected_at_utc": cutoff.isoformat(), "provenance": finding["provenance"], "detail": finding["detail"]}
            fp = fingerprint(material); material.update({"incident_id": "forward-test-incident-" + fp, "incident_fingerprint": fp})
            row = self.connection.execute("SELECT incident_fingerprint FROM forward_test_monitoring_incidents WHERE incident_fingerprint=?", (fp,)).fetchone()
            if not row:
                with self.connection:
                    self.connection.execute("INSERT INTO forward_test_monitoring_incidents VALUES (?,?,?,?,?,?,?)", (material["incident_id"], material["incident_code"], material["severity"], material["affected_identifier"], material["detected_at_utc"], fp, canonical_json(material)))
            incidents.append(material)
        return incidents

    def acknowledge_incident(self, incident_id: str, operator_identity: str, reason: str, occurred_at_utc: datetime, *, resolved: bool = False) -> dict[str, Any]:
        if not operator_identity.strip() or not reason.strip(): raise ValueError("Operator identity and reason are required.")
        if self.connection.execute("SELECT 1 FROM forward_test_monitoring_incidents WHERE incident_id=?", (incident_id,)).fetchone() is None: raise ValueError("Incident not found.")
        event_type = "RESOLVED" if resolved else "ACKNOWLEDGED"; material = {"incident_id": incident_id, "event_type": event_type, "operator_identity": operator_identity, "reason": reason, "occurred_at_utc": _dt(occurred_at_utc).isoformat()}; fp = fingerprint(material); material.update({"event_id": "forward-test-incident-event-" + fp, "event_fingerprint": fp})
        existing = self.connection.execute("SELECT event_fingerprint FROM forward_test_monitoring_incident_events WHERE incident_id=? AND event_type=?", (incident_id, event_type)).fetchone()
        if existing and existing[0] != fp: raise ValueError("INCIDENT_EVENT_REPLAY_CONFLICT")
        if not existing:
            with self.connection: self.connection.execute("INSERT INTO forward_test_monitoring_incident_events VALUES (?,?,?,?,?,?,?,?)", (material["event_id"], incident_id, event_type, operator_identity, reason, material["occurred_at_utc"], fp, canonical_json(material)))
        return material

    def _metrics(self, bundle: dict[str, Any]) -> dict[str, Any]:
        observations = [item["observation"] for item in bundle["observations"]]; settlements = bundle["settlements"]
        decisive = [s for s in settlements if s.get("outcome") in {"WON", "LOST"}]; wins = sum(s["outcome"] == "WON" for s in decisive); losses = len(decisive) - wins; voids = sum(s.get("outcome") == "VOID" for s in settlements)
        odds = [_d(s.get("quoted_odds")) for s in decisive if s.get("quoted_odds") is not None]
        returns = [_d(s.get("hypothetical_net_return")) for s in settlements if s.get("outcome") in {"WON", "LOST", "VOID"}]
        selected_evals = [e for o in observations for e in o.get("market_evaluations", ()) if e.get("market") == o.get("actionable_market")]
        probabilities = [_d(e.get("calibrated_probability")) for e in selected_evals]; raw_probabilities = [_d(e.get("raw_probability")) for e in selected_evals]; evs = [_d(e.get("expected_value")) for e in selected_evals]
        curve=[]; cumulative=peak=max_drawdown=Decimal(0); drawdown_start=None; recovery=0
        for index, value in enumerate(returns):
            cumulative += value; curve.append(cumulative)
            if cumulative >= peak: peak=cumulative; drawdown_start=None
            else:
                if drawdown_start is None: drawdown_start=index
                recovery=max(recovery, index-drawdown_start+1)
            max_drawdown=max(max_drawdown, peak-cumulative)
        probability_rows=[]
        result_map={r["observation_id"]:r for r in bundle["results"]}
        for observation in observations:
            result=result_map.get(observation["observation_id"])
            if not result: continue
            for evaluation in observation.get("market_evaluations", ()):
                actual=Decimal(1 if self._market_won(evaluation["market"], int(result["final_home_score"]), int(result["final_away_score"])) else 0)
                probability_rows.append((_d(evaluation.get("raw_probability")), _d(evaluation.get("calibrated_probability")), actual, evaluation["market"]))
        calibration=self._calibration(probability_rows)
        positive=sum((value for value in returns if value > 0), Decimal(0)); negative=abs(sum((value for value in returns if value < 0), Decimal(0)))
        return {"sample_status": self.policy.sample_status(len(settlements)), "sample_warning": self.policy.sample_status(len(settlements)) != "POLICY_MINIMUM_MET", "volume": {"analyses_attempted": len(observations), "observations_created": len(observations), "actionable_selections": sum(bool(o.get("actionable")) for o in observations), "no_selections": sum(o.get("status") == "NO_SELECTION" for o in observations), "blocked_analyses": sum(o.get("status") == "BLOCKED" for o in observations), "published_predictions": bundle["published_count"], "unpublished_valid_predictions": sum(bool(o.get("actionable")) for o in observations)-bundle["published_count"], "settled_predictions": len(settlements), "pending_predictions": len(observations)-len(settlements), "void_predictions": voids}, "results": {"wins": wins, "losses": losses, "voids": voids, "hit_rate": _safe_ratio(wins, wins+losses), "loss_rate": _safe_ratio(losses, wins+losses), "void_rate": _safe_ratio(voids, len(settlements)), "longest_win_streak": self._streak(settlements, "WON"), "longest_loss_streak": self._streak(settlements, "LOST"), "current_streak": self._current_streak(settlements)}, "odds": {"average": _avg(odds), "median": _median(odds), "minimum": min(odds) if odds else None, "maximum": max(odds) if odds else None, "average_winning": _avg(_d(s.get("quoted_odds")) for s in decisive if s["outcome"] == "WON"), "average_losing": _avg(_d(s.get("quoted_odds")) for s in decisive if s["outcome"] == "LOST"), "distribution": self._numeric_bins(odds, (Decimal("1.5"), Decimal("2"), Decimal("3")))}, "probability": {"average_raw": _avg(raw_probabilities), "average_calibrated": _avg(probabilities), "median_calibrated": _median(probabilities), "distribution": self._numeric_bins(probabilities, (Decimal("0.5"), Decimal("0.6"), Decimal("0.7"), Decimal("0.8"))), "extreme_count": sum(p <= self.policy.extreme_probability_low or p >= self.policy.extreme_probability_high for p in probabilities)}, "expected_value": {"average_reported_ev": _avg(evs), "median_reported_ev": _median(evs), "expected_units": sum(evs, Decimal(0)), "realized_units": sum(returns, Decimal(0)), "expected_vs_realized_difference": sum(returns, Decimal(0))-sum(evs, Decimal(0))}, "hypothetical_flat_stake": {"label": "HYPOTHETICAL_FLAT_STAKE", "stake_per_selection": self.policy.flat_stake_units, "total_staked_units": Decimal(len(returns)), "total_return_units": Decimal(len(returns))+sum(returns, Decimal(0)), "net_profit_units": sum(returns, Decimal(0)), "roi": _safe_ratio(sum(returns, Decimal(0)), len(returns)), "yield": _safe_ratio(sum(returns, Decimal(0)), len(returns)), "peak_cumulative_units": max(curve) if curve else None, "maximum_drawdown": max_drawdown if returns else None, "current_drawdown": peak-cumulative if returns else None, "recovery_duration_observations": recovery, "profit_factor": _safe_ratio(positive, negative)}, "calibration": calibration, "closing_line_value": {"status": "UNAVAILABLE", "policy": self.policy.clv_policy}}

    def _calibration(self, rows):
        if not rows: return {"status": "NO_SAMPLE", "sample": 0, "brier_score": None, "log_loss": None, "expected_calibration_error": None, "maximum_calibration_error": None, "bins": []}
        brier=_avg((p-y)**2 for _,p,y,_ in rows)
        with localcontext() as context:
            context.prec=40; epsilon=Decimal("0.000000000001")
            log_loss=_avg(-(y*max(epsilon,min(Decimal(1)-epsilon,p)).ln()+(Decimal(1)-y)*(Decimal(1)-max(epsilon,min(Decimal(1)-epsilon,p))).ln()) for _,p,y,_ in rows)
        bins=[]
        for index in range(self.policy.calibration_bins):
            low=Decimal(index)/self.policy.calibration_bins; high=Decimal(index+1)/self.policy.calibration_bins
            selected=[(p,y) for _,p,y,_ in rows if low <= p < high or index == self.policy.calibration_bins-1 and p == 1]
            if selected:
                predicted=_avg(p for p,_ in selected); observed=_avg(y for _,y in selected); gap=abs(predicted-observed)
                bins.append({"lower":low,"upper":high,"count":len(selected),"predicted":predicted,"observed":observed,"absolute_error":gap,"sample_status":"SUFFICIENT" if len(selected)>=self.policy.minimum_probability_bin_sample else "INSUFFICIENT"})
        ece=sum((Decimal(b["count"])/Decimal(len(rows)))*b["absolute_error"] for b in bins)
        return {"status":"SUFFICIENT" if len(rows)>=self.policy.minimum_calibration_sample else "INSUFFICIENT_CALIBRATION_SAMPLE","sample":len(rows),"brier_score":brier,"log_loss":log_loss,"calibration_error":ece,"expected_calibration_error":ece,"maximum_calibration_error":max((b["absolute_error"] for b in bins),default=None),"bins":bins}

    def _segments(self, bundle):
        definitions={"market":lambda o,e:o.get("actionable_market") or "NO_SELECTION","competition":lambda o,e:e.get("competition","UNKNOWN"),"bookmaker":lambda o,e:e.get("bookmaker","UNKNOWN"),"provider":lambda o,e:e.get("provider","UNKNOWN"),"model_generation":lambda o,e:o.get("model_artifact_id") or "UNKNOWN","calibration_artifact":lambda o,e:o.get("calibration_id") or "UNKNOWN","calibration_quality":lambda o,e:str((o.get("calibration_quality") or {}).get("status") or (o.get("calibration_quality") or {}).get("lab_outcome") or "UNKNOWN"),"distribution_shift":lambda o,e:str((o.get("distribution_shift") or {}).get("status","UNKNOWN")),"publication_status":lambda o,e:"PUBLISHED" if e.get("published") else "UNPUBLISHED","result_status":lambda o,e:e.get("outcome","PENDING")}
        settlement_map={s["observation_id"]:s for s in bundle["settlements"]}; output={}
        for name,key_fn in definitions.items():
            groups=defaultdict(list)
            for item in bundle["observations"]:
                o=item["observation"]; odds=item["odds"] or {}; analysis=item["analysis"] or {}; extra={"competition":self._competition(analysis),"bookmaker":odds.get("bookmaker_name"),"provider":odds.get("provider_source_id"),"published":o["observation_id"] in bundle["published_ids"],"outcome":settlement_map.get(o["observation_id"],{}).get("outcome")}
                groups[str(key_fn(o,extra))].append(o["observation_id"])
            output[name]=[{"key":key,"count":len(ids),"sample_status":self.policy.sample_status(len(ids)),"observation_ids":sorted(ids)} for key,ids in sorted(groups.items())]
        return output

    def _report_records(self, bundle):
        settlement_map={item["observation_id"]:item for item in bundle["settlements"]}
        observations=[]
        for item in bundle["observations"]:
            observation=item["observation"]; odds=item["odds"] or {}; settlement=settlement_map.get(observation["observation_id"],{})
            selected=next((value for value in observation.get("market_evaluations",()) if value.get("market")==observation.get("actionable_market")),{})
            observations.append({"observation_id":observation["observation_id"],"fixture_id":observation.get("canonical_fixture_id"),"created_at_utc":observation.get("created_at_utc"),"status":observation.get("status"),"actionable":bool(observation.get("actionable")),"market":observation.get("actionable_market"),"bookmaker":odds.get("bookmaker_name"),"provider":odds.get("provider_source_id"),"quoted_odds":selected.get("bookmaker_odds"),"raw_probability":selected.get("raw_probability"),"calibrated_probability":selected.get("calibrated_probability"),"expected_value":selected.get("expected_value"),"published":observation["observation_id"] in bundle["published_ids"],"outcome":settlement.get("outcome","PENDING"),"observation_fingerprint":observation.get("observation_fingerprint")})
        settlements=[{"settlement_id":item.get("settlement_id"),"observation_id":item.get("observation_id"),"result_id":item.get("result_id"),"market":item.get("market"),"outcome":item.get("outcome"),"quoted_odds":item.get("quoted_odds"),"hypothetical_stake":item.get("hypothetical_flat_stake"),"hypothetical_net_return":item.get("hypothetical_net_return"),"settled_at_utc":item.get("settled_at_utc"),"settlement_fingerprint":item.get("settlement_fingerprint")} for item in bundle["settlements"]]
        return {"observations":observations,"settlements":settlements}

    def _source_rows(self, cutoff, start):
        observation_rows=self.connection.execute("SELECT * FROM forward_test_observations WHERE created_at_utc<=? ORDER BY created_at_utc,observation_id",(cutoff.isoformat(),)).fetchall(); observations=[]
        for row in observation_rows:
            if start and _dt(row["created_at_utc"]) < start: continue
            odds_row=self.connection.execute("SELECT snapshot_json FROM forward_test_odds_snapshots WHERE odds_snapshot_id=?",(row["odds_snapshot_id"],)).fetchone(); analysis_row=self.connection.execute("SELECT request_snapshot FROM real_match_lab_analyses WHERE analysis_id=?",(row["analysis_id"],)).fetchone()
            observations.append({"observation":json.loads(row["observation_json"]),"odds":json.loads(odds_row[0]) if odds_row else None,"analysis":json.loads(analysis_row[0]) if analysis_row else None})
        ids=[item["observation"]["observation_id"] for item in observations]
        def linked(table,json_col,time_col):
            if not ids:return []
            placeholders=','.join('?' for _ in ids); rows=self.connection.execute(f"SELECT {json_col} FROM {table} WHERE observation_id IN ({placeholders}) AND {time_col}<=? ORDER BY {time_col}",(*ids,cutoff.isoformat())).fetchall(); return [json.loads(row[0]) for row in rows]
        results=linked("forward_test_results","result_json","result_retrieval_timestamp_utc"); settlements=linked("forward_test_settlements","settlement_json","settled_at_utc")
        reviews=self.connection.execute("SELECT observation_id,review_snapshot FROM forward_test_publication_reviews WHERE reviewed_at_utc<=? ORDER BY reviewed_at_utc",(cutoff.isoformat(),)).fetchall(); reviews=[(r[0],json.loads(r[1])) for r in reviews if r[0] in ids]
        published_ids=set()
        for item in observations:
            oid=item["observation"]["observation_id"]; aid=next((r["analysis_id"] for r in observation_rows if r["observation_id"]==oid),None)
            if aid and self.connection.execute("SELECT COUNT(*) FROM real_match_lab_deliveries WHERE analysis_id=? AND status='SENT' AND occurred_at<=?",(aid,cutoff.isoformat())).fetchone()[0]:published_ids.add(oid)
        return {"observations":observations,"results":results,"settlements":settlements,"reviews":reviews,"published_ids":published_ids,"published_count":len(published_ids)}

    def _comparisons(self, kind,start,cutoff):
        if kind!="WEEKLY" or start is None:return {"status":"NOT_APPLICABLE"}
        duration=cutoff-start; previous_start=start-duration; current=self._source_rows(cutoff,start); previous=self._source_rows(start,previous_start)
        return {"status":"AVAILABLE" if previous["observations"] else "NO_PRIOR_SAMPLE","current_observations":len(current["observations"]),"previous_observations":len(previous["observations"]),"observation_delta":len(current["observations"])-len(previous["observations"]),"interpretation":"Descriptive only; small samples do not establish a trend."}

    def _database_identity(self):
        rows=self.connection.execute("SELECT version,applied_at FROM schema_migrations ORDER BY version").fetchall(); return hashlib.sha256(canonical_json([tuple(r) for r in rows]).encode()).hexdigest()
    def _competition(self,analysis):
        return analysis.get("competition") or analysis.get("input",{}).get("competition") or "UNKNOWN"
    def _week_start(self,cutoff):
        from app.real_match_lab_analysis.message import _riga_time
        local=_riga_time(cutoff); monday=(local-self._days(local.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
        return monday.astimezone(_UTC)
    @staticmethod
    def _hours(value):
        from datetime import timedelta
        return timedelta(hours=value)
    @staticmethod
    def _days(value):
        from datetime import timedelta
        return timedelta(days=value)
    @staticmethod
    def _finding(item): return {"code":item.code,"severity":item.severity,"affected_identifier":item.affected_identifier,"provenance":item.provenance,"detail":item.detail}
    @staticmethod
    def _streak(items,status):
        best=current=0
        for item in items: current=current+1 if item.get("outcome")==status else 0; best=max(best,current)
        return best
    @staticmethod
    def _current_streak(items):
        decisive=[i.get("outcome") for i in items if i.get("outcome") in {"WON","LOST"}]
        if not decisive:return {"outcome":None,"length":0}
        status=decisive[-1]; count=0
        for item in reversed(decisive):
            if item!=status:break
            count+=1
        return {"outcome":status,"length":count}
    @staticmethod
    def _numeric_bins(values,edges):
        labels=[f"LT_{edges[0]}"]+[f"{edges[i-1]}_TO_{edges[i]}" for i in range(1,len(edges))]+[f"GE_{edges[-1]}"]; counts=Counter()
        for value in values:
            index=next((i for i,e in enumerate(edges) if value<e),len(edges)); counts[labels[index]]+=1
        return dict(sorted(counts.items()))
    @staticmethod
    def _market_won(market,home,away):
        total=home+away; values={"HOME_WIN":home>away,"DRAW":home==away,"AWAY_WIN":away>home,"OVER_1_5":total>1,"UNDER_1_5":total<2,"OVER_2_5":total>2,"UNDER_2_5":total<3,"OVER_3_5":total>3,"UNDER_3_5":total<4,"BTTS_YES":home>0 and away>0,"BTTS_NO":home==0 or away==0}; return values.get(market,False)
    @classmethod
    def _expected_outcome(cls,market,home,away): return "NOT_APPLICABLE" if market is None else "WON" if cls._market_won(market,home,away) else "LOST"
