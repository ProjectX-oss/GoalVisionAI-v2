"""Two-leg replacement: exact filters, diagnostic disagreement, delivery and results."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import product
from types import SimpleNamespace

import pytest

from app.lab_v2_shadow import combo_double as double, combo_market as market, combo_agreement
from app.lab_v2_shadow.publication import prepare_v2_publications, v2_combo_message
from app.lab_v2_shadow.accuracy_combo import review_accuracy_combo, combo_identity
from app.lab_v2_shadow.publication_policy import review_accuracy_publication
from app.lab_combo.service import LabComboService
from app.lab_combo.settlement import aggregate, economic_settlement, resolve_leg
from app.lab_combo.odds_policy import combo_odds_blocker
from app.lab_combo.bot_routing import cohort_statistics
from tests.test_private_single_170 import candidate
from tests.test_lab_v2_shadow import NOW, bind_candidate_evidence
from tests.test_prematch_v2_enablement import ledger
from tests.test_combo_bot_routing import routed, send, RoutedTransport, TOKEN
from tests.test_lab_combo_early_loss import Provider, payload


@pytest.fixture(autouse=True)
def active(monkeypatch):
    for flag in (double.FLAG, combo_agreement.FLAG, market.FLAG,
                 'GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130', 'GOALVISION_LAB_TODAY_ONLY',
                 'GOALVISION_LAB_SINGLE_MIN_ODDS_150', 'GOALVISION_LAB_SETTLEMENT_REPLIES'):
        monkeypatch.setenv(flag, '1')
    def deny(*args, **kwargs):
        raise AssertionError('NETWORK_FORBIDDEN')
    monkeypatch.setattr('socket.socket.connect', deny)
    monkeypatch.setattr('socket.create_connection', deny)


def prepare(store, rows=None, now=NOW):
    return prepare_v2_publications({'candidate_markets': rows if rows is not None else [candidate(0),candidate(1)]},
        store, now=now, label_origin=True, accuracy_combos=True)


@pytest.mark.parametrize('odds,p,expected', [
    ('1.70','.70',True), ('1.70','.80',True), ('2.25','.75',True),
    ('1.699999999999999999','.75',False), ('1.70','.699999999999999999',False),
    ('1.70','.800000000000000001',False), ('1.70','0',False), ('1.70','1',False),
])
def test_exact_two_leg_filters_and_real_delivery(ledger, routed, odds, p, expected):
    result = prepare(ledger, [candidate(0,odds,p),candidate(1,odds,p)])
    assert bool(result['combos']) is expected
    assert 'parallel_double' in result['combo_diagnostics']
    assert 'parallel_market' not in result['combo_diagnostics']
    if expected:
        value, = result['combos']
        assert len(value['legs']) == 2 and value['policy'] == double.POLICY
        assert Decimal(value['combined_odds']) == Decimal(odds)**2
        assert value['statistics_cohort'] == double.COHORT
        assert review_accuracy_combo(value, now=NOW)['eligible']
        client = RoutedTransport(TOKEN)
        outcome = send(ledger,'combo_prediction',value['prediction_id'],routed[2],client)
        assert outcome['sent'] and len(client.calls) == 1
        text = client.calls[0]['text']
        assert 'COMBO Double tests' in text and '2 spēles' in text and '70–80%' in text
        assert '3️⃣' not in text and 'Tirgus' not in text


def test_disagreement_relaxed_only_for_double_and_findings_retained(ledger, monkeypatch):
    rows = [candidate(i,'2.25','.75') for i in range(2)]
    for row in rows:
        row['confidence']='LOW'
        row['soft_findings']=['MATERIAL_SIGNAL_DISAGREEMENT','SEVERE_CURRENT_MATCH_INTELLIGENCE_CONTRADICTION']
        assert not review_accuracy_publication(row,now=NOW)['eligible']
    before=deepcopy(rows)
    value, = prepare(ledger,rows)['combos']
    assert rows == before
    assert not prepare(ledger,rows)['singles']
    for leg in value['legs']:
        findings=leg['double_selection_review']['diagnostic_quality_findings']
        assert 'MATERIAL_SIGNAL_DISAGREEMENT' in findings
        assert 'SEVERE_MODEL_MARKET_CONTRADICTION' in findings
        assert 'accuracy_publication_review' not in leg
    monkeypatch.setenv(double.FLAG,'0')
    assert not double.requested()


def test_filter_before_fixture_rank_and_full_pool_without_mutation(ledger):
    rows=[candidate(i,'1.50','.79') for i in range(4)]
    rows.extend([candidate(2,'1.70','.71','UNDER_2_5'),candidate(3,'1.80','.72','UNDER_2_5')])
    before=deepcopy(rows)
    value,=prepare(ledger,rows)['combos']
    assert rows==before and len(value['legs'])==2
    assert all(leg['market']=='UNDER_2_5' for leg in value['legs'])
    same,=prepare(ledger,list(reversed(rows)),now=NOW+timedelta(seconds=1))['combos']
    assert same==value


@pytest.mark.parametrize('problem', ['stale_quote','future_quote','quote_tamper','probability_tamper',
    'zero_signal','no_model','missing_signal','unknown_hard','fixture_mismatch','tomorrow','started',
    'early','missing_review','expired_review','same_team','same_fixture','no_label','invalid_flag'])
def test_integrity_freshness_and_independence_still_block(ledger, monkeypatch, problem):
    rows=[candidate(0),candidate(1)]
    row=rows[1]
    if problem=='stale_quote': row['provider_origin_timestamp_utc']=(NOW-timedelta(days=2)).isoformat()
    elif problem=='future_quote': row['goalvision_retrieved_at_utc']=(NOW+timedelta(seconds=1)).isoformat()
    elif problem=='quote_tamper': row['quote_provenance_fingerprint']='bad'
    elif problem=='probability_tamper': row['ensemble_probability']='.76'
    elif problem=='zero_signal': row['signals'][0]['probability']='0'
    elif problem=='no_model': row['signals']=row['signals'][1:]
    elif problem=='missing_signal': row.pop('signals')
    elif problem=='unknown_hard': row['hard_failures']=['FUTURE_UNKNOWN_DATA_FAILURE']
    elif problem=='fixture_mismatch': row['home_team_id']=123456
    elif problem=='tomorrow': row['kickoff_utc']=(NOW+timedelta(days=1)).isoformat()
    elif problem=='started': row['kickoff_utc']=NOW.isoformat()
    elif problem=='early': row['stage']='EARLY_CANDIDATE'
    elif problem=='missing_review': row.pop('final_review_completed_at_utc')
    elif problem=='expired_review': row['final_review_completed_at_utc']=(NOW-timedelta(hours=1)).isoformat()
    elif problem=='same_team':
        row['home_team_id']=rows[0]['home_team_id'];bind_candidate_evidence(row)
    elif problem=='same_fixture': rows[1]=deepcopy(rows[0])
    elif problem=='invalid_flag': monkeypatch.setenv(double.FLAG,'yes')
    if problem=='no_label':
        values,_=double.prepare(rows,ledger,now=NOW,label_origin=False)
        assert not values
    else:
        assert not prepare(ledger,rows)['combos']
    assert not ledger.all('claim')


@pytest.mark.parametrize('field', ['combined_odds','estimated_probability_if_independent',
    'estimated_ev_if_independent','leg_count','minimum_combo_leg_decimal_odds','statistics_cohort','leg_probability'])
def test_frozen_tampering_is_rejected_before_claim(ledger, field):
    value,=prepare(ledger)['combos']
    changed=deepcopy(value)
    if field=='leg_probability': changed['legs'][0]['probability']='.79'
    else: changed[field]='bad'
    assert not review_accuracy_combo(changed,now=NOW)['eligible']


def test_flag_off_or_old_market_does_not_send_new_claims(ledger,routed,monkeypatch):
    value,=prepare(ledger)['combos']
    client=RoutedTransport(TOKEN)
    monkeypatch.setenv(double.FLAG,'0')
    assert not send(ledger,'combo_prediction',value['prediction_id'],routed[2],client)['sent']
    monkeypatch.setenv(double.FLAG,'1')
    assert market.published_selection_blocker(market.POLICY)=='COMBO_MARKET_REPLACED_BY_DOUBLE'
    assert not market.requested()
    assert not client.calls and not ledger.all('claim')


def test_exact_cardinality_requires_double_policy(ledger):
    value,=prepare(ledger)['combos']
    assert combo_odds_blocker(value,minimum=Decimal('1.30')) is None
    changed=deepcopy(value);changed['combo_selection_policy']='UNKNOWN'
    assert combo_odds_blocker(changed,minimum=Decimal('1.30')) is not None
    triple=deepcopy(value);triple['legs'].append(candidate(2))
    assert not review_accuracy_combo(triple,now=NOW)['eligible']


def test_one_per_cycle_disjoint_with_claimed_and_prepared_dc(ledger,routed):
    rows=[candidate(i) for i in range(6)]
    first,=prepare(ledger,rows)['combos']
    assert send(ledger,'combo_prediction',first['prediction_id'],routed[2],RoutedTransport(TOKEN))['sent']
    second,=prepare(ledger,rows)['combos']
    assert not {x['fixture_id'] for x in first['legs']} & {x['fixture_id'] for x in second['legs']}
    dc={'prediction_id':'prepared-dc','legs':rows[2:5]}
    third,diag=double.prepare(rows,ledger,now=NOW,label_origin=True,excluded_combos=(dc,))
    assert third==[] and diag['eligible_fixture_count']==1


def test_atomic_cross_lane_claim_blocks_overlap_in_both_directions(ledger):
    value,=prepare(ledger)['combos']
    old={**value,'prediction_id':'old-market','combo_selection_policy':market.POLICY,'policy':market.POLICY}
    ledger.append('prediction',old['prediction_id'],old)
    assert ledger.claim_publication('combo_prediction',old,{'prediction_id':old['prediction_id']})
    assert not ledger.claim_publication('combo_prediction',value,{'prediction_id':value['prediction_id']})


@pytest.mark.parametrize('outcomes', list(product(('WON','LOST','VOID'),repeat=2)))
def test_two_leg_complete_outcomes_and_separate_statistics(ledger,routed,outcomes,monkeypatch):
    value,=prepare(ledger)['combos']
    assert send(ledger,'combo_prediction',value['prediction_id'],routed[2],RoutedTransport(TOKEN))['sent']
    later=max(datetime.fromisoformat(x['kickoff_utc']) for x in value['legs'])+timedelta(hours=3)
    responses={leg['fixture_id']:payload(leg['fixture_id'],'CANC' if outcome=='VOID' else 'FT',
        (3,0) if outcome=='WON' else (0,0)) for leg,outcome in zip(value['legs'],outcomes)}
    monkeypatch.setenv(double.FLAG,'0') # results remain enabled after new-pick pause
    report=asyncio.run(LabComboService(ledger,None,clock=lambda:later,early_combo_loss=True)
        .check_results(Provider(responses),maximum_calls=20))
    assert report['completed']==[value['prediction_id']]
    settled=ledger.get('settlement',value['prediction_id'])
    expected=('LOST' if 'LOST' in outcomes else 'VOID' if outcomes==('VOID','VOID')
              else 'PARTIAL_VOID' if 'VOID' in outcomes else 'WON')
    assert settled['status']==expected
    assert settled['partial_void']==(outcomes.count('VOID')==1)
    stats=cohort_statistics(ledger,routed[2].route,selection_policy=double.POLICY)
    assert stats['total_published']==stats['total_settled']==1 and stats['selection_cohort']==double.COHORT
    assert cohort_statistics(ledger,routed[2].route,selection_policy=market.POLICY)['total_published']==0
    assert cohort_statistics(ledger,routed[2].route,selection_policy='LEGACY')['total_published']==0
    client=RoutedTransport(TOKEN)
    assert send(ledger,'combo_settlement',value['prediction_id'],routed[2],client,now=later)['sent']
    assert client.calls[0]['reply_to_message_id']==123
    assert 'COMBO Double testa statistika' in client.calls[0]['text']
    assert not send(ledger,'combo_settlement',value['prediction_id'],routed[2],client,now=later)['sent']
    assert len(client.calls)==1


def test_double_photo_result_uses_original_reply(ledger,routed,tmp_path):
    from app.lab_combo.presentation import ResultImagePaths
    value,=prepare(ledger)['combos']
    assert send(ledger,'combo_prediction',value['prediction_id'],routed[2],RoutedTransport(TOKEN))['sent']
    later=max(datetime.fromisoformat(x['kickoff_utc']) for x in value['legs'])+timedelta(hours=3)
    responses={leg['fixture_id']:payload(leg['fixture_id'],score=(3,0)) for leg in value['legs']}
    asyncio.run(LabComboService(ledger,None,clock=lambda:later).check_results(Provider(responses),maximum_calls=20))
    photo=tmp_path/'won.jpg';photo.write_bytes(b'offline-test-only')
    client=RoutedTransport(TOKEN)
    service=LabComboService(ledger,None,clock=lambda:later,
        result_images=ResultImagePaths(win=photo,loss=None))
    result=asyncio.run(service.publish_experimental('combo_settlement',value['prediction_id'],routed[2],client))
    assert result['sent'] and client.calls[0]['image_path']==photo
    assert client.calls[0]['reply_to_message_id']==123


def test_bounded_full_pool_without_forced_pair(ledger):
    rows=[candidate(i,'1.50','.75') for i in range(61)]
    values,diagnostics=double.prepare(rows+[candidate(100),candidate(101)],ledger,now=NOW,label_origin=True)
    assert len(values)==1 and len(values[0]['legs'])==2
    empty,diagnostics=double.prepare([candidate(0)]*(double.MAX_CANDIDATES+1),ledger,now=NOW,label_origin=True)
    assert not empty and diagnostics['reason']=='COMBO_DOUBLE_CAPACITY'


def test_double_early_loss_retains_remaining_leg_and_immutable_accounting(ledger,routed):
    rows=[candidate(0),candidate(1)]
    rows[0]['kickoff_utc']=(NOW+timedelta(minutes=30)).isoformat()
    rows[1]['kickoff_utc']=(NOW+timedelta(hours=4)).isoformat()
    value,=prepare(ledger,rows)['combos']
    assert send(ledger,'combo_prediction',value['prediction_id'],routed[2],RoutedTransport(TOKEN))['sent']
    first=NOW+timedelta(hours=3)
    asyncio.run(LabComboService(ledger,None,clock=lambda:first,early_combo_loss=True)
        .check_results(Provider({7001:payload(7001,score=(0,0))}),maximum_calls=20))
    frozen=ledger.get('settlement',value['prediction_id'])
    assert frozen['status']=='LOST' and len(frozen['pending_legs'])==1 and frozen['unit_result']=='-1'
    later=NOW+timedelta(hours=7)
    report=asyncio.run(LabComboService(ledger,None,clock=lambda:later,early_combo_loss=False)
        .check_results(Provider({7002:payload(7002,score=(3,0))}),maximum_calls=20))
    assert report['combo_detail_completed']==[value['prediction_id']]
    assert ledger.get('settlement',value['prediction_id'])==frozen
    assert len(ledger.get('combo_result_detail',value['prediction_id'])['legs'])==2
    assert cohort_statistics(ledger,routed[2].route,selection_policy=double.POLICY)['total_settled']==1
