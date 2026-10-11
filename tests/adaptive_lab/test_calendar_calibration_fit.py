"""Synthetic fit-only chronology/provenance tests; no runtime or transports."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest
from app.adaptive_lab.baseline import artifact, context, infer
from app.adaptive_lab.calendar_research import CalendarPlan
from app.adaptive_lab.calendar_calibration_fit import fit_only
from app.adaptive_lab.contracts import digest
from .conftest import START
from .test_calendar_research import row, resign
from .test_prematch_autonomy import signals


def inputs(count=320):
    model = artifact()
    champion = {'generation_id': 'synthetic-generation', 'artifact_id': 'bootstrap-artifact-' + digest(model),
        'evidence': {'artifact_fingerprint': digest(model)}, 'created_at': START.isoformat(),
        'reason': 'BOOTSTRAP', 'previous_generation': None}
    p = CalendarPlan(anchor=START.isoformat(), declared_at=START.isoformat(),
        model_generation=champion['generation_id'], model_artifact_identity=champion['artifact_id'],
        policy_version='TEST_POLICY_V1', classifier_version='TEST_CLASSIFIER_V1')
    rows = []
    for i in range(count + 20):
        at = START + timedelta(hours=i) if i < 20 else p.windows()['CALIBRATION_FIT'][0] + timedelta(minutes=(i-20)*20)
        r = row(i, at, model_generation=p.model_generation, model_artifact_identity=p.model_artifact_identity)
        frozen = context(signals('HOME_WIN', str(Decimal('.4') + Decimal(i % 10) / 20)),
                         'SENIOR_MEN_PRO', [], 'HOME_WIN', Decimal('2'))
        r['frozen_features']['baseline_context'] = frozen
        r['frozen_model_probability'] = str(infer(frozen))
        rows.append(resign(r))
    return rows, p, champion, model, p.windows()['CALIBRATION_FIT'][1] + timedelta(hours=1)


def test_fit_is_deterministic_detached_and_not_activation_eligible():
    args = inputs()
    original = deepcopy(args)
    result = fit_only(*args[:4], now=args[4])
    assert result == fit_only(list(reversed(args[0])), *args[1:4], now=args[4])
    assert args == original
    assert result['fit_independent_fixtures'] == 320
    assert result['raw_probability_replay'] == 'EXACT_DECIMAL_PASS'
    assert result['methods']['temperature']['status'] == 'FIT_ONLY'
    assert result['methods']['identity']['metrics']['probability_observations'] == 320
    assert result['methods']['isotonic']['status'] == 'NOT_FITTED'
    assert result['method_selection'] is None
    assert not result['activation_allowed'] and not result['promotion_allowed'] and not result['production_eligible']
    assert result['validation_rows_used_for_fit'] == result['holdout_rows_used_for_fit'] == 0


def test_later_labels_are_never_inspected_or_used():
    rows, p, champion, model, now = inputs()
    expected = fit_only(rows, p, champion, model, now=now)
    for partition in ('VALIDATION_EVALUATION', 'SEALED_HOLDOUT'):
        # Intentionally no outcome/target/fingerprint: no future label is needed.
        rows.append({'prediction_created_at': p.windows()[partition][0].isoformat()})
    assert fit_only(rows, p, champion, model, now=now) == expected


@pytest.mark.parametrize('count', [0, 299])
def test_independent_minimum_never_relaxed(count):
    rows, p, champion, model, now = inputs(count)
    with pytest.raises(ValueError, match='NOT_READY'):
        fit_only(rows, p, champion, model, now=now)


def test_open_window_late_fit_and_late_declaration_blocked():
    rows, p, champion, model, now = inputs()
    with pytest.raises(ValueError, match='NOT_READY'):
        fit_only(rows, p, champion, model, now=p.windows()['CALIBRATION_FIT'][1]-timedelta(seconds=1))
    with pytest.raises(ValueError, match='PRECEDE_VALIDATION'):
        fit_only(rows, p, champion, model, now=p.windows()['VALIDATION_EVALUATION'][0])
    with pytest.raises(ValueError, match='NOT_READY'):
        fit_only(rows, replace(p, declared_at=p.windows()['CALIBRATION_FIT'][0].isoformat()), champion, model, now=now)


@pytest.mark.parametrize('probability', ['0', '1', 'NaN', '0.123456789'])
def test_invalid_or_unreproducible_raw_probability_rejected(probability):
    rows, p, champion, model, now = inputs()
    rows[20]['frozen_model_probability'] = probability
    resign(rows[20])
    with pytest.raises(ValueError, match='FROZEN_INPUT|RAW_REPLAY'):
        fit_only(rows, p, champion, model, now=now)


@pytest.mark.parametrize('defect', ['context', 'market', 'generation', 'artifact'])
def test_missing_context_or_provenance_is_not_silently_imputed(defect):
    rows, p, champion, model, now = inputs()
    if defect == 'context':
        rows[20]['frozen_features'].pop('baseline_context'); resign(rows[20])
    elif defect == 'market':
        rows[20]['frozen_features']['baseline_context']['market'] = 'DRAW'; resign(rows[20])
    elif defect == 'generation':
        champion['generation_id'] = 'changed'
    else:
        model['accepted_commit'] = 'changed'
    with pytest.raises(ValueError):
        fit_only(rows, p, champion, model, now=now)


def test_combo_and_late_labels_cannot_manufacture_minimum():
    rows, p, champion, model, now = inputs(300)
    rows[20]['source_product'] = 'COMBO_LEG'; resign(rows[20])
    with pytest.raises(ValueError, match='NOT_READY'):
        fit_only(rows, p, champion, model, now=now)
    rows[20]['source_product'] = 'SINGLE'
    rows[20]['settled_at'] = p.windows()['CALIBRATION_FIT'][1].isoformat(); resign(rows[20])
    with pytest.raises(ValueError, match='NOT_READY'):
        fit_only(rows, p, champion, model, now=now)
