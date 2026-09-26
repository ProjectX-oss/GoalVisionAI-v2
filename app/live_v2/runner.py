"""One discovery and useful details for one fixture, always no-send."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from .contracts import digest, utc
from .markets import normalize
from .policy import evaluate
from .provider import Transport
from .quota import Governor
from .schedule import opportunity
from .state import features, shortlist
from .store import Store


class Runner:
    """Dependency-injected transport and clock; LIVE documents own all side effects."""
    def __init__(self, store: Store, governor: Governor, transport: Transport,
                 mapping: dict, competitions: frozenset[int], *,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 contexts: dict[int, dict] | None = None) -> None:
        self.store, self.governor, self.transport = store, governor, transport
        self.mapping, self.competitions, self.clock = mapping, competitions, clock
        self.contexts = contexts or {}

    def run(self, *, rehearsal: bool = False) -> dict:
        """Rehearsal consumes the nearest slot budget; one lifetime rehearsal per store."""
        now = self.clock()
        slot = opportunity(now)
        if rehearsal:
            # A rehearsal cannot create a ninth daily allowance or escape daily caps.
            from .schedule import opportunities, RIGA
            slots = opportunities(utc(now).astimezone(RIGA).date())
            slot = min(slots, key=lambda s: abs((utc(s)-utc(now)).total_seconds())).isoformat()
        if slot is None:
            self.store.append('schedule_skip', digest(now.isoformat()),
                              {'at': now.isoformat(), 'status': 'OUTSIDE_LIVE_SCHEDULE'}, now)
            return {'status': 'OUTSIDE_LIVE_SCHEDULE', 'api_calls': 0, 'telegram_sends': 0}
        with self.store.opportunity_lock():
            if self.store.get('opportunity', slot) or (rehearsal and self.store.all('rehearsal')):
                return {'status': 'OPPORTUNITY_ALREADY_CLAIMED', 'api_calls': 0, 'telegram_sends': 0}
            self.store.append('opportunity', slot, {'slot': slot, 'at': now.isoformat(), 'rehearsal': rehearsal}, now)
            try:
                report = self._discover(slot)
            except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
                report = {'status': 'INVALID_LIVE_EVIDENCE', 'candidate_qualified': False,
                          'api_calls': sum(c['slot'] == slot for c in self.store.all('api_claim'))}
                self.store.append('rejection', slot, report, self.clock(), ('opportunity', slot))
            report.update(slot=slot, telegram_sends=0)
            self.store.append('run', slot, report, self.clock(), ('opportunity', slot))
            if rehearsal:
                self.store.append('rehearsal', 'bounded-real-api', report, self.clock(), ('run', slot))
            return report

    def _call(self, slot: str, endpoint: str, query: dict) -> tuple[dict, datetime, dict] | None:
        key = self.governor.claim(slot, endpoint, query, self.clock())
        if not key:
            return None
        try:
            payload, quota = self.transport.get(endpoint, query)
            at = self.clock()
            if payload.get('errors') or not isinstance(payload.get('response'), list):
                raise ValueError
            evidence = {'at': at.isoformat(), 'endpoint': endpoint, 'query': query,
                        'quota': quota, 'payload': payload, 'source_fingerprint': digest(payload)}
            self.store.append('api_response', key, evidence, at, ('api_claim', key))
            return payload, at, quota
        except Exception:
            self.store.append('api_failure', key, {'status': 'CURRENT_REQUEST_FAILED', 'endpoint': endpoint},
                              self.clock(), ('api_claim', key))
            return None  # Never fall back to prior odds, even after a timeout.

    def _discover(self, slot: str) -> dict:
        def finish(status: str, **fields: object) -> dict:
            return {'status': status, 'api_calls': sum(c['slot'] == slot for c in self.store.all('api_claim')),
                    'candidate_qualified': False, **fields}
        discovery = self._call(slot, '/fixtures', {'live': 'all'})
        if discovery is None:
            return finish('QUOTA_RESERVED_FOR_PREMATCH' if not any(c['slot'] == slot for c in self.store.all('api_claim')) else 'DISCOVERY_UNAVAILABLE')
        payload, at, quota = discovery
        rows = payload['response']
        self.store.append('global_snapshot', slot, {'at': at.isoformat(), 'fixtures': rows, 'provider_quota': quota,
                          'source_fingerprint': digest(payload)}, at, ('opportunity', slot))
        if not rows:
            return finish('NO_LIVE_FIXTURES', live_fixtures=0)
        state, decisions = shortlist(rows, at, self.competitions, self.contexts)
        self.store.append('shortlist', slot, {'decisions': decisions, 'selected': state}, at, ('global_snapshot', slot))
        if state is None:
            return finish('NO_SUPPORTED_FIXTURE', live_fixtures=len(rows))
        fixture_id = state['fixture_id']
        detail = {'live_fixtures': len(rows), 'shortlisted_fixture': fixture_id}
        # The catalogue capture uses one of the four detail slots; no ID is auto-approved.
        if self.mapping.get('review_status') != 'REVIEWED':
            catalogue = self._call(slot, '/odds/live/bets', {})
            if catalogue:
                self.store.append('market_catalogue', slot, {'endpoint': '/odds/live/bets',
                                  'payload': catalogue[0], 'at': catalogue[1].isoformat(),
                                  'review_status': 'AWAITING_REVIEW'}, catalogue[1])
        odds = self._call(slot, '/odds/live', {'fixture': fixture_id})
        if odds is None:
            return finish('CURRENT_ODDS_UNAVAILABLE', **detail)
        quotes, reasons = normalize(odds[0], state, self.mapping, retrieved_at=odds[1])
        self.store.append('normalized_odds', slot, {'quotes': quotes, 'reasons': reasons,
                          'at': odds[1].isoformat()}, odds[1])
        books = sorted({q['bookmaker_id'] for q in quotes})
        detail.update(available_bookmakers=books, odds_rejections=reasons)
        # Without consensus-capable quotes, further pressure/lineup calls have no utility.
        if len(books) < 3:
            self.store.append('candidate', slot, {'qualified': False, 'reasons': reasons or ['INSUFFICIENT_BOOKMAKERS'],
                              'state': state}, self.clock())
            return finish('NO_MULTIBOOK_MARKET_EVIDENCE', **detail)
        statistics = self._call(slot, '/fixtures/statistics', {'fixture': fixture_id})
        original = next(r for r in rows if r['fixture']['id'] == fixture_id)
        if isinstance(original.get('events'), list):
            events = original['events']
        else:
            event_response = self._call(slot, '/fixtures/events', {'fixture': fixture_id})
            events = event_response[0]['response'] if event_response else None
        feature = features(state, statistics[0]['response'] if statistics else [], events)
        self.store.append('feature_snapshot', slot, {'state': state, 'features': feature}, self.clock())
        # At the call ceiling, capacity for a further call is zero; only the protective
        # PREMATCH reserve matters to evaluation after the final authorized call.
        decision = self.governor.inspect(slot, self.clock())
        safe = decision['protected_remaining_requirement'] is not None and not [
            r for r in decision['reasons'] if r != 'PROTECTED_CAPACITY_EXHAUSTED'] and (
            decision['observed_daily_remaining'] >= decision['protected_remaining_requirement'])
        evaluations = evaluate(state, feature, quotes, now=self.clock(), safe_quota=safe,
                               published=frozenset(c['economic_key'] for c in self.store.all('claim')),
                               prematch_context=self.contexts.get(fixture_id))
        for evaluation in evaluations:
            self.store.append('candidate', digest(evaluation), evaluation, self.clock(), ('feature_snapshot', slot))
        return finish('EVALUATED', **detail, available_statistics=feature,
                      candidate_qualified=any(e['qualified'] for e in evaluations))
