"""Fit-only PREMATCH research; no registry, activation, validation or holdout use.

Reuses the frozen calendar and reviewed calibrators. Training-set diagnostics are
explicitly in-sample and cannot select/promote a method. Frozen raw probabilities
are verified against the exact bootstrap inference before fitting.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from app.calibration.calibrators import CalibrationFitRequest, CalibrationFittingPolicy, PlattCalibrator, PlattFittingConfig
from app.calibration.models import CalibrationObservation, CalibrationScope, CalibrationTrainingWindow
from app.calibration.serialization import CalibratorSerializer
from .baseline import infer, validate as validate_baseline
from .calendar_research import CalendarPlan, calendar_dataset
from .calibration_research import MIN_ISOTONIC, apply, temperature_fit
from .contracts import digest, number, utc
from .features import FEATURE_SCHEMA
from .performance import probability_metrics
from .policy import POLICY

VERSION = "PREMATCH_CALENDAR_FIT_ONLY_RESEARCH_V1"


def _observations(rows: list[dict], probabilities: list[float], identity: str) -> list:
    return [CalibrationObservation(r['observation_id'], int(r['fixture_id']),
        str(r.get('competition_profile') or 'UNKNOWN'), r['market'], r['market'],
        utc(r['prediction_created_at']), utc(r['settled_at']), Decimal(str(p)), r['target'],
        model_version=identity) for r, p in zip(rows, probabilities)]


def fit_only(rows: list[dict], plan: CalendarPlan, champion: dict, artifact: dict, *,
             now: datetime, consumed_holdout_fixtures: set[str] | None = None) -> dict:
    """Create detached research JSON only after all FIT-specific readiness gates.

    The validation/holdout gates in calendar_dataset remain unchanged. They are
    deliberately NOT claimed to pass by this separate, non-activatable artifact.
    """
    now = utc(now)
    if now >= plan.windows()['VALIDATION_EVALUATION'][0]:
        raise ValueError('CALIBRATION_FIT_MUST_PRECEDE_VALIDATION')
    validate_baseline(artifact)
    model_digest = digest(artifact)
    if (champion.get('generation_id') != plan.model_generation
            or champion.get('artifact_id') != plan.model_artifact_identity
            or champion.get('evidence', {}).get('artifact_fingerprint') != model_digest
            or champion.get('artifact_id') != 'bootstrap-artifact-' + model_digest
            or champion.get('reason') != 'BOOTSTRAP'
            or champion.get('previous_generation') is not None
            or utc(champion['created_at']) >= plan.windows()['CALIBRATION_FIT'][0]):
        raise ValueError('CALIBRATION_MODEL_PROVENANCE_MISMATCH')
    # Never inspect later partition labels, even if the caller has them.
    rows = [r for r in rows if utc(r['prediction_created_at']) < plan.windows()['CALIBRATION_FIT'][1]]
    dataset = calendar_dataset(rows, plan, now=now,
                              consumed_holdout_fixtures=consumed_holdout_fixtures)
    fit_blockers = [b for b in dataset['blocked_by']
                   if not b.startswith(('VALIDATION_EVALUATION_', 'SEALED_HOLDOUT_'))]
    if fit_blockers:
        raise ValueError('CALIBRATION_FIT_NOT_READY:' + ','.join(fit_blockers))
    fit = dataset['partitions']['CALIBRATION_FIT']
    train = dataset['partitions']['TRAIN']
    if ({str(r['fixture_id']) for r in train} & {str(r['fixture_id']) for r in fit}
            or max(utc(r['settled_at']) for r in train) >= min(utc(r['prediction_created_at']) for r in fit)):
        raise ValueError('CALIBRATION_TRAIN_LEAKAGE')
    probabilities = []
    for row in fit:
        raw = Decimal(str(row['frozen_model_probability']))
        context = row.get('frozen_features', {}).get('baseline_context')
        if (context is None or context.get('market') != row['market']
                or not raw.is_finite() or not 0 < raw < 1
                or utc(row['prediction_created_at']) >= utc(row['kickoff_utc'])):
            raise ValueError('CALIBRATION_FROZEN_INPUT_INVALID')
        if infer(context) != raw:
            raise ValueError('CALIBRATION_RAW_REPLAY_MISMATCH')
        probabilities.append(number(raw, low=0, high=1))
    request = CalibrationFitRequest(now, CalibrationTrainingWindow(
        min(utc(r['prediction_created_at']) for r in fit), max(utc(r['settled_at']) for r in fit)),
        CalibrationScope.global_scope(), VERSION, plan.windows()['VALIDATION_EVALUATION'][0], model_digest)
    policy = CalibrationFittingPolicy(global_minimum=POLICY.calibration_min)
    trainer = PlattCalibrator(config=PlattFittingConfig(epsilon=Decimal('1e-12')), policy=policy)
    serializer = CalibratorSerializer()
    observations = _observations(fit, probabilities, model_digest)
    methods = {'identity': {'status': 'FIT_ONLY', 'calibrator': None}}
    for name, fitter in (
        ('platt', lambda: serializer.serialize(trainer.fit(observations, request))),
        ('temperature', lambda: temperature_fit(probabilities, [r['target'] for r in fit])),
    ):
        try:
            calibrated = fitter()
            # The foundation's production_eligible flag is a numerical-fit check,
            # not GoalVision governance approval. This enclosing artifact is inert.
            methods[name] = {'status': 'FIT_ONLY', 'calibrator': calibrated}
        except (ValueError, ArithmeticError) as exc:
            methods[name] = {'status': 'FIT_REJECTED', 'reason': type(exc).__name__}
    for name, method in methods.items():
        if method['status'] != 'FIT_ONLY':
            continue
        try:
            values = probabilities if name == 'identity' else [apply(method['calibrator'], p) for p in probabilities]
            pairs = list(zip(values, [r['target'] for r in fit]))
            groups = defaultdict(list)
            for row, pair in zip(fit, pairs):
                market = row['market']
                family = '1X2' if market in {'HOME_WIN', 'DRAW', 'AWAY_WIN'} else 'BTTS' if market.startswith('BTTS') else 'TOTAL'
                groups['family:' + family].append(pair)
                groups['market:' + market].append(pair)
            method.update(metrics=probability_metrics(pairs),
                segments={key: probability_metrics(sample) for key, sample in sorted(groups.items())},
                probability_extremes={'min': min(values), 'max': max(values),
                    'below_001': sum(p < .01 for p in values), 'above_099': sum(p > .99 for p in values)},
                probes=[{'raw': p, 'output': p if name == 'identity' else apply(method['calibrator'], p)}
                        for p in (.001, .01, .1, .5, .9, .99, .999)])
            try:
                diagnostic = trainer.fit(_observations(fit, values, model_digest), request)
                method['calibration_slope_intercept'] = {'slope': str(diagnostic.fit_data.a),
                    'intercept': str(diagnostic.fit_data.b), 'regularization': str(diagnostic.fit_data.regularization),
                    'basis': 'REGULARIZED_LOGIT_DIAGNOSTIC_IN_SAMPLE'}
            except (ValueError, ArithmeticError) as exc:
                method['calibration_slope_intercept'] = {'status': 'UNAVAILABLE', 'reason': type(exc).__name__}
        except (ValueError, ArithmeticError) as exc:
            method.update(status='FIT_REJECTED', reason=type(exc).__name__)
            method.pop('calibrator', None)
    methods['isotonic'] = {'status': 'NOT_FITTED', 'minimum_independent_fixtures': MIN_ISOTONIC,
        'reason': 'INSUFFICIENT_SAMPLE_OR_INDEPENDENT_EVALUATION', 'independent_evaluation_used': False}
    manifest = [[r['observation_id'], r['fixture_id'], r['observation_fingerprint']] for r in fit]
    result = {'version': VERSION, 'mode': 'ISOLATED_RESEARCH_FIT_ONLY', 'fitted_at': now.isoformat(),
        'model_generation': champion['generation_id'], 'model_family': artifact['family'],
        'model_artifact_identity': champion['artifact_id'], 'model_document_fingerprint': model_digest,
        'model_artifact_fingerprint': artifact['artifact_fingerprint'], 'feature_schema': FEATURE_SCHEMA,
        'plan_fingerprint': plan.document()['plan_fingerprint'], 'calendar_windows': plan.document()['windows'],
        'dataset_fingerprint': dataset['dataset_fingerprint'], 'fit_manifest': manifest,
        'fit_manifest_fingerprint': digest(manifest), 'fit_observations': len(fit),
        'fit_independent_fixtures': len({r['fixture_id'] for r in fit}),
        'fit_class_counts': {str(y): sum(r['target'] == y for r in fit) for y in (0, 1)},
        'train_manifest_fingerprint': digest([[r['observation_id'], r['observation_fingerprint']] for r in train]),
        'raw_probability_replay': 'EXACT_DECIMAL_PASS', 'methods': methods,
        'metrics_basis': 'CALIBRATION_FIT_IN_SAMPLE_NOT_OUT_OF_SAMPLE',
        'method_selection': None, 'independent_quality_verdict': 'NEEDS_VALIDATION_AND_SEALED_HOLDOUT',
        'validation_rows_used_for_fit': 0, 'holdout_rows_used_for_fit': 0, 'holdout_evaluated': False,
        'production_eligible': False, 'activation_allowed': False, 'promotion_allowed': False,
        'combo_learning_observations': 0, 'provider_calls': 0, 'telegram_sends': 0}
    result['fingerprint'] = digest(result)
    return result
