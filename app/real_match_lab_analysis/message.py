"""Deterministic Telegram-safe HTML presentation."""

from __future__ import annotations

import html
from datetime import timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from .fingerprint import fingerprint
from .models import EngineEvidence, MarketEvaluation, RealMatchLabInput


def build_message(
    command: RealMatchLabInput,
    evidence: EngineEvidence,
    selection: MarketEvaluation,
) -> tuple[str, str]:
    esc = lambda value: html.escape(str(value), quote=True)
    kickoff = command.kickoff_utc.strftime("%d %B %Y, %H:%M UTC")
    local_kickoff = _riga_time(command.kickoff_utc).strftime("%d %B %Y, %H:%M Europe/Riga")
    quality = evidence.calibration_quality_report or {}
    quality_status = quality.get("lab_outcome", "CALIBRATION_QUALITY_NOT_EVALUATED") if isinstance(quality, dict) else "CALIBRATION_QUALITY_NOT_EVALUATED"
    quality_permits_value = quality_status == "CALIBRATION_QUALITY_ACCEPTABLE" and selection.distribution_shift_status == "DISTRIBUTION_SHIFT_ACCEPTABLE"
    probability = _percent(selection.calibrated_probability) if selection.calibrated_probability <= Decimal("0.95") else "withheld — unsupported extreme"
    reasons = evidence.reasoning_facts[:4] or (
        "validated model probability and supplied immutable odds",
    )
    body = "\n".join((
        "🧪 <b>GoalVision AI Lab</b>",
        "",
        f"⚽ {esc(command.home_team)} vs {esc(command.away_team)}",
        f"🏆 {esc(command.competition)}",
        f"🕒 {esc(kickoff)}",
        f"🕒 {esc(local_kickoff)}",
        "",
        "🔬 <b>Experimental AI prediction</b>",
        "",
        f"<b>Selection:</b> {esc(_market_label(selection.market, command))}",
        f"<b>Bookmaker/source:</b> {esc(command.odds[0].bookmaker_id)} / {esc(command.odds[0].source_provider)}",
        f"<b>Bookmaker odds:</b> {_number(selection.bookmaker_odds)}",
        f"<b>Odds captured:</b> {esc(command.odds[0].captured_at.isoformat())}",
        f"<b>AI calibrated probability:</b> {probability}",
        f"<b>Fair odds:</b> {_number(selection.fair_odds) if quality_permits_value else 'withheld — quality blocked'}",
        f"<b>Expected value:</b> {_signed_percent(selection.expected_value) if quality_permits_value else 'withheld — quality blocked'}",
        f"<b>Confidence:</b> {esc(selection.confidence)}",
        "",
        "<b>Key reasoning:</b>",
        *(f"• {esc(reason)}" for reason in reasons),
        "",
        "<b>Official eligibility:</b> ❌ Lab-only forward test",
        "",
        "<b>Data status:</b>",
        f"• odds age: {selection.freshness}",
        f"• feature snapshot age: {evidence.feature_age_seconds}s",
        f"• lineup status: {esc(evidence.lineup_status)}",
        f"• calibration quality: {esc(quality_status)}",
        f"• distribution shift: {esc(selection.distribution_shift_status)}",
        f"• active model: {esc(evidence.model_artifact_id)}",
        f"• trace: {esc(command.request_id[-16:])}",
        "",
        "⚠️ Experimental Lab analysis only. No guarantee or certainty claim.",
        "Not included in Official bankroll or Official statistics.",
    ))
    message_fingerprint = fingerprint({"version": "lab-message-v1", "body": body})
    return body + f"\n\n<code>{message_fingerprint}</code>", message_fingerprint


def _market_label(market: str, command: RealMatchLabInput) -> str:
    return {
        "HOME_WIN": f"{command.home_team} to win",
        "DRAW": "Draw",
        "AWAY_WIN": f"{command.away_team} to win",
        "OVER_1_5": "Over 1.5 goals",
        "UNDER_1_5": "Under 1.5 goals",
        "OVER_2_5": "Over 2.5 goals",
        "UNDER_2_5": "Under 2.5 goals",
        "OVER_3_5": "Over 3.5 goals",
        "UNDER_3_5": "Under 3.5 goals",
        "BTTS_YES": "Both teams to score — Yes",
        "BTTS_NO": "Both teams to score — No",
    }[market]


def _number(value: Decimal) -> str:
    return f"{value:.2f}"


def _percent(value: Decimal) -> str:
    return f"{value * 100:.1f}%"


def _signed_percent(value: Decimal) -> str:
    return f"{value * 100:+.1f}%"


def _riga_time(value):
    """Use system tzdata when available and a deterministic EU-DST fallback."""
    try:
        return value.astimezone(ZoneInfo("Europe/Riga"))
    except Exception:
        year = value.year
        march_end = max(day for day in range(25, 32) if __import__("datetime").date(year, 3, day).weekday() == 6)
        october_end = max(day for day in range(25, 32) if __import__("datetime").date(year, 10, day).weekday() == 6)
        summer = (value.month, value.day) >= (3, march_end) and (value.month, value.day) < (10, october_end)
        return value.astimezone(timezone(timedelta(hours=3 if summer else 2)))
