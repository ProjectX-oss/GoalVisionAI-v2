"""Deterministic, independent policy review with append-only operator decisions."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal

from app.forward_test_governance.policy import DEFAULT_POLICY, GovernancePolicy
from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint

APPROVE_CONFIRMATION = "APPROVE_GOALVISION_LAB_GOVERNANCE_POLICY"
REVOKE_CONFIRMATION = "REVOKE_GOALVISION_LAB_GOVERNANCE_POLICY"
PASSED_OUTCOMES = {"PASSED", "PASSED_WITH_WARNINGS"}


class GovernanceReviewConflict(RuntimeError):
    """Raised when immutable review or approval evidence conflicts."""


def review_governance_policy(policy: GovernancePolicy = DEFAULT_POLICY, *, reviewed_at_utc: datetime) -> dict:
    """Review every policy parameter and cross-rule without using operational evidence."""
    reviewed = _utc(reviewed_at_utc)
    raw = asdict(policy)
    findings: list[dict] = []
    for name, value in raw.items():
        classification = "IDENTITY" if name in {"policy_id", "version", "timezone"} else "CONSERVATIVE_CONTROL"
        findings.append({"parameter_name": name, "classification": classification, "severity": "INFO", "value": str(value)})
    checks = {
        "warning_precedes_block": all((getattr(policy, stem + "_warning") < getattr(policy, stem + "_block")) for stem in ("brier", "log_loss", "ece", "probability_bias", "missingness", "psi", "stale_odds", "explanation_fragile", "audit_failure")),
        "recovery_exceeds_block_hysteresis": policy.recovery_consecutive_evaluations > policy.blocking_consecutive_evaluations,
        "warning_hysteresis_positive": policy.warning_consecutive_evaluations > 0,
        "stale_evidence_bounded": 0 < policy.maximum_evaluation_age_hours <= 24,
        "insufficient_sample_fail_closed": policy.minimum_total_settled_sample >= policy.minimum_recent_window_sample >= policy.minimum_scope_sample,
        "market_isolation_supported": policy.minimum_scope_sample > 0,
        "integrity_global_block_supported": True,
    }
    blockers = [name for name, passed in checks.items() if not passed]
    warnings = []
    if policy.market_concentration_warning >= Decimal("0.50"):
        warnings.append("MARKET_CONCENTRATION_REQUIRES_OPERATOR_ATTENTION")
        findings.append({"parameter_name": "market_concentration_warning", "classification": "OPERATOR_REVIEW_REQUIRED", "severity": "WARNING", "value": str(policy.market_concentration_warning)})
    outcome = "BLOCKED" if blockers else "PASSED_WITH_WARNINGS" if warnings else "PASSED"
    material = {"schema_version": "goalvision-governance-policy-review-v1", "policy_version": policy.version, "policy_fingerprint": policy.fingerprint, "outcome": outcome, "checks": checks, "warnings": warnings, "blockers": blockers, "findings": findings, "reviewed_at_utc": reviewed.isoformat()}
    review_fp = fingerprint(material)
    return {**material, "review_id": "governance-policy-review-" + review_fp, "review_fingerprint": review_fp}


class GovernancePolicyReviewService:
    """Persist reviews, approvals and revocations on an already-migrated connection."""

    def __init__(self, connection) -> None:
        self.connection = connection

    def persist_review(self, review: dict) -> dict:
        existing = self.connection.execute("SELECT review_json FROM governance_policy_reviews WHERE review_id=?", (review["review_id"],)).fetchone()
        if existing:
            if json.loads(existing[0]) != review: raise GovernanceReviewConflict("Review ID conflicts with immutable evidence.")
            return {**review, "replayed": True}
        with self.connection:
            self.connection.execute("INSERT INTO governance_policy_reviews VALUES (?,?,?,?,?,?,?)", (review["review_id"], review["policy_version"], review["policy_fingerprint"], review["outcome"], review["review_fingerprint"], canonical_json(review), review["reviewed_at_utc"]))
            for item in review["findings"]:
                fp = fingerprint({"review_id": review["review_id"], **item})
                self.connection.execute("INSERT INTO governance_policy_review_findings VALUES (?,?,?,?,?,?)", ("governance-finding-" + fp, review["review_id"], item["classification"], item["parameter_name"], fp, canonical_json(item)))
        return {**review, "replayed": False}

    def approve(self, review_id: str, policy_fingerprint: str, operator: str, confirmation: str, *, approved_at_utc: datetime) -> dict:
        if confirmation != APPROVE_CONFIRMATION: raise GovernanceReviewConflict("Exact approval confirmation is required.")
        row = self.connection.execute("SELECT outcome,policy_fingerprint FROM governance_policy_reviews WHERE review_id=?", (review_id,)).fetchone()
        if not row or row[0] not in PASSED_OUTCOMES or row[1] != policy_fingerprint: raise GovernanceReviewConflict("A passed review of the exact policy is required.")
        material = {"review_id": review_id, "policy_fingerprint": policy_fingerprint, "operator_identity": operator, "approved_at_utc": _utc(approved_at_utc).isoformat()}
        fp = fingerprint(material); value = {**material, "approval_id": "governance-policy-approval-" + fp, "approval_fingerprint": fp, "status": "POLICY_APPROVED"}
        existing = self.connection.execute("SELECT approval_json FROM governance_policy_approvals WHERE approval_id=?", (value["approval_id"],)).fetchone()
        if existing:
            if json.loads(existing[0]) != value: raise GovernanceReviewConflict("Approval conflict.")
            return {**value, "replayed": True}
        with self.connection:
            self.connection.execute("INSERT INTO governance_policy_approvals VALUES (?,?,?,?,?,?,?)", (value["approval_id"], review_id, policy_fingerprint, operator, fp, canonical_json(value), value["approved_at_utc"]))
        return {**value, "replayed": False}

    def revoke(self, approval_id: str, operator: str, confirmation: str, *, occurred_at_utc: datetime) -> dict:
        if confirmation != REVOKE_CONFIRMATION: raise GovernanceReviewConflict("Exact revocation confirmation is required.")
        if not self.connection.execute("SELECT 1 FROM governance_policy_approvals WHERE approval_id=?", (approval_id,)).fetchone(): raise GovernanceReviewConflict("Approval not found.")
        return self._event(approval_id, "REVOKED", operator, occurred_at_utc)

    def is_active(self, approval_id: str) -> bool:
        return bool(self.connection.execute("SELECT 1 FROM governance_policy_approvals WHERE approval_id=?", (approval_id,)).fetchone()) and not bool(self.connection.execute("SELECT 1 FROM governance_policy_approval_events WHERE approval_id=? AND event_type='REVOKED'", (approval_id,)).fetchone())

    def _event(self, approval_id: str, event_type: str, operator: str, occurred: datetime) -> dict:
        material = {"approval_id": approval_id, "event_type": event_type, "operator_identity": operator, "occurred_at_utc": _utc(occurred).isoformat()}; fp = fingerprint(material)
        value = {**material, "event_id": "governance-policy-event-" + fp, "event_fingerprint": fp}
        with self.connection:
            self.connection.execute("INSERT OR IGNORE INTO governance_policy_approval_events VALUES (?,?,?,?,?,?,?)", (value["event_id"], approval_id, event_type, operator, fp, canonical_json(value), value["occurred_at_utc"]))
        return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None: raise ValueError("UTC offset is required.")
    return value.astimezone(timezone.utc)
