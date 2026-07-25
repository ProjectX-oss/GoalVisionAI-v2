"""Typed pre-bootstrap/pre-execution audit mode without weakening full audit."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path

from app.model_activation_audit.checks import run_checks
from app.model_activation_audit.models import (
    AuditCheck,
    AuditReport,
    AuditSeverity,
)
from app.model_activation_audit.policy import (
    AUDIT_SCHEMA_VERSION,
    SUPPORTED_ENVIRONMENTS,
    SUPPORTED_SCOPES,
    assess_staging_readiness,
    overall_status,
)
from app.model_activation_audit.service import AuditInputError


PREFLIGHT_CHECK_IDS = {
    "schema.version",
    "schema.tables",
    "schema.indexes",
    "schema.append_only_triggers",
    "schema.foreign_keys",
    "schema.uniqueness_idempotency",
    "resolver.fail_closed",
    "resolver.runtime_unwired",
    "activation.manual_only",
    "cli.confirmations",
    "cli.read_only_inspection",
    "cli.no_side_effect_integrations",
    "cli.known_failure_guidance",
    "rehearsal.fidelity",
    "runbook.consistency",
    "staging.human_authorization",
}


class StagingPreflightInputError(AuditInputError):
    """Safely reportable preflight input failure."""


class StagingPreflightAuditService:
    def __init__(self, repository, project_root: Path | None = None):
        self._repository = repository
        self._project_root = project_root or Path(__file__).resolve().parents[2]

    def audit(
        self,
        *,
        source_commit: str,
        generated_timestamp_utc: str,
        environment: str,
        scope: str,
    ) -> AuditReport:
        environment = environment.upper()
        if environment != "STAGING" or environment not in SUPPORTED_ENVIRONMENTS:
            raise StagingPreflightInputError(
                "Preflight is restricted to explicitly authorized STAGING."
            )
        if scope not in SUPPORTED_SCOPES:
            raise StagingPreflightInputError("Unsupported explicit model scope.")
        if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
            raise StagingPreflightInputError(
                "Source commit must be a full lowercase SHA-1."
            )
        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
            generated_timestamp_utc,
        ):
            raise StagingPreflightInputError(
                "Generated timestamp must be explicit UTC."
            )
        complete = run_checks(self._repository, scope, self._project_root)
        checks = tuple(
            item for item in complete if item.check_id in PREFLIGHT_CHECK_IDS
        )
        generation_count = int(
            self._repository.scalar(
                "SELECT COUNT(*) FROM model_champion_generations WHERE model_scope=?",
                (scope,),
            )
            or 0
        )
        registry = AuditCheck(
            "staging_preflight.registry_state",
            "STAGING_PREFLIGHT",
            AuditSeverity.INFO if generation_count == 0 else AuditSeverity.PASS,
            (
                "Staging registry is explicitly unbootstrapped."
                if generation_count == 0
                else "Staging registry has a champion and remains append-only."
            ),
            ("model_champion_generations",),
            mandatory=False,
        )
        checks += (registry,)
        return _report(
            checks,
            source_commit,
            generated_timestamp_utc,
            environment,
            scope,
        )


def _report(checks, source_commit, timestamp, environment, scope):
    status = overall_status(checks)
    readiness = assess_staging_readiness(status, checks)
    counts = tuple(
        (severity.value, sum(item.severity is severity for item in checks))
        for severity in AuditSeverity
    )
    material = {
        "checks": [_check(item) for item in checks],
        "environment": environment,
        "generated_timestamp_utc": timestamp,
        "schema_version": AUDIT_SCHEMA_VERSION,
        "scope": scope,
        "source_commit": source_commit,
        "staging_readiness": readiness.value,
        "summary_counts": dict(counts),
        "overall_status": status.value,
        "audit_mode": "STAGING_PREFLIGHT",
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    return AuditReport(
        AUDIT_SCHEMA_VERSION,
        source_commit,
        timestamp,
        environment,
        scope,
        "SQLITE_READ_ONLY_STAGING_PREFLIGHT",
        status,
        readiness,
        checks,
        counts,
        fingerprint,
    )


def _check(item):
    value = asdict(item)
    value["severity"] = item.severity.value
    value["evidence_references"] = list(item.evidence_references)
    return value
