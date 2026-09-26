"""Public string snapshots and offline immutable labelled-single lifecycle."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import asyncio
import subprocess
from pathlib import Path

import pytest

from app.lab_combo.service import LabComboService
from app.lab_combo.settlement import resolve_single
from app.lab_v2_shadow.origin import result_message as legacy_result_message
from app.lab_v2_shadow.publication import prepare_v2_publications, v2_single_message
from app.lab_v2_shadow.public_presentation import (
    MARKETS, SIGNALS, TITLE, analysis_signals, result_message, statistics_block,
)
from app.lab_v2_shadow.statistics import public_single_snapshot, single_cohorts
from app.real_match_lab_analysis.models import LAB_CHAT_ID
from tests.test_prematch_v2_enablement import ledger, candidate, prepare, Transport, config
from tests.test_lab_v2_shadow import NOW

AFTER = NOW + timedelta(hours=4)


def receipt(store, value, number=1):
    store.append('receipt', 'single_prediction:' + value['prediction_id'], {
        'status': 'SENT', 'sent': True, 'chat_id': LAB_CHAT_ID,
        'message_id': number, 'sent_at_utc': NOW.isoformat()})


def payload(value, status='FT', goals=(2, 0)):
    return {'response': [{'fixture': {'id': value['fixture_id'], 'status': {'short': status}},
                         'score': {'fulltime': dict(zip(('home', 'away'), goals))}}]}


def settle(store, value, status='FT', goals=(2, 0)):
    result = resolve_single(value, payload(value, status, goals), AFTER)
    store.append('single_settlement', value['prediction_id'], result)
    return result


def assert_clean(message):
    for forbidden in ('Atsauce', 'lab-v2-', 'https://t.me/', 'API_FOOTBALL_PREDICTION',
                      'RESULT_HISTORY_MODEL_CONTEXT', 'nekalibrēts', 'Eksperimentāla atlase',
                      'Noslēguma pārbaude', 'Hipotētisks', 'Koef.:', 'Starts:'):
        assert forbidden not in message
    assert len(message.encode('utf-16-le')) // 2 < 1024


@pytest.mark.parametrize('market,label', list(MARKETS.items()))
def test_every_supported_market(ledger, market, label):
    from app.adaptive_lab.contracts import MARKETS as supported
    assert set(MARKETS) == set(supported)
    value = prepare(ledger)
    value['market'] = market
    text = v2_single_message(value)
    assert f'🎯 Likme: {label}\n' in text
    assert_clean(text)


@pytest.mark.parametrize('signal,label', list(SIGNALS.items()))
def test_signal_mapping(signal, label):
    assert analysis_signals([signal]) == label


def test_multiple_unknown_and_consensus_signals():
    assert analysis_signals(['RESULT_HISTORY_MODEL_CONTEXT', 'API_FOOTBALL_PREDICTION']) == (
        'API-Football prognoze, Rezultātu vēstures modelis')
    assert analysis_signals(['CURRENT_MARKET_CONSENSUS']) == '—'
    assert analysis_signals(['SOME_PRIVATE_ID', 'OTHER_NEW_ID']) == 'Modeļa signāls'


def test_exact_prediction_snapshot_and_zero_statistics(ledger):
    value = prepare(ledger)
    value.update(home_team='Faroe Islands', away_team='Kazakhstan', market='HOME_WIN',
                 captured_odds='2.28', kickoff_utc='2026-09-26T16:00:00+00:00',
                 ensemble_probability='0.50', edge='0.061')
    value['selection_origin']['predictive_families'] = ['API_FOOTBALL_PREDICTION']
    assert v2_single_message(value) == '''🧪 GoalVision AI Lab • V2 atlase

⚽ Faroe Islands – Kazakhstan
🎯 Likme: 1
💰 Koeficients: 2.28
⏰ Sākums: 26.09.2026 19:00 (Latvija)

📊 Novērtētā varbūtība: 50.0%
📈 Vērtības pārsvars: +6.1 pp
🧠 Analīzes signāli: API-Football prognoze

📊 V2 statistika
Likmes: 0 | ✅ WON: 0 | ❌ LOST: 0 | ➖ VOID: 0
🎯 Precizitāte: —
📈 P/L: +0.00u | ROI: —'''


@pytest.mark.parametrize('status,goals,outcome,pnl', [
    ('FT', (2, 0), '✅ WON', '+0.90u'), ('FT', (0, 1), '❌ LOST', '-1.00u'),
    ('CANC', (None, None), '➖ VOID', '0.00u'),
])
def test_settlement_snapshots_existing_accounting(ledger, status, goals, outcome, pnl):
    value = prepare(ledger); receipt(ledger, value)
    result = settle(ledger, value, status, goals)
    snap = public_single_snapshot(ledger, as_of=AFTER)
    text = result_message(result, snap)
    score = f'{goals[0]}:{goals[1]}' if goals[0] is not None else '—'
    assert text == '\n'.join((TITLE, '', outcome, '',
        f"⚽ {value['home_team']} – {value['away_team']}", '🎯 Likme: 1',
        '💰 Koeficients: 1.90', f'🏁 Rezultāts: {score}', f'💵 P/L: {pnl}', '', statistics_block(snap)))
    assert snap['totals']['settled'] == 1
    assert_clean(text)
    # The display must use the accepted value, never another winnings formula.
    assert '💵 P/L: +0.66u' in result_message({**result, 'unit_result': '0.66'}, snap)


def test_exact_cohort_denominators_and_exclusions(ledger):
    for i, status in enumerate(('WON', 'LOST', 'VOID', 'PENDING', 'UNPUBLISHED', 'OLD', 'LIVE', 'OFFICIAL', 'BAD_RECEIPT')):
        value = prepare(ledger, candidate(i), labelled=status != 'OLD')
        if status in {'LIVE', 'OFFICIAL'}:
            # A separate synthetic record with a product marker, never a history rewrite.
            value = {**value, 'prediction_id': status, 'product': status}
            ledger.append('single_prediction', status, value)
        if status not in {'UNPUBLISHED', 'BAD_RECEIPT'}:
            receipt(ledger, value, i + 1)
        if status == 'BAD_RECEIPT':
            ledger.append('receipt', 'single_prediction:' + value['prediction_id'], {'sent': False})
        if status != 'PENDING':
            settle(ledger, value, 'CANC' if status == 'VOID' else 'FT', (0, 1) if status == 'LOST' else (2, 0))
    ledger.append('settlement', 'unrelated-combo', {'status': 'WON', 'unit_result': '99'})
    snap = public_single_snapshot(ledger, as_of=AFTER)
    totals = snap['totals']
    assert (totals['settled'], totals['WON'], totals['LOST'], totals['VOID'], totals['pending']) == (3, 1, 1, 1, 1)
    assert totals['hit_rate'] == '0.5'
    assert Decimal(totals['flat_unit_pnl']) == Decimal('-0.10')
    assert Decimal(totals['flat_unit_roi']) == Decimal('-0.10') / 3
    assert totals['roi_denominator_units'] == 3
    existing = single_cohorts(ledger, start=NOW-timedelta(days=1), end=AFTER+timedelta(days=1), as_of=AFTER)
    assert totals == existing['forward_union']
    assert 'Precizitāte: 50.0%' in statistics_block(snap)


def test_prediction_snapshot_replay_ignores_later_settlement(ledger):
    value = prepare(ledger)
    preview = deepcopy(ledger.get('single_preview', value['prediction_id']))
    other = prepare(ledger, candidate(1)); receipt(ledger, other); settle(ledger, other)
    assert prepare(ledger) == value
    assert ledger.get('single_preview', value['prediction_id']) == preview
    assert v2_single_message(value) == preview['message']
    assert value['public_presentation']['statistics']['totals']['settled'] == 0
    item = candidate(2)
    # New valid future candidate at the later preview creation time.
    shift = AFTER - NOW
    for key in ('kickoff_utc', 'goalvision_retrieved_at_utc', 'provider_origin_timestamp_utc', 'final_review_completed_at_utc'):
        if item.get(key):
            from datetime import datetime
            item[key] = (datetime.fromisoformat(item[key]) + shift).isoformat()
    from tests.test_lab_v2_shadow import bind_candidate_evidence
    bind_candidate_evidence(item)
    new = prepare_v2_publications({'candidate_markets': [item]}, ledger, now=AFTER, label_origin=True)['singles'][0]
    assert new['public_presentation']['statistics']['totals']['settled'] == 1


class NoProvider:
    request_count = 0
    async def fixture(self, fixture_id):
        pytest.fail('Unexpected provider call')


def test_settlement_crash_recovery_freezes_snapshot_and_replay(ledger):
    value = prepare(ledger); receipt(ledger, value); result = settle(ledger, value)
    service = LabComboService(ledger, None, clock=lambda: AFTER)
    asyncio.run(service.check_results(NoProvider()))
    original = deepcopy(ledger.get('single_settlement_preview', value['prediction_id']))
    assert original['statistics']['totals']['settled'] == 1
    assert original['message'] == result_message(result, original['statistics'])
    other = prepare(ledger, candidate(1)); receipt(ledger, other, 2); settle(ledger, other)
    asyncio.run(service.check_results(NoProvider()))
    assert ledger.get('single_settlement_preview', value['prediction_id']) == original
    transport = Transport()
    assert asyncio.run(service.publish_experimental('single_settlement', value['prediction_id'], config(), transport))['sent']
    assert transport.calls[0]['text'] == original['message']
    assert transport.calls[0]['parse_mode'] is None
    assert not asyncio.run(service.publish_experimental('single_settlement', value['prediction_id'], config(), transport))['sent']
    assert len(transport.calls) == 1


def test_historical_formatter_bytes_and_delivery_unchanged(ledger):
    # Load the accepted formatter offline to create a genuine pre-change preview.
    source = subprocess.check_output(['git', 'show', '4fd68bd:app/lab_v2_shadow/publication.py'], text=True, cwd=Path(__file__).resolve().parents[1])
    namespace = {'__name__': 'app.lab_v2_shadow._historical', '__package__': 'app.lab_v2_shadow'}
    exec(compile(source, 'accepted-publication.py', 'exec'), namespace)
    old = namespace['prepare_v2_publications']({'candidate_markets': [candidate()]}, ledger, now=NOW, label_origin=True)['singles'][0]
    before = deepcopy(ledger.get('single_preview', old['prediction_id']))
    assert 'Atsauce:' in before['message']
    assert prepare(ledger) == old
    assert v2_single_message(old).encode() == before['message'].encode()
    service = LabComboService(ledger, None, clock=lambda: NOW); transport = Transport()
    assert asyncio.run(service.publish_experimental('single_prediction', old['prediction_id'], config(), transport))['sent']
    result = settle(ledger, old)
    old_result = legacy_result_message(result, {'message_id': 123})
    ledger.append('single_settlement_preview', old['prediction_id'], {'message': old_result, 'statistics': {}})
    service.clock = lambda: AFTER
    asyncio.run(service.check_results(NoProvider()))
    assert ledger.get('single_settlement_preview', old['prediction_id'])['message'].encode() == old_result.encode()
    assert asyncio.run(service.publish_experimental('single_settlement', old['prediction_id'], config(), transport))['sent']
    assert transport.calls[-1]['text'] == old_result


def test_newly_accepted_settlement_included_in_service_preview(ledger):
    value = prepare(ledger); receipt(ledger, value)
    class FixtureClient:
        request_count = 0
        def quota_snapshot(self):
            return {'interpretation_status': 'NORMALIZED', 'daily_remaining': 1000, 'minute_remaining': 100}
        async def fixture(self, fixture_id):
            self.request_count += 1
            return payload(value)
    service = LabComboService(ledger, None, clock=lambda: AFTER)
    client = FixtureClient()
    report = asyncio.run(service.check_results(client))
    assert client.request_count == 1
    assert report['single_completed'] == [value['prediction_id']]
    preview = ledger.get('single_settlement_preview', value['prediction_id'])
    assert preview['statistics']['totals']['settled'] == 1
    assert 'Likmes: 1 | ✅ WON: 1' in preview['message']
    assert preview['message'] == result_message(
        ledger.get('single_settlement', value['prediction_id']), preview['statistics'])


def test_duplicate_confirmed_economic_selection_fails_closed(ledger):
    value = prepare(ledger); receipt(ledger, value)
    duplicate = {**value, 'prediction_id': 'duplicate'}
    ledger.append('single_prediction', 'duplicate', duplicate); receipt(ledger, duplicate, 2)
    with pytest.raises(ValueError, match='DUPLICATE_CONFIRMED_ECONOMIC_SELECTION'):
        public_single_snapshot(ledger, as_of=AFTER)
