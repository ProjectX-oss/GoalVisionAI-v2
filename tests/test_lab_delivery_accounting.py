"""Real service/CLI boundary with disposable SQLite stores and fake transports."""
import asyncio
import json
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from app.lab_combo.repository import ComboRepository
from app.lab_combo.service import DeliveryFailure, LabComboService
from app.lab_v2_shadow import cli
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from app.lab_v2_shadow.statistics import single_cohorts
from tests.test_lab_v2_shadow import (
    NOW, _DeterministicReadyRunner, _FakeBot, _RecordingTransport,
    _controlled_cycle_arguments, _controlled_ready_candidate,
    _install_controlled_cycle_fakes, bind_candidate_evidence,
)


@pytest.fixture
def cycle(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _install_controlled_cycle_fakes(monkeypatch)
    original = _DeterministicReadyRunner.run

    async def run_ready(self, **kwargs):
        report = await original(self, **kwargs)
        for item in report['candidate_markets']:
            item.update(predictive_family_count=2,
                        predictive_families=['PI_RATINGS', 'API_FOOTBALL_PREDICTION'])
        return report

    monkeypatch.setattr(_DeterministicReadyRunner, 'run', run_ready)

    def run():
        assert cli.main([*_controlled_cycle_arguments(send=True), '--label-v2-selections']) == 0
        report = json.loads(capsys.readouterr().out)
        assert 'secret' not in json.dumps(report)
        return report

    return run


def fail_append(monkeypatch, record, *, on_call=1):
    original = ComboRepository.append
    calls = 0

    def append(self, kind, identity, value):
        nonlocal calls
        if kind == record:
            calls += 1
            if calls == on_call:
                raise sqlite3.OperationalError('secret database/transport details')
        return original(self, kind, identity, value)

    monkeypatch.setattr(ComboRepository, 'append', append)


@pytest.mark.parametrize('record', ['receipt', 'delivery_unknown'])
def test_persistence_failure_retains_delivery_and_retry_never_resends(cycle, monkeypatch, record):
    _RecordingTransport.fail = record == 'delivery_unknown'
    fail_append(monkeypatch, record)
    report = cycle()
    publication = report['controlled_publication']
    item, = publication['deliveries']
    acknowledged = record == 'receipt'
    assert report['delivery_status'] == 'FAILED'
    assert report['analysis_status'] == 'COMPLETED'
    assert report['publication_attempt_count'] == publication['publication_attempt_count'] == 1
    assert publication['send_attempted'] is True
    assert report['telegram_sends'] == publication['singles_sent'] == 0
    assert item['claim_persisted'] and item['transport_attempted']
    assert item['acknowledgement_received'] is acknowledged
    assert item['transport_failure_kind'] == (None if acknowledged else 'TIMEOUT')
    assert item['acknowledgement'] == ({'chat_id': '-1003510920417', 'message_id': 9001} if acknowledged else None)
    assert not item['receipt_persisted'] and not item['unknown_marker_persisted']
    assert item['reconciliation_required'] and not item['sent']
    assert item['persistence_failure'] == ('RECEIPT' if acknowledged else 'DELIVERY_UNKNOWN')
    assert item['stage'] == ('RECEIPT_PERSISTENCE' if acknowledged else 'UNKNOWN_MARKER_PERSISTENCE')
    assert publication['failure']['prediction_id'] == item['prediction_id']
    assert publication['failure']['code'] == 'LAB_DELIVERY_PERSISTENCE_FAILED'
    ledger = ComboRepository(Path('var/lab_combo/ledger.db'))
    shadow = ShadowEvidenceRepository(Path('var/lab_v2/shadow.db'))
    try:
        assert len(ledger.all('claim')) == len(ledger.all('economic_claim')) == 1
        assert ledger.all('receipt') == ledger.all('delivery_unknown') == []
        assert shadow.all('publication_cycle')[0]['controlled_publication']['deliveries'] == [item]
        assert single_cohorts(ledger, start=NOW-timedelta(days=1), end=NOW+timedelta(days=1),
                              as_of=NOW+timedelta(hours=1))['forward_union']['published'] == 0
        # Direct service replay exercises the existing claim gate as well as the CLI retry.
        replay = asyncio.run(LabComboService(ledger, None, clock=lambda: NOW).publish_experimental(
            item['kind'], item['prediction_id'], cli.load_lab_telegram_config(), _RecordingTransport('fictional')))
        assert replay['status'] == 'DELIVERY_ALREADY_CLAIMED'
        assert not replay['transport_attempted']
        ledger.append('single_settlement', item['prediction_id'], {'status': 'WON'})
        ledger.append('single_settlement_preview', item['prediction_id'], {'message': 'synthetic result'})
        settlement = asyncio.run(LabComboService(ledger, None, clock=lambda: NOW).publish_experimental(
            'single_settlement', item['prediction_id'], cli.load_lab_telegram_config(), _RecordingTransport('fictional')))
        assert settlement['status'] == 'PUBLISHED_PREDICTION_AND_SETTLEMENT_REQUIRED'
        assert not settlement['transport_attempted']
    finally:
        ledger.close()
        shadow.close()
    replay = cycle()
    assert replay['publication_attempt_count'] == 0
    assert _RecordingTransport.calls == 1


@pytest.mark.parametrize('record', ['receipt', 'delivery_unknown'])
def test_second_failure_preserves_first_and_does_not_attempt_remaining(cycle, monkeypatch, record):
    class Runner(_DeterministicReadyRunner):
        async def run(self, **kwargs):
            report = await super().run(**kwargs)
            candidates = []
            for index in range(3):
                item = _controlled_ready_candidate(kwargs['now'])
                item.update(candidate_id=f'candidate-{index}', fixture_id=7001+index,
                            predictive_family_count=2,
                            predictive_families=['PI_RATINGS', 'API_FOOTBALL_PREDICTION'])
                bind_candidate_evidence(item)
                candidates.append(item)
            return {**report, 'candidate_markets': candidates, 'ready_candidate_count': 3}

    monkeypatch.setattr(cli, 'LabV2ShadowRunner', Runner)
    original = _RecordingTransport.send_message_receipt

    async def send(self, **kwargs):
        type(self).fail = record == 'delivery_unknown' and type(self).calls == 1
        return await original(self, **kwargs)

    monkeypatch.setattr(_RecordingTransport, 'send_message_receipt', send)
    fail_append(monkeypatch, record, on_call=2 if record == 'receipt' else 1)
    report = cycle()
    first, failed = report['controlled_publication']['deliveries']
    assert first['receipt_persisted'] and first['sent']
    assert failed['reconciliation_required'] and not failed['receipt_persisted']
    assert first['prediction_id'] != failed['prediction_id']
    assert report['publication_attempt_count'] == _RecordingTransport.calls == 2
    assert report['telegram_sends'] == report['controlled_publication']['singles_sent'] == 1
    ledger = ComboRepository(Path('var/lab_combo/ledger.db'))
    try:
        assert len(ledger.all('single_prediction')) == 3
        assert len(ledger.all('receipt')) == 1 and len(ledger.all('claim')) == 2
        assert ledger.get('receipt', first['kind'] + ':' + first['prediction_id'])['message_id'] == first['message_id']
    finally:
        ledger.close()


@pytest.mark.parametrize('after_claim', [False, True])
def test_pre_transport_rejection_is_not_an_attempt(cycle, monkeypatch, after_claim):
    calls = 0

    def reject(*args):
        nonlocal calls
        calls += 1
        return None if after_claim and calls == 1 else 'PUBLICATION_WINDOW_CLOSED'

    monkeypatch.setattr('app.lab_combo.service.publication_blocker', reject)
    report = cycle()
    item, = report['controlled_publication']['deliveries']
    assert item['stage'] == 'REJECTED_BEFORE_TRANSPORT'
    assert item['claim_persisted'] is after_claim
    assert not item['transport_attempted'] and not item['reconciliation_required']
    assert report['publication_attempt_count'] == report['telegram_sends'] == _RecordingTransport.calls == 0
    assert not report['controlled_publication']['send_attempted']


@pytest.mark.parametrize('stage', ['INITIALIZATION', 'SHUTDOWN'])
def test_lifecycle_failure_retains_explicit_delivery_facts(cycle, monkeypatch, stage):
    async def fail(*args):
        raise TimeoutError('secret lifecycle details')

    async def shutdown(*args):
        pass

    monkeypatch.setattr(_FakeBot, '__aenter__' if stage == 'INITIALIZATION' else '__aexit__', fail)
    monkeypatch.setattr(_FakeBot, 'shutdown', shutdown, raising=False)
    report = cycle()
    sent = int(stage == 'SHUTDOWN')
    assert report['publication_attempt_count'] == report['telegram_sends'] == _RecordingTransport.calls == sent
    assert report['controlled_publication']['send_attempted'] is bool(sent)
    deliveries = report['controlled_publication']['deliveries']
    assert len(deliveries) == sent
    if sent:
        assert deliveries[0]['receipt_persisted'] and deliveries[0]['acknowledgement_received']
    assert report['controlled_publication']['failure']['stage'] == stage


@pytest.mark.parametrize('record', ['receipt', 'delivery_unknown', None])
def test_reporting_persistence_failure_exposes_bounded_failure(cycle, monkeypatch, record):
    if record:
        _RecordingTransport.fail = record == 'delivery_unknown'
        fail_append(monkeypatch, record)
    original = ShadowEvidenceRepository.append

    def append(self, kind, *args, **kwargs):
        if kind == 'publication_cycle':
            raise sqlite3.OperationalError('secret reporting failure')
        return original(self, kind, *args, **kwargs)

    monkeypatch.setattr(ShadowEvidenceRepository, 'append', append)
    report = cycle()
    assert report['publication_cycle_persistence'] == {
        'persisted': False, 'code': 'LAB_PUBLICATION_CYCLE_PERSISTENCE_FAILED',
    }
    assert report['delivery_status'] == ('FAILED' if record else 'DEGRADED')
    assert report['publication_attempt_count'] == _RecordingTransport.calls == 1
    item, = report['controlled_publication']['deliveries']
    assert item['transport_attempted']
    assert item['receipt_persisted'] is (record is None)
    assert report['telegram_sends'] == int(record is None)


def test_typed_failure_preserves_identity_without_exception_text(tmp_path, monkeypatch):
    from tests.test_prematch_v2_enablement import Transport, config, prepare
    monkeypatch.chdir(tmp_path)
    ledger = ComboRepository(Path('var/lab_combo/ledger.db'))
    try:
        prediction = prepare(ledger)
        fail_append(monkeypatch, 'receipt')
        with pytest.raises(DeliveryFailure) as caught:
            asyncio.run(LabComboService(ledger, None, clock=lambda: NOW).publish_experimental(
                'single_prediction', prediction['prediction_id'], config(), Transport()))
        assert caught.value.outcome['prediction_id'] == prediction['prediction_id']
        assert caught.value.outcome['acknowledgement_received']
        assert 'secret' not in str(caught.value) + json.dumps(caught.value.outcome)
    finally:
        ledger.close()


def test_shutdown_failure_does_not_replace_delivery_failure(cycle, monkeypatch):
    fail_append(monkeypatch, 'receipt')

    async def fail(*args):
        raise RuntimeError('secret shutdown failure')

    monkeypatch.setattr(_FakeBot, '__aexit__', fail)
    monkeypatch.setattr(_FakeBot, 'shutdown', fail, raising=False)
    report = cycle()
    item, = report['controlled_publication']['deliveries']
    failure = report['controlled_publication']['failure']
    assert item['acknowledgement_received'] and item['reconciliation_required']
    assert report['publication_attempt_count'] == _RecordingTransport.calls == 1
    assert failure['code'] == 'LAB_DELIVERY_PERSISTENCE_FAILED'
    assert failure['lifecycle_failure']['stage'] == 'SHUTDOWN'
    assert failure['cleanup'] == 'FAILED'


@pytest.mark.parametrize('blocker', ['policy', 'existing_claim', 'claim_failure'])
def test_other_pre_transport_boundaries_have_zero_attempts(cycle, monkeypatch, blocker):
    if blocker == 'policy':
        from app.lab_v2_shadow.publication_policy import review_publication

        def review(item, **kwargs):
            result = review_publication(item, **kwargs)
            return {**result, 'eligible': False} if 'prediction_id' in item else result

        monkeypatch.setattr('app.lab_v2_shadow.publication_policy.review_publication', review)
    elif blocker == 'existing_claim':
        async def enter(self):
            ledger = ComboRepository(Path('var/lab_combo/ledger.db'))
            try:
                item, = ledger.all('single_prediction')
                assert ledger.claim_publication('single_prediction', item, {'prediction_id': item['prediction_id']})
            finally:
                ledger.close()
            return self

        monkeypatch.setattr(_FakeBot, '__aenter__', enter)
    else:
        def fail(*args):
            raise sqlite3.OperationalError('secret claim failure')

        monkeypatch.setattr(ComboRepository, 'claim_publication', fail)
    report = cycle()
    item, = report['controlled_publication']['deliveries']
    assert item['prediction_id'] and not item['transport_attempted']
    assert not item['acknowledgement_received'] and not item['receipt_persisted']
    assert report['publication_attempt_count'] == report['telegram_sends'] == _RecordingTransport.calls == 0
    assert not report['controlled_publication']['send_attempted']
    assert item['status'] == {
        'policy': 'LAB_PUBLICATION_POLICY_REJECTED',
        'existing_claim': 'DELIVERY_ALREADY_CLAIMED',
        'claim_failure': 'LAB_DELIVERY_STAGE_FAILED',
    }[blocker]
