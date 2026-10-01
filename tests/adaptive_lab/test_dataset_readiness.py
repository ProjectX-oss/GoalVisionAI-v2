"""Offline chronological preflight regressions against a disposable audit database."""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

from app.adaptive_lab.automl import AutoLearner, dataset_readiness
from app.adaptive_lab.datasets import chronological_dataset
from app.adaptive_lab.governance import Governance
from app.adaptive_lab.models import candidate_specs, train, validate_training_rows
from app.adaptive_lab.observations import ingest
from app.adaptive_lab.policy import POLICY
from app.adaptive_lab.repository import AuditRepository
from .conftest import START, frozen, observation


RESEARCH_TABLES = (
    'learning_cycles', 'learning_datasets', 'split_assignments', 'model_specs',
    'training_runs', 'model_artifacts', 'validation_results', 'holdout_results',
    'candidate_events', 'candidate_comparisons', 'shadow_runs',
)
NOW = START + timedelta(days=300)


def seed_dataset(repo: AuditRepository, count: int, *, validation_keep: int | None = None,
                 training: str = 'BINARY') -> dict:
    """Freeze synthetic delayed settlements through the real ingestion contract."""
    a, b = int(count * .6), int(count * .8)
    with repo.transaction():
        for i in range(count):
            won = i % 2 or (training == 'ONE_CLASS' and i < a)
            prediction, receipt, settlement = frozen(i, outcome='WON' if won else 'LOST')
            if validation_keep is not None and a + validation_keep <= i < b:
                settlement['settled_at_utc'] = (START + timedelta(hours=b * 6)).isoformat()
            if training == 'EMPTY' and i < a:
                settlement['settled_at_utc'] = (START + timedelta(hours=a * 6)).isoformat()
            ingest(repo, prediction, receipt, settlement, stream='PREMATCH',
                   publication_id=prediction['prediction_id'])
    return chronological_dataset(repo.all('learning_observations'), 'PREMATCH', now=NOW)


@pytest.mark.parametrize('count,validation_keep,training,counts,reasons', [
    (500, 0, 'BINARY', (296, 0, 100, 104), ['VALIDATION_SAMPLE_INSUFFICIENT']),
    (500, 29, 'BINARY', (296, 29, 100, 75), ['VALIDATION_SAMPLE_INSUFFICIENT']),
    (495, None, 'BINARY', (293, 95, 99, 8), ['INSUFFICIENT_FRESH_HOLDOUT']),
    (100, 0, 'BINARY', (56, 0, 20, 24),
     ['INSUFFICIENT_FRESH_HOLDOUT', 'VALIDATION_SAMPLE_INSUFFICIENT']),
    (500, None, 'EMPTY', (0, 96, 100, 304), ['TRAINING_RESOURCE_OR_STREAM_CONTRACT']),
    (500, None, 'ONE_CLASS', (296, 96, 100, 8), ['TRAIN_CLASS_DIVERSITY_REQUIRED']),
])
def test_not_ready_never_creates_research_evidence(
    repo: AuditRepository, monkeypatch: pytest.MonkeyPatch, count: int,
    validation_keep: int | None, training: str, counts: tuple[int, ...], reasons: list[str],
) -> None:
    dataset = seed_dataset(repo, count, validation_keep=validation_keep, training=training)
    before = list(repo.connection.iterdump())
    changes = repo.connection.total_changes

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail('Not-ready research must not generate specs, train, append, or acquire a write lock')

    monkeypatch.setattr('app.adaptive_lab.automl.candidate_specs', forbidden)
    monkeypatch.setattr('app.adaptive_lab.automl.train', forbidden)
    monkeypatch.setattr('app.adaptive_lab.prepared.PreparedAudit.append', forbidden)
    monkeypatch.setattr(repo, 'transaction', forbidden)
    result = AutoLearner(repo).run('PREMATCH', now=NOW)
    assert result == {
        'status': 'RESEARCH_DATASET_NOT_READY',
        'dataset_fingerprint': dataset['dataset_fingerprint'],
        'counts': dict(zip(('TRAIN', 'VALIDATION', 'SEALED_HOLDOUT', 'PURGED'), counts)),
        'required_minimums': {'TRAIN': 1, 'VALIDATION': POLICY.subgroup_min,
                              'SEALED_HOLDOUT': POLICY.holdout_min, 'PURGED': 0},
        'training_contract': {'required_classes': [0, 1], 'single_stream': True,
                              'maximum_rows': POLICY.training_rows_limit},
        'blocked_by': reasons,
    }
    assert AutoLearner(repo).run('PREMATCH', now=NOW) == result
    later = AutoLearner(repo).run('PREMATCH', now=NOW + timedelta(days=1))
    assert later['status'] == result['status'] and later['blocked_by'] == reasons
    assert later['counts'] == result['counts']
    assert all(repo.all(table) == [] for table in RESEARCH_TABLES)
    assert list(repo.connection.iterdump()) == before
    assert repo.connection.total_changes == changes


def test_preflight_is_pure_and_ready_at_existing_minimums(repo: AuditRepository) -> None:
    dataset = seed_dataset(repo, 500, validation_keep=POLICY.subgroup_min)
    before = deepcopy(dataset)
    result = dataset_readiness(dataset)
    assert result['status'] == 'RESEARCH_DATASET_READY' and result['blocked_by'] == []
    assert result['counts'] == {'TRAIN': 296, 'VALIDATION': 30, 'SEALED_HOLDOUT': 100, 'PURGED': 74}
    assert dataset == before
    consumed = {row['observation_id'] for row in dataset['partitions']['SEALED_HOLDOUT']}
    projected = chronological_dataset(repo.all('learning_observations'), 'PREMATCH', now=NOW,
                                      consumed_holdout=consumed)
    assert dataset_readiness(projected)['blocked_by'] == ['INSUFFICIENT_FRESH_HOLDOUT']
    assert dataset_readiness(projected)['counts']['PURGED'] == 174


def test_consumed_holdout_blocks_without_new_evidence_or_champion_change(
    repo: AuditRepository, monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = seed_dataset(repo, 500)
    spec = next(s for s in candidate_specs('PREMATCH') if s['family'] == 'LOGISTIC')
    champion = Governance(repo).bootstrap(train(spec, dataset['partitions']['TRAIN']),
                                          now=START - timedelta(days=1))
    consumed = [row['observation_id'] for row in dataset['partitions']['SEALED_HOLDOUT']]
    repo.append('holdout_results', 'synthetic-consumed-holdout', 'PREMATCH',
                {'observation_ids': consumed}, START.isoformat(), artifact_id=champion['artifact_id'])
    before = list(repo.connection.iterdump())
    changes = repo.connection.total_changes

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail('Consumed holdout must block before candidate creation')

    monkeypatch.setattr('app.adaptive_lab.automl.candidate_specs', forbidden)
    result = AutoLearner(repo).run('PREMATCH', now=NOW)
    assert result['status'] == 'RESEARCH_DATASET_NOT_READY'
    assert result['blocked_by'] == ['INSUFFICIENT_FRESH_HOLDOUT']
    assert result['counts'] == {'TRAIN': 296, 'VALIDATION': 96, 'SEALED_HOLDOUT': 0, 'PURGED': 108}
    assert AutoLearner(repo).run('PREMATCH', now=NOW) == result
    assert repo.champion('PREMATCH') == champion
    assert list(repo.connection.iterdump()) == before
    assert repo.connection.total_changes == changes


@pytest.mark.parametrize('invalid,reason', [
    ([], 'TRAINING_RESOURCE_OR_STREAM_CONTRACT'),
    ([observation(0), observation(1, stream='LIVE')], 'TRAINING_RESOURCE_OR_STREAM_CONTRACT'),
    ([observation(0), observation(1)], 'TRAIN_CLASS_DIVERSITY_REQUIRED'),
])
def test_shared_training_contract(invalid: list[dict], reason: str) -> None:
    spec = next(s for s in candidate_specs('PREMATCH') if s['family'] == 'LOGISTIC')
    with pytest.raises(ValueError, match=reason):
        validate_training_rows(invalid)
    with pytest.raises(ValueError, match=reason):
        train(spec, invalid)


def test_ready_raw_dataset_waits_for_disjoint_calibration_without_consuming_cycle(repo: AuditRepository) -> None:
    dataset = seed_dataset(repo, 500, validation_keep=POLICY.subgroup_min)
    assert dataset_readiness(dataset)['status'] == 'RESEARCH_DATASET_READY'
    before = list(repo.connection.iterdump())
    result = AutoLearner(repo).run('PREMATCH', now=NOW)
    assert result['status'] == 'CALIBRATION_DATASET_NOT_READY'
    assert not result['research_cycle_consumed'] and not result['holdout_consumed']
    assert list(repo.connection.iterdump()) == before
    assert repo.champion('PREMATCH') is None and repo.champion('LIVE') is None

def test_existing_shadow_still_reports_dataset_readiness_without_writes(repo, monkeypatch):
    seed_dataset(repo, 500, validation_keep=0)
    before = list(repo.connection.iterdump())
    original_all = repo.all
    def existing_shadow(table, stream=None):
        if table == "shadow_runs":
            return [{"shadow_id": "synthetic-existing-shadow", "champion_generation": None}]
        return original_all(table, stream)
    monkeypatch.setattr(repo, "all", existing_shadow)
    result = AutoLearner(repo)._run("PREMATCH", now=NOW)
    assert result["status"] == "CHALLENGER_ALREADY_IN_SHADOW"
    assert result["dataset_readiness"]["counts"]["VALIDATION"] == 0
    assert result["dataset_readiness"]["status"] == "RESEARCH_DATASET_NOT_READY"
    assert list(repo.connection.iterdump()) == before
