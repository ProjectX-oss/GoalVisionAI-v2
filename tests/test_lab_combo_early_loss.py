"""Offline economic settlement, restart and provider-diagnostic regressions."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import product
from types import SimpleNamespace

import pytest

from app.lab_combo.repository import ComboRepository
from app.lab_combo.service import LabComboService
from app.lab_combo.settlement import economic_settlement, resolve_leg, statistics
from app.lab_combo.cli import _settlement_work_relevant
from app.lab_telegram.models import LabTelegramConfig
from app.real_match_lab_analysis.models import LAB_CHAT_ID
from app.adaptive_lab.metrics import combo_record
from app.adaptive_lab.performance import performance_snapshot

NOW = datetime(2026, 10, 2, 6, tzinfo=timezone.utc)


def payload(fid, status='FT', score=(0, 2), kickoff=None):
    fixture = {'id': fid, 'status': {'short': status}}
    if kickoff:
        fixture['date'] = kickoff.isoformat()
    return {'response': [{'fixture': fixture,
                          'score': {'fulltime': {'home': score[0], 'away': score[1]}}}]}


class Provider:
    def __init__(self, responses):
        self.responses, self.calls, self.request_count = responses, [], 0

    def quota_snapshot(self):
        return {'interpretation_status': 'NORMALIZED', 'daily_remaining': 1000,
                'minute_remaining': 100}

    async def fixture(self, fid):
        self.calls.append(fid)
        self.request_count += 1
        response = self.responses[fid]
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / 'var/lab_combo/ledger.db'
    ledger = ComboRepository(path)
    combo = {'prediction_id': 'c1', 'combined_odds': '3.375', 'legs': [
        {'observation_id': f'o{i}', 'fixture_id': i, 'market': 'OVER_2_5',
         'odds': '1.5', 'home_team': f'Home{i}', 'away_team': f'Away{i}',
         'kickoff_utc': (NOW + timedelta(hours=-4 if i == 1 else i)).isoformat()}
        for i in (1, 2, 3)]}
    ledger.append('prediction', 'c1', combo)
    ledger.append('receipt', 'combo_prediction:c1', {'status': 'SENT', 'sent': True,
                  'chat_id': LAB_CHAT_ID, 'message_id': 1,
                  'sent_at_utc': (NOW - timedelta(hours=5)).isoformat()})
    yield ledger, combo, path
    ledger.close()


def sweep(ledger, provider, now=NOW, *, enabled=True, maximum_calls=20):
    return asyncio.run(LabComboService(ledger, None, clock=lambda: now,
                       early_combo_loss=enabled).check_results(provider, maximum_calls=maximum_calls))


def test_early_loss_restart_delivery_and_later_void_do_not_double_count(setup):
    ledger, combo, path = setup
    client = Provider({1: payload(1)})
    report = sweep(ledger, client)
    first = ledger.get('settlement', 'c1')
    frozen_preview = ledger.get('settlement_preview', 'c1')
    assert report['completed'] == ['c1'] and client.calls == [1]
    assert first['status'] == 'LOST' and first['unit_result'] == '-1'
    assert len(first['legs']) == 1 and len(first['pending_legs']) == 2
    assert first['effective_combined_odds'] is None
    assert 'GAIDA REZULTĀTU' in frozen_preview['message']
    assert 'Home2' in frozen_preview['message'] and 'Home3' in frozen_preview['message']
    assert combo_record(combo, first)['flat_unit_pnl'] == '-1'
    assert performance_snapshot(ledger, now=NOW)['COMBO']['LOST'] == 1
    assert not _settlement_work_relevant(ledger, NOW)
    later = NOW + timedelta(hours=6)
    assert _settlement_work_relevant(ledger, later)
    restarted = ComboRepository(path)
    try:
        client = Provider({2: payload(2, score=(2, 2)), 3: payload(3, 'CANC', (None, None))})
        # Rollback mode keeps reading old early-loss evidence and finishes its audit.
        report = sweep(restarted, client, later, enabled=False)
        assert client.calls == [2, 3]
        assert report['completed'] == [] and report['combo_detail_completed'] == ['c1']
        detail = restarted.get('combo_result_detail', 'c1')
        assert detail['status'] == 'LOST' and detail['partial_void']
        assert [r['outcome'] for r in detail['legs']] == ['LOST', 'WON', 'VOID']
        assert restarted.get('settlement', 'c1') == first
        assert restarted.get('settlement_preview', 'c1') == frozen_preview
        assert len(restarted.all('settlement')) == 1
        assert statistics(restarted, published_only=True)['hypothetical_profit_loss'] == '-1'
        assert not _settlement_work_relevant(restarted, later)
        assert sweep(restarted, Provider({}), later)['api_calls'] == 0
        class Transport:
            calls = 0
            async def send_message_receipt(self, **kwargs):
                self.calls += 1
                return SimpleNamespace(chat_id=LAB_CHAT_ID, message_id=2)
        transport = Transport()
        service = LabComboService(restarted, None, clock=lambda: later)
        config = LabTelegramConfig('fictional', LAB_CHAT_ID, True)
        assert asyncio.run(service.publish_experimental('combo_settlement', 'c1', config, transport))['sent']
        assert not asyncio.run(service.publish_experimental('combo_settlement', 'c1', config, transport))['sent']
        assert transport.calls == 1
    finally:
        restarted.close()


@pytest.mark.parametrize('boundary', ['leg_result', 'settlement', 'settlement_preview'])
def test_restart_after_durable_write_recovers_once(setup, monkeypatch, boundary):
    ledger, combo, path = setup
    original = ledger.append
    fired = False
    def fail_after(kind, identity, value):
        nonlocal fired
        result = original(kind, identity, value)
        if kind == boundary and not fired:
            fired = True
            raise RuntimeError('synthetic process interruption')
        return result
    monkeypatch.setattr(ledger, 'append', fail_after)
    with pytest.raises(RuntimeError):
        sweep(ledger, Provider({1: payload(1)}))
    monkeypatch.setattr(ledger, 'append', original)
    sweep(ledger, Provider({}), NOW + timedelta(minutes=1))
    assert len(ledger.all('settlement')) == len(ledger.all('settlement_preview')) == 1
    assert statistics(ledger, published_only=True)['hypothetical_profit_loss'] == '-1'


def test_timeout_send_is_claimed_and_never_automatically_retried(setup):
    ledger, _, _ = setup
    sweep(ledger, Provider({1: payload(1)}))
    class Transport:
        calls = 0
        async def send_message_receipt(self, **kwargs):
            self.calls += 1
            raise TimeoutError('fictional transport secret')
    transport = Transport()
    config = LabTelegramConfig('fictional', LAB_CHAT_ID, True)
    for _ in range(2):
        result = asyncio.run(LabComboService(ledger, None).publish_experimental(
            'combo_settlement', 'c1', config, transport))
        assert not result['sent']
    assert transport.calls == 1
    assert ledger.get('delivery_unknown', 'combo_settlement:c1')


@pytest.mark.parametrize('status,score', [('NS', (None, None)), ('PST', (None, None)),
                                        ('2H', (0, 0)), ('FT', (None, None))])
def test_nonterminal_or_missing_scores_cannot_cause_loss(setup, status, score):
    ledger, _, _ = setup
    report = sweep(ledger, Provider({1: payload(1, status, score)}))
    assert not ledger.all('settlement')
    assert report['settlement_diagnostics']['records'][0]['provider_status'] == status


def test_rescheduled_future_fixture_is_diagnostic_not_result(setup):
    ledger, _, _ = setup
    report = sweep(ledger, Provider({1: payload(1, 'NS', (None, None), NOW + timedelta(days=1))}))
    d = report['settlement_diagnostics']['records'][0]
    assert d['reason'] == 'RESCHEDULED_FUTURE_KICKOFF' and d['schedule_changed']
    assert not ledger.all('settlement')
    assert len(ledger.all('settlement_diagnostic')) == 1


@pytest.mark.parametrize('tamper', ['fixture_id', 'market', 'captured_odds', 'outcome',
                                  'source_fingerprint', 'retrieved_at_utc', 'fulltime_home'])
def test_early_loss_requires_bound_terminal_evidence(setup, tamper):
    _, combo, _ = setup
    result = resolve_leg(combo['legs'][0], payload(1), NOW)
    bad = {'fixture_id': 99, 'market': 'UNDER_2_5', 'captured_odds': '9',
           'outcome': 'PENDING', 'source_fingerprint': '',
           'retrieved_at_utc': (NOW + timedelta(days=1)).isoformat(), 'fulltime_home': 5}
    result[tamper] = bad[tamper]
    with pytest.raises(ValueError):
        economic_settlement(combo, [result], NOW)


@pytest.mark.parametrize('outcomes', list(product(('WON', 'LOST', 'VOID'), repeat=3)))
def test_full_settlement_matrix_retains_all_returns(setup, outcomes):
    _, combo, _ = setup
    rows = [{'observation_id': l['observation_id'], 'outcome': s}
            for l, s in zip(combo['legs'], outcomes)]
    result = economic_settlement(combo, rows, NOW)
    expected = Decimal(-1) if 'LOST' in outcomes else Decimal('1.5')**outcomes.count('WON')-1
    assert Decimal(result['unit_result']) == expected
    assert 'settlement_version' not in result


def test_feature_disabled_keeps_new_combos_pending(setup):
    ledger, _, _ = setup
    sweep(ledger, Provider({1: payload(1)}), enabled=False)
    assert not ledger.all('settlement') and ledger.get('leg_result', 'o1')['outcome'] == 'LOST'


@pytest.mark.parametrize('response', [None, {'response': ['bad']}, {'response': []},
                                    {'response': [{'fixture': 'bad'}]},
                                    {'errors': {'key': 'fictional secret'}}])
def test_malformed_results_and_errors_are_safely_diagnosed(setup, response):
    ledger, _, _ = setup
    report = sweep(ledger, Provider({1: response}))
    assert not ledger.all('settlement')
    assert 'fictional secret' not in str(report['settlement_diagnostics'])


def test_shared_fixture_cache_and_call_limit_are_preserved(setup):
    ledger, combo, _ = setup
    prediction = {**combo['legs'][0], 'fixture_id': '1', 'prediction_id': 's1', 'captured_odds': '1.5'}
    ledger.append('single_prediction', 's1', prediction)
    ledger.append('receipt', 'single_prediction:s1', {'sent': True})
    client = Provider({1: payload(1)})
    report = sweep(ledger, client, maximum_calls=1)
    assert client.calls == [1]
    assert report['single_completed'] == ['s1'] and report['completed'] == ['c1']


def test_request_error_and_budget_evidence_are_bounded_and_secret_free(setup):
    ledger, combo, _ = setup
    for i in range(105):
        prediction = {**combo['legs'][0], 'fixture_id': i+100,
                      'prediction_id': f's{i:03}', 'captured_odds': '1.5'}
        ledger.append('single_prediction', prediction['prediction_id'], prediction)
        ledger.append('receipt', 'single_prediction:'+prediction['prediction_id'], {'sent': True})
    client = Provider({100: RuntimeError('secret-token-body')})
    report = sweep(ledger, client, maximum_calls=1)
    d = report['settlement_diagnostics']
    assert client.calls == [100] and len(d['records']) == 100
    assert d['truncated'] and d['total_unresolved'] == 106
    assert d['records'][0]['reason'] == 'REQUEST_FAILED'
    assert d['records'][1]['reason'] == 'CALL_BUDGET_EXHAUSTED'
    assert 'secret-token-body' not in str(ledger.all('settlement_diagnostic'))


def test_early_combo_never_becomes_model_learning_observation(setup, tmp_path):
    from app.adaptive_lab.repository import AuditRepository
    from app.adaptive_lab.observations import import_prematch
    ledger, _, _ = setup
    sweep(ledger, Provider({1: payload(1)}))
    audit = AuditRepository(tmp_path/'audit.db')
    try:
        for _ in range(2):
            imported = import_prematch(ledger, audit, now=NOW.isoformat())
            assert imported['combo_records'] == 1
        assert not audit.all('learning_observations', 'PREMATCH')
        assert len(audit.all('combo_analytics', 'COMBO')) == 1
    finally:
        audit.close()


@pytest.mark.parametrize('flag,expected', [('1', True), ('0', False), ('invalid', False)])
def test_offline_cli_composition_honors_exact_feature_flag(setup, monkeypatch, flag, expected):
    from argparse import Namespace
    from app.database import Database
    from app.lab_combo import cli
    ledger, _, path = setup
    analysis = path.parent/'analysis.db'
    Database(analysis).close()
    class Client(Provider):
        def restrict_requests(self, *args, **kwargs):
            pass
        async def account_status(self):
            self.request_count += 1
        async def close(self):
            pass
    client = Client({1: payload(1)})
    monkeypatch.setattr(cli, 'FootballClient', lambda **kwargs: client)
    monkeypatch.setattr(cli, 'LabComboService', lambda *args, **kwargs:
                        LabComboService(*args, **kwargs, clock=lambda: NOW))
    monkeypatch.setenv('GOALVISION_LAB_EARLY_COMBO_LOSS', flag)
    args = Namespace(command='settle', database=analysis, ledger=path, send=False)
    result = asyncio.run(cli.cycle(args))
    assert 'terminal_error' not in result
    assert bool(ledger.get('settlement', 'c1')) is expected
    assert not result['lab_telegram_sent']
