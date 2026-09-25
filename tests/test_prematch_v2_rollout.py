"""Disposable systemd configuration rehearsal with every administrative call faked."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

SOURCE=Path(__file__).resolve().parents[1]/'docs/operations/install_prematch_v2.py'


@pytest.fixture
def rollout(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('reviewed_installer',SOURCE)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    real_path=Path;etc=tmp_path/'systemd';etc.mkdir()
    monkeypatch.setattr(module,'Path',lambda value:etc if str(value)=='/etc/systemd/system' else real_path(value))
    monkeypatch.setattr(module.os,'geteuid',lambda:0)
    services=['goalvision-lab-v2-discover.service','goalvision-lab-combo-settle.service']
    value={'release':str(tmp_path/'release'),'commit':'synthetic-commit','regression_status':'PASSED',
        'installed_fingerprints':{},'services':services,'discovery_service':services[0],
        'release_environment_file':str(tmp_path/'release.env'),'ledger':str(tmp_path/'ledger.sqlite'),
        'discovery_command':['/unchanged/python','-P','-m','app.lab_v2_shadow','controlled-cycle','--send','--max-calls','400','--settlement-reserve','100'],
        'observation_arguments':['--football-context-root',str(tmp_path/'evidence')]}
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps(value));calls=[]
    def run(*args):
        calls.append(args)
        if args[0]=='git':return 'synthetic-commit' if args[-1]=='HEAD' else ''
        if args[:2]==('systemctl','show'):return 'active' if args[2].endswith('.timer') else 'inactive'
        return ''
    monkeypatch.setattr(module,'run',run)
    monkeypatch.setattr(sys,'argv',['installer',str(manifest),'apply'])
    return module,manifest,services,etc,calls,run


def test_install_waits_at_boundary_and_only_restarts_existing_timers(rollout):
    module,manifest,services,etc,calls,run=rollout
    module.main()
    text=(etc/(services[0]+'.d')/module.DROPIN).read_text()
    assert '--max-calls 400 --settlement-reserve 100' in text
    assert '--football-context-root' in text and '--label-v2-selections' in text
    assert all(arg.endswith('.timer') for call in calls if call[:2]==('systemctl','start') for arg in call[2:])
    assert not any(call[:2]==('systemctl','restart') for call in calls)
    assert ('systemctl','daemon-reload') in calls


def test_verification_failure_restores_config_and_timers(rollout,monkeypatch):
    module,manifest,services,etc,calls,run=rollout
    def fail(*args):
        if args[0]=='systemd-analyze':raise RuntimeError('synthetic verify rejection')
        return run(*args)
    monkeypatch.setattr(module,'run',fail)
    with pytest.raises(RuntimeError):module.main()
    assert not any((etc/(s+'.d')/module.DROPIN).exists() for s in services)
    assert any(call[:2]==('systemctl','start') for call in calls)


def test_no_privilege_means_no_service_change(rollout,monkeypatch):
    module,manifest,services,etc,calls,run=rollout
    monkeypatch.setattr(module.os,'geteuid',lambda:1001)
    with pytest.raises(SystemExit,match='Root is required'):module.main()
    assert calls==[]


def test_full_rollback_blocked_after_confirmed_labelled_publication(rollout,monkeypatch):
    module,manifest,services,etc,calls,run=rollout
    monkeypatch.setattr(sys,'argv',['installer',str(manifest),'rollback'])
    monkeypatch.setattr(module,'labelled_receipts',lambda p:1)
    with pytest.raises(SystemExit,match='Keep compatible settlement'):module.main()
    assert not any(call[0]=='systemctl' for call in calls)


@pytest.mark.parametrize('action',['disable-data-labels','disable-new-picks'])
def test_independent_disablement_keeps_settlement_configuration(rollout,monkeypatch,action):
    module,manifest,services,etc,calls,run=rollout
    module.main();settler=etc/(services[1]+'.d')/module.DROPIN;before=settler.read_bytes();calls.clear()
    monkeypatch.setattr(sys,'argv',['installer',str(manifest),action]);module.main()
    text=(etc/(services[0]+'.d')/module.DROPIN).read_text()
    assert settler.read_bytes()==before
    assert '--label-v2-selections' not in text
    assert ('--send' in text)==(action=='disable-data-labels')
    assert ('--football-context-root' in text)==(action=='disable-new-picks')
    assert not any(services[1] in call for call in calls)
