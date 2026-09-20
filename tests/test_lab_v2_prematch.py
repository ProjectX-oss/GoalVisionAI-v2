"""Offline deterministic PREMATCH throughput, light-safety and boundary replay."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse
import asyncio
import json

import pytest

from app.lab_v2_shadow import cli
from app.lab_v2_shadow.capability import LeagueCapabilityCache
from app.lab_v2_shadow.ensemble import EnsembleSignal, evaluate_ensemble
from app.lab_v2_shadow.forward_evidence import capture_selection
from app.lab_v2_shadow.global_evaluation import evaluate_profile
from app.lab_v2_shadow.profiles import policy_for, is_priority
from app.lab_v2_shadow.publication import prepare_v2_publications
from app.lab_v2_shadow.quota import adaptive_quota_budget, discovery_cycles_remaining, PRIORITY_EXACT_RETRIES_PER_CYCLE
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from app.lab_v2_shadow.runner import LabV2ShadowRunner, _fixture_rows_with_evidence, _readiness
from app.lab_v2_shadow.summary import latest_cycle_summary
from app.lab_v2_shadow.diagnostics import human_diagnostic
from app.lab_combo.repository import ComboRepository
from test_lab_v2_shadow import NOW, FakeClient, Response, odds_payload, coverage, _controlled_ready_candidate
from test_lab_v2_global import fixture, signals

RIGA = ZoneInfo('Europe/Riga')


@pytest.mark.parametrize('month', [1, 9])
@pytest.mark.parametrize('hour,minute,allowed', [(8,59,False),(9,0,True),(22,30,True),(23,0,False)])
def test_discovery_window_calls(tmp_path, monkeypatch, month, hour, minute, allowed):
    monkeypatch.chdir(tmp_path)
    clock = datetime(2026, month, 15, hour, minute, tzinfo=RIGA)
    repo = ShadowEvidenceRepository(tmp_path/'shadow.db')
    client = FakeClient()
    runner = LabV2ShadowRunner(client, repo, capability_cache_path=tmp_path/'var/caps.json', maximum_calls=1)
    report = asyncio.run(runner.run(now=clock, horizon_days=1))
    assert client.request_count == int(allowed)
    assert report['discovery_state'] == ('DAYTIME_DISCOVERY' if allowed else 'NIGHT_DISCOVERY_PAUSED')
    if not allowed:
        summary = latest_cycle_summary(tmp_path/'shadow.db', now=clock)
        assert summary['status'] == 'NIGHT_DISCOVERY_PAUSED'
        assert 'NIGHT_DISCOVERY_PAUSED' in human_diagnostic(summary)
        assert summary['throughput_warnings'] == []
    repo.close()


def test_manual_night_cli_does_not_construct_provider(tmp_path, monkeypatch):
    class Clock:
        @staticmethod
        def now(tz):
            return datetime(2026,9,15,3,tzinfo=RIGA).astimezone(tz)
    def forbidden(*a, **kw):
        pytest.fail('Night discovery constructed a provider')
    monkeypatch.setattr(cli, 'datetime', Clock)
    monkeypatch.setattr(cli, 'FootballClient', forbidden)
    monkeypatch.setattr(cli, 'LabTelegramTransport', forbidden)
    args = argparse.Namespace(shadow_database=tmp_path/'s.db', send=True)
    result = asyncio.run(cli._cycle(args))
    assert result['status'] == 'NIGHT_DISCOVERY_PAUSED'
    assert result['api_calls_consumed'] == result['telegram_sends'] == 0


def test_timer_only_riga_daytime():
    root = Path(__file__).parents[1]/'app/lab_v2_shadow/systemd'
    timer = (root/'goalvision-lab-v2-discover.timer').read_text()
    assert [line for line in timer.splitlines() if line.startswith('On')] == [
        'OnCalendar=*-*-* 09..22:00,30:00 Europe/Riga']
    assert 'Persistent=false' in timer
    service = (root/'goalvision-lab-v2-discover.service').read_text()
    assert '--max-calls 400 --settlement-reserve 100' in service
    assert '1500' not in service


def test_low_odds_positive_ev_survives():
    rows = [replace(s, probability=Decimal('.8')) for s in signals()]
    decision, evidence = evaluate_profile('HOME_WIN', Decimal('1.40'), rows, policy_for('SENIOR_MEN_PRO'), ())
    assert decision.decision == 'APPROVED' and not evidence['hard_failures']
    assert decision.ensemble_probability * decision.offered_odds > 1


@pytest.mark.parametrize('p', ['.5', '.49'])
def test_nonpositive_ev_is_nonactionable(p):
    decision, evidence = evaluate_profile('HOME_WIN', Decimal('2'),
        [replace(s, probability=Decimal(p)) for s in signals()], policy_for('SENIOR_MEN_PRO'), ())
    assert decision.decision == 'REJECTED'
    assert 'NON_POSITIVE_VALUE' in evidence['hard_failures']


@pytest.mark.parametrize('kind,reason', [
    ('few', 'INSUFFICIENT_INDEPENDENT_SIGNALS'),
    ('market_only', 'NO_INDEPENDENT_NON_MARKET_EVIDENCE'),
    ('disagree', 'MATERIAL_SIGNAL_DISAGREEMENT'),
    ('disagree', 'WEIGHTED_AGREEMENT_BELOW_0_65'),
    ('contradiction', 'SEVERE_CURRENT_MATCH_INTELLIGENCE_CONTRADICTION'),
    ('small_edge', 'VALUE_BELOW_PROFILE_THRESHOLD'),
    ('divergence', 'ENSEMBLE_MARKET_DIVERGENCE_TOO_LARGE'),
])
def test_quality_findings_survive_as_lower_lanes(kind, reason):
    rows = signals()
    odds = Decimal('2')
    if kind == 'market_only': rows = rows[:1]
    if kind == 'disagree': rows = [replace(rows[0], probability=Decimal('.4')), replace(rows[1], probability=Decimal('.8'))]
    if kind == 'small_edge': rows = [replace(s, probability=Decimal('.51')) for s in rows]
    if kind == 'divergence': rows = [replace(s, probability=Decimal('.85')) for s in rows]
    decision, evidence = evaluate_profile('HOME_WIN', odds, rows, policy_for('SENIOR_MEN_PRO'), (), contradiction=kind=='contradiction')
    assert decision.decision == 'APPROVED'
    assert decision.confidence == 'LOW'
    assert evidence['candidate_lane'] in {'EXPERIMENTAL', 'TRACKING'}
    assert reason in evidence['soft_findings'] and not evidence['hard_failures']


def test_missing_price_preserves_model_probability_without_ev():
    decision, evidence = evaluate_profile('HOME_WIN', None, signals()[1:], policy_for('SENIOR_MEN_PRO'), ())
    assert decision.decision == 'TRACKING' and evidence['waiting_for_refresh']
    assert decision.ensemble_probability is not None and decision.edge is None
    assert not evidence['hard_failures']


@pytest.mark.parametrize('bad', ['stale', 'started', 'nonpositive', 'tracking', 'invalid_probability'])
def test_publication_boundary_revalidates(bad, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    row = _controlled_ready_candidate(NOW)
    if bad == 'stale': row['provider_origin_timestamp_utc'] = (NOW-timedelta(hours=4)).isoformat()
    if bad == 'started': row['kickoff_utc'] = NOW.isoformat()
    if bad == 'nonpositive': row['ensemble_probability'] = '.1'
    if bad == 'tracking': row['candidate_lane'] = 'TRACKING'
    if bad == 'invalid_probability': row['ensemble_probability'] = '1'
    ledger = ComboRepository(tmp_path/'var/lab_combo/ledger.db')
    assert prepare_v2_publications({'candidate_markets':[row]}, ledger, now=NOW)['singles'] == []
    assert ledger.all('single_prediction') == []
    ledger.close()


def test_started_fixture_is_retained_for_results(tmp_path):
    row = fixture()
    row['fixture'].update(date=(NOW-timedelta(hours=1)).isoformat(), status={'short':'1H'})
    cache = LeagueCapabilityCache.from_api_payload({'response':[]}, retrieved_at=NOW)
    accepted, excluded = _fixture_rows_with_evidence({'response':[row]}, cache, NOW)
    assert len(accepted)==1 and not excluded and not accepted[0]['prematch_eligible']
    decision, _ = evaluate_profile('HOME_WIN', Decimal(2), signals(), policy_for('UNKNOWN'), ())
    assert _readiness(decision, accepted[0], NOW, {})[0]=='RESULT_TRACKING'


def test_daytime_quota_paces_without_large_unused_reserve():
    quota = {'interpretation_status':'NORMALIZED','daily_remaining':2900,'minute_remaining':1000}
    early = datetime(2026,9,15,9,tzinfo=RIGA)
    late = early.replace(hour=22, minute=30)
    a = adaptive_quota_budget(quota, requested_maximum=400, already_consumed=1, now=early)
    b = adaptive_quota_budget(quota, requested_maximum=400, already_consumed=1, now=late)
    assert a.additional_calls_available == 100 and a.remaining_discovery_cycles == 28
    assert b.additional_calls_available == 399 and b.remaining_discovery_cycles == 1
    end = adaptive_quota_budget({**quota,'daily_remaining':120},requested_maximum=400,already_consumed=1,now=late)
    assert end.additional_calls_available == 20 and end.daily_safety_reserve == 100
    assert adaptive_quota_budget({**quota,'minute_remaining':3},requested_maximum=400,already_consumed=1,now=late).additional_calls_available==3
    assert discovery_cycles_remaining(early.replace(hour=23))==0


class BatchClient(FakeClient):
    """300 fixtures: 100 fresh, 100 stale, 100 missing; two priority misses."""
    def __init__(self):
        super().__init__()
        self.requests = []
    def _hit(self, endpoint, query, payload):
        self.requests.append((endpoint, query))
        return super()._hit(endpoint, query, payload)
    async def leagues(self, *, current=True):
        # Unknown coverage is permitted; histories supply all model evidence.
        return self._hit('/leagues', {}, {'response':[]})
    async def fixtures_by_date(self, day, *, timezone_name='UTC'):
        rows = []
        for i in range(1,301):
            row = fixture('Regional Division 4', i)
            row['league']['id'] = 999
            if i in {201,202}:
                row['league'].update(id=9000+i, competition_profile='INTERNATIONAL_SENIOR')
            rows.append(row)
        return self._hit('/fixtures', {'date':day}, {'response':rows})
    async def _get(self, endpoint, *, params):
        if endpoint=='/odds' and 'date' in params:
            rows = [odds_payload(NOW if i<=100 else NOW-timedelta(hours=4),fixture_id=i)['response'][0] for i in range(1,201)]
            return Response(self._hit(endpoint, params, {'response':rows,'paging':{'current':1,'total':1}}))
        return await super()._get(endpoint, params=params)


def batch_run(tmp_path, monkeypatch, maximum=100):
    monkeypatch.chdir(tmp_path)
    # Fixed model vector isolates throughput policy from statistical model quality.
    monkeypatch.setattr('app.lab_v2_shadow.runner._history_market_probabilities',
                        lambda *a: {'HOME_WIN':Decimal('.60'),'DRAW':Decimal('.24'),'AWAY_WIN':Decimal('.16')})
    repo = ShadowEvidenceRepository(tmp_path/'shadow.db')
    client = BatchClient()
    runner = LabV2ShadowRunner(client,repo,capability_cache_path=tmp_path/'var/caps.json',maximum_calls=maximum)
    report = asyncio.run(runner.run(now=NOW,horizon_days=1))
    return report, client, repo


def test_priority_exact_retry_and_context_before_ordinary(tmp_path, monkeypatch):
    report, client, repo = batch_run(tmp_path, monkeypatch, maximum=15)
    retries = report['odds_pagination']['priority_exact_retries']
    assert len(retries)==2<=PRIORITY_EXACT_RETRIES_PER_CYCLE
    assert all(r['broad_reason']=='ODDS_COMPLETE_SWEEP_NO_FIXTURE_RECORD' and r['recovered'] for r in retries)
    assert report['priority_fixtures_analyzed']==2
    history_ids = [q['league'] for endpoint,q in client.requests if endpoint=='/fixtures' and 'league' in q]
    assert history_ids[:2]==[9201,9202]
    assert ('/odds',{'fixture':203}) not in client.requests
    assert report['api_calls_consumed']<=15
    repo.close()


def test_representative_300_fixture_old_new_throughput(tmp_path, monkeypatch):
    report, client, repo = batch_run(tmp_path, monkeypatch)
    # Baseline 5076b470: only fresh-odds/tracked fixtures entered _evaluate.
    old_covered = 100
    assert report['fixtures_discovered']==300
    assert report['model_analysis_attempts']==report['total_analyzed']==300
    assert report['current_odds_fixtures']==102  # two recovered priority misses
    assert report['waiting_odds_refresh']==198
    assert len(repo.all('model_analysis'))==300
    assert all(row['state']=='WAITING_FOR_REFRESH' for row in repo.all('model_analysis') if 101<=row['fixture_id']<=200)
    assert report['actual_hard_rejects']>0  # negative EV remains blocked
    assert report['soft_confidence_penalties']>0
    assert report['positive_ev_shadow_observations']>0
    assert report['ready_candidate_count']==report['telegram_sends']==0
    # Representative small positive edge: V1's uncertainty margin killed all;
    # the new policy retains the exact probabilities in the TRACKING lane.
    baseline_rejected = new_tracking = 0
    for i in range(300):
        probability = Decimal('.505') + Decimal(i%10)/1000
        rows = [replace(s, probability=probability) for s in signals()]
        old = evaluate_ensemble('HOME_WIN', Decimal(2), rows)
        new, evidence = evaluate_profile('HOME_WIN', Decimal(2), rows, policy_for('SENIOR_MEN_PRO'), ())
        baseline_rejected += old.decision=='REJECTED'
        new_tracking += evidence['candidate_lane']=='TRACKING'
        assert old.ensemble_probability==new.ensemble_probability
    assert baseline_rejected==new_tracking==300
    comparison = {'old':{'discovered':300,'considered':old_covered,'evaluated':old_covered,'odds_covered':old_covered},
                  'new':{'discovered':300,'considered':report['fixtures_considered_for_evaluation'],
                         'evaluated':report['total_analyzed'],'odds_covered':report['current_odds_fixtures'],
                         'tracking':report['throughput']['fixtures_tracking'],
                         'experimental':report['throughput']['experimental_candidates'],
                         'standard':report['throughput']['standard_candidates'],'strong':report['throughput']['strong_candidates'],
                         'rejected':report['throughput']['rejected_candidates'],'ready':report['ready_candidate_count'],
                         'hard_blocked':report['actual_hard_rejects'],'soft_penalized':report['soft_confidence_penalties']}}
    print('THROUGHPUT_REPLAY='+json.dumps(comparison,sort_keys=True))
    assert repo.connection.execute('PRAGMA foreign_key_check').fetchall()==[]
    repo.close()


def test_midcycle_night_guard(tmp_path):
    repo = ShadowEvidenceRepository(tmp_path/'shadow.db')
    client = FakeClient()
    runner = LabV2ShadowRunner(client, repo, capability_cache_path=tmp_path/'var/caps.json',
        runtime_clock=lambda: datetime(2026,9,15,23,tzinfo=RIGA))
    payload, _ = asyncio.run(runner._fetch('/status', {}, client.account_status,
        clock=NOW, ttl=None, use_cache=False))
    assert client.request_count==0 and payload['errors']['request']=='NIGHT_DISCOVERY_PAUSED'
    repo.close()


def test_priority_retry_bound_rotates_after_restart(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    class ManyPriority(BatchClient):
        async def fixtures_by_date(self, day, *, timezone_name='UTC'):
            rows = [fixture('International Championship', i) for i in range(1,31)]
            for row in rows:
                row['league']['id'] = 999
            return self._hit('/fixtures', {'date':day}, {'response':rows})
        async def _get(self, endpoint, *, params):
            if endpoint=='/odds' and 'date' in params:
                return Response(self._hit(endpoint,params,{'response':[],'paging':{'current':1,'total':1}}))
            return await super()._get(endpoint,params=params)
    sets = []
    for offset in (0,30):
        repo = ShadowEvidenceRepository(tmp_path/'shadow.db')
        runner = LabV2ShadowRunner(ManyPriority(),repo,capability_cache_path=tmp_path/'var/caps.json',maximum_calls=100)
        report = asyncio.run(runner.run(now=NOW+timedelta(minutes=offset),horizon_days=1))
        retries = report['odds_pagination']['priority_exact_retries']
        assert 0 < len(retries) <= PRIORITY_EXACT_RETRIES_PER_CYCLE
        sets.append({row['fixture_id'] for row in retries})
        repo.close()
    assert len(sets[0] | sets[1])==30


def test_long_cycle_cannot_backdate_shadow_capture(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repo = ShadowEvidenceRepository(tmp_path/'shadow.db')
    runner = LabV2ShadowRunner(FakeClient(),repo,capability_cache_path=tmp_path/'var/caps.json',maximum_calls=40,
        runtime_clock=lambda: NOW+timedelta(hours=5))
    report = asyncio.run(runner.run(now=NOW,horizon_days=1))
    assert any(c['decision']=='APPROVED' for c in report['candidate_markets'])
    assert report['positive_ev_shadow_observations']==0
    assert not repo.all('forward_selection')
    repo.close()
