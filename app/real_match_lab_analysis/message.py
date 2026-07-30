"""Deterministic Telegram-safe HTML presentation."""

from __future__ import annotations

import html
from decimal import Decimal

from .fingerprint import fingerprint
from .models import EngineEvidence, MarketEvaluation, RealMatchLabInput


def build_message(
    command: RealMatchLabInput,
    evidence: EngineEvidence,
    selection: MarketEvaluation,
) -> tuple[str, str]:
    esc = lambda value: html.escape(str(value), quote=True)
    kickoff = command.kickoff_utc.strftime("%d %B %Y, %H:%M UTC")
    official = (
        "✅ Would currently satisfy the main Official thresholds"
        if selection.official_minimum_odds_pass
        and selection.official_quality_gate_pass
        else "❌ Not an Official publication"
    )
    reasons = evidence.reasoning_facts[:4] or (
        "validated model probability and supplied immutable odds",
    )
    body = "\n".join((
        "🧪 <b>GOALVISION AI LAB</b>",
        "",
        f"⚽ {esc(command.home_team)} vs {esc(command.away_team)}",
        f"🏆 {esc(command.competition)}",
        f"🕒 {esc(kickoff)}",
        "",
        "🔬 <b>Experimental AI prediction</b>",
        "",
        f"<b>Selection:</b> {esc(_market_label(selection.market, command))}",
        f"<b>Bookmaker odds:</b> {_number(selection.bookmaker_odds)}",
        f"<b>AI calibrated probability:</b> {_percent(selection.calibrated_probability)}",
        f"<b>Fair odds:</b> {_number(selection.fair_odds)}",
        f"<b>Expected value:</b> {_signed_percent(selection.expected_value)}",
        f"<b>Confidence:</b> {esc(selection.confidence)}",
        "",
        "<b>Key reasoning:</b>",
        *(f"• {esc(reason)}" for reason in reasons),
        "",
        f"<b>Official eligibility:</b> {official}",
        "",
        "<b>Data status:</b>",
        f"• odds age: {selection.freshness}",
        f"• feature snapshot age: {evidence.feature_age_seconds}s",
        f"• lineup status: {esc(evidence.lineup_status)}",
        f"• active model: {esc(evidence.model_artifact_id)}",
        "",
        "⚠️ Experimental Lab analysis only.",
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
