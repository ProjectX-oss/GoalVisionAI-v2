"""Transport-free LIVE single and settlement text."""
from __future__ import annotations
from app.lab_combo.presentation import market_label


def prediction_message(value: dict) -> str:
    source = (['Avots: API-Football LIVE; bukmeikers nav norādīts.',
               'API koeficients ir orientējošs; pieejamību pārbaudi savā bukmeikerī.']
              if value.get('quote_origin_kind') == 'API_FOOTBALL_FEED_UPDATE_V1' else [])
    from .selection import PROBABILITY_POLICY
    probability_test=value.get('selection_policy') == PROBABILITY_POLICY
    selection_lines = (['🧪 LIVE tests · modeļa varbūtība 60–70%.',
                        'Modeļa procents nav pierādīts uzvaru biežums.'] if probability_test else
                       [f"📈 Edge: {value['edge']:+.1%}", f"📊 EV: {value['expected_value']:+.1%}"])
    return '\n'.join([
        '🔴 GOALVISION LIVE — Lab',
        f"⚽ {value['home_team']} vs {value['away_team']}",
        f"⏱ {value['live_minute']}'",f"📊 Score: {value['live_score_home']}–{value['live_score_away']}",
        f"🎯 LIVE selection: {market_label(value['market'])}",f"💰 LIVE odds: {float(value['captured_odds']):.2f}",
        f"🧠 GoalVision: {float(value['ensemble_probability']):.1%}", *selection_lines,
        f"Confidence: {value['candidate_lane'].removeprefix('LIVE_')}",
        *source, value['reasoning'],'Experimental estimate; no guaranteed outcome.'])


def settlement_message(value: dict, statistics: dict) -> str:
    label={'WON':'✅ LIVE WON','LOST':'❌ LIVE LOST','VOID':'↩️ LIVE VOID'}[value['status']]
    source = ['Uzskaite pēc orientējošā API-Football koeficienta.'] if value.get('quote_origin_kind') == 'API_FOOTBALL_FEED_UPDATE_V1' else []
    return '\n'.join([label,f"{value.get('home_team')} vs {value.get('away_team')}",
                      f"{market_label(value['market'])} | odds {value['captured_odds']}",
                      f"LIVE flat-unit PnL: {statistics['flat_unit_pnl']:+.2f}",
                      f"LIVE wins/losses/voids: {statistics['wins']}/{statistics['losses']}/{statistics['voids']}",*source])
