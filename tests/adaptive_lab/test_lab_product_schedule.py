"""Riga product-clock boundaries and receipt-backed weekly reporting, no network."""
from __future__ import annotations
import asyncio
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from types import SimpleNamespace as N
import pytest
from app.lab_combo.publication_window import RIGA,publication_blocker,window_status
from app.adaptive_lab.weekly import week_bounds,latest_due,next_scheduled,statistics,freeze,deliver
from app.lab_telegram.models import LabTelegramConfig
from app.real_match_lab_analysis.models import LAB_CHAT_ID


def riga(value):return datetime.fromisoformat(value).replace(tzinfo=RIGA)


@pytest.mark.parametrize('month',[1,7])
@pytest.mark.parametrize('minute,reason',[(8*60+59,'LAB_PUBLICATION_WINDOW_CLOSED'),(9*60,None),(0,'LAB_PUBLICATION_WINDOW_CLOSED'),(30,'LAB_PUBLICATION_WINDOW_CLOSED'),(3*60,'LAB_PUBLICATION_WINDOW_CLOSED'),(5*60,'LAB_PUBLICATION_WINDOW_CLOSED'),(22*60+59,None),(23*60,'LAB_PUBLICATION_WINDOW_CLOSED'),(23*60+1,'LAB_PUBLICATION_WINDOW_CLOSED')])
def test_publication_clock_dst_and_boundary(month,minute,reason):
    clock=datetime(2026,month,10,minute//60,minute%60,tzinfo=RIGA)
    assert publication_blocker(clock.astimezone(timezone.utc),[])==reason
    assert clock.utcoffset()==timedelta(hours=2 if month==1 else 3)


@pytest.mark.parametrize('kickoff,reason',[('22:59',None),('23:00','FIXTURE_AFTER_LAB_CUTOFF'),('23:30','FIXTURE_AFTER_LAB_CUTOFF')])
def test_fixture_clock(kickoff,reason):
    assert publication_blocker(riga('2026-07-10T21:00'),[riga('2026-07-10T'+kickoff)])==reason


def test_utc_date_boundary_remains_closed():
    clock=datetime(2026,7,10,21,5,tzinfo=timezone.utc)
    assert clock.astimezone(RIGA).day==11
    assert publication_blocker(clock,[]) == 'LAB_PUBLICATION_WINDOW_CLOSED'
    assert window_status(riga('2026-07-10T23:00'))['next_cutoff'].startswith('2026-07-11T23:00')
    with pytest.raises(ValueError):publication_blocker(datetime(2026,1,1),[])


class Ledger:
    def __init__(self):self.rows={}
    def get(self,kind,identity):return self.rows.get((kind,identity))
    def all(self,kind):return [v for (k,i),v in self.rows.items() if k==kind]
    def append(self,kind,identity,value):
        if (kind,identity) in self.rows:
            assert self.rows[kind,identity]==value
            return False
        self.rows[kind,identity]=deepcopy(value);return True
    def add(self,identity,*,combo=False,status='WON',published=None,settled=None,receipt=True,partial=False,stream=None):
        publication=published or riga('2026-09-15T12:00')
        value={'prediction_id':identity,'captured_odds':'2','combined_odds':'4','legs':[{'id':1},{'id':2},{'id':3}]}
        if stream:value['stream']=stream
        self.append('prediction' if combo else 'single_prediction',identity,value)
        if receipt:self.append('receipt',('combo_prediction:' if combo else 'single_prediction:')+identity,
                     {'status':'SENT','sent':True,'chat_id':LAB_CHAT_ID,'message_id':1,'sent_at_utc':publication.isoformat()})
        if status:self.append('settlement' if combo else 'single_settlement',identity,
              {'prediction_id':identity,'status':status,'unit_result':{'WON':'3' if combo else '1','LOST':'-1','VOID':'0','PARTIAL_VOID':'1'}[status],
               'partial_void':partial,'settled_at_utc':(settled or publication+timedelta(hours=3)).isoformat()})


def test_weekly_products_void_pending_and_no_leg_inflation():
    l=Ledger()
    for status in ('WON','LOST','VOID',None):l.add('s'+str(status),status=status)
    for status in ('WON','LOST','VOID','PARTIAL_VOID',None):l.add('c'+str(status),combo=True,status=status)
    l.add('unpublished',receipt=False);l.add('live',stream='LIVE');l.add('official',stream='OFFICIAL')
    s=statistics(l,week_start=riga('2026-09-14T00:00'),as_of=riga('2026-09-20T22:30'))
    assert s['SINGLE']=={'published':4,'settled':3,'WON':1,'LOST':1,'VOID':1,'PARTIAL_VOID':0,'pending':1,
        'hit_rate':'0.5','flat_unit_pnl':'0','flat_unit_roi':'0','average_odds':'2'}
    assert s['COMBO']['published']==5 and s['COMBO']['settled']==4 and s['COMBO']['pending']==1
    assert s['COMBO']['PARTIAL_VOID']==1 and s['COMBO']['flat_unit_pnl']=='3'
    assert s['COMBO']['flat_unit_roi']=='0.75'
    assert Decimal(s['COMBO']['hit_rate'])==Decimal(2)/3
    assert 'hit_rate' not in s


@pytest.mark.parametrize('day,hours',[('2026-03-29T22:30',167),('2026-10-25T22:30',169)])
def test_week_dst(day,hours):
    start,end=week_bounds(riga(day))
    assert start.weekday()==0 and start.hour==0 and end.weekday()==0
    assert (end.astimezone(timezone.utc)-start.astimezone(timezone.utc)).total_seconds()==hours*3600
    assert latest_due(riga(day))==riga(day)
    assert next_scheduled(riga(day)).hour==22 and next_scheduled(riga(day)).minute==30


def test_local_publication_week_late_settlement_frozen_report(repo):
    l=Ledger();due=riga('2026-09-20T22:30');published=riga('2026-09-14T00:01')
    assert published.astimezone(timezone.utc).date().isoformat()=='2026-09-13'
    l.add('late',published=published,status=None)
    report=freeze(repo,l,now=due)
    assert report['statistics']['SINGLE']['pending']==1
    l.append('single_settlement','late',{'status':'WON','unit_result':'1','settled_at_utc':riga('2026-09-21T01:00').isoformat()})
    assert freeze(repo,l,now=due+timedelta(days=1))==report
    history=statistics(l,week_start=riga('2026-09-14T00:00'),as_of=due+timedelta(days=2))
    assert history['SINGLE']['WON']==1 and history['SINGLE']['pending']==0
    assert statistics(l,week_start=riga('2026-09-21T00:00'),as_of=due+timedelta(days=2))['SINGLE']['published']==0


class Transport:
    def __init__(self,fail=False):self.calls=[];self.fail=fail
    async def send_message_receipt(self,**kwargs):
        self.calls.append(kwargs)
        if self.fail:raise TimeoutError('synthetic ambiguous delivery')
        return N(chat_id=LAB_CHAT_ID,message_id=101)


def config():return LabTelegramConfig('123456:synthetic',LAB_CHAT_ID,True,frozenset({'@goalvisionai'}))


def test_weekly_send_restart_idempotency_and_safe_failure(repo):
    from app.adaptive_lab.repository import AuditRepository
    due=riga('2026-09-20T22:30');l=Ledger();l.add('win');report=freeze(repo,l,now=due);transport=Transport()
    assert asyncio.run(deliver(repo,report,config(),transport,now=due))['sent']
    path=repo.connection.execute('PRAGMA database_list').fetchone()[2];reopened=AuditRepository(path)
    try:assert asyncio.run(deliver(reopened,report,config(),transport,now=due+timedelta(days=1)))['status']=='ALREADY_SENT'
    finally:reopened.close()
    assert len(transport.calls)==1 and transport.calls[0]['chat_id']==LAB_CHAT_ID
    assert 'SINGLE' in report['message'] and 'COMBO' in report['message'] and 'Pending:' in report['message']
    next_report=freeze(repo,l,now=due+timedelta(days=7));failure=Transport(True)
    for _ in range(2):assert asyncio.run(deliver(repo,next_report,config(),failure,now=due+timedelta(days=7)))['status']=='DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED'
    assert len(failure.calls)==1
    assert list(repo.connection.execute('PRAGMA foreign_key_check'))==[]


def test_weekly_invalid_config_can_retry_before_transport_claim(repo):
    due=riga('2026-09-20T22:30');report=freeze(repo,Ledger(),now=due);t=Transport()
    bad=LabTelegramConfig(None,LAB_CHAT_ID,True,frozenset())
    assert not asyncio.run(deliver(repo,report,bad,t,now=due))['sent']
    assert not repo.all('weekly_claims') and not t.calls
    assert asyncio.run(deliver(repo,report,config(),t,now=due))['sent']


@pytest.mark.parametrize('hour',[0,3,5,8,23])
def test_cutoff_blocks_send_not_settlement_and_never_counts_unpublished(hour):
    from app.lab_combo.service import LabComboService
    clock=riga('2026-09-20T23:00').replace(hour=hour);ledger=Ledger();transport=Transport()
    ledger.append('single_prediction','p',{'prediction_id':'p','kickoff_utc':(clock+timedelta(hours=1)).isoformat()})
    ledger.append('single_preview','p',{'message':'synthetic preview'})
    service=LabComboService(ledger,None,clock=lambda:clock)
    assert asyncio.run(service.publish_experimental('single_prediction','p',config(),transport))['status']=='LAB_PUBLICATION_WINDOW_CLOSED'
    assert not transport.calls
    assert statistics(ledger,week_start=week_bounds(clock)[0],as_of=clock)['SINGLE']['published']==0
    ledger.append('single_settlement','p',{'status':'WON'})
    ledger.append('single_settlement_preview','p',{'message':'synthetic settlement'})
    assert asyncio.run(service.publish_experimental('single_settlement','p',config(),transport))['status']=='PUBLISHED_PREDICTION_AND_SETTLEMENT_REQUIRED'
    ledger.append('receipt','single_prediction:p',{'status':'SENT','sent':True,'chat_id':LAB_CHAT_ID,'message_id':123})
    assert asyncio.run(service.publish_experimental('single_settlement','p',config(),transport))['sent']
    assert len(transport.calls)==1


def test_fixture_cutoff_final_send_and_learning_shadow_remain_unrestricted(repo):
    from app.lab_combo.service import LabComboService
    from app.adaptive_lab.observer import observe
    clock=riga('2026-09-20T22:59');l=Ledger();l.append('single_prediction','p',{'kickoff_utc':riga('2026-09-20T23:00').isoformat()})
    l.append('single_preview','p',{'message':'test'});t=Transport()
    assert asyncio.run(LabComboService(l,None,clock=lambda:clock).publish_experimental('single_prediction','p',config(),t))['status']=='FIXTURE_AFTER_LAB_CUTOFF'
    result=observe(repo,Ledger(),now=riga('2026-09-20T23:01'))
    assert result['heavy_training'] is False and result['api_calls']==0
    assert not repo.all('learning_observations') and not t.calls


def test_send_boundary_rechecked_after_durable_claim(monkeypatch):
    import app.lab_combo.service as module
    clock=[riga('2026-09-20T22:58')];l=Ledger();original=l.append
    def append(kind,identity,value):
        result=original(kind,identity,value)
        if kind=='claim':clock[0]=riga('2026-09-20T23:00')
        return result
    l.append=append
    l.claim_publication=lambda kind,value,claim:l.append('claim',kind+':'+value['prediction_id'],claim)
    l.append('single_prediction','p',{'prediction_id':'p','kickoff_utc':riga('2026-09-20T22:59').isoformat(),
       'stage':'READY_TO_PUBLISH','final_review_completed_at_utc':clock[0].isoformat()})
    l.append('single_preview','p',{'message':'synthetic'})
    monkeypatch.setattr(module,'_fresh_captured_odds',lambda *_:True)
    t=Transport();service=module.LabComboService(l,None,clock=lambda:clock[0])
    assert asyncio.run(service.publish_experimental('single_prediction','p',config(),t))['status']=='LAB_PUBLICATION_WINDOW_CLOSED'
    assert not t.calls and not l.all('receipt')
    assert l.get('publication_blocked','single_prediction:p')['status']=='LAB_PUBLICATION_WINDOW_CLOSED'


def test_combo_leg_cutoff_and_preparation_reason():
    from app.lab_combo.service import LabComboService
    from app.lab_v2_shadow.publication import prepare_v2_publications
    l=Ledger();clock=riga('2026-09-20T22:00');t=Transport()
    l.append('prediction','c',{'prediction_id':'c','legs':[{'kickoff_utc':riga('2026-09-20T22:59').isoformat()},
                                    {'kickoff_utc':riga('2026-09-20T23:00').isoformat()}]})
    l.append('preview','c',{'message':'synthetic'})
    assert asyncio.run(LabComboService(l,None,clock=lambda:clock).publish_experimental('combo_prediction','c',config(),t))['status']=='FIXTURE_AFTER_LAB_CUTOFF'
    candidate={'decision':'APPROVED','stage':'READY_TO_PUBLISH','captured_odds':'2','ensemble_probability':'.6',
               'fixture_id':1,'candidate_id':'x','kickoff_utc':riga('2026-09-20T23:00').isoformat()}
    prepared=prepare_v2_publications({'candidate_markets':[candidate]},l,now=clock)
    assert prepared['publication_blockers']=={'x':'FIXTURE_AFTER_LAB_CUTOFF'}
    assert not prepared['singles'] and not prepared['combos'] and not t.calls


@pytest.mark.parametrize('night',['2026-09-20T23:59','2026-09-21T00:00','2026-09-21T03:00','2026-09-21T08:59'])
def test_real_observer_ingestion_and_shadow_run_after_23(repo,night):
    from .conftest import frozen
    from .test_governance_rehearsal import baseline
    from app.adaptive_lab.governance import Governance
    from app.adaptive_lab.coordinator import opportunity
    from app.adaptive_lab.observer import observe
    l=Ledger();p,receipt,result=frozen()
    created=riga('2026-09-20T22:00');now=riga(night)
    p.update(prepared_at_utc=created.isoformat(),kickoff_utc=(created+timedelta(minutes=30)).isoformat(),
      provider_origin_timestamp_utc=(created-timedelta(seconds=5)).isoformat(),goalvision_retrieved_at_utc=created.isoformat())
    receipt['sent_at_utc']=(created+timedelta(seconds=1)).isoformat();result['settled_at_utc']=now.isoformat()
    l.append('single_prediction',p['prediction_id'],p);l.append('receipt','single_prediction:'+p['prediction_id'],receipt)
    l.append('single_settlement',p['prediction_id'],result)
    observe(repo,l,now=now)
    assert len(repo.all('learning_observations','PREMATCH'))==1
    gov=Governance(repo);gen=gov.bootstrap(baseline('PREMATCH'),now=now-timedelta(days=1))
    run={'shadow_id':'night','artifact_id':gen['artifact_id'],'champion_generation':gen['generation_id'],
         'created_at':(now-timedelta(hours=1)).isoformat(),'stream':'PREMATCH'}
    repo.append('shadow_runs','night','PREMATCH',run,run['created_at'],artifact_id=gen['artifact_id'])
    p.update(prepared_at_utc=now.isoformat(),kickoff_utc=(now+timedelta(hours=1)).isoformat())
    ids=gov.observe('PREMATCH',opportunity(p,'PREMATCH'),now=now)
    assert len(ids)==1 and len(repo.all('shadow_predictions','PREMATCH'))==1
    assert len(repo.all('learning_observations','PREMATCH'))==1


def test_weekly_claim_crash_and_immutable_guards(repo):
    import sqlite3
    due=riga('2026-09-20T22:30');report=freeze(repo,Ledger(),now=due);identity=report['report_id']
    repo.append('weekly_claims',identity,'PREMATCH',{'report_id':identity},due.isoformat(),report_id=identity)
    t=Transport()
    assert asyncio.run(deliver(repo,report,config(),t,now=due))['status']=='DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED'
    assert not t.calls
    for table in ('weekly_reports','weekly_claims'):
        for action in ('DELETE FROM '+table,'UPDATE '+table+' SET stream="LIVE"'):
            with pytest.raises(sqlite3.IntegrityError):repo.connection.execute(action)
    assert repo.connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


def test_weekly_two_workers_claim_only_once(repo):
    from app.adaptive_lab.repository import AuditRepository
    due=riga('2026-09-20T22:30');report=freeze(repo,Ledger(),now=due);transport=Transport()
    other=AuditRepository(repo.connection.execute('PRAGMA database_list').fetchone()[2])
    async def both():return await asyncio.gather(deliver(repo,report,config(),transport,now=due),deliver(other,report,config(),transport,now=due))
    try:
        results=asyncio.run(both());assert sum(r['sent'] for r in results)==1
        assert len(transport.calls)==1
    finally:other.close()


def test_schema3_upgrade_weekly_fk_guards_and_replay(tmp_path):
    from app.adaptive_lab.repository import AuditRepository
    import sqlite3
    path=tmp_path/'upgrade.db';r=AuditRepository(path)
    r.append('cycle_health','preserve','PREMATCH',{'value':1},riga('2026-09-14T00:00').isoformat())
    for table in ('weekly_receipts','weekly_delivery_unknown','weekly_claims','weekly_reports'):
        r.connection.execute('DROP TABLE '+table)
    r.connection.execute('DELETE FROM adaptive_schema WHERE version=4')
    r.connection.execute('INSERT OR IGNORE INTO adaptive_schema VALUES(3)');r.close()
    r=AuditRepository(path)
    try:
        r.migrate();assert r.get('cycle_health','preserve')=={'value':1}
        with pytest.raises(sqlite3.IntegrityError):
            r.append('weekly_receipts','orphan','PREMATCH',{},riga('2026-09-20T22:30').isoformat(),claim_id='missing')
        report=freeze(r,Ledger(),now=riga('2026-09-20T22:30'))
        assert freeze(r,Ledger(),now=riga('2026-09-21T08:00'))==report
        assert list(r.connection.execute('PRAGMA foreign_key_check'))==[]
        assert r.connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    finally:r.close()


def test_current_week_status_and_weekly_preview_are_inert(tmp_path,monkeypatch,repo):
    from app.adaptive_lab.health import status
    import app.adaptive_lab.health as health
    monkeypatch.setattr(health,'timer_state',lambda name:{'unit':name,'ActiveState':'inactive'})
    clock=riga('2026-09-20T23:01')
    result=status(repo,Ledger(),tmp_path/'absent.db',now=clock)
    assert result['PUBLICATION_WINDOW']['state']=='CLOSED'
    assert result['WEEKLY_REPORT']['next_scheduled'].startswith('2026-09-27T22:30')
    assert result['WEEKLY_REPORT']['statistics']['SINGLE']['WON']==0
    assert not repo.all('weekly_reports') and not repo.all('weekly_claims')


def test_losing_combo_with_void_leg_is_not_a_partial_win():
    l=Ledger();l.add('c',combo=True,status='LOST',partial=True)
    stats=statistics(l,week_start=riga('2026-09-14T00:00'),as_of=riga('2026-09-20T22:30'))['COMBO']
    assert stats['LOST']==1 and stats['WON']==stats['PARTIAL_VOID']==0
    assert stats['partial_void_count']==1 and stats['hit_rate']=='0' and stats['flat_unit_pnl']=='-1'


def test_current_cutoff_never_erases_historical_published_losses():
    ledger=Ledger();ledger.add('old-night',published=riga('2026-09-15T23:30'),status='LOST')
    ledger.add('prior-week',published=riga('2026-09-13T12:00'),status='LOST',settled=riga('2026-09-15T12:00'))
    ledger.add('wrong-chat');ledger.rows['receipt','single_prediction:wrong-chat']['chat_id']='@goalvisionai'
    stats=statistics(ledger,week_start=riga('2026-09-14T00:00'),as_of=riga('2026-09-20T22:30'))
    assert stats['SINGLE']['published']==stats['SINGLE']['LOST']==1
    assert stats['SINGLE']['flat_unit_pnl']=='-1'


@pytest.mark.parametrize('kickoff',['2026-07-11T00:30','2026-07-11T03:00','2026-07-11T08:59'])
def test_next_day_night_fixture_cannot_bypass_cutoff(kickoff):
    assert publication_blocker(riga('2026-07-10T22:00'),[riga(kickoff)])=='FIXTURE_AFTER_LAB_CUTOFF'


@pytest.mark.parametrize('day',['2026-03-28','2026-10-24'])
def test_next_window_across_dst(day):
    clock=riga(day+'T23:30');status=window_status(clock)
    opening=datetime.fromisoformat(status['next_open'])
    assert opening.astimezone(RIGA).hour==9
    assert opening.date()==(clock+timedelta(days=1)).date()
    assert status['window']=='09:00–23:00 Europe/Riga'
    assert status['state']=='CLOSED'
    assert datetime.fromisoformat(status['next_close']).astimezone(RIGA).hour==23
    assert publication_blocker(opening,[]) is None


@pytest.mark.parametrize('time,state,next_open,next_close',[
    ('08:59','CLOSED',18,18),('09:00','OPEN',19,18),
    ('22:59:59','OPEN',19,18),('23:00','CLOSED',19,19),('00:00','CLOSED',18,18)])
def test_status_window_boundaries(time,state,next_open,next_close):
    status=window_status(riga('2026-09-18T'+time))
    assert status['state']==state
    assert datetime.fromisoformat(status['next_open']).day==next_open
    assert datetime.fromisoformat(status['next_close']).day==next_close


def test_sunday_report_time_inside_publication_window():
    assert publication_blocker(riga('2026-09-20T22:30'),[]) is None
