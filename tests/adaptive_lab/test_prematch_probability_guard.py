"""Invalid baseline probabilities must not abort adaptive PREMATCH discovery."""
from dataclasses import replace
from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.adaptive_lab.baseline import artifact
from app.adaptive_lab.coordinator import LearningCoordinator
from app.adaptive_lab.governance import Governance
from app.adaptive_lab.repository import AuditRepository
from app.lab_v2_shadow.ensemble import EnsembleSignal
from app.lab_v2_shadow.global_evaluation import evaluate_profile
from app.lab_v2_shadow.profiles import policy_for
from .conftest import START


def signals(market: str, probability: Decimal) -> list[EnsembleSignal]:
    return [
        EnsembleSignal('CURRENT_MARKET_CONSENSUS', market, Decimal('.45'), None,
                       Decimal('.9'), 'AVAILABLE', 'test-market', 'CURRENT_MARKET_CONSENSUS'),
        EnsembleSignal('API_FOOTBALL_PREDICTION', market, probability, None,
                       Decimal('.8'), 'AVAILABLE', 'CURRENT_/PREDICTIONS', 'API_FOOTBALL_PREDICTION'),
    ]


@pytest.mark.parametrize('zero', [Decimal('0'), Decimal('0E+1')])
def test_zero_away_probability_preserves_rejection_and_following_evaluations(
    repo: AuditRepository, zero: Decimal,
) -> None:
    generation = Governance(repo).bootstrap(artifact(), now=START)
    coordinator = LearningCoordinator(repo)
    policy = policy_for('SENIOR_MEN_PRO')
    for fixture_id, market, probability, odds in (
        (1, 'AWAY_WIN', zero, Decimal('151.00')),
        (1, 'HOME_WIN', Decimal('.6'), Decimal('2')),
        (2, 'AWAY_WIN', Decimal('.6'), Decimal('2')),
    ):
        raw = signals(market, probability)
        original = tuple(raw)
        baseline, evidence = evaluate_profile(market, odds, raw, policy, ())
        adapted, provenance = coordinator.prematch_signals(
            raw, baseline, evidence,
            {'fixture_id': fixture_id, 'competition_profile': policy.profile},
            market, odds, now=START, quote_fingerprint=f'q-{fixture_id}-{market}',
        )
        assert adapted is raw and tuple(raw) == original
        decision, new_evidence = evaluate_profile(market, odds, adapted, policy, ())
        assert decision == baseline and new_evidence == evidence
        if probability == 0:
            assert baseline.ensemble_probability == 0
            assert provenance == {}
            assert decision.decision == 'REJECTED'
            assert 'INVALID_MODEL_PROBABILITY' in decision.rejection_reasons
            assert new_evidence['candidate_lane'] == 'REJECTED'
        else:
            assert provenance['model_generation'] == generation['generation_id']
            assert decision.ensemble_probability == probability


@pytest.mark.parametrize('probability', [
    None, Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity'), Decimal('-Infinity'),
    Decimal('-0.1'), Decimal('0'), Decimal('1'), Decimal('1.1'),
])
def test_invalid_baseline_skips_governance(
    repo: AuditRepository, probability: Decimal | None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    Governance(repo).bootstrap(artifact(), now=START)
    coordinator = LearningCoordinator(repo)
    resolve = Mock(side_effect=AssertionError('invalid baseline reached governance'))
    monkeypatch.setattr(coordinator.governance, 'safe_resolve', resolve)
    raw = signals('AWAY_WIN', Decimal('.6'))
    baseline, evidence = evaluate_profile('AWAY_WIN', Decimal('2'), raw, policy_for('SENIOR_MEN_PRO'), ())
    baseline = replace(baseline, ensemble_probability=probability)
    adapted, provenance = coordinator.prematch_signals(
        raw, baseline, evidence, {'fixture_id': 1, 'competition_profile': 'SENIOR_MEN_PRO'},
        'AWAY_WIN', Decimal('2'), now=START, quote_fingerprint='q',
    )
    assert adapted is raw and provenance == {}
    resolve.assert_not_called()
