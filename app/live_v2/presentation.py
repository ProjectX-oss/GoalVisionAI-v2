"""Truthful Latvian plain text, rendered only from frozen LIVE evidence."""
from decimal import Decimal

TITLE = '🟢 GoalVision AI • V2 LIVE'


def label(quote: dict) -> str:
    if quote['family'] == '1X2':
        return {'1': '1', 'X': 'X', '2': '2'}[quote['side']]
    if quote['family'] == 'BTTS':
        return 'Abas komandas gūs vārtus — ' + {'YES': 'Jā', 'NO': 'Nē'}[quote['side']]
    if quote['family'] == 'TOTALS' and quote['line'] in {'1.5', '2.5', '3.5'}:
        return {'OVER': 'Virs', 'UNDER': 'Zem'}[quote['side']] + f" {quote['line']} vārtiem"
    raise ValueError('UNSUPPORTED_PUBLIC_MARKET')


def team(value: str) -> str:
    return ' '.join(value.split())[:100]


def prediction(candidate: dict) -> str:
    """Consensus is explicitly a market assessment, never a model probability."""
    state, market = candidate['state'], candidate['market']
    return '\n'.join((TITLE, '', f"⚽ {team(state['home'])} – {team(state['away'])}",
        f"⏱ {state['minute']}' | {state['home_score']}:{state['away_score']}",
        f"🎯 Likme: {label(market['quote'])}", f"💰 Koeficients: {Decimal(market['quote']['odds']):.2f}", '',
        f"📊 LIVE tirgus novērtējums: {Decimal(market['probability'])*100:.1f}%",
        f"📈 Cenas pārsvars: {Decimal(market['edge'])*100:+.1f} pp",
        '🧠 LIVE signāli: rezultāts, spēles minūte, sitieni un sitieni vārtu rāmī',
        'Vērtējums balstīts pašreizējā tirgus cenās. Peļņa nav garantēta.'))


def result(settlement: dict, statistics: dict) -> str:
    candidate = settlement['selection']
    state, quote = candidate['state'], candidate['market']['quote']
    score = settlement['regulation_score']
    totals = statistics['overall']
    accuracy = '—' if totals['accuracy'] is None else f"{Decimal(totals['accuracy'])*100:.1f}%"
    roi = '—' if totals['roi'] is None else f"{Decimal(totals['roi'])*100:+.1f}%"
    return '\n'.join((TITLE, '', {'WON': '✅ WON', 'LOST': '❌ LOST', 'VOID': '➖ VOID'}[settlement['outcome']],
        f"⚽ {team(state['home'])} – {team(state['away'])}",
        f"⏱ Izvēle veikta: {state['minute']}' | {state['home_score']}:{state['away_score']}",
        f"🎯 Likme: {label(quote)}", f"💰 Koeficients: {Decimal(quote['odds']):.2f}",
        f"🏁 Gala rezultāts: {score[0]}:{score[1]}" if score else '🏁 Gala rezultāts: —',
        f"💵 P/L: {Decimal(settlement['unit_result']):+.2f}u", '', '📊 V2 LIVE statistika',
        f"Likmes: {totals['bets']}", f"✅ WON: {totals['WON']} | ❌ LOST: {totals['LOST']} | ➖ VOID: {totals['VOID']}",
        f"Precizitāte: {accuracy}", f"P/L: {Decimal(totals['pnl']):+.2f}u | ROI: {roi}"))
