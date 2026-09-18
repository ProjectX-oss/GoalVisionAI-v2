"""Bounded explicit LIVE scan/refresh/settlement; injected provider and shared quota."""
from __future__ import annotations
from datetime import datetime
from typing import Callable
from app.adaptive_lab.contracts import digest, utc
from app.adaptive_lab.quota import SharedQuota
from .engine import state_snapshot, attach_events
from .provider import normalize_quotes, history_rates
from .policy import POLICY
from .service import LiveService


class LiveRunner:
    def __init__(self, service: LiveService, client: object, quota: SharedQuota, *,
                 clock: Callable[[],datetime]) -> None:
        self.service,self.client,self.quota,self.clock=service,client,quota,clock
        quota.bind(client,clock)

    async def refresh(self, fixture_id: int) -> tuple[dict,list[dict],dict]:
        payload=await self.quota.call('LIVE_REFRESH',self.client.fixture,fixture_id)
        rows=payload.get('response')
        if payload.get('errors') or not isinstance(rows,list) or len(rows)!=1 or rows[0].get('fixture',{}).get('id')!=fixture_id:
            raise ValueError('LIVE_FIXTURE_UNAVAILABLE')
        state=state_snapshot(rows[0],retrieved_at=self.clock())
        events=await self.quota.call('LIVE_STATE',self.client.events,fixture_id)
        state=attach_events(state,events,retrieved_at=self.clock())
        # Existing client/cache governs requests; no historical bookmaker prices.
        home=await self.quota.call('LIVE_STATE',self.client.last_matches,state['home_team_id'],last=10)
        away=await self.quota.call('LIVE_STATE',self.client.last_matches,state['away_team_id'],last=10)
        rates=history_rates(state,home,away,retrieved_at=self.clock())
        catalog=await self.quota.call('LIVE_ODDS',self.client.live_bets)
        catalog={**catalog,'endpoint':'/odds/live/bets'}
        odds=await self.quota.call('LIVE_REFRESH',self.client.live_odds,fixture_id)
        quotes,reasons=normalize_quotes(odds,state,catalog,retrieved_at=self.clock())
        if reasons:
            self._diagnostic(fixture_id,reasons)
        return state,quotes,rates

    async def scan(self) -> dict:
        prepared=[]
        try:
            payload=await self.quota.call('LIVE_STATE',self.client.live_fixtures)
            if payload.get('errors'):
                raise ValueError('LIVE_DISCOVERY_UNAVAILABLE')
            rows=payload.get('response') or []
        except Exception:
            return {'status':'LIVE_DISCOVERY_UNAVAILABLE','candidates':[]}
        for row in sorted(rows,key=lambda r:r.get('fixture',{}).get('id',0))[:POLICY.max_fixtures_per_scan]:
            identity=row.get('fixture',{}).get('id')
            try:
                state_snapshot(row,retrieved_at=self.clock())
                state,quotes,rates=await self.refresh(identity)
                self.service.repository.append('live_snapshots',state['state_fingerprint'],'LIVE',state,state['retrieved_at'])
                markets=set()
                for quote in quotes:
                    if quote['market'] in markets:
                        continue
                    markets.add(quote['market'])
                    candidate=self.service.candidate(state,quote,rates,now=self.clock())
                    prepared.append(candidate)
            except Exception:
                self._diagnostic(identity,['LIVE_FIXTURE_REVIEW_UNAVAILABLE'])
        return {'status':'LIVE_SCAN_COMPLETE','candidates':prepared}

    async def settle(self) -> list[str]:
        completed=[]
        cache={}
        for receipt in self.service.repository.all('live_publications','LIVE'):
            identity=receipt['selection_id']
            if self.service.repository.get('live_settlements',identity):
                continue
            candidate=self.service.repository.get('live_candidates',identity)
            fid=candidate['fixture_id']
            try:
                if fid not in cache:
                    if len(cache)>=POLICY.max_fixtures_per_scan:
                        break
                    cache[fid]=await self.quota.call('SETTLEMENT',self.client.fixture,fid)
                if self.service.settle(identity,cache[fid],now=self.clock()):
                    completed.append(identity)
            except Exception:
                self._diagnostic(fid,['LIVE_SETTLEMENT_UNAVAILABLE'])
        # Shadow opportunities have no publication receipt and are never added to
        # product statistics. Their final fixture evidence uses the same result API.
        for pred in self.service.repository.all('shadow_predictions'):
            if self.service.repository.get('shadow_settlements', pred['prediction_id']):
                continue
            row=pred['frozen_opportunity']
            if utc(self.clock()) <= utc(row['kickoff_utc']):
                continue
            fid=row['fixture_id']
            try:
                if fid not in cache:
                    if len(cache)>=POLICY.max_fixtures_per_scan:
                        break
                    cache[fid]=await self.quota.call('SETTLEMENT',self.client.fixture,fid)
                self.service.governance.settle_shadow_result(pred['prediction_id'],cache[fid],now=self.clock())
            except Exception:
                self._diagnostic(fid,['SHADOW_SETTLEMENT_UNAVAILABLE'])
        return completed

    def _diagnostic(self, fixture_id: int, reasons: list[str]) -> None:
        value={'fixture_id':fixture_id,'reasons':reasons,'created_at':utc(self.clock()).isoformat()}
        self.service.repository.append('live_diagnostics',digest(value),'LIVE',value,value['created_at'])
