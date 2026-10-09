"""Research-only goal-market payoffs on supplied, pinned as-of score scenarios.

No provider mapping, active market list, selection, calibration or publication is
changed. A goal distribution cannot model cards/corners. DNB/whole handicaps have
push probability: probability of winning is not conditional win probability.
"""
from datetime import datetime
from decimal import Decimal
from fractions import Fraction

from .contracts import digest, utc
from .joint_scenarios import _exact_decimal

VERSION = 'EXPANDED_GOAL_MARKETS_RESEARCH_V1'


def contract(family: str, side: str, line: str | None = None) -> dict:
    """Only regulation-time DC, DNB, totals and integer/half-goal handicaps."""
    allowed = {'DOUBLE_CHANCE':{'1X','X2','12'},'DNB':{'HOME','AWAY'},
               'TOTAL':{'OVER','UNDER'},'ASIAN_HANDICAP':{'HOME','AWAY'}}
    if family not in allowed or side not in allowed[family]:
        raise ValueError('UNSUPPORTED_RESEARCH_MARKET')
    normalized = None
    if family in {'TOTAL','ASIAN_HANDICAP'}:
        if not isinstance(line,str): raise ValueError('EXPLICIT_LINE_REQUIRED')
        try: value=Decimal(line)
        except Exception: raise ValueError('INVALID_RESEARCH_LINE') from None
        if not value.is_finite() or abs(value)>10 or (Fraction(value)*2).denominator != 1:
            raise ValueError('UNSUPPORTED_RESEARCH_LINE')
        if family=='TOTAL' and value<0: raise ValueError('INVALID_RESEARCH_LINE')
        normalized=str(value.normalize()) if value else '0'
    elif line is not None:
        raise ValueError('UNEXPECTED_RESEARCH_LINE')
    return {'family':family,'side':side,'line':normalized,'period':'REGULATION_TIME'}


def payoff(market: dict, home: int, away: int) -> str:
    """Return WON/LOST/VOID; quarter-line partial returns are not approximated."""
    if any(type(g) is not int or not 0<=g<=60 for g in (home,away)):
        raise ValueError('INVALID_SCORE')
    if market != contract(market['family'],market['side'],market.get('line')):
        raise ValueError('NON_CANONICAL_RESEARCH_MARKET')
    family,side=market['family'],market['side']
    if family=='DOUBLE_CHANCE':
        won = home>=away if side=='1X' else away>=home if side=='X2' else home!=away
        return 'WON' if won else 'LOST'
    if family=='DNB': delta=Decimal(home-away if side=='HOME' else away-home)
    elif family=='ASIAN_HANDICAP':
        delta=Decimal(home-away if side=='HOME' else away-home)+Decimal(market['line'])
    else:
        delta=Decimal(home+away)-Decimal(market['line'])
        if side=='UNDER': delta=-delta
    return 'WON' if delta>0 else 'LOST' if delta<0 else 'VOID'


def evaluate(market: dict, artifact: dict, *, expected_fingerprint: str, at: datetime,
             quote: dict | None = None) -> dict:
    """Integrate an unvalidated input distribution; never manufacture a live quote."""
    stamp=utc(at)
    if digest(artifact)!=expected_fingerprint: raise ValueError('SCENARIO_HASH_MISMATCH')
    if (artifact.get('version')!='FROZEN_SINGLE_SCORE_SCENARIOS_V1'
            or artifact.get('scope')!='RESEARCH_ONLY' or not artifact.get('source_fingerprint')
            or not artifact.get('model_generation') or type(artifact.get('fixture_id')) is not int):
        raise ValueError('SCENARIO_PROVENANCE_REQUIRED')
    if not utc(artifact['inputs_available_at'])<=utc(artifact['created_at'])<=stamp:
        raise ValueError('FUTURE_SCENARIO_INPUT')
    if any(k in artifact for k in ('target','result_label','settlement')):
        raise ValueError('LABEL_IN_FORECAST_INPUT')
    rows=artifact['scenarios']
    if not isinstance(rows,list) or not 1<=len(rows)<=4096: raise ValueError('SCENARIO_BOUND')
    masses={k:Fraction(0) for k in ('WON','LOST','VOID')};seen=set()
    for row in rows:
        h,a=row['home'],row['away']; result=payoff(market,h,a)
        if (h,a) in seen: raise ValueError('DUPLICATE_SCENARIO')
        seen.add((h,a));p=Decimal(str(row['probability']))
        if not p.is_finite() or not 0<=p<=1 or len(str(p))>128 or p.as_tuple().exponent < -100:
            raise ValueError('INVALID_SCENARIO_MASS')
        masses[result]+=Fraction(p)
    if sum(masses.values())!=1: raise ValueError('SCENARIO_MASS_NOT_ONE')
    value={'version':VERSION,'as_of':stamp.isoformat(),'market':market,'fixture_id':artifact['fixture_id'],
           'probabilities':{k:_exact_decimal(p) for k,p in masses.items()},
           'model_generation':artifact['model_generation'],'scenario_fingerprint':expected_fingerprint,
           'calibration_status':'UNVALIDATED_RESEARCH_DISTRIBUTION','production_eligible':False,
           'selection_effect':'NONE','model_learning_observations':0,'expected_flat_pnl':None,
           'quote_status':'NO_RETAINED_VERIFIED_QUOTE','quote_fingerprint':None}
    if quote is not None:
        if (quote.get('fixture_id')!=artifact['fixture_id'] or quote.get('market')!=market
                or not quote.get('source_fingerprint') or quote.get('type')!='CURRENT_CAPTURED_QUOTE'):
            raise ValueError('QUOTE_IDENTITY_OR_PROVENANCE_REQUIRED')
        if not utc(quote['origin_timestamp'])<=utc(quote['captured_at'])<=stamp:
            raise ValueError('FUTURE_OR_INVALID_QUOTE_TIME')
        odds=Decimal(str(quote['odds']))
        if not odds.is_finite() or not 1<odds<=10000: raise ValueError('INVALID_QUOTE_ODDS')
        value.update(expected_flat_pnl=_exact_decimal(masses['WON']*(Fraction(odds)-1)-masses['LOST']),
                     quote_status='SUPPLIED_RESEARCH_QUOTE_NOT_EXECUTION_PROOF',quote_fingerprint=digest(quote),
                     quote_age_seconds=(stamp-utc(quote['origin_timestamp'])).total_seconds())
    value['fingerprint']=digest(value)
    return value
