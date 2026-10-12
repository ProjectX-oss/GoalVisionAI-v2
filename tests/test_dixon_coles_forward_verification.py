"""Preserve full forward validation while removing duplicate numerical replay."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch
import pytest
from app.dixon_coles_forward import model, service
from tests.test_dixon_coles_forward import PLAN, START, artifact, fact, forecasts, reseal

@pytest.mark.parametrize('state', ['resolved', 'pending', 'future', 'reserved'])
def test_each_record_retains_one_full_verification(artifact, forecasts, state):
    record = forecasts[0]
    now = START - timedelta(seconds=1) if state == 'future' else START + timedelta(days=1)
    reserved = frozenset({record['fixture_id']}) if state == 'reserved' else frozenset()
    results = [fact()] if state == 'resolved' else []
    with patch.object(model, 'verify_artifact', wraps=model.verify_artifact) as verify:
        result = service.evaluate([record], {artifact['fingerprint']: artifact}, results,
            plan=PLAN, now=now, additional_reserved=reserved)
    assert verify.call_count == 1
    assert result['overall']['fixtures'] == int(state == 'resolved')
    assert result['selection_effect'] == 'NONE'

@pytest.mark.parametrize('state', ['resolved', 'pending', 'future', 'reserved'])
@pytest.mark.parametrize('corruption', ['hash', 'numerical_certificate'])
def test_corrupt_models_still_fail_for_every_lifecycle(artifact, forecasts, state, corruption):
    bad = deepcopy(artifact)
    bad['optimizer_theta'][0] += .1
    if corruption == 'numerical_certificate':
        bad = reseal(bad)
    now = START - timedelta(seconds=1) if state == 'future' else START + timedelta(days=1)
    reserved = frozenset({forecasts[0]['fixture_id']}) if state == 'reserved' else frozenset()
    with pytest.raises(ValueError):
        service.evaluate([forecasts[0]], {artifact['fingerprint']: bad}, [fact()],
            plan=PLAN, now=now, additional_reserved=reserved)

@pytest.mark.parametrize('pending', [False, True])
def test_consumed_training_fixture_reaches_predict_validation(artifact, forecasts, pending):
    reserved = frozenset({artifact['training_matches'][0]['fixture_id']})
    with pytest.raises(ValueError):
        service.evaluate([forecasts[0]], {artifact['fingerprint']: artifact},
            [] if pending else [fact()], plan=PLAN, now=START + timedelta(days=1),
            additional_reserved=reserved)

def test_reproduced_report_matches_previous_algorithm(artifact, forecasts):
    from app.dixon_coles_research import metrics
    from app.dixon_coles_forward.contracts import VERSION, reserved
    models = {artifact['fingerprint']: artifact}
    results = [fact(i) for i in range(3)]
    for record in forecasts:
        model.verify_artifact(models[record['model_fingerprint']], plan=PLAN)
    old = metrics.evaluate(forecasts, models, results, plan=PLAN,
        now=START + timedelta(days=1), additional_reserved=reserved(PLAN),
        reproduce=service.forecast, comparators=service.COMPARATORS, record_version=VERSION)
    new = service.evaluate(forecasts, models, results, plan=PLAN, now=START + timedelta(days=1))
    assert new == old
