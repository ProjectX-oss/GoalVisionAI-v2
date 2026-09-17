"""Reasoning-bound Lab preview and publication integrity helpers."""

from __future__ import annotations

from app.real_match_lab_analysis.fingerprint import fingerprint

from .models import ReasoningAudit, ReasoningRecord


def compose_reasoned_message(base_message_html: str, record: ReasoningRecord) -> dict:
    """Bind the exact public explanation to the exact candidate message."""
    message = "\n\n".join((base_message_html.rstrip(), record.public_reasoning_html.rstrip()))
    material = {
        "schema_version": "goalvision-reasoned-lab-message-v1",
        "analysis_id": record.analysis_id,
        "observation_id": record.observation_id,
        "reasoning_id": record.reasoning_id,
        "reasoning_fingerprint": record.reasoning_fingerprint,
        "public_reasoning_fingerprint": record.public_reasoning_fingerprint,
        "message_html": message,
    }
    return {**material, "message_fingerprint": fingerprint(material)}


def publication_reasoning_checks(
    record: ReasoningRecord | None,
    audit: ReasoningAudit | None,
    *,
    analysis_id: str,
    observation_id: str,
    selected_market: str | None,
) -> tuple[tuple[str, bool], ...]:
    """Return fail-closed checks shared by review and manual authorization."""
    return (
        ("REASONING_PRESENT", record is not None),
        ("REASONING_ANALYSIS_LINKAGE", record is not None and record.analysis_id == analysis_id),
        ("REASONING_OBSERVATION_LINKAGE", record is not None and record.observation_id == observation_id),
        ("REASONING_MARKET_LINKAGE", record is not None and record.selected_market == selected_market),
        ("REASONING_CREATED", record is not None and record.reasoning_status == "REASONING_CREATED"),
        ("REASONING_REPRODUCED", record is not None and record.contribution_reproduction_status == "CONTRIBUTIONS_COMPUTED"),
        ("REASONING_AUDIT_PRESENT", audit is not None),
        ("REASONING_AUDIT_PASSED", audit is not None and audit.status == "REASONING_AUDIT_PASSED"),
    )
