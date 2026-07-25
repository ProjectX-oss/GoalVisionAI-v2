"""Canonical redacted staging evidence output."""

from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
import re

from .models import StagingRehearsalOutcome


_SECRET = re.compile(
    r"(?i)(token|secret|password|credential|api[_-]?key)"
    r"([\"'=:\s]+)([^\s,\"']+)"
)


def canonical_json(outcome: StagingRehearsalOutcome) -> str:
    return redact(
        json.dumps(
            asdict(outcome),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )


def evidence_fingerprint(outcome: StagingRehearsalOutcome) -> str:
    material = asdict(replace(outcome, evidence_fingerprint=""))
    return hashlib.sha256(
        json.dumps(
            material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def format_human(outcome: StagingRehearsalOutcome) -> str:
    lines = (
        "GOALVISION CONTROLLED STAGING MODEL OPERATIONS REHEARSAL",
        f"Status: {outcome.status}",
        f"Environment: {outcome.environment}",
        f"Scope: {outcome.scope}",
        f"Source commit: {outcome.source_commit}",
        f"Source SHA-256 before: {outcome.source.sha256_before}",
        f"Source SHA-256 after: {outcome.source.sha256_after}",
        f"Artifact mode: {outcome.selected_artifact_mode}",
        f"Initial state: {outcome.initial_state}",
        f"Activation plan: {outcome.activation_plan_fingerprint}",
        f"Activation execution: {outcome.activation_execution_fingerprint}",
        f"Rollback plan: {outcome.rollback_plan_fingerprint}",
        f"Rollback execution: {outcome.rollback_execution_fingerprint}",
        f"Final audit: {outcome.final_audits[-1].overall_status}",
        f"Evidence fingerprint: {outcome.evidence_fingerprint}",
        "Authorization: production activation remains unauthorized.",
    )
    return redact("\n".join(lines))


def redact(value: str) -> str:
    return _SECRET.sub(
        lambda match: match.group(1) + match.group(2) + "[REDACTED]",
        value,
    )
