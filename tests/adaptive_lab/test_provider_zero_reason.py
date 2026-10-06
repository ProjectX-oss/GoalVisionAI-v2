from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from app.lab_v2_shadow.api_prediction import normalize_api_prediction
from app.lab_v2_shadow.global_evaluation import evaluate_profile, provider_probability_diagnostic
from app.lab_v2_shadow.profiles import policy_for
from .test_prematch_probability_guard import signals


def evaluated():
    api=normalize_api_prediction({'response':[{'predictions':{
        'percent':{'home':'0%','draw':'50%','away':'50%'}}}]},fixture_id=1639967)
    d,e=evaluate_profile('HOME_WIN',Decimal('15'),signals('HOME_WIN',Decimal(0)),
                         policy_for('INTERNATIONAL_SENIOR'),(),fixture_id=1639967)
    return api,d,e


def test_zero_reason_preserves_endpoint_and_downstream_rejection():
    api,d,e=evaluated()
    result,trace=provider_probability_diagnostic(d,e,api,fixture_id=1639967,market='HOME_WIN',
                                               now=datetime(2026,10,6,tzinfo=timezone.utc))
    assert result.ensemble_probability==d.ensemble_probability==0
    assert result.decision==d.decision=='REJECTED'
    assert result.edge==d.edge and trace['candidate_lane']=='REJECTED'
    assert 'PROVIDER_ZERO_PROBABILITY' in result.rejection_reasons
    assert 'INVALID_MODEL_PROBABILITY' not in result.rejection_reasons
    assert 'PROVIDER_ZERO_PROBABILITY' in trace['hard_failures']
    assert trace['provider_zero_probability_evidence']['raw_provider_probability']=='0%'
    assert trace['provider_zero_probability_evidence']['source_fingerprint']==api.source_fingerprint
    assert trace['provider_zero_probability_evidence']['observed_at_utc']=='2026-10-06T00:00:00+00:00'


@pytest.mark.parametrize('case',['missing_raw','nonzero_raw','wrong_fixture','other_producer','unknown_source','nonfinite'])
def test_unproven_provider_cause_keeps_generic_guard(case):
    api,d,e=evaluated()
    if case=='missing_raw':api=replace(api,raw_provider_probabilities=None)
    if case=='nonzero_raw':api=replace(api,raw_provider_probabilities={'HOME_WIN':'1%'})
    if case=='wrong_fixture':api=replace(api,fixture_id=9)
    if case=='other_producer':e['predictive_families']=['OTHER_MODEL']
    if case=='unknown_source':api=replace(api,source_fingerprint=None)
    if case=='nonfinite':d=replace(d,ensemble_probability=Decimal('NaN'))
    result,trace=provider_probability_diagnostic(d,e,api,fixture_id=1639967,market='HOME_WIN',
                                               now=datetime.now(timezone.utc))
    assert 'INVALID_MODEL_PROBABILITY' in result.rejection_reasons
    assert 'provider_zero_probability_evidence' not in trace
