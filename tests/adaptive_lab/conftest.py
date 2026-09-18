from __future__ import annotations
from datetime import datetime, timedelta, timezone
import pytest
from app.adaptive_lab.repository import AuditRepository
from app.adaptive_lab.contracts import digest
from app.adaptive_lab.observations import freeze_observation

START=datetime(2025,1,1,tzinfo=timezone.utc)


def frozen(index: int = 0, *, stream: str = 'PREMATCH', outcome: str = 'WON', probability: float = .6) -> tuple[dict,dict,dict]:
    created=START+timedelta(hours=index*6)
    kickoff=created+timedelta(hours=1) if stream=='PREMATCH' else created-timedelta(hours=1)
    prediction={'prediction_id':f'p-{stream}-{index}','candidate_id':f'c-{stream}-{index}',
        'observation_id':f'c-{stream}-{index}','fixture_id':index+1,'league_id':index%5+1,
        'competition_profile':('SENIOR_MEN','WOMEN','YOUTH')[index%3],
        'kickoff_utc':kickoff.isoformat(),'market':'HOME_WIN','candidate_lane':'EXPERIMENTAL',
        'captured_odds':str(1.9+(index%4)*.1),'ensemble_probability':str(probability),
        'quote_provenance_fingerprint':digest(['quote',stream,index]),
        'provider_origin_timestamp_utc':(created-timedelta(seconds=5)).isoformat(),
        'goalvision_retrieved_at_utc':created.isoformat(),'prepared_at_utc':created.isoformat(),
        'bookmaker_id':1,'bookmaker':'Fictional Test Bookmaker','uncertainty_penalty':.05,
        'predictive_families':['RESULT_HISTORY'],'profile_policy_version':'TEST_POLICY_V1',
        'classifier_version':'TEST_CLASSIFIER_V1','model_generation':'baseline',
        'model_artifact_identity':'fixture-baseline','adaptive_features':{'recent_form':float(index%2),
        'goals_scored':float(index%2)*2,'strength':float(index%2)},'missing_features':['lineup'],
        'calibration_status':'UNCALIBRATED_LAB_ENSEMBLE'}
    if stream=='LIVE':
        prediction.update(live_minute=60,live_score_home=0,live_score_away=0,
                          live_match_state_fingerprint=digest(['state',index]))
    receipt={'status':'SENT','sent':True,'sent_at_utc':(created+timedelta(seconds=1)).isoformat(),
             'message_id':index+1,'chat_id':'-1003510920417'}
    result={'prediction_id':prediction['prediction_id'],'fixture_id':index+1,'market':'HOME_WIN',
            'captured_odds':prediction['captured_odds'],'status':outcome,
            'fulltime_home':2 if outcome=='WON' else 0,'fulltime_away':0 if outcome=='WON' else 1,
            'settled_at_utc':(created+timedelta(hours=3)).isoformat(),'source_fingerprint':digest(['result',index])}
    return prediction,receipt,result


def observation(index: int=0, **kwargs: object) -> dict:
    pred,receipt,result=frozen(index,**kwargs)
    return freeze_observation(pred,receipt,result,stream=kwargs.get('stream','PREMATCH'),publication_id=pred['prediction_id'])


@pytest.fixture
def repo(tmp_path):
    value=AuditRepository(tmp_path/'audit.db')
    yield value
    value.close()
