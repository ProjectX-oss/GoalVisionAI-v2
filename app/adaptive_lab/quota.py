"""Durable shared API quota categories on top of FootballClient's exact-header limits."""
from __future__ import annotations
from contextvars import ContextVar
from datetime import datetime, timedelta
from uuid import uuid4
from .contracts import digest, utc
from .repository import AuditRepository
from app.football.quota import FootballQuotaError

CATEGORY = ContextVar('goalvision_quota_category', default='PREMATCH_DISCOVERY')
RESERVES = {'SETTLEMENT':150,'PREMATCH_REVIEW':300,'LIVE_STATE':200,'LIVE_ODDS':300,'LIVE_REFRESH':200}
LIVE_DAILY_CAP = 1800
QUOTA_VERSION = 'LAB_SHARED_QUOTA_V1'


class SharedQuota:
    """One shared audit DB across workers. Consume durable slots before each HTTP attempt."""
    def __init__(self, repository: AuditRepository, *, daily_limit: int = 7500, minute_limit: int = 300) -> None:
        if not 1<=daily_limit<=7500 or not 1<=minute_limit<=300:
            raise ValueError('INVALID_QUOTA_LIMIT')
        self.repository,self.daily_limit,self.minute_limit=repository,daily_limit,minute_limit

    def claim(self, category: str, *, now: datetime, provider: dict) -> dict:
        if category not in {*RESERVES,'PREMATCH_DISCOVERY','STATUS'}:
            raise ValueError('UNKNOWN_QUOTA_CATEGORY')
        if provider.get('interpretation_status')!='NORMALIZED':
            raise FootballQuotaError('QUOTA_UNAVAILABLE')
        for key in ('daily_remaining','minute_remaining'):
            if type(provider.get(key)) is not int or provider[key]<0:
                raise FootballQuotaError('QUOTA_UNAVAILABLE')
        clock=utc(now)
        with self.repository.transaction():
            # Include the prior minute across UTC midnight. Filtering below keeps
            # the exact existing day/minute policy, including future same-day claims.
            since = clock.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=60)
            claims=self.repository.quota_since(since.isoformat())
            today=[r for r in claims if utc(r['created_at']).date()==clock.date()]
            recent=[r for r in claims if clock-timedelta(seconds=60)<utc(r['created_at'])<=clock]
            live=sum(r['category'].startswith('LIVE_') for r in today)
            reserve = (100 if category in {'PREMATCH_DISCOVERY', 'PREMATCH_REVIEW', 'STATUS'}
                       else 0 if category == 'SETTLEMENT'
                       else sum(v for k, v in RESERVES.items() if k != category))
            if category.startswith('LIVE_') and live>=LIVE_DAILY_CAP:
                raise FootballQuotaError('LIVE_DAILY_CAP')
            available=min(self.daily_limit-len(today),provider['daily_remaining'])
            minute=min(self.minute_limit-len(recent),provider['minute_remaining'])
            if available-1<reserve or minute<1:
                raise FootballQuotaError('PROTECTED_QUOTA_RESERVE')
            value={'category':category,'created_at':clock.isoformat(),'remaining_daily_before':available,
                   'remaining_minute_before':minute,'protected_reserve':reserve,'policy_version':QUOTA_VERSION}
            self.repository.append('quota_claims',str(uuid4()),'LIVE' if category.startswith('LIVE_') else 'PREMATCH',value,clock.isoformat())
            return value

    async def call(self, category: str, operation: object, *args: object, **kwargs: object) -> object:
        """Propagate category through retries via the client's request authorizer."""
        token=CATEGORY.set(category)
        try:
            return await operation(*args,**kwargs)
        finally:
            CATEGORY.reset(token)

    def bind(self, client: object, clock: object, *, allow_status_preflight: bool = False) -> None:
        """Bind before work to an already quota-verified client; never fetches on binding."""
        def authorize() -> None:
            provider=client.quota_snapshot()
            if allow_status_preflight and CATEGORY.get()=='STATUS' and provider.get('interpretation_status')=='NOT_OBSERVED':
                # Reserve a local slot before the initial status attempt. Actual
                # provider headers govern every following request, including retries.
                provider={'interpretation_status':'NORMALIZED','daily_remaining':self.daily_limit,
                          'minute_remaining':self.minute_limit}
            self.claim(CATEGORY.get(),now=clock(),provider=provider)
        client.request_authorizer=authorize
