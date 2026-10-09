from copy import deepcopy
from datetime import datetime, timedelta
import pytest
from app.adaptive_lab.contracts import MARKETS,digest
from app.adaptive_lab.expanded_markets_research import contract,payoff,evaluate

AT=datetime.fromisoformat('2026-10-09T18:00:00+00:00')

def artifact():
    return {'version':'FROZEN_SINGLE_SCORE_SCENARIOS_V1','scope':'RESEARCH_ONLY','fixture_id':7,
            'source_fingerprint':'synthetic-source','model_generation':'SYNTHETIC_NOT_A_MODEL',
            'inputs_available_at':AT.isoformat(),'created_at':AT.isoformat(),
            'scenarios':[{'home':1,'away':0,'probability':'.4'},
                         {'home':0,'away':0,'probability':'.3'},
                         {'home':0,'away':1,'probability':'.3'}]}

@pytest.mark.parametrize('family,side,line,home,away,want',[
    ('DOUBLE_CHANCE','1X',None,0,0,'WON'),('DOUBLE_CHANCE','X2',None,0,1,'WON'),
    ('DOUBLE_CHANCE','12',None,0,0,'LOST'),('DNB','HOME',None,0,0,'VOID'),
    ('DNB','AWAY',None,1,0,'LOST'),('DNB','AWAY',None,0,1,'WON'),
    ('ASIAN_HANDICAP','HOME','-1',2,1,'VOID'),('ASIAN_HANDICAP','HOME','-1.5',2,1,'LOST'),
    ('ASIAN_HANDICAP','AWAY','.5',1,1,'WON'),('ASIAN_HANDICAP','AWAY','-.5',0,1,'WON'),
    ('TOTAL','OVER','0.5',1,0,'WON'),('TOTAL','UNDER','4.5',2,2,'WON'),
    ('TOTAL','OVER','4',2,2,'VOID'),('TOTAL','UNDER','4.5',3,2,'LOST')])
def test_exact_market_payoffs(family,side,line,home,away,want):
    assert payoff(contract(family,side,line),home,away)==want

@pytest.mark.parametrize('family,side,line',[
    ('CARDS','OVER','2.5'),('CORNERS','OVER','8.5'),('CORRECT_SCORE','1:0',None),
    ('ASIAN_HANDICAP','HOME','.25'),('ASIAN_HANDICAP','HOME','NaN'),('TOTAL','OVER','-0.5'),
    ('ASIAN_HANDICAP','HOME','.500000000000000000000000000000000000001')])
def test_unmodelled_and_quarter_markets_fail_closed(family,side,line):
    with pytest.raises(ValueError): contract(family,side,line)

def test_dnb_refund_probability_and_ev_are_not_binary_or_conditional():
    a=artifact(); m=contract('DNB','HOME')
    q={'fixture_id':7,'market':m,'type':'CURRENT_CAPTURED_QUOTE','odds':'2',
       'source_fingerprint':'synthetic-quote','origin_timestamp':AT.isoformat(),'captured_at':AT.isoformat()}
    value=evaluate(m,a,expected_fingerprint=digest(a),at=AT,quote=q)
    assert value['probabilities']=={'WON':'0.4','LOST':'0.3','VOID':'0.3'}
    assert value['expected_flat_pnl']=='0.1'  # .4*(2-1)-.3, not .4*2-1
    assert value==evaluate(m,a,expected_fingerprint=digest(a),at=AT,quote=q)
    assert not value['production_eligible'] and value['model_learning_observations']==0
    assert len(MARKETS)==11

def test_no_quote_means_no_price_or_ev_is_invented():
    a=artifact();v=evaluate(contract('DOUBLE_CHANCE','1X'),a,expected_fingerprint=digest(a),at=AT)
    assert v['probabilities']['WON']=='0.7' and v['expected_flat_pnl'] is None

@pytest.mark.parametrize('change',['hash','future','label','duplicate','mass','tiny_mass','negative_score'])
def test_integrity_and_asof_boundaries(change):
    a=artifact();fp=digest(a)
    if change=='hash': a['source_fingerprint']='tampered'
    if change=='future': a['created_at']=(AT+timedelta(seconds=1)).isoformat()
    if change=='label': a['result_label']='WON'
    if change=='duplicate': a['scenarios'][2]={'home':1,'away':0,'probability':'.3'}
    if change=='mass': a['scenarios'][0]['probability']='.5'
    if change=='tiny_mass': a['scenarios'][0]['probability']='.40000000000000000000000000000000000000001'
    if change=='negative_score': a['scenarios'][0]['home']=-1
    if change!='hash': fp=digest(a)
    with pytest.raises(ValueError): evaluate(contract('DNB','HOME'),a,expected_fingerprint=fp,at=AT)

def test_opposing_handicap_pushes_and_monotonic_totals():
    for h in range(5):
        for a in range(5):
            x=payoff(contract('ASIAN_HANDICAP','HOME','-1'),h,a)
            y=payoff(contract('ASIAN_HANDICAP','AWAY','1'),h,a)
            assert (x,y) in {('WON','LOST'),('LOST','WON'),('VOID','VOID')}
            wins=[payoff(contract('TOTAL','OVER',str(line)),h,a)=='WON' for line in [.5,1.5,2.5,3.5,4.5]]
            assert wins==sorted(wins,reverse=True)
