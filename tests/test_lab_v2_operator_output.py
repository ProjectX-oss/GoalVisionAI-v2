"""Stdout contract tests; disposable evidence stores and in-process fakes only."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest

from app.lab_v2_shadow import cli
from app.lab_v2_shadow.operator_output import operator_cycle_summary, SCHEMA_VERSION
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from app.lab_v2_shadow.runner import LabV2ShadowRunner, night_report
from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint
from tests.test_lab_v2_shadow import (
    NOW, FakeClient, _DeterministicReadyRunner, _RecordingTransport,
    _controlled_cycle_arguments, _install_controlled_cycle_fakes,
)


def synthetic_report(fixtures=2500, candidates=600):
    """Large evidence, including deliberately sensitive excluded fields."""
    return {
        'evaluated_at_utc': NOW.isoformat(), 'mode': 'LAB_V2_NO_SEND',
        'analysis_mode': 'LAB_V2_NO_SEND', 'fixtures_discovered': fixtures,
        'current_odds_fixtures': fixtures, 'candidate_markets_evaluated': candidates,
        'early_candidate_count': candidates, 'final_review_candidate_count': 0,
        'ready_candidate_count': 0, 'api_calls_consumed': 120,
        'candidate_markets': [{'candidate_id': f'candidate-{i}', 'message': 'PRIVATE_MESSAGE',
                               'provider_payload': 'PRIVATE_PROVIDER' * 1000} for i in range(candidates)],
        'fixtures': [{'fixture_id': i, 'payload': 'PRIVATE_PROVIDER' * 100} for i in range(fixtures)],
        'token': '12345:PRIVATE_TOKEN', 'raw_exception': 'PRIVATE_EXCEPTION',
    }


@pytest.mark.parametrize('command', ['controlled-cycle', 'rehearse'])
def test_large_no_send_cli_is_compact_and_keeps_persisted_evidence(tmp_path, monkeypatch, capsys, command):
    monkeypatch.chdir(tmp_path)
    _install_controlled_cycle_fakes(monkeypatch)
    source = synthetic_report()
    identity = 'lab-v2-cycle-' + fingerprint((NOW, 2500, 120))

    class Runner(_DeterministicReadyRunner):
        async def run(self, **kwargs):
            # Match the existing storage shape: report plus individually stored candidates.
            persisted = {k: v for k, v in source.items() if k != 'candidate_markets'}
            persisted['candidate_ids'] = [c['candidate_id'] for c in source['candidate_markets']]
            self.repository.append('rehearsal', identity, persisted, created_at=NOW)
            for c in source['candidate_markets']:
                self.repository.append('candidate', c['candidate_id'], c, created_at=NOW)
            return deepcopy(source)

    monkeypatch.setattr(cli, 'LabV2ShadowRunner', Runner)
    args = _controlled_cycle_arguments(send=False)
    args[0] = command
    assert cli.main(args) == 0
    output = capsys.readouterr().out
    value = json.loads(output)
    assert len(output.splitlines()) == 1
    assert len(output.encode()) < 20 * 1024
    assert value['schema_version'] == SCHEMA_VERSION
    assert value['cycle_id'] == identity and value['evaluated_at_utc'] == NOW.isoformat()
    assert value['analysis_status'] == 'COMPLETED' and value['delivery_status'] == 'NOT_REQUESTED'
    assert value['publication_cycle_persistence'] == {'persisted': True}
    assert not value['publication_requested'] and not value['publication_enabled']
    assert not value['telegram_transport_constructed']
    assert value['publication_attempt_count'] == value['telegram_sends'] == _RecordingTransport.calls == 0
    assert value['fixtures_discovered'] == 2500 and value['early_candidate_count'] == 600
    assert 'PRIVATE_' not in output and 'candidate_markets"' not in output
    repository = ShadowEvidenceRepository(Path('var/lab_v2/shadow.db'))
    try:
        persisted = repository.get('rehearsal', value['cycle_id'])
        recovered = {k: v for k, v in persisted.items() if k != 'candidate_ids'}
        recovered['candidate_markets'] = [repository.get('candidate', c) for c in persisted['candidate_ids']]
        assert recovered == source
        with pytest.raises(sqlite3.IntegrityError, match='immutable'):
            repository.connection.execute("DELETE FROM lab_v2_shadow_evidence WHERE kind='rehearsal'")
    finally:
        repository.close()


def test_real_runner_evidence_remains_inspectable_and_summary_command_unchanged(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    repository = ShadowEvidenceRepository(Path('var/shadow.db'))
    try:
        runner = LabV2ShadowRunner(FakeClient(), repository, capability_cache_path=Path('var/cache.json'), maximum_calls=40)
        report = asyncio.run(runner.run(now=NOW, horizon_days=1, publication_requested=False))
        before = list(repository.connection.execute('SELECT * FROM lab_v2_shadow_evidence'))
        snapshot = deepcopy(report)
        value = operator_cycle_summary(report)
        assert report == snapshot
        assert list(repository.connection.execute('SELECT * FROM lab_v2_shadow_evidence')) == before
        stored = repository.get('rehearsal', value['cycle_id'])
        assert stored is not None
        assert [repository.get('candidate', c) for c in stored['candidate_ids']] == report['candidate_markets']
        assert stored['global_fixture_states'] == report['global_fixture_states']
    finally:
        repository.close()
    assert cli.main(['summary', '--shadow-database', 'var/shadow.db']) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected['fixtures_discovered'] == report['fixtures_discovered']
    assert 'one_x_two_diagnostics' in inspected
    assert inspected.get('schema_version') != SCHEMA_VERSION


def test_size_grows_only_with_delivery_records_not_candidates():
    small = synthetic_report(1, 1)
    large = synthetic_report()
    small_size = len(canonical_json(operator_cycle_summary(small)).encode())
    large_size = len(canonical_json(operator_cycle_summary(large)).encode())
    assert large_size - small_size < 30
    assert large_size < 20 * 1024
    delivery = {
        'kind': 'single_prediction', 'prediction_id': 'lab-v2-single-' + 'a' * 64,
        'stage': 'RECEIPT_PERSISTENCE', 'claim_persisted': True, 'transport_attempted': True,
        'acknowledgement_received': True, 'acknowledgement': {'chat_id': '-1003510920417', 'message_id': 9001},
        'receipt_persisted': False, 'reconciliation_required': True, 'unknown_marker_persisted': False,
        'persistence_failure': 'RECEIPT', 'status': 'LAB_DELIVERY_PERSISTENCE_FAILED',
    }
    for report in (small, large):
        report['controlled_publication'] = {'deliveries': [delivery] * 100}
    projected = operator_cycle_summary(large)
    assert len(projected['controlled_publication']['deliveries']) == 100
    assert len(canonical_json(projected)) - len(canonical_json(operator_cycle_summary(small))) < 30


@pytest.mark.parametrize('terminal', [None, 'secret raw exception ' * 10000, {'message': '12345:PRIVATE_TOKEN'}])
def test_cli_exit_and_typed_terminal_error(monkeypatch, capsys, terminal):
    async def cycle(args):
        return {**synthetic_report(0, 0), 'terminal_error': terminal}
    monkeypatch.setattr(cli, 'configured_cycle', cycle)
    assert cli.main(['controlled-cycle']) == int(bool(terminal))
    output = capsys.readouterr().out
    assert json.loads(output)['terminal_error'] == ({'code': 'CYCLE_TERMINAL_ERROR'} if terminal else None)
    assert 'secret' not in output and 'PRIVATE_' not in output


def test_nested_extra_payloads_never_cross_output_boundary():
    payload = '12345:PRIVATE_TOKEN message body https://provider.invalid/payload ' * 10000
    report = synthetic_report(0, 0)
    report.update(terminal_error={'message': payload}, publication_cycle_persistence={'persisted': False, 'message': payload})
    report['controlled_publication'] = {
        'reason': payload, 'publication_reviews': [payload], 'failure': {'code': 'LAB_DELIVERY_PERSISTENCE_FAILED', 'message': payload},
        'deliveries': [{'kind': 'single_prediction', 'prediction_id': 'lab-v2-single-' + 'b' * 64,
            'status': 'SENT', 'stage': 'RECEIPT_PERSISTED', 'acknowledgement_received': True,
            'acknowledgement': {'chat_id': '-1003510920417', 'message_id': 1, 'response': payload},
            'message': payload, 'token': payload, 'provider_payload': payload}],
    }
    output = canonical_json(operator_cycle_summary(report))
    assert len(output) < 3000 and 'PRIVATE_' not in output and 'provider.invalid' not in output
    item, = json.loads(output)['controlled_publication']['deliveries']
    assert item['prediction_id'] == 'lab-v2-single-' + 'b' * 64
    assert item['acknowledgement'] == {'chat_id': '-1003510920417', 'message_id': 1}


def test_night_pause_has_identity_zero_attempts_and_no_fabricated_persistence():
    report = night_report(NOW)
    value = operator_cycle_summary(report)
    assert value['cycle_id'] == 'lab-v2-night-' + fingerprint(NOW)
    assert value['analysis_status'] == 'SKIPPED'
    assert value['publication_cycle_persistence'] == {'persisted': None}
    assert value['publication_attempt_count'] == value['telegram_sends'] == 0
