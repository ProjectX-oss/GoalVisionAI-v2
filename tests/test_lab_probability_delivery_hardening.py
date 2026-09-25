"""Offline incident, unit-contract, publication and lifecycle regressions."""
import asyncio
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path

import pytest
from telegram.error import TimedOut

from app.lab_v2_shadow.api_prediction import _probability, normalize_api_prediction
from app.lab_v2_shadow.ensemble import EnsembleSignal
from app.lab_v2_shadow.global_evaluation import evaluate_profile
from app.lab_v2_shadow.profiles import policy_for
from app.lab_v2_shadow.publication_policy import review_publication, SEVERE_FINDINGS, PUBLICATION_POLICY_VERSION
from app.lab_v2_shadow.publication import prepare_v2_publications
from app.lab_combo.repository import ComboRepository
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from tests.test_lab_v2_shadow import (NOW, _controlled_ready_candidate, bind_candidate_evidence,
    _install_controlled_cycle_fakes, _controlled_cycle_arguments, _RecordingTransport, _FakeBot)


@pytest.mark.parametrize('raw,expected', [('0%', '0'), ('0.5%', '.005'), ('1%', '.01'),
                                         ('50%', '.5'), ('100%', '1')])
def test_explicit_percentage_units(raw, expected):
    assert _probability(raw) == Decimal(expected)


@pytest.mark.parametrize('raw', ['1', 1, Decimal('1'), 1.0])
def test_bare_percent_field_is_not_normalized_internal_probability(raw):
    assert _probability(raw, unit='percentage') == Decimal('.01')
    assert _probability(raw, unit='probability') == Decimal(1)
    assert _probability('0.5', unit='probability') == Decimal('.5')
    assert _probability('50%', unit='probability') is None


@pytest.mark.parametrize('raw', [None, True, False, '', '%', '1%%', '1%2', '-1%', '101%',
    'NaN', 'Infinity', float('inf'), Decimal('NaN'), '1,5%', '1_0%', {}, [], '0.5 %'])
def test_invalid_probabilities_unavailable(raw):
    assert _probability(raw) is None


def payload(percent=None):
    return {'parameters': {'fixture': '7'}, 'response': [{'league': {'id': 36, 'season': 2027},
        'teams': {'home': {'id': 31}, 'away': {'id': 1503}},
        'predictions': {'percent': percent or {'home': '50%', 'draw': '50%', 'away': '0%'},
                        'goals': {'home': '+2.5', 'away': '1.5'}},
        'comparison': {'form': {'home': '1%', 'away': '99%'}}}]}


@pytest.mark.parametrize('percent,available', [
    ({'home': '50%', 'draw': '50%'}, False),
    ({'home': 50, 'draw': 50, 'away': 0}, False),
    ({'home': '0.5', 'draw': '0.5', 'away': '0'}, False),
    ({'home': '1%', 'draw': '50%', 'away': '49%'}, True),
    ({'home': '0.5%', 'draw': '50%', 'away': '49.5%'}, True),
    ({'home': '50%', 'draw': '50%', 'away': '50%'}, False),
    ({'home': '99%', 'draw': '1%', 'away': '0%'}, True),
    ({'home': '33%', 'draw': '33%', 'away': '33%'}, True),
    ({'home': '32%', 'draw': '32%', 'away': '32%'}, False),
    ({'home': 'NaN', 'draw': '50%', 'away': '50%'}, False),
])
def test_complete_distribution_and_existing_rounding_tolerance(percent, available):
    result = normalize_api_prediction(payload(percent), fixture_id=7)
    assert result.available is available
    if available:
        assert abs(sum(result.probabilities.values()) - 1) < Decimal('1e-25')
        assert result.comparison['form']['home'] == Decimal('.01')
        assert set(result.probabilities) == {'HOME_WIN', 'DRAW', 'AWAY_WIN'}
        assert result.expected_goals_home is result.expected_goals_away is None
    else:
        assert not result.probabilities


@pytest.mark.parametrize('kwargs', [dict(fixture_id=8), dict(fixture_id=7, home_team_id=1503, away_team_id=31),
                                     dict(fixture_id=7, league_id=39), dict(fixture_id=7, season=2026)])
def test_prediction_identity_mismatch(kwargs):
    assert not normalize_api_prediction(payload(), **kwargs).available


def severe_candidate():
    c = _controlled_ready_candidate(NOW)
    signals = [EnsembleSignal('API_FOOTBALL_PREDICTION', 'HOME_WIN', Decimal('.5'), 'HOME_WIN',
                             Decimal('.75'), 'AVAILABLE', 'retained-provider'),
               EnsembleSignal('CURRENT_MARKET_CONSENSUS', 'HOME_WIN', Decimal('.117'), 'AWAY_WIN',
                             Decimal('.90'), 'AVAILABLE', 'retained-current-quotes')]
    d, evidence = evaluate_profile('HOME_WIN', Decimal('9'), signals, policy_for('INTERNATIONAL_SENIOR'), ())
    c.update(evidence, captured_odds='9', ensemble_probability=str(d.ensemble_probability),
             edge=str(d.edge), decision=d.decision,
             signals=[{k: str(v) if isinstance(v, Decimal) else v for k,v in asdict(s).items()} for s in d.signals])
    bind_candidate_evidence(c)
    c['api_prediction_normalization']['probabilities'] = {'HOME_WIN': '.5', 'DRAW': '.5', 'AWAY_WIN': '0'}
    return c


def test_severe_experiment_remains_trackable_but_cannot_prepare_single_or_combo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    c = severe_candidate()
    assert c['decision'] == 'APPROVED' and c['candidate_lane'] == 'EXPERIMENTAL'
    assert SEVERE_FINDINGS <= set(c['soft_findings'])
    # Omission of warning fields cannot bypass numeric revalidation.
    c.pop('soft_findings')
    gate = review_publication(c, now=NOW)
    assert SEVERE_FINDINGS <= set(gate['rejection_reasons'])
    assert gate['version'] == PUBLICATION_POLICY_VERSION
    ledger = ComboRepository(Path('var/lab_combo/ledger.db'))
    try:
        prepared = prepare_v2_publications({'candidate_markets': [c]}, ledger, now=NOW)
        assert not prepared['singles'] and not prepared['combos']
        assert not ledger.all('claim')
        assert prepared['publication_reviews'][c['candidate_id']] == gate
    finally:
        ledger.close()


def test_normal_candidate_remains_eligible():
    assert review_publication(_controlled_ready_candidate(NOW), now=NOW)['eligible']


@pytest.mark.parametrize('mutate', [
    lambda c: c.pop('signals'),
    lambda c: c.update(final_review_completed_at_utc=(NOW-timedelta(minutes=6)).isoformat()),
    lambda c: c.update(fixture_id=999),
    lambda c: c.update(home_team_id=c['away_team_id']),
    lambda c: c.update(market='AWAY_WIN'),
    lambda c: c.update(ensemble_probability='50%'),
    lambda c: c.pop('api_prediction_normalization'),
])
def test_missing_stale_wrong_identity_and_market_cannot_bypass_gate(mutate):
    c = _controlled_ready_candidate(NOW)
    mutate(c)
    assert not review_publication(c, now=NOW)['eligible']


@pytest.mark.parametrize('stage', ['INITIALIZATION', 'SHUTDOWN'])
def test_lifecycle_failure_preserves_analysis_and_receipts(tmp_path, monkeypatch, capsys, stage):
    from app.lab_v2_shadow import cli
    from app.adaptive_lab.health import cycle_health
    monkeypatch.chdir(tmp_path)
    _install_controlled_cycle_fakes(monkeypatch)
    closed = []

    async def enter(self):
        if stage == 'INITIALIZATION':
            raise TimedOut('secret-token-must-not-be-persisted')
        return self

    async def leave(self, *args):
        raise RuntimeError('secret shutdown details')

    async def shutdown(self):
        closed.append(True)

    monkeypatch.setattr(_FakeBot, '__aenter__', enter)
    monkeypatch.setattr(_FakeBot, '__aexit__', leave)
    monkeypatch.setattr(_FakeBot, 'shutdown', shutdown, raising=False)
    assert cli.main(_controlled_cycle_arguments(send=True)) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['analysis_status'] == 'COMPLETED'
    assert report['delivery_status'] == ('FAILED' if stage == 'INITIALIZATION' else 'DEGRADED')
    assert report['controlled_publication']['failure']['stage'] == stage
    assert 'secret' not in json.dumps(report)
    sent = 0 if stage == 'INITIALIZATION' else 1
    assert report['telegram_sends'] == report['publication_attempt_count'] == sent
    assert _RecordingTransport.calls == sent and closed
    assert cycle_health(report, started=NOW, completed=NOW)['result'] == 'DEGRADED'
    ledger = ComboRepository(Path('var/lab_combo/ledger.db'))
    shadow = ShadowEvidenceRepository(Path('var/lab_v2/shadow.db'))
    try:
        assert len(ledger.all('claim')) == len(ledger.all('receipt')) == sent
        assert not ledger.all('delivery_unknown')
        assert shadow.all('publication_cycle')[0]['analysis_status'] == 'COMPLETED'
    finally:
        ledger.close(); shadow.close()
    if sent:
        assert cli.main(_controlled_cycle_arguments(send=True)) == 0
        assert _RecordingTransport.calls == 1


def test_retained_forward_cohort_replay_and_incident_market():
    from app.lab_v2_shadow.market_consensus import current_market_consensus, best_current_price
    from app.lab_v2_shadow.bookmakers import review_bookmaker_catalogue
    fixture = json.loads((Path(__file__).parent / 'fixtures/lab_probability_incident_20260925.json').read_text())
    for candidate, source in zip(fixture['candidates'], fixture['sources']):
        parsed = normalize_api_prediction(source['projection'], fixture_id=candidate['fixture_id'],
            home_team_id=candidate['home_team_id'], away_team_id=candidate['away_team_id'],
            league_id=candidate['league_id'], season=candidate['season'])
        assert parsed.available
        assert parsed.probabilities == {'HOME_WIN': Decimal('.5'), 'DRAW': Decimal('.5'), 'AWAY_WIN': Decimal('0')}
        baseline = candidate['adaptive_features']['baseline_context']
        signals = [EnsembleSignal(**{**s, 'probability': Decimal(s['probability']),
                                     'reliability': Decimal(s['reliability'])}) for s in baseline['signals']]
        old, evidence = evaluate_profile(candidate['market'], Decimal(candidate['captured_odds']), signals,
            policy_for(baseline['profile']), tuple(baseline['missing']), contradiction=baseline['contradiction'])
        assert old.decision == candidate['decision'] == 'APPROVED'
        assert old.ensemble_probability == parsed.probabilities[candidate['market']] == Decimal('.5')
        assert old.edge == Decimal(candidate['edge'])
        assert SEVERE_FINDINGS <= set(evidence['soft_findings'])
        when = datetime.fromisoformat(candidate['final_review_completed_at_utc']) + timedelta(seconds=1)
        unannotated = {**candidate, 'soft_findings': []}
        gate = review_publication(unannotated, now=when)
        assert not gate['eligible'] and SEVERE_FINDINGS <= set(gate['rejection_reasons'])
    morocco = next(c for c in fixture['candidates'] if c['fixture_id'] == 1545826)
    odds = fixture['morocco_odds_projection']
    catalogue = {'response': [{'id':b['id'],'name':b['name']} for b in odds['response'][0]['bookmakers']]}
    allowed = frozenset(b.bookmaker_id for b in review_bookmaker_catalogue(catalogue)
                        if b.relevance != 'OTHER_CURRENT_PROVIDER_SOURCE')
    when = datetime.fromisoformat(morocco['goalvision_retrieved_at_utc'])
    consensus = current_market_consensus(odds, fixture_id=1545826, retrieved_at=when, now=when,
                                         allowed_bookmaker_ids=allowed)['1X2']
    price = best_current_price(consensus, 'DRAW')
    assert price.decimal_odds == Decimal('9.00') and price.bookmaker_id == 8
    assert price.provenance_fingerprint == morocco['quote_provenance_fingerprint']
    assert consensus.fair_probabilities['DRAW'] == Decimal(morocco['market_fair_probability'])
    assert not current_market_consensus(odds, fixture_id=123, retrieved_at=when, now=when)
    wrong_market = deepcopy(odds)
    for b in wrong_market['response'][0]['bookmakers']:
        b['bets'][0]['name'] = 'First Half Winner'
    assert current_market_consensus(wrong_market, fixture_id=1545826, retrieved_at=when, now=when)['1X2'].quotes == ()


def test_severe_leg_cannot_join_two_ordinary_legs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidates = [severe_candidate(), _controlled_ready_candidate(NOW), _controlled_ready_candidate(NOW)]
    for i,c in enumerate(candidates):
        c.update(candidate_id=f'candidate-{i}', fixture_id=900+i, home_team_id=100+i*2, away_team_id=101+i*2)
        bind_candidate_evidence(c)
    ledger = ComboRepository(Path('var/lab_combo/ledger.db'))
    try:
        prepared = prepare_v2_publications({'candidate_markets':candidates}, ledger, now=NOW)
        assert len(prepared['singles']) == 2 and not prepared['combos']
    finally:
        ledger.close()


def test_ordinary_single_family_experiment_remains_eligible():
    c = severe_candidate()
    c['signals'][0]['probability'] = '0.6'
    c['signals'][1]['probability'] = '0.56'
    c.update(ensemble_probability='0.6', captured_odds='1.90', soft_findings=[])
    bind_candidate_evidence(c)
    assert review_publication(c, now=NOW)['eligible']


def test_real_bot_getme_failure_closes_fake_request_pools_without_sending(tmp_path, monkeypatch, capsys):
    from telegram import Bot
    from telegram.request import BaseRequest
    from app.lab_v2_shadow import cli
    monkeypatch.chdir(tmp_path)
    _install_controlled_cycle_fakes(monkeypatch)
    events = []

    class Request(BaseRequest):
        @property
        def read_timeout(self):
            return 1

        async def initialize(self):
            events.append('initialize')

        async def shutdown(self):
            events.append('shutdown')

        async def do_request(self, url, method, request_data=None, **kwargs):
            assert url.endswith('/getMe')
            events.append('getMe')
            raise TimedOut('synthetic')

    class Transport:
        def __init__(self, token):
            self.bot = Bot('12345:fictional', request=Request(), get_updates_request=Request())

        async def send_message_receipt(self, **kwargs):
            pytest.fail('getMe failure must not send')

    monkeypatch.setattr(cli, 'LabTelegramTransport', Transport)
    assert cli.main(_controlled_cycle_arguments(send=True)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['analysis_status'] == 'COMPLETED' and result['delivery_status'] == 'FAILED'
    assert events.count('getMe') == 1 and events.count('shutdown') == 2
    assert result['publication_attempt_count'] == result['telegram_sends'] == 0


def test_initialization_failure_finishes_observation_as_completed(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.lab_v2_shadow import cli
    from tests.test_lab_v2_shadow import _NoNetworkClient
    monkeypatch.chdir(tmp_path)
    _install_controlled_cycle_fakes(monkeypatch)
    completed = []

    class Observer:
        def __init__(self, *args, **kwargs):
            pass

        def capture(self, *args, **kwargs):
            pass

        def finish(self, *, completed):
            completion = completed
            return record(completion)

    def record(value):
        completed.append(value)
        return {}

    class Client(_NoNetworkClient):
        def __init__(self, *, response_observer=None, **kwargs):
            super().__init__(**kwargs)

    async def fail(self):
        raise TimedOut('synthetic getMe')

    async def shutdown(self):
        pass

    monkeypatch.setattr(cli, 'FootballClient', Client)
    monkeypatch.setattr(_FakeBot, '__aenter__', fail)
    monkeypatch.setattr(_FakeBot, 'shutdown', shutdown, raising=False)
    monkeypatch.setattr('app.prematch_football_context.readiness.composition.ProspectiveObservation', Observer)
    args = SimpleNamespace(shadow_database=Path('var/lab_v2/shadow.db'), ledger=Path('var/lab_combo/ledger.db'),
        analysis_database=Path('var/lab_combo/analysis.db'), capability_cache=Path('var/cache.json'),
        max_calls=40, daily_reserve=100, horizon_days=1, send=True, football_context_root=tmp_path)
    result = asyncio.run(cli.configured_cycle(args))
    assert result['analysis_status'] == 'COMPLETED' and result['delivery_status'] == 'FAILED'
    assert completed == [True]
