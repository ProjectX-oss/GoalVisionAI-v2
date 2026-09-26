"""Read-only PREMATCH evidence adapter and conservative per-attempt LIVE governor."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import math
import re
import subprocess
from pathlib import Path
import sqlite3
from typing import Callable

from .contracts import digest, fresh, integer, utc
from .schedule import RIGA, prematch_remaining
from .store import Store

LIVE_MAX_CALLS_PER_DAY = 40
MAX_CALLS_PER_OPPORTUNITY = 5
DAILY_LIMIT = 7500
MINUTE_LIMIT = 300
SAFETY_MARGIN = 375


def distribution(values: list[int]) -> dict:
    ordered = sorted(values)
    return {'count': len(values), 'total': sum(values), 'min': min(values, default=None),
            'median': ordered[len(ordered)//2] if ordered else None,
            'p95': ordered[math.ceil(len(ordered)*.95)-1] if ordered else None,
            'max': max(values, default=None)}


def installed_contract() -> dict:
    """Read active systemd configuration; reject drift in schedule or missing call ceiling."""
    try:
        service = subprocess.run(['systemctl', 'show', 'goalvision-lab-v2-discover.service',
                                  '--property=ExecStart', '--value'], capture_output=True, text=True,
                                 timeout=3, check=True).stdout
        timer = subprocess.run(['systemctl', 'show', 'goalvision-lab-v2-discover.timer',
                                '--property=TimersCalendar', '--value'], capture_output=True, text=True,
                               timeout=3, check=True).stdout
        limits = re.findall(r'--max-calls (\d+)', service)
        verified = len(limits) == 1 and timer.count('OnCalendar=') == 1 and 'OnCalendar=*-*-* 09..22:00,30:00 Europe/Riga ;' in timer
        return {'verified': verified, 'cycle_ceiling': int(limits[0]) if len(limits) == 1 else None,
                'configuration_fingerprint': digest([service.split(' ; start_time=')[0], timer.split(' ; next_elapse=')[0]])}
    except (OSError, subprocess.SubprocessError):
        return {'verified': False, 'cycle_ceiling': None}


def read_prematch(path: Path, now: datetime) -> dict:
    """Inspect retained audit rows via mode=ro. No imports of PREMATCH services."""
    clock = utc(now)
    since = (clock - timedelta(days=7)).isoformat()
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=2) as db:
        db.execute('PRAGMA query_only=ON')
        cycles = [json.loads(r[0]) for r in db.execute(
            "SELECT document FROM cycle_health WHERE stream='PREMATCH' AND created_at>=? ORDER BY created_at", (since,))]
        claims = [json.loads(r[0]) for r in db.execute(
            "SELECT document FROM quota_claims WHERE stream='PREMATCH' AND created_at>=? ORDER BY created_at", (since,))]
    cycles = [c for c in cycles if utc(c['completed_at']) <= clock and integer(c.get('provider_calls'))]
    claims = [c for c in claims if utc(c['created_at']) <= clock]
    recent = [c for c in cycles if utc(c['completed_at']) >= clock - timedelta(days=1)]
    recent_claims = [c for c in claims if utc(c['created_at']) >= clock - timedelta(days=1)]
    daily_settlements: dict[str, int] = {}
    for claim in claims:
        if claim['category'] == 'SETTLEMENT':
            day = utc(claim['created_at']).date().isoformat()
            daily_settlements[day] = daily_settlements.get(day, 0) + 1
    last = claims[-1] if claims else {}
    return {'source': 'PREMATCH_READ_ONLY_AUDIT', 'installed_contract': installed_contract(), 'observed_at': clock.isoformat(),
            'cycle_24h': distribution([c['provider_calls'] for c in recent]),
            'cycle_7d': distribution([c['provider_calls'] for c in cycles]),
            'cycle_active_24h': distribution([c['provider_calls'] for c in recent if c['provider_calls'] > 1]),
            'cycle_active_7d': distribution([c['provider_calls'] for c in cycles if c['provider_calls'] > 1]),
            'earliest_retained_cycle_in_window': cycles[0]['completed_at'] if cycles else None,
            'earliest_retained_claim_in_window': claims[0]['created_at'] if claims else None,
            'claims_24h': len(recent_claims), 'claims_7d': len(claims),
            'settlement_24h': sum(c['category'] == 'SETTLEMENT' for c in recent_claims),
            'settlement_7d': sum(c['category'] == 'SETTLEMENT' for c in claims),
            'settlement_max_utc_day': max(daily_settlements.values(), default=0),
            'status_24h': sum(c['category'] == 'STATUS' for c in recent_claims),
            'latest_cycle_at': cycles[-1]['completed_at'] if cycles else None,
            'last_claim_at': last.get('created_at'),
            'daily_remaining_upper_bound': max(0, last.get('remaining_daily_before', 1)-1),
            'minute_remaining_upper_bound': max(0, last.get('remaining_minute_before', 1)-1),
            'remaining_prematch_cycles': prematch_remaining(clock),
            'future_scheduled_prematch_cycles': prematch_remaining(clock, include_current=False),
            # Retained claims are pre-request evidence, not fresh exact response headers.
            'provider_headers_verified': False,
            # Existing producers do not participate in a LIVE-owned cross-worker permit.
            'shared_token_exclusive_until': None}


def budget(evidence: dict, *, now: datetime, daily_calls: int, slot_calls: int,
           minute_calls: int = 0) -> dict:
    """Prove capacity from fresh evidence; missing evidence has a zero-call fallback."""
    recent = evidence.get('cycle_24h', {})
    maximum = recent.get('max')
    installed = evidence.get('installed_contract', {})
    reliable = (integer(recent.get('count'), 8) and integer(maximum, 1)
                and fresh(evidence.get('latest_cycle_at'), now, 3600)
                and installed.get('verified') is True and integer(installed.get('cycle_ceiling'), 1, 7500))
    per_cycle = max(installed['cycle_ceiling'], math.ceil(maximum * 1.2)) if reliable else None
    result_reserve = math.ceil(max(100, evidence.get('settlement_24h', 0),
                                  evidence.get('settlement_max_utc_day', 0)) * 1.2)
    cycles = prematch_remaining(now)
    protected = cycles * per_cycle + result_reserve + SAFETY_MARGIN if reliable else None
    daily = evidence.get('daily_remaining_upper_bound', 0)
    minute = evidence.get('minute_remaining_upper_bound', 0)
    reasons = []
    if not reliable:
        reasons.append('INSUFFICIENT_RECENT_PREMATCH_EVIDENCE')
    if not evidence.get('provider_headers_verified') or not fresh(evidence.get('last_claim_at'), now, 60):
        reasons.append('FRESH_PROVIDER_QUOTA_REQUIRED')
    lease = evidence.get('shared_token_exclusive_until')
    if not lease or not (0 < (utc(lease) - utc(now)).total_seconds() <= 60):
        reasons.append('SHARED_TOKEN_CONCURRENCY_UNPROVEN')
    if not integer(daily, 0, DAILY_LIMIT) or not integer(minute, 0, MINUTE_LIMIT):
        reasons.append('INVALID_QUOTA_EVIDENCE')
        daily, minute = 0, 0
    capacity = min(40-daily_calls, 5-slot_calls, 300-minute_calls, minute,
                   max(0, daily - protected) if protected is not None else 0)
    if capacity <= 0:
        reasons.append('PROTECTED_CAPACITY_EXHAUSTED')
    return {'version': 'LIVE_PREMATCH_FIRST_QUOTA_V1', 'status': 'QUOTA_RESERVED_FOR_PREMATCH' if reasons else 'SAFE',
            'safe_calls': 0 if reasons else capacity, 'reasons': reasons,
            'per_cycle_protected': per_cycle, 'remaining_cycles': cycles,
            'settlement_reserve': result_reserve, 'safety_margin': SAFETY_MARGIN,
            'protected_remaining_requirement': protected,
            'protected_full_day_requirement': 28*per_cycle+result_reserve+SAFETY_MARGIN if per_cycle else None,
            'median_projected_full_day_requirement': (28*recent['median']+result_reserve+SAFETY_MARGIN
                if integer(recent.get('median')) else None),
            'observed_daily_remaining': daily, 'observed_minute_remaining': minute,
            'live_daily_calls': daily_calls, 'live_opportunity_calls': slot_calls,
            'evidence': evidence}


@dataclass
class Governor:
    """Durable reservation before *every* attempted call, including failed calls."""
    store: Store
    evidence: Callable[[datetime], dict]

    def inspect(self, slot: str, now: datetime) -> dict:
        clock = utc(now)
        claims = self.store.all('api_claim')
        daily = sum(utc(c['at']).date() == clock.date() or
                    utc(c['at']).astimezone(RIGA).date() == clock.astimezone(RIGA).date() for c in claims)
        minute = sum(0 <= (clock-utc(c['at'])).total_seconds() < 60 for c in claims)
        evidence = dict(self.evidence(clock))
        if claims:
            last = max(claims, key=lambda c: c['attempt'])
            key = digest(last)
            failed = self.store.get('api_failure', key)
            response = self.store.get('api_response', key)
            if failed:
                evidence['provider_headers_verified'] = False
            if response:
                observed = response['quota']
                if (observed.get('interpretation_status') != 'NORMALIZED'
                    or not integer(observed.get('daily_remaining'), 0, DAILY_LIMIT)
                    or not integer(observed.get('minute_remaining'), 0, MINUTE_LIMIT)):
                    evidence['provider_headers_verified'] = False
                else:
                    # New observations may reduce capacity; cannot authorize concurrency
                    # or retroactively make stale PREMATCH evidence trustworthy.
                    for field, provider_field in (('daily_remaining_upper_bound', 'daily_remaining'),
                                                   ('minute_remaining_upper_bound', 'minute_remaining')):
                        evidence[field] = min(evidence.get(field, 0), observed[provider_field])
        stamp = evidence.get('last_claim_at')
        unobserved = sum(utc(c['at']) >= utc(stamp) for c in claims) if stamp else len(claims)
        for field in ('daily_remaining_upper_bound', 'minute_remaining_upper_bound'):
            if integer(evidence.get(field)):
                evidence[field] = max(0, evidence[field]-unobserved)
        return budget(evidence, now=clock, daily_calls=daily,
                      slot_calls=sum(c['slot'] == slot for c in claims), minute_calls=minute)

    def claim(self, slot: str, endpoint: str, query: dict, now: datetime) -> str | None:
        with self.store.transaction():
            decision = {**self.inspect(slot, now), 'at': utc(now).isoformat(), 'slot': slot,
                        'endpoint': endpoint, 'query': query}
            identity = digest(decision)
            self.store.append('quota_decision', identity, decision, now)
            if not decision['safe_calls']:
                return None
            claim = {'at': utc(now).isoformat(), 'slot': slot, 'endpoint': endpoint, 'query': query,
                     'quota_decision': identity, 'attempt': len(self.store.all('api_claim')) + 1}
            key = digest(claim)
            self.store.append('api_claim', key, claim, now, ('quota_decision', identity))
            return key
