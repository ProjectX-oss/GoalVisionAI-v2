"""Real quota authorizer + mock HTTP: settlement may consume its own reserve."""
import asyncio
import httpx
import pytest
from app.adaptive_lab.quota import SharedQuota,CATEGORY
from app.football.client import FootballClient
from app.football.quota import FootballQuotaError
from .conftest import START


def run_status(repo, *, category, limit=86, observed=None):
    attempts=[]
    async def run():
        client=FootballClient(api_key='synthetic',request_limit=2)
        await client._client.aclose()
        def response(request):
            claims=repo.all('quota_claims')
            assert claims[-1]['category']==category
            attempts.append(request.url.path)
            return httpx.Response(200,json={'response':[]},headers={
                'x-ratelimit-requests-limit':'7500','x-ratelimit-requests-remaining':'0',
                'x-ratelimit-limit':'300','x-ratelimit-remaining':'299'})
        client._client=httpx.AsyncClient(base_url=client.BASE_URL,transport=httpx.MockTransport(response))
        if observed is not None:client.quota_snapshot=lambda:observed
        shared=SharedQuota(repo,daily_limit=limit)
        shared.bind(client,lambda:START,allow_status_preflight=True,status_preflight_category=category)
        try:await shared.call(category,client.account_status)
        finally:await client.close()
    asyncio.run(run())
    return attempts


def test_settlement_preflight_uses_reserve_and_reserves_before_http(repo):
    assert run_status(repo,category='SETTLEMENT')==['/status']
    assert repo.all('quota_claims')[0]['protected_reserve']==0
    assert CATEGORY.get()=='PREMATCH_DISCOVERY'


def test_status_discovery_still_cannot_use_settlement_reserve(repo):
    with pytest.raises(FootballQuotaError):run_status(repo,category='STATUS')
    assert repo.all('quota_claims')==[]


def test_locally_exhausted_settlement_preflight_is_blocked(repo):
    run_status(repo,category='SETTLEMENT',limit=1)
    with pytest.raises(FootballQuotaError):run_status(repo,category='SETTLEMENT',limit=1)
    assert len(repo.all('quota_claims'))==1


@pytest.mark.parametrize('daily,minute',[(0,300),(7500,0)])
def test_provider_header_limits_are_not_overridden(repo,daily,minute):
    with pytest.raises(FootballQuotaError):
        run_status(repo,category='SETTLEMENT',observed={'interpretation_status':'NORMALIZED',
            'daily_remaining':daily,'minute_remaining':minute})
    assert repo.all('quota_claims')==[]


def test_preflight_does_not_invent_unavailable_provider_quota(repo):
    with pytest.raises(FootballQuotaError):
        run_status(repo,category='SETTLEMENT',observed={'interpretation_status':'UNAVAILABLE'})
    assert repo.all('quota_claims')==[]
