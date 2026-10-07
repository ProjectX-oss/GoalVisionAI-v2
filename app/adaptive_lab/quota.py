"""Durable shared API quota categories on top of FootballClient's exact-header limits."""
from __future__ import annotations
from contextvars import ContextVar
from datetime import datetime, timedelta
from uuid import uuid4
import asyncio
import json
import sqlite3
import sys
import time
from contextlib import contextmanager
from typing import Callable, Iterator
from .prepared import PreparedAudit, AuditSnapshotChanged
from .contracts import digest, utc
from .repository import AuditRepository
from app.football.quota import FootballQuotaError
from . import daypart

CATEGORY = ContextVar('goalvision_quota_category', default='PREMATCH_DISCOVERY')
RESERVES = {'SETTLEMENT':150,'PREMATCH_REVIEW':300,'LIVE_STATE':200,'LIVE_ODDS':300,'LIVE_REFRESH':200}
LIVE_DAILY_CAP = 1800
CATEGORIES = frozenset({*RESERVES, 'PREMATCH_DISCOVERY', 'STATUS', 'LIVE_SETTLEMENT'})
QUOTA_VERSION = 'LAB_SHARED_QUOTA_V1'


CONTENTION_WINDOW_SECONDS = 0.5
CONTENTION_INTERVAL_SECONDS = 0.025


class QuotaDBContentionError(RuntimeError):
    """Fail closed before HTTP; the fixed code is safe for incident monitoring."""
    code = 'QUOTA_DB_CONTENTION_EXHAUSTED'

    def __init__(self) -> None:
        super().__init__(self.code)


class SharedQuota:
    """One shared audit DB across workers. Consume durable slots before each HTTP attempt."""
    def __init__(self, repository: AuditRepository, *, daily_limit: int = 7500, minute_limit: int = 300) -> None:
        if not 1<=daily_limit<=7500 or not 1<=minute_limit<=300:
            raise ValueError('INVALID_QUOTA_LIMIT')
        self.repository,self.daily_limit,self.minute_limit=repository,daily_limit,minute_limit

    def claim(self, category: str, *, now: datetime, provider: dict) -> dict:
        """Synchronous local-only reservation with a single bounded retry budget."""
        started = time.monotonic()
        attempt = 0
        while True:
            if attempt and time.monotonic() - started >= CONTENTION_WINDOW_SECONDS:
                self._retry_delay(category, attempt, started, stage)
            attempt += 1
            result, stage = self._attempt(category, now=now, provider=provider)
            if result is not None:
                return result
            delay = self._retry_delay(category, attempt, started, stage)
            time.sleep(delay)

    async def claim_async(self, category: str, *, clock: Callable[[], datetime],
                          provider: Callable[[], dict]) -> dict:
        """Cancellation-friendly reservations; this loop has no HTTP capability."""
        started = time.monotonic()
        attempt = 0
        while True:
            await asyncio.sleep(0)  # Honor pending shutdown before reserving a slot.
            if attempt and time.monotonic() - started >= CONTENTION_WINDOW_SECONDS:
                self._retry_delay(category, attempt, started, stage)
            attempt += 1
            result, stage = self._attempt(category, now=clock(), provider=provider())
            if result is not None:
                return result
            await asyncio.sleep(self._retry_delay(category, attempt, started, stage))

    def _retry_delay(self, category: str, attempt: int, started: float, stage: str) -> float:
        elapsed = time.monotonic() - started
        exhausted = elapsed >= CONTENTION_WINDOW_SECONDS
        code = 'QUOTA_DB_CONTENTION_EXHAUSTED' if exhausted else 'QUOTA_DB_CONTENTION_RETRY'
        # One JSON line; fixed vocabulary only, no SQLite text/SQL/provider values.
        print(json.dumps({'code': code, 'attempt': attempt,
                          'elapsed_ms': min(round(elapsed * 1000), 2147483647),
                          'category': category if category in CATEGORIES else 'INVALID',
                          'stage': stage}, sort_keys=True), file=sys.stderr)
        if exhausted:
            raise QuotaDBContentionError() from None
        return min(CONTENTION_INTERVAL_SECONDS, CONTENTION_WINDOW_SECONDS - elapsed)

    @contextmanager
    def _nonblocking(self) -> Iterator[None]:
        connection = self.repository.connection
        if connection.in_transaction:
            raise ValueError('QUOTA_REQUIRES_OWN_DURABLE_TRANSACTION')
        previous = connection.execute('PRAGMA busy_timeout').fetchone()[0]
        connection.execute('PRAGMA busy_timeout=0')
        try:
            yield
        finally:
            connection.execute(f'PRAGMA busy_timeout={previous}')

    def _attempt(self, category: str, *, now: datetime, provider: dict) -> tuple[dict | None, str]:
        stage = {'value': 'READ'}
        committed = False
        try:
            with self._nonblocking():
                result = self._claim_once(category, now=now, provider=provider, stage=stage)
                committed = True
            return result, stage['value']
        except AuditSnapshotChanged:
            return None, 'VALIDATE'
        except sqlite3.OperationalError as error:
            # Extended result codes retain the primary code in the low byte.
            if (getattr(error, 'sqlite_errorcode', 0) & 0xff) not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise
            if committed or self.repository.connection.in_transaction:
                # Never retry a completed or unconfirmed rollback/commit outcome.
                raise
            return None, stage['value']

    def _claim_once(self, category: str, *, now: datetime, provider: dict, stage: dict[str, str]) -> dict:
        if category not in CATEGORIES:
            raise ValueError('UNKNOWN_QUOTA_CATEGORY')
        if provider.get('interpretation_status')!='NORMALIZED':
            raise FootballQuotaError('QUOTA_UNAVAILABLE')
        for key in ('daily_remaining','minute_remaining'):
            if type(provider.get(key)) is not int or provider[key]<0:
                raise FootballQuotaError('QUOTA_UNAVAILABLE')
        clock=utc(now)
        batch = PreparedAudit(self.repository)
        with batch.transaction():
            # Include the prior minute across UTC midnight. Filtering below keeps
            # the exact existing day/minute policy, including future same-day claims.
            since = clock.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=60)
            claims=batch.quota_since(since.isoformat())
            today=[r for r in claims if utc(r['created_at']).date()==clock.date()]
            recent=[r for r in claims if clock-timedelta(seconds=60)<utc(r['created_at'])<=clock]
            live=sum(r['category'].startswith('LIVE_') for r in today)
            reserve = (100 if category in {'PREMATCH_DISCOVERY', 'PREMATCH_REVIEW', 'STATUS'}
                       else 0 if category == 'SETTLEMENT'
                       else sum(v for k, v in RESERVES.items() if k != category))
            evening = daypart.enabled()
            if evening:
                if category in {'PREMATCH_DISCOVERY', 'PREMATCH_REVIEW', 'STATUS'}:
                    local = clock.astimezone(daypart.RIGA)
                    if not 10 <= local.hour < 18:
                        raise FootballQuotaError('PREMATCH_DISCOVERY_WINDOW_CLOSED')
                    reserve = daypart.prematch_discovery_reserve(clock)
                elif category.startswith('LIVE_'):
                    if category != 'LIVE_SETTLEMENT' and not daypart.live_window(clock):
                        raise FootballQuotaError('LIVE_DISCOVERY_WINDOW_CLOSED')
                    reserve = daypart.prematch_results_reserve(clock)
            if not evening and category.startswith('LIVE_') and live>=LIVE_DAILY_CAP:
                raise FootballQuotaError('LIVE_DAILY_CAP')
            available=min(self.daily_limit-len(today),provider['daily_remaining'])
            minute=min(self.minute_limit-len(recent),provider['minute_remaining'])
            if available-1<reserve or minute<1:
                raise FootballQuotaError('PROTECTED_QUOTA_RESERVE')
            value={'category':category,'created_at':clock.isoformat(),'remaining_daily_before':available,
                   'remaining_minute_before':minute,'protected_reserve':reserve,'policy_version':'LAB_SHARED_EVENING_QUOTA_V1' if evening else QUOTA_VERSION}
            batch.append('quota_claims',str(uuid4()),'LIVE' if category.startswith('LIVE_') else 'PREMATCH',value,clock.isoformat())
            stage['value'] = 'RESERVE_COMMIT'
            batch.commit()
            return value

    async def call(self, category: str, operation: object, *args: object, **kwargs: object) -> object:
        """Propagate category through retries via the client's request authorizer."""
        token=CATEGORY.set(category)
        try:
            return await operation(*args,**kwargs)
        finally:
            CATEGORY.reset(token)

    def bind(self, client: object, clock: object, *, allow_status_preflight: bool = False,
             status_preflight_category: str = 'STATUS') -> None:
        """Bind before work to an already quota-verified client; never fetches on binding."""
        if status_preflight_category not in {'STATUS', 'SETTLEMENT', 'LIVE_SETTLEMENT'}:
            raise ValueError('INVALID_STATUS_PREFLIGHT_CATEGORY')
        def provider_snapshot() -> dict:
            provider=client.quota_snapshot()
            if allow_status_preflight and CATEGORY.get()==status_preflight_category and provider.get('interpretation_status')=='NOT_OBSERVED':
                # Reserve a local slot before the initial status attempt. Actual
                # provider headers govern every following request, including retries.
                provider={'interpretation_status':'NORMALIZED','daily_remaining':self.daily_limit,
                          'minute_remaining':self.minute_limit}
            return provider

        async def authorize() -> None:
            await self.claim_async(CATEGORY.get(), clock=clock, provider=provider_snapshot)
        client.request_authorizer=authorize
