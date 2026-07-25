"""Canonical JSON and deterministic human audit formatting."""

from __future__ import annotations

import json
import re
from dataclasses import asdict


_SECRET = re.compile(
    r"(?i)(token|secret|password|credential)([\"'=:\s]+)([^\s,\"']+)"
)


def report_document(report) -> dict:
    checks = []
    for item in report.checks:
        check = asdict(item)
        check["severity"] = item.severity.value
        check["evidence_references"] = list(item.evidence_references)
        checks.append(check)
    return {
        "schema_version": report.schema_version,
        "source_commit": report.source_commit,
        "generated_timestamp_utc": report.generated_timestamp_utc,
        "environment": report.environment,
        "scope": report.scope,
        "database_type": report.database_type,
        "overall_status": report.overall_status.value,
        "staging_readiness": report.staging_readiness.value,
        "summary_counts": dict(report.summary_counts),
        "checks": checks,
        "audit_fingerprint": report.audit_fingerprint,
    }


def format_json(report) -> str:
    return redact(
        json.dumps(
            report_document(report),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )


def format_human(report) -> str:
    lines = [
        "GOALVISION MODEL ACTIVATION INDEPENDENT AUDIT",
        f"Status: {report.overall_status.value}",
        f"Staging readiness: {report.staging_readiness.value}",
        f"Environment: {report.environment}",
        f"Scope: {report.scope}",
        f"Source commit: {report.source_commit}",
        f"Generated: {report.generated_timestamp_utc}",
        f"Audit fingerprint: {report.audit_fingerprint}",
        "Counts: "
        + ", ".join(f"{name}={count}" for name, count in report.summary_counts),
        "Checks:",
    ]
    lines.extend(
        f"- [{item.severity.value}] {item.check_id}: {item.summary}"
        for item in report.checks
    )
    lines.append(
        "Authorization: this assessment does not authorize or start staging."
    )
    return redact("\n".join(lines))


def redact(value: str) -> str:
    return _SECRET.sub(lambda match: match.group(1) + match.group(2) + "[REDACTED]", value)
