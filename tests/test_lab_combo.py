"""Controlled replay/backtest cases; never contact a provider or Telegram."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from itertools import permutations, product
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.current_odds_forward_test.discovery import discover_current_fixture
from app.lab_combo.engine import select_combo, prediction_message
from app.lab_combo.repository import ComboRepository
from app.lab_combo.service import LabComboService
from app.lab_combo.settlement import aggregate, resolve_leg, statistics, settlement_message
from app.lab_telegram.models import LabTelegramConfig
from app.real_match_lab_analysis.models import LAB_CHAT_ID
from tests.test_api_football_adaptive_discovery import NOW, fixture, odds
from tests.test_api_football_discovery_efficiency import CostProvider, history


def legs():
    return [dict(observation_id=f'o{i}', analysis_id=f'a{i}', fixture_id=str(i),
                 home_team_id=str(i*10), away_team_id=str(i*10+1), home_team=f'H{i}', away_team=f'A{i}',
                 competition_id=str(i), competition=f'League {i}', kickoff_utc=(NOW + timedelta(hours=2)).isoformat(),
                 market='HOME_WIN', odds='1.40', probability='0.8', expected_value='0.12', confidence='HIGH',
                 quote={'bookmaker_name': 'Book'}, review={'status': 'PASSED'}) for i in range(1, 4)]


@pytest.fixture
def ledger():
    root = Path('var/lab_combo')
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as directory:
        value = ComboRepository(Path(directory) / 'ledger.db')
        yield value
        value.close()


def test_discovery_rejects_stale_and_missing_before_history():
    client = CostProvider({'2026-08-01': [fixture(1), fixture(2)]},
                          {1: odds(1, updated='2026-08-01T00:00:00+00:00')})
    value = asyncio.run(discover_current_fixture(client, now=NOW, horizon_days=1, maximum_api_calls=10))
    assert client.history_calls == []
    assert client.odds_calls == [1, 2]
    assert value['skip_reasons']['STALE_CURRENT_ODDS'] == 1
    assert value['fresh_odds_candidates'] == 0


def test_discovery_collects_multiple_with_one_shared_budget():
    client = CostProvider({'2026-08-01': [fixture(1), fixture(2), fixture(3)]},
                          {i: odds(i) for i in range(1, 4)},
                          histories={i: history(i) for i in (10, 11, 20, 21, 30, 31)}, minute=300)
    value = asyncio.run(discover_current_fixture(client, now=NOW, horizon_days=1, maximum_fixtures=3))
    assert len(value['selected_fixtures']) == 3
    assert value['fresh_odds_candidates'] == 3
    assert value['api_call_count'] == 11
    assert all(t['required_order'][0] == 'CURRENT_ODDS' for t in value['request_cost_report'])


def test_deterministic_combo_and_correlations():
    outputs = [select_combo(list(order), NOW)[0] for order in permutations(legs())]
    assert all(value == outputs[0] for value in outputs)
    assert Decimal(outputs[0]['combined_odds']) == Decimal('2.744')
    assert select_combo(legs()[:2], NOW)[0] is None
    for key in ('fixture_id', 'home_team_id', 'competition_id'):
        values = legs()
        values[1][key] = values[0][key]
        assert select_combo(values, NOW)[0] is None
    values = legs()
    values[0]['odds'] = '4'
    assert select_combo(values, NOW)[1] == ['COMBINED_ODDS_OUTSIDE_TARGET']
    assert '🧪 GoalVision AI Lab Combo' in prediction_message(outputs[0])


def test_immutable_ledger_and_atomic_claim(ledger):
    assert ledger.append('claim', 'id', {'a': 1})
    assert not ledger.append('claim', 'id', {'a': 1})
    with pytest.raises(ValueError):
        ledger.append('claim', 'id', {'a': 2})
    with pytest.raises(Exception, match='Immutable'):
        with ledger.connection:
            ledger.connection.execute("DELETE FROM evidence")
    second = ComboRepository(Path(ledger.connection.execute('PRAGMA database_list').fetchone()[2]))
    try:
        assert not second.append('claim', 'id', {'a': 1})
    finally:
        second.close()


def test_all_27_settlement_outcomes_replay_backtest():
    combo = select_combo(legs(), NOW)[0]
    for outcomes in product(('WON', 'LOST', 'VOID'), repeat=3):
        results = [dict(observation_id=leg['observation_id'], outcome=status) for leg, status in zip(combo['legs'], outcomes)]
        value = aggregate(combo, results, NOW)
        assert value['status'] == ('LOST' if 'LOST' in outcomes else 'VOID' if set(outcomes) == {'VOID'}
                                   else 'PARTIAL_VOID' if 'VOID' in outcomes else 'WON')
        expected_odds = Decimal('1.4') ** (3-outcomes.count('VOID'))
        assert Decimal(value['effective_combined_odds']) == expected_odds
        assert Decimal(value['unit_result']) == (-1 if 'LOST' in outcomes else expected_odds-1)
        assert aggregate(combo, list(reversed(results)), NOW) == value


def test_regulation_score_void_pending_and_identity():
    leg = legs()[0]
    now = NOW + timedelta(hours=4)
    payload = {'response': [{'fixture': {'id': 1, 'status': {'short': 'AET'}},
                             'goals': {'home': 1, 'away': 2}, 'score': {'fulltime': {'home': 2, 'away': 1}}}]}
    assert resolve_leg(leg, payload, now)['outcome'] == 'WON'
    for status, outcome in [('CANC', 'VOID'), ('ABD', 'VOID'), ('PST', None), ('NS', None)]:
        payload['response'][0]['fixture']['status']['short'] = status
        result = resolve_leg(leg, payload, now)
        assert (result['outcome'] if result else None) == outcome
    payload['response'][0]['fixture']['id'] = 99
    assert resolve_leg(leg, payload, now) is None


def test_send_revalidation_and_ambiguous_delivery_never_retry(ledger):
    combo = select_combo(legs(), NOW)[0]
    ledger.append('prediction', combo['prediction_id'], combo)
    ledger.append('preview', combo['prediction_id'], {'message': prediction_message(combo)})
    service = LabComboService(ledger, None, clock=lambda: NOW)
    config = LabTelegramConfig(token='fictional', chat_id=LAB_CHAT_ID, automatic_enabled=False, official_destinations=frozenset())
    class Transport:
        calls = 0
        async def send_message_receipt(self, **kwargs):
            self.calls += 1
            assert kwargs['chat_id'] == LAB_CHAT_ID
            raise TimeoutError()
    transport = Transport()
    with patch('app.lab_combo.service.load_leg', return_value=(None, ['STALE_CURRENT_ODDS'])):
        assert not asyncio.run(service.publish(combo['prediction_id'], config, transport))['sent']
        assert transport.calls == 0
    by_id = {leg['observation_id']: leg for leg in combo['legs']}
    with patch('app.lab_combo.service.load_leg', side_effect=lambda repo, identity, now: (by_id[identity], [])):
        assert asyncio.run(service.publish(combo['prediction_id'], config, transport))['status'] == 'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED'
        assert asyncio.run(service.publish(combo['prediction_id'], config, transport))['status'] == 'DELIVERY_ALREADY_CLAIMED'
    assert transport.calls == 1


def test_result_sweep_persists_losses_and_recovers_previews(ledger):
    combo = select_combo(legs(), NOW)[0]
    ledger.append('prediction', combo['prediction_id'], combo)
    ledger.append('receipt', 'combo_prediction:' + combo['prediction_id'], {'sent': True})
    class Provider:
        request_count = 0
        def quota_snapshot(self):
            return dict(interpretation_status='NORMALIZED', daily_remaining=100, minute_remaining=100)
        async def fixture(self, identity):
            self.request_count += 1
            return {'response': [{'fixture': {'id': identity, 'status': {'short': 'FT'}}, 'score': {'fulltime': {'home': 0, 'away': 1}}}]}
    client = Provider()
    service = LabComboService(ledger, None, clock=lambda: NOW + timedelta(hours=4))
    output = asyncio.run(service.check_results(client))
    assert output['statistics']['LOST'] == 1
    assert client.request_count == 3
    assert ledger.get('settlement_preview', combo['prediction_id'])
    asyncio.run(service.check_results(client))
    assert client.request_count == 3
    assert statistics(ledger)['units'] == '-1'


def test_existing_publication_review_cannot_be_bypassed(ledger):
    from tests.test_first_lab_operational_readiness import FirstLabOperationalReadinessTests, NOW as review_now
    from app.lab_combo.engine import load_leg
    fixture_test = FirstLabOperationalReadinessTests()
    fixture_test.setUp()
    try:
        output, _ = fixture_test.run_workflow()
        leg, blockers = load_leg(fixture_test.repo, output['observation_id'], review_now)
        assert leg is None
        assert 'CALIBRATION_EVIDENCE_PRODUCTION' in blockers
        service = LabComboService(ledger, fixture_test.repo, clock=lambda: review_now)
        value = service.prepare([output['observation_id']])
        assert value['combo'] is None
        assert value['eligible_singles'] == 0
        assert ledger.all('prediction') == []
    finally:
        fixture_test.tearDown()


def test_successful_send_and_settlement_share_lab_lock(ledger):
    combo = select_combo(legs(), NOW)[0]
    ledger.append('prediction', combo['prediction_id'], combo)
    ledger.append('preview', combo['prediction_id'], {'message': prediction_message(combo)})
    config = LabTelegramConfig(token='fictional', chat_id=LAB_CHAT_ID, automatic_enabled=False)
    class Transport:
        calls = 0
        async def send_message_receipt(self, **kwargs):
            self.calls += 1
            assert kwargs['chat_id'] == LAB_CHAT_ID
            return SimpleNamespace(chat_id=LAB_CHAT_ID, message_id=self.calls)
    transport = Transport()
    service = LabComboService(ledger, None, clock=lambda: NOW)
    by_id = {leg['observation_id']: leg for leg in combo['legs']}
    with patch('app.lab_combo.service.load_leg', side_effect=lambda repo, identity, now: (by_id[identity], [])):
        assert asyncio.run(service.publish(combo['prediction_id'], config, transport))['sent']
        assert not asyncio.run(service.publish(combo['prediction_id'], config, transport))['sent']
    results = [dict(observation_id=leg['observation_id'], fixture_id=leg['fixture_id'], market=leg['market'], outcome='LOST') for leg in combo['legs']]
    for result in results:
        ledger.append('leg_result', result['observation_id'], result)
    settled = aggregate(combo, results, NOW)
    ledger.append('settlement', combo['prediction_id'], settled)
    stats = statistics(ledger, published_only=True)
    ledger.append('settlement_preview', combo['prediction_id'], {'message': settlement_message(settled, stats), 'statistics': stats})
    assert asyncio.run(service.publish(combo['prediction_id'], config, transport, settlement=True))['sent']
    assert not asyncio.run(service.publish(combo['prediction_id'], config, transport, settlement=True))['sent']
    wrong = LabTelegramConfig(token='fictional', chat_id='@goalvisionai', automatic_enabled=False)
    assert not asyncio.run(service.publish(combo['prediction_id'], wrong, transport))['sent']
    assert transport.calls == 2


def test_request_reserve_applies_before_retry():
    import httpx
    from app.football.client import FootballClient
    from app.football.quota import FootballQuotaError
    class HTTP:
        calls = 0
        async def get(self, path, params):
            self.calls += 1
            return httpx.Response(503, request=httpx.Request('GET', 'https://example.invalid'),
                headers={'x-ratelimit-requests-limit': '7500', 'x-ratelimit-requests-remaining': '20',
                         'x-ratelimit-limit': '300', 'x-ratelimit-remaining': '299'}, json={})
        async def aclose(self):
            pass
    async def run():
        client = FootballClient(api_key='fictional', request_limit=40)
        await client.close()
        client._client = HTTP()
        client.restrict_requests(40)
        with patch('app.football.client.asyncio.sleep', return_value=None):
            with pytest.raises(FootballQuotaError):
                await client.account_status()
        assert client.request_count == 1
        await client.close()
    asyncio.run(run())


def test_provider_odds_errors_fail_closed_before_history():
    payload = odds(1)
    payload['errors'] = {'provider': 'Unavailable'}
    client = CostProvider({'2026-08-01': [fixture(1)]}, {1: payload})
    value = asyncio.run(discover_current_fixture(client, now=NOW, horizon_days=1))
    assert value['selected_fixture'] is None
    assert value['skip_reasons']['PROVIDER_ODDS_QUERY_REJECTED'] == 1
    assert client.history_calls == []


def test_cli_bounded_discovery_persists_no_selection_without_telegram(ledger):
    from argparse import Namespace
    from app.database import Database
    from app.lab_combo.cli import cycle
    analysis_path = Path(ledger.connection.execute('PRAGMA database_list').fetchone()[2]).with_name('analysis.db')
    database = Database(analysis_path)
    database.close()
    class Provider(CostProvider):
        def __init__(self, **kwargs):
            super().__init__()
        @property
        def request_count(self):
            return self.calls
        def restrict_requests(self, *args, **kwargs):
            pass
    report = {'selected_fixtures': [], 'terminal_result': 'NO_ELIGIBLE_CURRENT_FIXTURE'}
    args = Namespace(database=analysis_path, ledger=analysis_path.with_name('ledger.db'), command='discover', send=True)
    with patch('app.lab_combo.cli.FootballClient', Provider), patch('app.lab_combo.cli.discover_current_fixture', return_value=report), patch('app.services.telegram_service.TelegramService') as transport:
        result = asyncio.run(cycle(args))
    assert result['real_combo_found'] is False
    assert result['lab_telegram_sent'] is False
    assert result['api_calls_consumed'] == 1
    assert result['policy'] == 'LAB_EXPERIMENTAL_SELECTION_V1'
    assert result['combos'] == []
    transport.assert_not_called()
    assert len(ledger.all('run')) == 1


def test_interrupted_discovery_preserves_partial_evidence_without_retry():
    from app.football.quota import FootballQuotaError
    class Interrupted(CostProvider):
        async def current_odds(self, fixture_id):
            if fixture_id == 2:
                self._record('/odds', {'fixture': fixture_id}, 0)
                raise FootballQuotaError('API_FOOTBALL_QUOTA_AMBIGUOUS')
            return await super().current_odds(fixture_id)
    client = Interrupted({'2026-08-01': [fixture(1), fixture(2)]})
    value = asyncio.run(discover_current_fixture(client, now=NOW, horizon_days=1))
    assert value['terminal_result'] == 'API_FOOTBALL_QUOTA_AMBIGUOUS'
    assert value['candidate_fixture_count'] == 2
    assert value['api_call_count'] == 4
    assert value['request_cost_report'][-1]['calls']['odds'] == 1
    assert value['skip_reasons']['CURRENT_ODDS_UNAVAILABLE'] == 1
    assert value['request_cost_report'][-1]['result'] == 'API_FOOTBALL_QUOTA_AMBIGUOUS'
    assert value['selected_fixtures'] == []
    assert value['incomplete_discovery'] is True
    assert client.history_calls == []
