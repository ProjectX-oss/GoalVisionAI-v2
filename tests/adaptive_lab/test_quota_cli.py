from __future__ import annotations
from datetime import timedelta
import pytest
from app.adaptive_lab.quota import SharedQuota,RESERVES,LIVE_DAILY_CAP
from app.adaptive_lab.repository import AuditRepository
from app.adaptive_lab.cli import main,COMMANDS
from app.football.quota import FootballQuotaError
from .conftest import START


def quota(daily=7500,minute=300):
    return {'interpretation_status':'NORMALIZED','daily_remaining':daily,'minute_remaining':minute}


@pytest.mark.parametrize('category',list(RESERVES)+['PREMATCH_DISCOVERY'])
def test_protected_reserves(repo,category):
    shared=SharedQuota(repo)
    reserve = 100 if category in {'PREMATCH_DISCOVERY', 'PREMATCH_REVIEW', 'STATUS'} else 0 if category == 'SETTLEMENT' else sum(v for k,v in RESERVES.items() if k!=category)
    with pytest.raises(FootballQuotaError): shared.claim(category,now=START,provider=quota(daily=reserve))
    assert shared.claim(category,now=START,provider=quota(daily=reserve+1))['protected_reserve']==reserve


def test_durable_minute_daily_and_restart_accounting(tmp_path):
    path=tmp_path/'quota.db';repo=AuditRepository(path)
    shared=SharedQuota(repo,minute_limit=2)
    shared.claim('LIVE_STATE',now=START,provider=quota())
    repo.close();repo=AuditRepository(path);shared=SharedQuota(repo,minute_limit=2)
    shared.claim('LIVE_STATE',now=START,provider=quota())
    with pytest.raises(FootballQuotaError): shared.claim('LIVE_STATE',now=START,provider=quota())
    shared.claim('SETTLEMENT',now=START+timedelta(seconds=61),provider=quota())
    with pytest.raises(FootballQuotaError): shared.claim('LIVE_ODDS',now=START,provider=quota(minute=0))
    with pytest.raises(FootballQuotaError): shared.claim('LIVE_ODDS',now=START,provider={})
    repo.close()


@pytest.mark.parametrize('command',COMMANDS)
def test_readonly_cli_inert_json(repo,tmp_path,command,capsys):
    path=tmp_path/'audit.db'
    before=path.read_bytes()
    assert main(['live',command,'--database',str(path),'--json','--at',START.isoformat()])==0
    assert path.read_bytes()==before
    import json
    assert isinstance(json.loads(capsys.readouterr().out),dict)
