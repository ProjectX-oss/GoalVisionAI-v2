"""Synthetic offline lifecycle regressions; no operational provider or Telegram calls."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest

from app.lab_combo.repository import ComboRepository
from app.lab_combo.service import LabComboService
from app.lab_combo.settlement import resolve_single
from app.lab_telegram.models import LabTelegramConfig
from app.lab_v2_shadow.origin import LABEL, SELECTOR, freeze_origin
from app.lab_v2_shadow.publication import prepare_v2_publications
from app.lab_v2_shadow.statistics import single_cohorts
from app.real_match_lab_analysis.models import LAB_BOT_USERNAME, LAB_CHAT_ID
from tests.test_lab_v2_shadow import NOW, _controlled_ready_candidate


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    value = ComboRepository(Path('var/lab_combo/ledger.db'))
    yield value
    value.close()


def candidate(index=0):
    value = _controlled_ready_candidate(NOW)
    value.update(candidate_id=f'candidate-{index}', fixture_id=7001+index,
                 predictive_family_count=2, predictive_families=['PI_RATINGS', 'API_FOOTBALL_PREDICTION'])
    return value


class Transport:
    def __init__(self, *, unknown=False, username=LAB_BOT_USERNAME[1:]):
        self.bot = SimpleNamespace(username=username)
        self.calls = []
        self.unknown = unknown

    async def send_message_receipt(self, **kwargs):
        self.calls.append(kwargs)
        if self.unknown:
            raise TimeoutError('synthetic unknown outcome')
        return SimpleNamespace(chat_id=LAB_CHAT_ID, message_id=123)


def config(chat=LAB_CHAT_ID):
    return LabTelegramConfig(token='fictional', chat_id=chat, automatic_enabled=True)


def prepare(ledger, item=None, labelled=True):
    return prepare_v2_publications({'candidate_markets': [item or candidate()]}, ledger, now=NOW,
                                   label_origin=labelled)['singles'][0]


def test_truthful_origin_frozen_no_retroactive_relabelling(ledger):
    value = prepare(ledger)
    origin = value['selection_origin']
    assert origin['origins'] == [SELECTOR]
    assert origin['independent_context_model'] is None and origin['context'] is None
    message = ledger.get('single_preview', value['prediction_id'])['message']
    assert LABEL in message and 'nekalibrēts' in message and 'Atsauce:' in message
    assert 'HIGH' not in message
    assert prepare(ledger) == value
    old = prepare(ledger, candidate(1), labelled=False)
    replay = prepare_v2_publications({'candidate_markets':[candidate(1)]}, ledger, now=NOW, label_origin=True)
    assert replay['singles'] == []
    assert replay['publication_blockers']['candidate-1'] == 'HISTORICAL_PREVIEW_REQUIRES_NEW_DECISION'
    assert old == ledger.get('single_prediction', old['prediction_id'])


@pytest.mark.parametrize('failure', ['absent', 'broken', 'different_candidate'])
def test_context_unavailability_cannot_suppress_selector(failure):
    class Snapshots:
        def load(self, key):
            if failure == 'broken': raise OSError('synthetic write/proof failure')
            if failure == 'absent': return None
            return SimpleNamespace(opportunity=SimpleNamespace(candidate_id='old'))
    origin = freeze_origin(candidate(), now=NOW, observer=SimpleNamespace(snapshots=Snapshots()))
    assert origin['context'] is None and origin['origins'] == [SELECTOR]


@pytest.mark.parametrize('wrong', ['chat', 'bot', 'approval', 'preview'])
def test_new_publication_fail_closed(ledger, wrong):
    item = candidate()
    value = prepare(ledger, item)
    transport = Transport(username='WrongBot' if wrong == 'bot' else LAB_BOT_USERNAME[1:])
    if wrong in {'approval','preview'}:
        # Corruption is simulated at an injected reader; no immutable evidence rewritten.
        get = ledger.get
        def altered(kind, key):
            result = get(kind, key)
            if key == value['prediction_id'] and kind == ('single_prediction' if wrong == 'approval' else 'single_preview'):
                return {**result, **({'decision': 'REJECTED'} if wrong == 'approval' else {'message':'invented'})}
            return result
        ledger.get = altered
    result = asyncio.run(LabComboService(ledger, None, clock=lambda: NOW).publish_experimental(
        'single_prediction', value['prediction_id'], config('wrong' if wrong == 'chat' else LAB_CHAT_ID), transport))
    assert not result['sent'] and not transport.calls


@pytest.mark.parametrize('unknown', [False, True])
def test_cross_path_economic_dedup_and_unknown_no_retry(ledger, unknown):
    first = prepare(ledger)
    changed = candidate(); changed.update(candidate_id='other-path', policy='other-selector-version')
    second = prepare(ledger, changed)
    transport = Transport(unknown=unknown)
    service = LabComboService(ledger, None, clock=lambda: NOW)
    asyncio.run(service.publish_experimental('single_prediction', first['prediction_id'], config(), transport))
    result = asyncio.run(service.publish_experimental('single_prediction', second['prediction_id'], config(), transport))
    assert not result['sent'] and len(transport.calls) == 1
    assert len(ledger.all('economic_claim')) == 1
    if unknown:
        assert ledger.get('delivery_unknown', 'single_prediction:' + first['prediction_id'])
        assert not ledger.all('receipt')


def test_concurrent_claims_and_interrupted_recovery(ledger):
    a = prepare(ledger)
    changed = candidate(); changed['candidate_id'] = 'another'
    b = prepare(ledger, changed)
    path = Path('var/lab_combo/ledger.db'); barrier = Barrier(2)
    def claim(p):
        store = ComboRepository(path)
        try:
            barrier.wait(timeout=5)
            return store.claim_publication('single_prediction', p, {'prediction_id':p['prediction_id']})
        finally:store.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim, (a,b))) == [False,True]
    # An interrupted claim without any receipt is still consumed after restart.
    assert not ledger.claim_publication('single_prediction', b, {'prediction_id':b['prediction_id']})


def test_legacy_claim_blocks_new_origin(ledger):
    old = prepare(ledger, labelled=False)
    changed = candidate();changed['candidate_id']='new-origin'
    value = prepare(ledger, changed)
    ledger.append('claim', 'single_prediction:'+old['prediction_id'], {'prediction_id':old['prediction_id']})
    t=Transport()
    assert not asyncio.run(LabComboService(ledger,None,clock=lambda:NOW).publish_experimental(
        'single_prediction',value['prediction_id'],config(),t))['sent']
    assert not t.calls


@pytest.mark.parametrize('status,score,expected', [('FT',(2,0),'WON'),('AET',(0,1),'LOST'),('CANC',(None,None),'VOID')])
def test_result_labels_original_link_and_receipt_requirement(ledger,status,score,expected):
    value=prepare(ledger);pid=value['prediction_id'];t=Transport()
    service=LabComboService(ledger,None,clock=lambda:NOW)
    assert asyncio.run(service.publish_experimental('single_prediction',pid,config(),t))['sent']
    after=NOW+timedelta(hours=4)
    payload={'response':[{'fixture':{'id':value['fixture_id'],'status':{'short':status}},
              'score':{'fulltime':{'home':score[0],'away':score[1]},'extratime':{'home':5,'away':5}},
              'goals':{'home':6,'away':6}}]}
    result=resolve_single(value,payload,after)
    assert result['status']==expected and result['selection_origin']==value['selection_origin']
    ledger.append('single_settlement',pid,result)
    message=service._single_result_message(result,{})
    assert LABEL in message and 'https://t.me/c/3510920417/123' in message and expected in message
    ledger.append('single_settlement_preview',pid,{'message':message})
    service.clock=lambda:after
    assert asyncio.run(service.publish_experimental('single_settlement',pid,config(),t))['sent']


def test_cohort_denominators_pending_void_overlap_and_asof(ledger):
    for i,status in enumerate(('WON','LOST','VOID',None)):
        p=prepare(ledger,candidate(i));pid=p['prediction_id']
        ledger.append('receipt','single_prediction:'+pid,dict(status='SENT',sent=True,chat_id=LAB_CHAT_ID,
                      message_id=i+1,sent_at_utc=NOW.isoformat()))
        if status:
            ledger.append('single_settlement',pid,dict(status=status,unit_result='0.90' if status=='WON' else '-1' if status=='LOST' else '0',settled_at_utc=(NOW+timedelta(hours=3)).isoformat()))
    kw=dict(start=NOW-timedelta(days=1),end=NOW+timedelta(days=1),as_of=NOW+timedelta(hours=4))
    s=single_cohorts(ledger,**kw);total=s['forward_union']
    assert (total['published'],total['pending'],total['WON'],total['LOST'],total['VOID'])==(4,1,1,1,1)
    assert total['hit_rate']=='0.5' and total['roi_denominator_units']==3 and total['flat_unit_pnl']=='-0.10'
    assert s['independent_football_context_model']['published']==0
    assert single_cohorts(ledger,**{**kw,'as_of':NOW})['forward_union']['pending']==4
    # Cohort endorsements supplied before outcomes; intersecting sets never inflate total.
    get=ledger.all
    def multi(kind):
        values=deepcopy(get(kind))
        if kind=='single_prediction':values[0]['selection_origin']['origins'].append('OTHER_VALIDATED_SELECTOR')
        return values
    ledger.all=multi
    s=single_cohorts(ledger,**kw)
    assert s['forward_union']['published']==4 and s['multi_origin_overlap']['published']==1
    assert s['cohorts_overlap_do_not_sum'][SELECTOR]['published']==4


@pytest.mark.parametrize('enabled,failed', [(False,False),(True,False),(True,True)])
def test_existing_cycle_wrapper_single_instance_and_no_output_change(tmp_path,monkeypatch,enabled,failed):
    from app.lab_v2_shadow import cli
    events=[];sentinel={'unchanged': True}
    class Observer:
        def __init__(self,*args,**kwargs):events.append(self)
        def finish(self,**kwargs):events.append(kwargs);return {'SYNTHETIC':1}
    monkeypatch.setattr('app.prematch_football_context.readiness.composition.ProspectiveObservation',Observer)
    async def cycle(args,*,football_context=None):
        if enabled:assert football_context is events[0]
        else:assert football_context is None
        if failed:raise RuntimeError('synthetic cycle failure')
        return sentinel
    monkeypatch.setattr(cli,'_cycle',cycle)
    args=SimpleNamespace(football_context_root=tmp_path if enabled else None)
    if failed:
        with pytest.raises(RuntimeError):asyncio.run(cli.configured_cycle(args))
    else:assert asyncio.run(cli.configured_cycle(args)) is sentinel
    assert len(events)==(2 if enabled else 0)
    if enabled:assert events[-1]['completed'] is not failed


def test_observer_reports_real_cycle_cooldown_without_training(tmp_path,monkeypatch):
    from app.adaptive_lab.repository import AuditRepository
    from app.adaptive_lab.coordinator import LearningCoordinator
    from app.adaptive_lab.automl import AutoLearner
    repo=AuditRepository(tmp_path/'adaptive.db')
    stamp=(NOW-timedelta(days=2)).isoformat()
    repo.append('learning_cycles','prior','PREMATCH',{'created_at':stamp},stamp)
    coordinator=LearningCoordinator(repo)
    monkeypatch.setattr(coordinator.governance,'rollback',lambda *args,**kw:{'status':'UNCHANGED'})
    monkeypatch.setattr(AutoLearner,'run',lambda *args,**kw:pytest.fail('inspection triggered training'))
    result=coordinator.after_settlement('PREMATCH',now=NOW,train=False)
    assert result['eligibility']['cycle_due'] is False
    assert result['eligibility']['new_resolved']==0
    assert result['research']['status']=='DAILY_LEARNING_JOB_ONLY'
    repo.close()


@pytest.mark.parametrize('stage',['construction','finish'])
def test_optional_observer_lifecycle_failure_preserves_cycle(tmp_path,monkeypatch,capsys,stage):
    from app.lab_v2_shadow import cli
    sentinel={'unchanged':True};calls=[]
    class Observer:
        def __init__(self,*args,**kwargs):
            if stage=='construction':raise OSError('secret must not appear')
        def finish(self,**kwargs):raise OSError('secret must not appear')
    async def cycle(args,*,football_context=None):
        calls.append(football_context);return sentinel
    monkeypatch.setattr('app.prematch_football_context.readiness.composition.ProspectiveObservation',Observer)
    monkeypatch.setattr(cli,'_cycle',cycle)
    assert asyncio.run(cli.configured_cycle(SimpleNamespace(football_context_root=tmp_path))) is sentinel
    assert len(calls)==1 and (calls[0] is None)==(stage=='construction')
    assert 'secret' not in capsys.readouterr().err


def test_outcome_correction_conflict_preserves_original_evidence(ledger):
    """No correction can silently overwrite a previously stored terminal outcome."""
    original={'prediction_id':'synthetic','status':'WON','unit_result':'0.9'}
    ledger.append('single_settlement','synthetic',original)
    with pytest.raises(ValueError,match='Conflicting'):
        ledger.append('single_settlement','synthetic',{**original,'status':'LOST','unit_result':'-1'})
    assert ledger.get('single_settlement','synthetic')==original


@pytest.mark.parametrize('failure',[None,'proof_missing','proof_corrupt','source_unavailable'])
def test_context_link_requires_offline_reproduction_and_retained_proof(tmp_path,monkeypatch,failure):
    from tests.test_prematch_registry_readiness import renewed_registry,start,decide
    path=tmp_path/'registry.sqlite';clock=renewed_registry(path)
    observer=start(tmp_path/'observation',path,lambda:clock,2)
    snapshot=decide(observer,2)
    item=candidate()
    item.update(fixture_id=9999,candidate_id=snapshot.opportunity.candidate_id,
                home_team_id=snapshot.home_team_id,away_team_id=snapshot.away_team_id)
    if failure in {'proof_missing','proof_corrupt'}:
        get=observer.ledger.get
        def broken(kind,key):
            if kind=='REGULATION_PROOF':
                if failure=='proof_missing':raise ValueError('missing proof')
                return {**get(kind,key),'resolution_fingerprint':'corrupt'}
            return get(kind,key)
        monkeypatch.setattr(observer.ledger,'get',broken)
    if failure=='source_unavailable':
        monkeypatch.setattr(observer.evidence,'load',lambda *a,**kw:(_ for _ in ()).throw(ValueError('missing source')))
    origin=freeze_origin(item,now=clock,observer=observer)
    assert (origin['context'] is not None)==(failure is None)
    if failure is None:
        assert origin['context']['snapshot_hash']==snapshot.snapshot_hash
        assert origin['context']['use']=='OBSERVATION_ONLY'
    assert origin['origins']==[SELECTOR]
    observer.finish(completed=True)
