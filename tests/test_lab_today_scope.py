"""Riga same-day discovery, restored fixtures and final delivery; offline only."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo

import pytest

from app.lab_combo.publication_window import publication_blocker
from app.lab_combo.service import LabComboService
from app.lab_v2_shadow import cli
from app.lab_v2_shadow.operator_output import operator_cycle_summary
from app.lab_v2_shadow.publication import prepare_v2_publications
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from app.lab_v2_shadow.runner import LabV2ShadowRunner, _fixture_rows_with_evidence, _plain
from app.lab_v2_shadow.capability import LeagueCapabilityCache
from tests.test_lab_accuracy_combo import candidates
from tests.test_lab_v2_shadow import NOW, FakeClient, bind_candidate_evidence
from tests.test_lab_v2_global import fixture
from tests.test_prematch_v2_enablement import ledger, config, Transport

RIGA = ZoneInfo('Europe/Riga')


@pytest.mark.parametrize('day',['2026-01-15','2026-03-29','2026-10-01','2026-10-25'])
@pytest.mark.parametrize('offset',[-1,0,1,2])
def test_calendar_day_gate_dst_and_host_timezone(day, offset):
    now = datetime.fromisoformat(day+'T15:00').replace(tzinfo=RIGA)
    kickoff = (now+timedelta(days=offset)).replace(hour=21, minute=45)
    expected = None if offset == 0 else 'FIXTURE_NOT_TODAY_RIGA'
    for zone in (timezone.utc, ZoneInfo('Europe/Berlin'), ZoneInfo('America/New_York')):
        assert publication_blocker(now.astimezone(zone), [kickoff.astimezone(zone)]) == expected


@pytest.mark.parametrize('delta',[timedelta(days=1),timedelta(days=2)])
def test_future_high_probability_cannot_displace_today_or_enter_combo(ledger, delta):
    rows = candidates(6)
    for row in rows[3:]:
        row['kickoff_utc'] = (datetime.fromisoformat(row['kickoff_utc'])+delta).isoformat()
        row['ensemble_probability'] = '0.90'
        row['signals'][0]['probability'] = '0.90'
        bind_candidate_evidence(row)
    before = deepcopy(rows)
    result = prepare_v2_publications({'candidate_markets':rows}, ledger, now=NOW,
                                     label_origin=True, accuracy_combos=True)
    assert rows == before
    assert len(result['singles']) == 3 and len(result['combos']) == 1
    assert {v['fixture_id'] for v in result['singles']} == {r['fixture_id'] for r in rows[:3]}
    assert all(v['fixture_id'] in {r['fixture_id'] for r in rows[:3]}
               for combo in result['combos'] for v in combo['legs'])
    for row in rows[3:]:
        assert result['single_publication_blockers'][row['candidate_id']] == 'FIXTURE_NOT_TODAY_RIGA'


def test_insufficient_today_candidates_never_borrow_future_combo_leg(ledger):
    rows = candidates()
    rows[-1]['kickoff_utc'] = (NOW+timedelta(days=1,hours=1)).isoformat()
    result = prepare_v2_publications({'candidate_markets':rows}, ledger, now=NOW,
                                     label_origin=True, accuracy_combos=True)
    assert len(result['singles']) == 2 and not result['combos']
    assert not ledger.all('prediction')


@pytest.mark.parametrize('kind',['single_prediction','combo_prediction'])
def test_retained_future_preview_cannot_be_sent(ledger, monkeypatch, kind):
    # Simulate an old immutable preview made before deployment.
    monkeypatch.setattr('app.lab_v2_shadow.publication.publication_blocker', lambda *a:None)
    rows = candidates()
    for row in rows:
        row['kickoff_utc'] = (NOW+timedelta(days=1,hours=1)).isoformat()
    prepared = prepare_v2_publications({'candidate_markets':rows}, ledger, now=NOW,
                                       label_origin=True, accuracy_combos=True)
    value = prepared['singles' if kind == 'single_prediction' else 'combos'][0]
    transport = Transport()
    result = asyncio.run(LabComboService(ledger,None,clock=lambda:NOW)
                         .publish_experimental(kind,value['prediction_id'],config(),transport))
    assert not result['sent'] and not transport.calls and not ledger.all('claim')


def test_calendar_date_checked_again_after_claim(ledger, monkeypatch):
    value = prepare_v2_publications({'candidate_markets':candidates(1)},ledger,now=NOW,
                                   label_origin=True)['singles'][0]
    clock = [NOW]
    claim = ledger.claim_publication
    def cross_date(*args):
        result = claim(*args)
        clock[0] += timedelta(days=1)
        return result
    monkeypatch.setattr(ledger,'claim_publication',cross_date)
    transport = Transport()
    result = asyncio.run(LabComboService(ledger,None,clock=lambda:clock[0])
                         .publish_experimental('single_prediction',value['prediction_id'],config(),transport))
    assert result['status'] == 'FIXTURE_NOT_TODAY_RIGA'
    assert not transport.calls and not ledger.all('receipt')
    assert ledger.get('publication_blocked','single_prediction:'+value['prediction_id'])


class ScopeClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.requests = []
    def _hit(self, endpoint, query, payload):
        self.requests.append((endpoint,query))
        return super()._hit(endpoint,query,payload)
    async def fixtures_by_date(self, day, *, timezone_name='UTC'):
        today = fixture(identity=7)
        future = fixture(identity=8)
        future['fixture']['date'] = (NOW+timedelta(days=1,hours=4)).isoformat()
        return self._hit('/fixtures',{'date':day,'timezone':timezone_name},{'response':[today,future]})


def test_today_scope_filters_provider_and_restored_global_fixtures(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repo = ShadowEvidenceRepository(tmp_path/'shadow.db')
    cached = fixture(identity=9)
    cached['fixture']['date'] = (NOW+timedelta(days=2,hours=4)).isoformat()
    caps = LeagueCapabilityCache.from_api_payload({'response':[]},retrieved_at=NOW)
    accepted,_ = _fixture_rows_with_evidence({'response':[cached]},caps,NOW)
    stored = {**_plain(accepted[0]),'state':'DISCOVERED'}
    repo.append('global_discovery','cached-future',stored,created_at=NOW-timedelta(minutes=30))
    repo.close()
    # Reopen to exercise the persistent restoration path.
    repo = ShadowEvidenceRepository(tmp_path/'shadow.db')
    client = ScopeClient()
    runner = LabV2ShadowRunner(client,repo,capability_cache_path=tmp_path/'var/caps.json',maximum_calls=30)
    report = asyncio.run(runner.run(now=NOW,horizon_days=3,today_only=True))
    assert report['discovery_dates_requested'] == [NOW.astimezone(RIGA).date().isoformat()]
    assert report['fixtures_discovered'] == 1
    assert report['discovery_day_scope']['excluded_fixture_count'] == 2
    assert report['discovery_day_scope']['mode'] == 'TODAY_RIGA'
    requests = [q for e,q in client.requests if e == '/fixtures' and 'date' in q]
    assert requests == [{'date':'2026-09-15','timezone':'Europe/Riga'}]
    assert not any(q.get('fixture') in {8,9} or q.get('id') in {8,9} for _,q in client.requests)
    assert {c['fixture_id'] for c in report['candidate_markets']} <= {7}
    assert repo.get('global_discovery','cached-future') == stored
    compact = operator_cycle_summary(report)
    assert compact['discovery_day_scope']['excluded_fixture_count'] == 2
    repo.close()


@pytest.mark.parametrize('environment',[False,True])
def test_cli_today_option_is_passed_without_provider_call(monkeypatch, capsys, environment):
    received = []
    if environment:
        monkeypatch.setenv('GOALVISION_LAB_TODAY_ONLY','1')
    else:
        monkeypatch.delenv('GOALVISION_LAB_TODAY_ONLY',raising=False)
    async def cycle(args):
        received.append(args.today_only)
        return {}
    monkeypatch.setattr(cli,'configured_cycle',cycle)
    assert cli.main(['rehearse']+([] if environment else ['--today-only'])) == 0
    assert received == [True]


def test_settlement_for_prior_date_remains_publishable():
    from tests.adaptive_lab.test_lab_product_schedule import Ledger, Transport, config
    store = Ledger()
    store.add('old-single', status='WON')
    store.append('single_settlement_preview','old-single',{'message':'synthetic settlement'})
    transport = Transport()
    later = datetime(2026,9,19,1,tzinfo=RIGA)
    result = asyncio.run(LabComboService(store,None,clock=lambda:later)
                         .publish_experimental('single_settlement','old-single',config(),transport))
    assert result['sent'] and len(transport.calls) == 1


def test_active_cli_today_flag_reaches_runner(tmp_path, monkeypatch, capsys):
    from tests.test_lab_v2_shadow import (
        _install_controlled_cycle_fakes, _controlled_cycle_arguments, _DeterministicReadyRunner)
    monkeypatch.chdir(tmp_path)
    _install_controlled_cycle_fakes(monkeypatch)
    monkeypatch.setenv('GOALVISION_LAB_TODAY_ONLY','1')
    original = _DeterministicReadyRunner.run
    observed = []
    async def run(self, **kwargs):
        observed.append(kwargs.pop('today_only'))
        return await original(self, **kwargs)
    monkeypatch.setattr(_DeterministicReadyRunner,'run',run)
    assert cli.main(_controlled_cycle_arguments(send=False)) == 0
    assert observed == [True]
    assert json.loads(capsys.readouterr().out)['telegram_sends'] == 0
