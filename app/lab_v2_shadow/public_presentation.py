"""Versioned Latvian presentation; all numeric evidence is supplied and frozen."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from zoneinfo import ZoneInfo

from app.lab_combo.presentation import public_decimal, public_percent, score, signed_units, team_pair

VERSION = 'LAB_V2_PUBLIC_MESSAGE_V2'
TITLE = '🧪 GoalVision AI Lab • V2 atlase'
MARKETS = MappingProxyType({
    'HOME_WIN': '1', 'DRAW': 'X', 'AWAY_WIN': '2',
    'OVER_1_5': 'Virs 1.5 vārtiem', 'UNDER_1_5': 'Zem 1.5 vārtiem',
    'OVER_2_5': 'Virs 2.5 vārtiem', 'UNDER_2_5': 'Zem 2.5 vārtiem',
    'OVER_3_5': 'Virs 3.5 vārtiem', 'UNDER_3_5': 'Zem 3.5 vārtiem',
    'BTTS_YES': 'Abas komandas gūs vārtus — Jā',
    'BTTS_NO': 'Abas komandas gūs vārtus — Nē',
})
SIGNALS = MappingProxyType({
    'API_FOOTBALL_PREDICTION': 'API-Football prognoze',
    'RESULT_HISTORY_MODEL_CONTEXT': 'Rezultātu vēstures modelis',
    'PI_RATINGS': 'Komandu spēka reitings',
    'CURRENT_MATCH_INTELLIGENCE': 'Spēles konteksta analīze',
    'GOALVISION_EXPERIMENTAL_MODEL': 'GoalVision modelis',
})
OUTCOMES = MappingProxyType({'WON': '✅ WON', 'LOST': '❌ LOST', 'VOID': '➖ VOID'})


def analysis_signals(families: list[str]) -> str:
    """Never turn market consensus or an unknown identifier into a model claim."""
    labels = sorted({SIGNALS.get(name, 'Modeļa signāls') for name in families
                     if name != 'CURRENT_MARKET_CONSENSUS'})
    return ', '.join(labels) if labels else '—'


def statistics_block(snapshot: dict) -> str:
    """Display the existing labelled single cohort totals without new accounting."""
    totals = snapshot['totals']
    roi = totals['flat_unit_roi']
    roi_text = f"{Decimal(roi) * 100:+.1f}%" if roi is not None else '—'
    return '\n'.join((
        '📊 V2 statistika',
        f"Likmes: {totals['settled']} | ✅ WON: {totals['WON']} | ❌ LOST: {totals['LOST']} | ➖ VOID: {totals['VOID']}",
        f"🎯 Precizitāte: {public_percent(totals['hit_rate'])}",
        f"📈 P/L: {Decimal(totals['flat_unit_pnl']):+.2f}u | ROI: {roi_text}",
    ))


def prediction_message(value: dict) -> str:
    """Render exclusively from the immutable prediction and its statistics snapshot."""
    presentation = value['public_presentation']
    if presentation['version'] != VERSION:
        raise ValueError('UNKNOWN_PUBLIC_PRESENTATION_VERSION')
    kickoff = datetime.fromisoformat(value['kickoff_utc']).astimezone(ZoneInfo('Europe/Riga'))
    return '\n'.join((TITLE, '', f"⚽ {team_pair(value)}",
        f"🎯 Likme: {MARKETS[value['market']]}",
        f"💰 Koeficients: {public_decimal(value['captured_odds'])}",
        f"⏰ Sākums: {kickoff:%d.%m.%Y %H:%M} (Latvija)", '',
        f"📊 Novērtētā varbūtība: {Decimal(value['ensemble_probability']) * 100:.1f}%",
        f"📈 Vērtības pārsvars: {Decimal(value['edge']) * 100:+.1f} pp",
        f"🧠 Analīzes signāli: {analysis_signals(value['selection_origin']['predictive_families'])}",
        '', statistics_block(presentation['statistics'])))


def result_message(value: dict, snapshot: dict) -> str:
    """Display the accepted settlement's unit result; never recompute winnings."""
    return '\n'.join((TITLE, '', OUTCOMES[value['status']], '',
        f"⚽ {team_pair(value)}", f"🎯 Likme: {MARKETS[value['market']]}",
        f"💰 Koeficients: {public_decimal(value['captured_odds'])}",
        f"🏁 Rezultāts: {score(value)}", f"💵 P/L: {signed_units(value['unit_result'])}",
        '', statistics_block(snapshot)))
