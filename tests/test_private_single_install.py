"""Private-only operator release, enrollment binding and failure recovery; offline."""
from types import SimpleNamespace
import importlib.util
import json
from pathlib import Path
import time

import pytest
from tests import test_prematch_settlement_upgrade as prior
from app.lab_private_single import routing
from app.lab_telegram.models import LabTelegramConfig
from app.real_match_lab_analysis.models import LAB_CHAT_ID


@pytest.fixture
def rig(tmp_path,monkeypatch):
    v=prior.rig.__wrapped__(tmp_path,monkeypatch,SimpleNamespace(param='private-single-170'))
    v.meta['runtime_import_smoke']={'status':'ISOLATED_COMBO_IMPORT_PASS'}
    (v.package/'configure.py').write_text('REVIEWED=True\n')
    v.meta['configure_sha256']=v.mod.sha(v.package/'configure.py')
    (v.package/'metadata.json').write_text(json.dumps(v.meta))
    return v


def test_apply_replay_pause_keeps_current_readers_and_all_public_flags(rig):
    prior.test_apply_replay_rollback_preserves_mixed_timer_states(rig)
    m=rig.mod
    assert m.environment(m.BASE,True)==m.environment(m.BASE).replace(
        b'GOALVISION_PRIVATE_SINGLE_170=1',b'GOALVISION_PRIVATE_SINGLE_170=0')
    assert 'app/lab_private_single/runtime.py' in m.FILES
    assert 'app/adaptive_lab/quota.py' not in m.FILES
    for flag in ('GOALVISION_COMBO_MARKET_PARALLEL','GOALVISION_COMBO_CONSERVATIVE_AGREEMENT',
                 'GOALVISION_LAB_SINGLE_MIN_ODDS_150','GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130',
                 'GOALVISION_LAB_TODAY_ONLY','GOALVISION_LAB_EARLY_COMBO_LOSS','GOALVISION_LAB_SETTLEMENT_REPLIES'):
        assert (flag+'=1\n').encode() in m.environment(m.BASE,True)


@pytest.mark.parametrize('failure_kind',['reload','timer','second_dropin'])
def test_failed_apply_restores_timers_and_routes(rig,monkeypatch,failure_kind):
    prior.test_partial_change_failure_restores_all_routes_and_timers(rig,monkeypatch,failure_kind)


def test_busy_workers_never_killed(rig,monkeypatch):
    prior.test_busy_service_is_not_killed_and_all_timers_restored(rig,monkeypatch)


@pytest.mark.parametrize('tamper',['overlay','updater','base','environment','unexpected_file'])
def test_tamper_rejected(rig,tamper):prior.test_tamper_refused_before_timer_controls(rig,tamper)


def test_configure_tamper_rejected_before_controls(rig):
    (rig.package/'configure.py').write_text('CHANGED=True\n')
    with pytest.raises(ValueError,match='CONFIGURE_HASH'):rig.mod.apply(rig.package)
    assert not rig.calls


def test_missing_private_enrollment_blocks_apply_before_controls(rig,monkeypatch):
    def missing(package):raise ValueError('PRIVATE_LAB_START_ENROLLMENT_REQUIRED')
    monkeypatch.setattr(rig.mod,'check_configuration',missing)
    with pytest.raises(ValueError,match='START_ENROLLMENT'):rig.mod.apply(rig.package)
    assert not rig.calls


def test_admin_and_protected_routes(rig,monkeypatch):
    prior.test_admin_codex_must_remain_disabled(rig,monkeypatch)


def configure_module():
    p=Path(__file__).parents[1]/'operations/private-single-170/configure.py'
    spec=importlib.util.spec_from_file_location('private_enrollment_test',p)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


@pytest.mark.parametrize('case',['valid','other_user','group','forward','old','duplicate'])
def test_enrollment_requires_fresh_start_and_same_confirmed_owner(tmp_path,monkeypatch,case):
    import app.lab_combo.bot_routing as combo
    import app.lab_telegram.service as lab
    m=configure_module()
    target=tmp_path/'private/lab-single.json'
    token='111111111:'+'synthetic_token_'*3
    monkeypatch.setattr(lab,'load_lab_telegram_config',lambda *args:LabTelegramConfig(token,LAB_CHAT_ID,True))
    anchor=SimpleNamespace(chat_id='55555555',route={'chat_id':'55555555','verified':True})
    monkeypatch.setattr(combo,'load_config',lambda:anchor)
    mod=SimpleNamespace(CONFIG_PATH=target,VERSION=routing.VERSION,PERIOD=routing.PERIOD,
        validate_route=routing.validate_route,load_config=lambda:None)
    monkeypatch.setattr(m,'contract',lambda package:mod)
    monkeypatch.setattr(m.secrets,'token_hex',lambda n:'a'*32)
    now=int(time.time())
    message={'text':'/start gvprivate_'+'a'*32,'date':now,
             'chat':{'id':55555555,'type':'private'},'from':{'id':55555555,'is_bot':False}}
    if case=='other_user':message['chat']['id']=message['from']['id']=999
    if case=='group':message['chat']['type']='group'
    if case=='forward':message['forward_origin']={}
    if case=='old':message['date']=now-3600
    reads=[]
    def reader(token,method,parameters=None):
        reads.append(method)
        if method=='getMe':return {'id':111111111,'is_bot':True,'username':'GoalVision_AI_Lab_Bot'}
        result=[{'update_id':1,'message':message}]
        if case=='duplicate':
            result.append({'update_id':2,'message':{**message,'chat':{'id':999,'type':'private'},'from':{'id':999,'is_bot':False}}})
        return result
    if case=='valid':
        m.configure(tmp_path,reader=reader,ask=lambda prompt:'')
        doc=json.loads(target.read_text())
        assert doc['route']['chat_id']==anchor.chat_id and 'token' not in doc
        assert target.stat().st_mode & 0o777==0o600
    else:
        with pytest.raises(ValueError):m.configure(tmp_path,reader=reader,ask=lambda prompt:'')
        assert not target.exists()
    assert reads==['getMe','getUpdates']


@pytest.mark.parametrize('bad',['valid','permissions','symlink','group','wrong_bot','token','anchor'])
def test_runtime_config_secure_and_pinned_to_existing_lab_token(tmp_path,monkeypatch,bad):
    stamp='2026-10-04T13:00:00+00:00'
    route={'version':routing.VERSION,'product':'PRIVATE_SINGLE','bot_username':'@GoalVision_AI_Lab_Bot',
        'bot_id':'111111111','chat_id':'55555555','chat_type':'private',
        'statistics_period':routing.PERIOD,'period_started_at':stamp}
    doc={'route':route,'verified_at':stamp,'start_update_id':1,'recipient_anchor_fingerprint':'a'*64}
    if bad=='group':route['chat_type']='group'
    if bad=='wrong_bot':route['bot_username']='@GoalVision_AI_Combo_Bot'
    if bad=='anchor':doc['recipient_anchor_fingerprint']='missing'
    path=tmp_path/'route.json';path.write_text(json.dumps(doc));path.chmod(0o644 if bad=='permissions' else 0o600)
    if bad=='symlink':
        link=tmp_path/'link.json';link.symlink_to(path);path=link
    token=('999999999' if bad=='token' else '111111111')+':'+'synthetic_token_'*3
    monkeypatch.setattr(routing,'load_lab_telegram_config',lambda *args:LabTelegramConfig(token,LAB_CHAT_ID,True))
    if bad=='valid':
        config=routing.load_config(path)
        assert config.route==route and token not in repr(config)
    else:
        with pytest.raises(routing.RoutingBlocked,match='PRIVATE_LAB_RECIPIENT_NOT_CONFIGURED'):
            routing.load_config(path)
