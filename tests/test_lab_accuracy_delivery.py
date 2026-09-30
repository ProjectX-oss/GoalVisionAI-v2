"""Offline accuracy-first handoff and fail-closed delivery regressions."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import asyncio
import json
from pathlib import Path

import pytest

from app.lab_combo.service import LabComboService
from app.lab_combo.repository import ComboRepository
from app.lab_v2_shadow import cli
from app.lab_v2_shadow.publication import prepare_v2_publications, v2_single_message
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from tests.test_prematch_v2_enablement import ledger, candidate, config, Transport
from tests.test_lab_v2_shadow import (
    NOW, bind_candidate_evidence, _controlled_cycle_arguments,
    _install_controlled_cycle_fakes, _DeterministicReadyRunner, _RecordingTransport,
)


def accuracy_candidate(market: str = 'OVER_2_5') -> dict:
    value = candidate()
    value.update(market=market, decision='REJECTED', stage='REJECTED', candidate_lane='REJECTED',
                 ensemble_probability='0.72', captured_odds='1.30', offered_odds='1.30',
                 edge=str(Decimal('.72') - 1 / Decimal('1.30')),
                 hard_failures=['NON_POSITIVE_VALUE'], rejection_reasons=['NON_POSITIVE_VALUE'],
                 soft_findings=[], predictive_family_count=0, predictive_families=[],
                 final_review_completed_at_utc=None)
    value['signals'] = [dict(name='CURRENT_MARKET_CONSENSUS', market=market, selection=market,
                             probability='0.72', reliability='0.90', availability='AVAILABLE',
                             provenance='CURRENT_API_FOOTBALL_QUOTES_ONLY',
                             independence_group='CURRENT_MARKET_CONSENSUS')]
    bind_candidate_evidence(value)
    return value


def prepare_accuracy(store: object, market: str = 'OVER_2_5', labelled: bool = True) -> dict:
    return prepare_v2_publications({'candidate_markets': [accuracy_candidate(market)]},
                                   store, now=NOW, label_origin=labelled)['singles'][0]


@pytest.fixture
def accuracy_cycle(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _install_controlled_cycle_fakes(monkeypatch)
    original = _DeterministicReadyRunner.run

    def run(row: dict | None, *, send: bool = True) -> tuple[dict, dict]:
        async def rejected_report(self, **kwargs):
            report = await original(self, **kwargs)
            return {**report, 'ready_candidate_count': 0,
                    'candidate_markets': [row] if row is not None else []}

        monkeypatch.setattr(_DeterministicReadyRunner, 'run', rejected_report)
        assert cli.main(_controlled_cycle_arguments(send=send)) == 0
        summary = json.loads(capsys.readouterr().out)
        repository = ShadowEvidenceRepository(Path('var/lab_v2/shadow.db'))
        try:
            evidence, = repository.all('publication_cycle')
        finally:
            repository.close()
        return summary, evidence

    return run


def test_controlled_cycle_sends_labelled_accuracy_single_with_zero_ready(accuracy_cycle):
    row = accuracy_candidate()
    summary, evidence = accuracy_cycle(row)
    assert summary['ready_candidate_count'] == evidence['ready_candidate_count'] == 0
    assert summary['publication_attempt_count'] == summary['telegram_sends'] == 1
    assert _RecordingTransport.calls == 1
    publication = evidence['controlled_publication']
    assert publication['singles_sent'] == 1 and publication['combos_sent'] == 0
    assert publication['reason'] is None
    assert publication['single_publication_blockers'] == publication['publication_blockers'] == {}
    assert publication['publication_reviews'] == {}
    ledger = ComboRepository(Path('var/lab_combo/ledger.db'))
    try:
        value, = ledger.all('single_prediction')
        assert value['decision'] == value['stage'] == 'REJECTED'
        assert value['hard_failures'] == value['rejection_reasons'] == ['NON_POSITIVE_VALUE']
        assert value['selection_origin']
        assert len(ledger.all('claim')) == len(ledger.all('receipt')) == 1
        assert publication['single_publication_reviews'][row['candidate_id']] == value['accuracy_publication_review']
        assert publication['single_accuracy_publication_policy_version'] == value['accuracy_publication_policy_version']
        assert publication['single_selection_policy'] == value['single_selection_policy']
        assert publication['minimum_published_probability'] == '0.55'
        assert publication['minimum_published_decimal_odds'] == '1.30'
    finally:
        ledger.close()


@pytest.mark.parametrize('blocker,reason', [
    ('accuracy', 'LAB_PUBLICATION_PROBABILITY_BELOW_0_55'),
    ('legacy', 'HISTORICAL_PREVIEW_REQUIRES_NEW_DECISION'),
    ('both', 'LAB_PUBLICATION_RULE_BLOCKED'),
])
def test_zero_ready_no_pending_retains_both_policy_blockers(accuracy_cycle, monkeypatch, blocker, reason):
    row = accuracy_candidate()
    if blocker == 'accuracy':
        row['ensemble_probability'] = row['signals'][0]['probability'] = '.54'
    elif blocker == 'legacy':
        ledger = ComboRepository(Path('var/lab_combo/ledger.db'))
        try:
            prepare_v2_publications({'candidate_markets': [row]}, ledger, now=NOW)
        finally:
            ledger.close()
    else:
        row = candidate()
        row['soft_findings'] = ['SEVERE_MODEL_MARKET_CONTRADICTION']
    monkeypatch.setattr(cli, 'load_lab_telegram_config',
                        lambda: pytest.fail('no pending publication must not load Telegram configuration'))
    summary, evidence = accuracy_cycle(row)
    publication = evidence['controlled_publication']
    assert summary['controlled_publication']['reason'] == publication['reason'] == reason
    assert bool(publication['single_publication_blockers']) is (blocker != 'legacy')
    assert bool(publication['publication_blockers']) is (blocker != 'accuracy')
    assert publication['single_selection_policy'] == 'LAB_SINGLE_ACCURACY_FIRST_PER_FIXTURE_V1'
    assert publication['single_accuracy_publication_policy_version'] == 'LAB_ACCURACY_FIRST_PUBLICATION_V1'
    assert publication['minimum_published_probability'] == '0.55'
    assert publication['minimum_published_decimal_odds'] == '1.30'
    assert not summary['publication_attempt_count'] and not summary['telegram_sends']
    assert _RecordingTransport.constructed == _RecordingTransport.calls == 0
    ledger = ComboRepository(Path('var/lab_combo/ledger.db'))
    try:
        assert not ledger.all('claim') and not ledger.all('receipt')
    finally:
        ledger.close()


@pytest.mark.parametrize('send,empty,reason', [
    (False, False, 'NO_SEND_VALIDATION'),
    (True, True, 'NO_READY_SELECTIONS'),
])
def test_zero_ready_without_publication_never_prepares(accuracy_cycle, monkeypatch, send, empty, reason):
    monkeypatch.setattr(cli, 'prepare_v2_publications',
                        lambda *args, **kwargs: pytest.fail('publication preparation must not run'))
    monkeypatch.setattr(cli, 'load_lab_telegram_config',
                        lambda: pytest.fail('Telegram configuration must not load'))
    summary, evidence = accuracy_cycle(None if empty else accuracy_candidate(), send=send)
    assert summary['controlled_publication']['reason'] == evidence['controlled_publication']['reason'] == reason
    assert not summary['publication_attempt_count'] and not summary['telegram_sends']
    assert _RecordingTransport.constructed == _RecordingTransport.calls == 0
    assert not Path('var/lab_combo/ledger.db').exists()


@pytest.mark.parametrize('market', ['OVER_2_5', 'UNDER_2_5', 'BTTS_YES', 'BTTS_NO'])
@pytest.mark.parametrize('labelled', [True, False])
def test_rejected_consensus_single_requires_label_for_delivery(ledger, monkeypatch, market, labelled):
    source = accuracy_candidate(market)
    value = prepare_accuracy(ledger, market, labelled)
    for key in ('decision', 'stage', 'candidate_lane', 'hard_failures', 'rejection_reasons',
                'final_review_completed_at_utc', 'predictive_family_count', 'predictive_families'):
        assert value[key] == source[key]
    assert value['accuracy_review_completed_at_utc'] == NOW.isoformat()
    # Re-preparation must not renew the immutable review timestamp.
    assert prepare_v2_publications({'candidate_markets': [source]}, ledger,
        now=NOW + timedelta(minutes=1), label_origin=labelled)['singles'][0] == value
    transport = Transport()
    service = LabComboService(ledger, None, clock=lambda: NOW)
    if not labelled:
        monkeypatch.setattr(ledger, 'claim_publication',
                            lambda *args: pytest.fail('unlabelled single must not attempt a claim'))
    result = asyncio.run(service.publish_experimental('single_prediction', value['prediction_id'], config(), transport))
    if not labelled:
        assert result['status'] == 'SELECTION_ORIGIN_OR_APPROVAL_INVALID'
        assert result['stage'] == 'REJECTED_BEFORE_TRANSPORT'
        assert not result['sent'] and not result['claim_persisted'] and not result['transport_attempted']
        assert not transport.calls and not ledger.all('claim') and not ledger.all('receipt')
        return
    assert result['sent'] and result['claim_persisted'] and result['receipt_persisted']
    assert result['transport_attempted'] and len(transport.calls) == 1
    assert ledger.get('single_prediction', value['prediction_id']) == value
    assert not asyncio.run(service.publish_experimental('single_prediction', value['prediction_id'], config(), transport))['sent']
    assert len(transport.calls) == 1


@pytest.mark.parametrize('previous', ['confirmed', 'unknown', 'claim_only'])
def test_claimed_accuracy_single_replay_after_review_expires(ledger, monkeypatch, previous):
    value = prepare_accuracy(ledger)
    transport = Transport(unknown=previous == 'unknown')
    identity = 'single_prediction:' + value['prediction_id']
    if previous == 'claim_only':
        assert ledger.claim_publication('single_prediction', value, {
            'prediction_id': value['prediction_id'],
            'message': ledger.get('single_preview', value['prediction_id'])['message'],
            'chat_id': config().chat_id,
        })
    else:
        first = asyncio.run(LabComboService(ledger, None, clock=lambda: NOW).publish_experimental(
            'single_prediction', value['prediction_id'], config(), transport))
        assert first['status'] == ('SENT' if previous == 'confirmed'
                                   else 'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED')
    claim = ledger.get('claim', identity)
    monkeypatch.setattr(ledger, 'claim_publication',
                        lambda *args: pytest.fail('claimed replay must not attempt another claim'))
    replay = asyncio.run(LabComboService(ledger, None, clock=lambda: NOW + timedelta(minutes=6))
        .publish_experimental('single_prediction', value['prediction_id'], config(), transport))
    assert replay['status'] == 'DELIVERY_ALREADY_CLAIMED'
    assert replay['stage'] == 'NO_TRANSPORT_EXISTING_CLAIM'
    assert not replay['sent'] and not replay['transport_attempted']
    assert len(transport.calls) == (0 if previous == 'claim_only' else 1)
    assert ledger.get('single_prediction', value['prediction_id']) == value
    assert ledger.get('claim', identity) == claim
    assert len(ledger.all('claim')) == 1


@pytest.mark.parametrize('bad', [
    'stale_quote', 'low_probability', 'low_odds', 'fixture', 'team', 'provenance',
    'contradiction', 'bot', 'preview', 'expired_review', 'future_review', 'missing_review',
    'wrong_policy_version', 'failed_review', 'replay', 'tiny_replay', 'signal_market',
    'signal_selection', 'signal_unavailable', 'signal_provenance', 'extra_hard_failure',
    'started', 'publication_window', 'origin', 'origin_version', 'origin_selector',
    'origin_artifact', 'origin_generation', 'origin_context_model', 'source_state',
])
def test_accuracy_delivery_fails_before_claim(ledger, monkeypatch, bad):
    value = prepare_accuracy(ledger)
    altered = deepcopy(value)
    clock = NOW
    if bad == 'stale_quote': altered['provider_origin_timestamp_utc'] = (NOW - timedelta(hours=4)).isoformat()
    if bad == 'low_probability':
        altered['ensemble_probability'] = altered['signals'][0]['probability'] = '.54'
    if bad == 'low_odds':
        altered['captured_odds'] = '1.29'
        bind_candidate_evidence(altered)
    if bad == 'fixture': altered['provider_metadata']['fixture']['id'] += 1
    if bad == 'team': altered['home_team_id'] = altered['away_team_id']
    if bad == 'provenance': altered['quote_provenance_fingerprint'] = 'bad'
    if bad == 'contradiction': altered['soft_findings'] = ['SEVERE_CURRENT_MATCH_INTELLIGENCE_CONTRADICTION']
    if bad == 'expired_review': altered['accuracy_review_completed_at_utc'] = (NOW - timedelta(hours=1)).isoformat()
    if bad == 'future_review': altered['accuracy_review_completed_at_utc'] = (NOW + timedelta(seconds=1)).isoformat()
    if bad == 'missing_review': altered.pop('accuracy_review_completed_at_utc')
    if bad == 'wrong_policy_version': altered['accuracy_publication_policy_version'] = 'unknown'
    if bad == 'failed_review': altered['accuracy_publication_review']['eligible'] = False
    if bad == 'replay': altered['signals'][0]['probability'] = '.71'
    if bad == 'tiny_replay': altered['signals'][0]['probability'] = '.720000000000000000000000001'
    if bad == 'signal_market': altered['signals'][0]['market'] = 'HOME_WIN'
    if bad == 'signal_selection': altered['signals'][0]['selection'] = 'HOME_WIN'
    if bad == 'signal_unavailable': altered['signals'][0]['availability'] = 'UNAVAILABLE'
    if bad == 'signal_provenance': altered['signals'][0]['provenance'] = ''
    if bad == 'extra_hard_failure': altered['hard_failures'].append('INVALID_FIXTURE')
    if bad == 'started': altered['kickoff_utc'] = NOW.isoformat()
    if bad == 'publication_window':
        clock = NOW.replace(hour=23)
        altered.update(provider_origin_timestamp_utc=clock.isoformat(),
                       goalvision_retrieved_at_utc=clock.isoformat(),
                       accuracy_review_completed_at_utc=clock.isoformat(),
                       kickoff_utc=(clock + timedelta(minutes=30)).isoformat())
        bind_candidate_evidence(altered)
    if bad == 'origin': altered['selection_origin']['selector_policy'] = 'other'
    if bad == 'origin_version': altered['selection_origin']['version'] = 'other'
    if bad == 'origin_selector': altered['selection_origin']['origins'] = ['other']
    if bad == 'origin_artifact': altered['selection_origin']['model_artifact'] = 'other'
    if bad == 'origin_generation': altered['selection_origin']['model_generation'] = 'other'
    if bad == 'origin_context_model': altered['selection_origin']['independent_context_model'] = 'other'
    if bad == 'source_state': altered['stage'] = 'READY_TO_PUBLISH'
    get = ledger.get

    def read(kind: str, key: str) -> dict | None:
        if key == value['prediction_id']:
            if kind == 'single_prediction': return altered
            if kind == 'single_preview':
                return {'message': 'wrong' if bad == 'preview' else v2_single_message(altered)}
        return get(kind, key)

    monkeypatch.setattr(ledger, 'get', read)
    transport = Transport(username='wrong' if bad == 'bot' else 'GoalVision_AI_Lab_Bot')
    result = asyncio.run(LabComboService(ledger, None, clock=lambda: clock).publish_experimental(
        'single_prediction', value['prediction_id'], config(), transport))
    assert not result['sent'] and not result['transport_attempted']
    assert result['stage'] == 'REJECTED_BEFORE_TRANSPORT'
    assert not transport.calls and not ledger.all('claim') and not ledger.all('receipt')


def test_consensus_only_result_market_is_not_accuracy_eligible(ledger):
    assert not prepare_v2_publications({'candidate_markets': [accuracy_candidate('HOME_WIN')]},
                                       ledger, now=NOW)['singles']


@pytest.mark.parametrize('bad', [False, True])
def test_legacy_v2_single_retains_positive_ev_review(ledger, bad):
    value = prepare_v2_publications({'candidate_markets': [candidate()]}, ledger, now=NOW)['singles'][0]
    legacy = {k: v for k, v in value.items() if not k.startswith('accuracy_') and k != 'single_selection_policy'}
    legacy['prediction_id'] = 'lab-v2-legacy-single'
    if bad:
        legacy.update(ensemble_probability='.72', captured_odds='1.30')
    ledger.append('single_prediction', legacy['prediction_id'], legacy)
    ledger.append('single_preview', legacy['prediction_id'], {'message': v2_single_message(legacy)})
    transport = Transport()
    result = asyncio.run(LabComboService(ledger, None, clock=lambda: NOW).publish_experimental(
        'single_prediction', legacy['prediction_id'], config(), transport))
    assert result['sent'] is (not bad)


@pytest.mark.parametrize('bad', [False, True])
def test_v2_combo_uses_existing_review(ledger, monkeypatch, bad):
    rows = []
    for index in range(3):
        row = candidate(index)
        row.update(home_team_id=100 + index * 2, away_team_id=101 + index * 2)
        bind_candidate_evidence(row)
        rows.append(row)
    combo, = prepare_v2_publications({'candidate_markets': rows}, ledger, now=NOW)['combos']
    if bad:
        get = ledger.get
        altered = deepcopy(combo)
        altered['legs'][0].update(accuracy_candidate())
        altered['legs'][0]['single_selection_policy'] = 'LAB_SINGLE_ACCURACY_FIRST_PER_FIXTURE_V1'
        monkeypatch.setattr(ledger, 'get', lambda kind, key: altered if kind == 'prediction' else get(kind, key))
    transport = Transport()
    result = asyncio.run(LabComboService(ledger, None, clock=lambda: NOW).publish_experimental(
        'combo_prediction', combo['prediction_id'], config(), transport))
    assert result['sent'] is (not bad)


@pytest.mark.parametrize('predictive', [False, True])
def test_accuracy_minimum_boundary_and_negative_ev_predictive_evidence(ledger, predictive):
    row = candidate() if predictive else accuracy_candidate()
    row.update(decision='REJECTED', stage='REJECTED', candidate_lane='REJECTED',
               captured_odds='1.30', offered_odds='1.30',
               hard_failures=['NON_POSITIVE_VALUE'], rejection_reasons=['NON_POSITIVE_VALUE'],
               final_review_completed_at_utc=None)
    if not predictive:
        row['ensemble_probability'] = row['signals'][0]['probability'] = '.55'
    bind_candidate_evidence(row)
    value, = prepare_v2_publications({'candidate_markets': [row]}, ledger, now=NOW,
                                     label_origin=True)['singles']
    assert Decimal(value['expected_value']) < 0
    transport = Transport()
    result = asyncio.run(LabComboService(ledger, None, clock=lambda: NOW).publish_experimental(
        'single_prediction', value['prediction_id'], config(), transport))
    assert result['sent'] and len(transport.calls) == 1
