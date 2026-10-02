"""Offline SINGLE floor boundaries, immutable delivery and COMBO independence."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import pytest

from app.lab_combo.service import LabComboService
from app.lab_v2_shadow.publication import prepare_v2_publications, v2_single_message
from app.lab_v2_shadow.single_odds_policy import (
    ENVIRONMENT_FLAG, FLOOR_SELECTION_POLICY, minimum_single_odds, single_odds_blocker,
)
from tests.test_lab_accuracy_combo import candidates, prepare
from tests.test_lab_v2_shadow import NOW, bind_candidate_evidence
from tests.test_prematch_v2_enablement import ledger, config, Transport


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv(ENVIRONMENT_FLAG, '1')


def quote(row, odds):
    row.update(captured_odds=odds, offered_odds=odds,
               edge=str(Decimal(row['ensemble_probability']) - 1 / Decimal(odds)))
    bind_candidate_evidence(row)
    return row


@pytest.mark.parametrize('odds,eligible', [('1.05', False), ('1.29', False),
    ('1.299999999999999999999999999', False), ('1.30', True), ('1.3000', True), ('1.31', True)])
def test_single_boundary_preparation_and_delivery(ledger, odds, eligible):
    row = quote(candidates(1)[0], odds)
    result = prepare(ledger, [row])
    assert result['minimum_published_decimal_odds'] == '1.30'
    assert result['single_selection_policy'] == FLOOR_SELECTION_POLICY
    assert bool(result['singles']) is eligible
    if not eligible:
        assert result['single_publication_blockers'][row['candidate_id']] == 'LAB_SINGLE_ODDS_BELOW_1_30'
        assert not ledger.all('single_prediction')
        return
    single, = result['singles']
    assert single['minimum_published_decimal_odds'] == '1.30'
    assert 'koef. ≥1.30' in v2_single_message(single)
    transport = Transport()
    delivered = asyncio.run(LabComboService(ledger, None, clock=lambda: NOW).publish_experimental(
        'single_prediction', single['prediction_id'], config(), transport))
    assert delivered['sent'] and len(transport.calls) == 1


def test_floor_before_per_fixture_ranking_and_separate_combo_pool(ledger):
    rows = [quote(r, '1.05') for r in candidates()]
    alternative = deepcopy(rows[0])
    alternative.update(candidate_id='qualifying-alternative', market='UNDER_2_5', ensemble_probability='.70')
    alternative['signals'][0].update(market='UNDER_2_5', selection='UNDER_2_5', probability='.70')
    quote(alternative, '1.30')
    result = prepare(ledger, [*rows, alternative])
    single, = result['singles']
    assert single['candidate_id'] == 'qualifying-alternative'
    combo, = result['combos']
    assert {leg['candidate_id'] for leg in combo['legs']} == {r['candidate_id'] for r in rows}
    assert Decimal(combo['combined_odds']) == Decimal('1.05') ** 3 < Decimal('1.30')
    assert all(leg['minimum_published_decimal_odds'] is None for leg in combo['legs'])
    transport = Transport()
    result = asyncio.run(LabComboService(ledger, None, clock=lambda: NOW).publish_experimental(
        'combo_prediction', combo['prediction_id'], config(), transport))
    assert result['sent'] and len(transport.calls) == 1


@pytest.mark.parametrize('bad', [None, 'stale', 'contradiction', 'same_team', 'hard_failure'])
def test_all_legs_below_floor_still_need_quality(ledger, bad):
    rows = [quote(r, '1.05') for r in candidates()]
    if bad == 'stale':
        rows[2]['provider_origin_timestamp_utc'] = (NOW - timedelta(hours=6)).isoformat()
        bind_candidate_evidence(rows[2])
    if bad == 'contradiction':
        rows[2]['soft_findings'] = ['SEVERE_CURRENT_MATCH_INTELLIGENCE_CONTRADICTION']
    if bad == 'same_team':
        rows[2]['home_team_id'] = rows[0]['home_team_id']
        bind_candidate_evidence(rows[2])
    if bad == 'hard_failure':
        rows[2]['hard_failures'].append('INVALID_FIXTURE')
    result = prepare(ledger, rows)
    assert not result['singles']
    assert len(result['combos']) == (1 if bad is None else 0)


@pytest.mark.parametrize('legacy', [False, True])
def test_prepared_low_single_cannot_bypass_delivery_floor(ledger, monkeypatch, legacy):
    monkeypatch.setenv(ENVIRONMENT_FLAG, '0')
    row = quote(candidates(1)[0], '1.05')
    single, = prepare(ledger, [row])['singles']
    if legacy:
        single = {k: v for k, v in single.items() if not k.startswith('accuracy_') and k != 'single_selection_policy'}
        single['prediction_id'] = 'legacy-prepared-low-single'
        ledger.append('single_prediction', single['prediction_id'], single)
        ledger.append('single_preview', single['prediction_id'], {'message': v2_single_message(single)})
    frozen = ledger.get('single_preview', single['prediction_id'])
    monkeypatch.setenv(ENVIRONMENT_FLAG, '1')
    transport = Transport()
    result = asyncio.run(LabComboService(ledger, None, clock=lambda: NOW).publish_experimental(
        'single_prediction', single['prediction_id'], config(), transport))
    assert result['status'] == 'LAB_SINGLE_ODDS_BELOW_1_30'
    assert not result['transport_attempted'] and not result['claim_persisted']
    assert not transport.calls and not ledger.all('claim') and not ledger.all('receipt')
    assert ledger.get('single_preview', single['prediction_id']) == frozen


def test_new_policy_identity_preserves_history_and_dedupes_fixture(ledger, monkeypatch):
    rows = candidates(1)
    monkeypatch.setenv(ENVIRONMENT_FLAG, '0')
    old, = prepare(ledger, rows)['singles']
    preview = ledger.get('single_preview', old['prediction_id'])
    monkeypatch.setenv(ENVIRONMENT_FLAG, '1')
    new, = prepare(ledger, rows)['singles']
    assert new['prediction_id'] != old['prediction_id']
    assert ledger.get('single_preview', old['prediction_id']) == preview
    assert 'bez koeficienta minimuma' in preview['message']
    assert prepare(ledger, rows)['singles'] == [new]
    ledger.claim_publication('single_prediction', old, {'prediction_id': old['prediction_id']})
    assert not prepare(ledger, rows)['singles']


@pytest.mark.parametrize('invalid', [None, 'NaN', 'Infinity', '-1', '1', 'bad'])
def test_invalid_odds_fail_closed(invalid):
    assert single_odds_blocker(invalid, minimum=minimum_single_odds()) == 'INVALID_CURRENT_DECIMAL_ODDS'


def test_invalid_configuration_cannot_silently_disable_floor(monkeypatch):
    monkeypatch.setenv(ENVIRONMENT_FLAG, 'true')
    with pytest.raises(ValueError, match='INVALID_LAB_SINGLE_MIN_ODDS_CONFIGURATION'):
        minimum_single_odds()


def test_rollback_restores_no_floor_and_keeps_combo_policy(ledger, monkeypatch):
    monkeypatch.setenv(ENVIRONMENT_FLAG, '0')
    result = prepare(ledger, [quote(r, '1.05') for r in candidates()])
    assert len(result['singles']) == 3 and len(result['combos']) == 1
    assert result['minimum_published_decimal_odds'] is None


@pytest.mark.parametrize('count', [1, 3])
def test_controlled_cycle_persists_floor_blockers_and_can_publish_only_combo(tmp_path, monkeypatch, capsys, count):
    import json
    from pathlib import Path
    from app.lab_v2_shadow import cli
    from app.lab_v2_shadow.repository import ShadowEvidenceRepository
    from tests.test_lab_v2_shadow import (
        _controlled_cycle_arguments, _install_controlled_cycle_fakes,
        _DeterministicReadyRunner, _RecordingTransport,
    )
    monkeypatch.chdir(tmp_path)
    _install_controlled_cycle_fakes(monkeypatch)
    original = _DeterministicReadyRunner.run
    rows = [quote(r, '1.05') for r in candidates(count)]
    async def report(self, **kwargs):
        result = await original(self, **kwargs)
        return {**result, 'candidate_markets': rows, 'ready_candidate_count': 0}
    monkeypatch.setattr(_DeterministicReadyRunner, 'run', report)
    assert cli.main([*_controlled_cycle_arguments(send=True), '--accuracy-combos']) == 0
    summary = json.loads(capsys.readouterr().out)
    publication = summary['controlled_publication']
    assert publication['singles_sent'] == 0
    assert publication['combos_sent'] == (1 if count == 3 else 0)
    assert _RecordingTransport.calls == (1 if count == 3 else 0)
    evidence = ShadowEvidenceRepository(Path('var/lab_v2/shadow.db'))
    try:
        cycle, = evidence.all('publication_cycle')
        retained = cycle['controlled_publication']
        assert retained['minimum_published_decimal_odds'] == '1.30'
        assert retained['single_selection_policy'] == FLOOR_SELECTION_POLICY
        assert set(retained['single_publication_blockers'].values()) == {'LAB_SINGLE_ODDS_BELOW_1_30'}
    finally:
        evidence.close()
    if count == 1:
        assert not _RecordingTransport.constructed
        assert publication['reason'] == 'LAB_SINGLE_ODDS_BELOW_1_30'


def test_historical_low_single_still_settles_and_announces(ledger, monkeypatch):
    from tests.test_lab_combo_early_loss import Provider, payload
    monkeypatch.setenv(ENVIRONMENT_FLAG, '0')
    single, = prepare(ledger, [quote(candidates(1)[0], '1.05')])['singles']
    transport = Transport()
    published = asyncio.run(LabComboService(ledger, None, clock=lambda: NOW).publish_experimental(
        'single_prediction', single['prediction_id'], config(), transport))
    assert published['sent']
    monkeypatch.setenv(ENVIRONMENT_FLAG, '1')
    later = NOW + timedelta(hours=12)
    service = LabComboService(ledger, None, clock=lambda: later)
    asyncio.run(service.check_results(Provider({single['fixture_id']: payload(single['fixture_id'], score=(2, 2))})))
    settled = ledger.get('single_settlement', single['prediction_id'])
    assert settled['status'] == 'WON' and Decimal(settled['unit_result']) == Decimal('.05')
    result = asyncio.run(service.publish_experimental('single_settlement', single['prediction_id'], config(), transport))
    assert result['sent'] and len(transport.calls) == 2
