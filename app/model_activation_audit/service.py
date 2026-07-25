"""Deterministic audit orchestration without state-changing domain calls."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path

from .checks import run_checks
from .models import AuditReport, AuditSeverity
from .policy import (
    AUDIT_SCHEMA_VERSION,
    SUPPORTED_ENVIRONMENTS,
    SUPPORTED_SCOPES,
    assess_staging_readiness,
    overall_status,
)


class AuditInputError(ValueError):
    """Known input failure safe for CLI display."""


class ModelActivationAuditService:
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
        if environment not in SUPPORTED_ENVIRONMENTS:
            raise AuditInputError("Unsupported explicit audit environment.")
        if scope not in SUPPORTED_SCOPES:
            raise AuditInputError("Unsupported explicit model scope.")
        if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
            raise AuditInputError("Source commit must be a full lowercase SHA-1.")
        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
            generated_timestamp_utc,
        ):
            raise AuditInputError(
                "Generated timestamp must be explicit UTC YYYY-MM-DDTHH:MM:SSZ."
            )
        checks = run_checks(self._repository, scope, self._project_root)
        status = overall_status(checks)
        readiness = assess_staging_readiness(status, checks)
        counts = tuple(
            (severity.value, sum(c.severity is severity for c in checks))
            for severity in AuditSeverity
        )
        material = {
            "checks": [_check_dict(item) for item in checks],
            "environment": environment,
            "generated_timestamp_utc": generated_timestamp_utc,
            "schema_version": AUDIT_SCHEMA_VERSION,
            "scope": scope,
            "source_commit": source_commit,
            "staging_readiness": readiness.value,
            "summary_counts": dict(counts),
            "overall_status": status.value,
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
            generated_timestamp_utc,
            environment,
            scope,
            "SQLITE_READ_ONLY",
            status,
            readiness,
            checks,
            counts,
            fingerprint,
        )


def _check_dict(check) -> dict:
    value = asdict(check)
    value["severity"] = check.severity.value
    value["evidence_references"] = list(check.evidence_references)
    return value
