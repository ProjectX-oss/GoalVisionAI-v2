"""Offline PREMATCH canonical replay and strict integrity regression coverage."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.adaptive_lab.coordinator import LearningCoordinator, opportunity
from app.adaptive_lab.governance import Governance
from app.adaptive_lab.repository import AuditRepository
from .conftest import frozen
from .test_governance_rehearsal import baseline

NOW = datetime(2026, 9, 23, 18, 35, 54, 526834, tzinfo=timezone.utc)


def candidate(fixture_id: int = 1612047) -> dict:
    row = frozen()[0]
    row.update(fixture_id=fixture_id, market='DRAW', candidate_id=f'current-{fixture_id}',
               kickoff_utc=NOW.replace(hour=20, minute=0, second=0, microsecond=0).isoformat(),
               prepared_at_utc=(NOW-timedelta(minutes=3)).isoformat(),
               goalvision_retrieved_at_utc=(NOW-timedelta(minutes=3)).isoformat(),
               provider_origin_timestamp_utc=(NOW-timedelta(minutes=4)).isoformat())
    return row


def seed(repo: AuditRepository, row: dict) -> None:
    repo.append('canonical_opportunities', f"{row['fixture_id']}:{row['market']}",
                'PREMATCH', row, row['prepared_at_utc'])


def canonical_rows(repo: AuditRepository) -> list[tuple]:
    return [tuple(row) for row in repo.connection.execute(
        'SELECT * FROM canonical_opportunities ORDER BY id')]


@pytest.fixture
def coordinator(repo: AuditRepository) -> LearningCoordinator:
    value = LearningCoordinator(repo)
    generation = value.governance.bootstrap(baseline('PREMATCH'), now=NOW-timedelta(days=1))
    run = {'shadow_id': 'chronology-run', 'artifact_id': generation['artifact_id'],
           'stream': 'PREMATCH', 'created_at': (NOW-timedelta(hours=2)).isoformat(),
           'champion_generation': generation['generation_id']}
    repo.append('shadow_runs', run['shadow_id'], 'PREMATCH', run, run['created_at'],
                artifact_id=run['artifact_id'])
    return value


@pytest.mark.parametrize('kickoff', [NOW, NOW.replace(hour=18, minute=0, second=0, microsecond=0)])
def test_expired_canonical_skips_and_later_valid_candidate_processes(
    repo: AuditRepository, coordinator: LearningCoordinator, kickoff: datetime,
) -> None:
    incoming = candidate()
    old = dict(incoming, candidate_id='original', kickoff_utc=kickoff.isoformat(),
               prepared_at_utc='2026-09-23T17:35:50.099876+00:00',
               goalvision_retrieved_at_utc='2026-09-23T17:31:35.738569+00:00',
               provider_origin_timestamp_utc='2026-09-23T16:01:14+00:00')
    seed(repo, old)
    before = canonical_rows(repo)[0]
    inputs = [incoming, candidate(2)]
    original_inputs = deepcopy(inputs)
    coordinator.shadow(inputs, stream='PREMATCH', now=NOW)
    coordinator.shadow(inputs, stream='PREMATCH', now=NOW)
    assert inputs == original_inputs
    assert before in canonical_rows(repo)
    assert len(canonical_rows(repo)) == 2
    assert repo.get('canonical_opportunities', '1612047:DRAW') == old
    shadows = repo.all('shadow_predictions')
    assert len(shadows) == 1 and shadows[0]['frozen_opportunity']['fixture_id'] == 2
    diagnostics = repo.all('linkage_diagnostics', 'PREMATCH')
    assert len(diagnostics) == 1
    assert diagnostics[0] == {
        'status': 'EXPIRED_CANONICAL_PREMATCH', 'canonical_key': '1612047:DRAW',
        'fixture_id': 1612047, 'market': 'DRAW', 'incoming_candidate_id': incoming['candidate_id'],
        'canonical_candidate_id': 'original', 'incoming_kickoff_utc': incoming['kickoff_utc'],
        'canonical_kickoff_utc': old['kickoff_utc'], 'prepared_at_utc': old['prepared_at_utc'],
        'observed_at_utc': NOW.isoformat(),
    }


@pytest.mark.parametrize('existing', [False, True])
def test_future_incoming_preparation_is_not_overwritten(
    repo: AuditRepository, coordinator: LearningCoordinator, existing: bool,
) -> None:
    row = candidate()
    if existing:
        seed(repo, row)
    before = canonical_rows(repo)
    row['prepared_at_utc'] = (NOW+timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError, match='SHADOW_CHRONOLOGY_INVALID'):
        coordinator.shadow([row, candidate(2)], stream='PREMATCH', now=NOW)
    assert canonical_rows(repo) == before
    assert repo.all('shadow_predictions') == repo.all('linkage_diagnostics') == []


@pytest.mark.parametrize('expired', [False, True])
def test_future_frozen_preparation_always_raises(
    repo: AuditRepository, coordinator: LearningCoordinator, expired: bool,
) -> None:
    incoming = candidate()
    old = dict(incoming, prepared_at_utc=(NOW+timedelta(seconds=1)).isoformat())
    if expired:
        old['kickoff_utc'] = NOW.isoformat()
    seed(repo, old)
    before = canonical_rows(repo)
    with pytest.raises(ValueError, match='SHADOW_CHRONOLOGY_INVALID'):
        coordinator.shadow([incoming, candidate(2)], stream='PREMATCH', now=NOW)
    assert canonical_rows(repo) == before
    assert repo.all('shadow_predictions') == repo.all('linkage_diagnostics') == []


def test_valid_revised_kickoff_replay_preserves_identity_and_original_evidence(
    repo: AuditRepository, coordinator: LearningCoordinator,
) -> None:
    incoming = candidate()
    old = dict(incoming, candidate_id='original',
               kickoff_utc=(NOW+timedelta(minutes=10)).isoformat())
    seed(repo, old)
    before = canonical_rows(repo)
    coordinator.shadow([incoming, incoming], stream='PREMATCH', now=NOW)
    shadows = repo.all('shadow_predictions')
    coordinator.shadow([incoming], stream='PREMATCH', now=NOW+timedelta(seconds=1))
    assert canonical_rows(repo) == before
    assert repo.all('shadow_predictions') == shadows and len(shadows) == 1
    assert shadows[0]['frozen_opportunity'] == opportunity(old, 'PREMATCH')
    assert repo.all('linkage_diagnostics') == []


def test_unrelated_governance_error_aborts_batch(
    repo: AuditRepository, coordinator: LearningCoordinator, monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = Mock(side_effect=ValueError('MODEL_INTEGRITY_PUBLICATION_BLOCKED'))
    monkeypatch.setattr(coordinator.governance, 'observe', observe)
    with pytest.raises(ValueError, match='MODEL_INTEGRITY_PUBLICATION_BLOCKED'):
        coordinator.shadow([candidate(), candidate(2)], stream='PREMATCH', now=NOW)
    assert observe.call_count == 1
    assert repo.get('canonical_opportunities', '2:DRAW') is None
    assert repo.all('linkage_diagnostics') == []


def test_corrupt_expired_canonical_still_fails_closed(
    repo: AuditRepository, coordinator: LearningCoordinator,
) -> None:
    seed(repo, dict(candidate(), kickoff_utc=NOW.isoformat()))
    # Simulated corruption only in this temporary test database.
    repo.connection.execute('DROP TRIGGER canonical_opportunities_no_update')
    repo.connection.execute("UPDATE canonical_opportunities SET fingerprint='corrupt'")
    with pytest.raises(ValueError, match='ARTIFACT_INTEGRITY_FAILURE'):
        coordinator.shadow([candidate(), candidate(2)], stream='PREMATCH', now=NOW)
    assert repo.all('shadow_predictions') == repo.all('linkage_diagnostics') == []


@pytest.mark.parametrize('field,value', [
    ('ensemble_probability', 'NaN'), ('ensemble_probability', 'Infinity'),
    ('captured_odds', 'NaN'), ('captured_odds', 'Infinity'),
])
def test_malformed_shadow_numbers_remain_integrity_errors(
    repo: AuditRepository, coordinator: LearningCoordinator, field: str, value: str,
) -> None:
    with pytest.raises(ValueError, match='INVALID_NUMBER'):
        coordinator.shadow([dict(candidate(), **{field: value}), candidate(2)], stream='PREMATCH', now=NOW)
    assert canonical_rows(repo) == []


@pytest.mark.parametrize('field,value', [
    ('ensemble_probability', '0'), ('ensemble_probability', '1'),
    ('ensemble_probability', '-0.1'), ('ensemble_probability', '1.1'),
    ('captured_odds', '1'), ('captured_odds', '-2'),
    ('captured_odds', '1.5'),  # Nonpositive EV at p=.6.
    ('kickoff_utc', NOW.isoformat()),
    ('kickoff_utc', (NOW-timedelta(seconds=1)).isoformat()),
    ('goalvision_retrieved_at_utc', (NOW+timedelta(seconds=1)).isoformat()),
    ('goalvision_retrieved_at_utc', (NOW-timedelta(hours=1)).isoformat()),
    ('provider_origin_timestamp_utc', (NOW-timedelta(hours=4)).isoformat()),
])
def test_existing_incoming_selection_gates_preserved(
    repo: AuditRepository, coordinator: LearningCoordinator, field: str, value: str,
) -> None:
    coordinator.shadow([dict(candidate(), **{field: value})], stream='PREMATCH', now=NOW)
    assert canonical_rows(repo) == []
    assert repo.all('shadow_predictions') == repo.all('linkage_diagnostics') == []


@pytest.mark.parametrize('field,value', [
    ('prepared_at_utc', (NOW+timedelta(seconds=1)).isoformat()),
    ('kickoff_utc', NOW.isoformat()),
    ('kickoff_utc', (NOW-timedelta(seconds=1)).isoformat()),
])
def test_direct_governance_chronology_unchanged(repo: AuditRepository, field: str, value: str) -> None:
    with pytest.raises(ValueError, match='SHADOW_CHRONOLOGY_INVALID'):
        Governance(repo).observe('PREMATCH', opportunity(dict(candidate(), **{field: value}), 'PREMATCH'), now=NOW)
    assert repo.all('shadow_predictions') == []
