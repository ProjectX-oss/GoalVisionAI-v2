"""Raw provider zero reaches the real runner's immutable rejected candidate."""
from test_final_review_queue import QueueClient, cycle, row, Response
from test_lab_v2_shadow import coverage


def test_runner_persists_distinct_zero_reason_without_probability_clamp(tmp_path, monkeypatch):
    original=QueueClient._get
    async def leagues(self, *, current=True):
        league_id=next(iter(self.rows.values()))['league']['id']
        return self._hit('/leagues',{}, {'response':[coverage(league_id=league_id, predictions=True)]})
    async def get(self, endpoint, *, params):
        if endpoint!='/predictions':return await original(self,endpoint,params=params)
        fixture=self.rows[int(params['fixture'])]
        payload={'parameters':{'fixture':params['fixture']},'response':[{
            'teams':fixture['teams'],'league':fixture['league'],
            'predictions':{'percent':{'home':'0%','draw':'50%','away':'50%'}}}]}
        return Response(self._hit(endpoint,params,payload))
    monkeypatch.setattr(QueueClient,'_get',get)
    monkeypatch.setattr(QueueClient,'leagues',leagues)
    report,_=cycle(tmp_path,monkeypatch,[row(7)])
    zeros=[r for r in report['candidate_markets'] if 'PROVIDER_ZERO_PROBABILITY' in r['rejection_reasons']]
    assert zeros
    for value in zeros:
        assert value['decision']=='REJECTED' and value['candidate_lane']=='REJECTED'
        assert value['provider_zero_probability_evidence']['fixture_id']==7
        assert value['provider_zero_probability_evidence']['raw_provider_probability']=='0%'
        assert 'INVALID_MODEL_PROBABILITY' not in value['rejection_reasons']
        assert float(value['ensemble_probability'])==0
