"""Operator integration rehearsal, exclusively temporary files/fake systemd."""
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def updater():
    spec=importlib.util.spec_from_file_location('live_evening_update',ROOT/'operations/live-evening/update.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_environment_retains_existing_lanes_and_only_adds_reviewed_flags(updater):
    before=updater.base_environment(updater.BASE).decode().splitlines()
    after=updater.environment(updater.BASE).decode().splitlines()
    assert after[:len(before)]==before
    assert after[len(before):]==['GOALVISION_LAB_EVENING_MODE=1','GOALVISION_LIVE_API_FEED_QUOTES=1']
    for flag in ('GOALVISION_COMBO_MARKET_PARALLEL=0','GOALVISION_COMBO_DOUBLE_170=1',
                 'GOALVISION_PRIVATE_SINGLE_170=1','GOALVISION_LAB_SINGLE_MIN_ODDS_150=1',
                 'GOALVISION_LAB_COMBO_LEG_MIN_ODDS_130=1','GOALVISION_LAB_EARLY_COMBO_LOSS=1',
                 'GOALVISION_LAB_SETTLEMENT_REPLIES=1'):
        assert flag in after


def test_apply_requires_concrete_quote_contract_acceptance_before_any_write(updater,monkeypatch):
    monkeypatch.setattr(sys,'argv',['update.py','--apply'])
    monkeypatch.setattr(updater,'validate',lambda *a:pytest.fail('must not prepare mutation'))
    with pytest.raises(SystemExit,match='EXPLICIT_API_FEED_QUOTE_ACCEPTANCE_REQUIRED'):
        updater.main()
    monkeypatch.setattr(sys,'argv',['update.py','--apply','--accept-api-feed-quotes'])
    monkeypatch.setattr(updater.os,'geteuid',lambda:1001)
    with pytest.raises(SystemExit,match='ROOT_REQUIRED'):
        updater.main()


def fake_system(updater,monkeypatch,tmp_path,*,fail=None):
    target=tmp_path/'release'
    monkeypatch.setattr(updater,'OVERRIDES',{u:tmp_path/(u+'.d')/'route.conf' for u in updater.SERVICES})
    monkeypatch.setattr(updater,'DISCOVERY_OVERRIDE',tmp_path/'discover.timer.d'/'clock.conf')
    monkeypatch.setattr(updater,'LIVE_UNIT_PATH',tmp_path/updater.LIVE_SERVICE)
    monkeypatch.setattr(updater,'LIVE_TIMER_PATH',tmp_path/updater.LIVE_TIMER)
    states={u:'active' for u in updater.TIMERS}
    states[updater.LIVE_TIMER]='inactive'
    enabled={'value':False}
    commands=[]
    def routes(units):
        return {u:('NEW' if u in updater.OVERRIDES and updater.OVERRIDES[u].exists() else 'BASE') for u in units}
    def props(unit,key):
        if key=='ActiveState':return states.get(unit,'inactive')
        if key=='UnitFileState':return 'enabled' if enabled['value'] else 'disabled'
        if key=='EnvironmentFiles':return str(target/'release.env')+' (ignore_errors=no)'
        if key=='User':return 'arvis'
        if key=='TimersCalendar':
            expr='10..17:00,30:00 Europe/Riga' if unit==updater.DISCOVERY_TIMER else '02/5:00 Europe/Riga'
            return '{ OnCalendar=*-*-* '+expr+' ; next_elapse=synthetic }'
        raise AssertionError((unit,key))
    def control(*args):
        commands.append(args)
        if fail and fail(args):raise RuntimeError('INJECTED_INSTALL_FAILURE')
        if args[0]=='stop':states[args[1]]='inactive'
        if args[0]=='start':states[args[1]]='active'
        if args[:2]==('enable','--now'):states[args[2]]='active';enabled['value']=True
        if args[:2]==('disable','--now'):states[args[2]]='inactive';enabled['value']=False
        return ''
    monkeypatch.setattr(updater,'routes',routes)
    monkeypatch.setattr(updater,'stable_commands',lambda units:{u:'FROZEN_COMMAND' for u in units})
    monkeypatch.setattr(updater,'property_of',props)
    monkeypatch.setattr(updater,'control',control)
    monkeypatch.setattr(updater,'verify_routes',lambda *a,**k:None)
    monkeypatch.setattr(updater,'disabled_worker',lambda:None)
    return target,states,commands


def test_install_routes_all_consumers_and_only_starts_natural_timers(updater,monkeypatch,tmp_path):
    target,states,commands=fake_system(updater,monkeypatch,tmp_path)
    updater.route(target)
    assert all(path.read_bytes()==data for path,data in updater.configuration(target).items())
    assert all(states[t]=='active' for t in updater.TIMERS)
    assert states[updater.LIVE_TIMER]=='active'
    assert ('enable','--now',updater.LIVE_TIMER) in commands
    assert not any(c[0] in ('start','restart') and c[-1].endswith('.service') for c in commands)
    text=updater.live_service(target).decode()
    assert 'Nice=10' in text and 'CPUQuota=25%' in text
    assert '--send' in text and 'learning-cycle' not in text
    assert 'Persistent=false' in updater.live_timer().decode()


def test_mid_install_failure_restores_existing_routes_and_timer_states(updater,monkeypatch,tmp_path):
    calls={'n':0}
    def fail(args):
        if args==('daemon-reload',):
            calls['n']+=1
            return calls['n']==1
        return False
    target,states,commands=fake_system(updater,monkeypatch,tmp_path,fail=fail)
    with pytest.raises(RuntimeError,match='INJECTED_INSTALL_FAILURE'):
        updater.route(target)
    assert not any(path.exists() for path in updater.configuration(target))
    assert all(states[t]=='active' for t in updater.TIMERS)
    assert states[updater.LIVE_TIMER]=='inactive'


def test_unreviewed_existing_configuration_is_rejected(updater,monkeypatch,tmp_path):
    target,_,_=fake_system(updater,monkeypatch,tmp_path)
    updater.LIVE_UNIT_PATH.write_text('foreign unit')
    with pytest.raises(ValueError,match='PARTIAL_OR_UNREVIEWED_OVERRIDE'):
        updater.current_mode(target)
