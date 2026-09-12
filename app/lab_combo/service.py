"""Bounded Lab Combo coordination; no scheduler or production activation."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Callable

from app.current_odds_forward_test.repository import SQLiteForwardTestRepository
from app.lab_telegram.service import validate_lab_telegram_config
from app.real_match_lab_analysis.models import LAB_CHAT_ID

from .engine import load_leg, select_combo, prediction_message
from .repository import ComboRepository
from .settlement import resolve_leg, aggregate, statistics, settlement_message


class LabComboService:
    """Compose existing single review, immutable ledger and explicit Lab delivery."""

    def __init__(self, ledger: ComboRepository, singles: SQLiteForwardTestRepository,
                 *, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self.ledger, self.singles, self.clock = ledger, singles, clock

    def prepare(self, observation_ids: list[str]) -> dict:
        now = self.clock()
        legs, rejections = [], {}
        used = {leg['fixture_id'] for combo in self.ledger.all('prediction') for leg in combo['legs']}
        for identity in sorted(set(observation_ids)):
            leg, blockers = load_leg(self.singles, identity, now)
            if leg and leg['fixture_id'] in used:
                blockers = ['FIXTURE_ALREADY_IN_LAB_COMBO']
                leg = None
            if leg:
                legs.append(leg)
            else:
                rejections[identity] = blockers
        combo, blockers = select_combo(legs, now)
        if combo:
            self.ledger.append('prediction', combo['prediction_id'], combo)
            self.ledger.append('preview', combo['prediction_id'], {'message': prediction_message(combo)})
        return {'combo': combo, 'eligible_singles': len(legs), 'rejections': rejections, 'blockers': blockers}

    async def publish(self, prediction_id: str, config: object, transport: object, *, settlement: bool = False) -> dict:
        """Recheck gates, durably claim once, never retry an ambiguous Telegram send."""
        if validate_lab_telegram_config(config) is not None:
            return {'status': 'LAB_CONFIGURATION_REJECTED', 'sent': False}
        combo = self.ledger.get('prediction', prediction_id)
        if combo is None:
            raise ValueError('Unknown Lab Combo')
        if settlement:
            preview = self.ledger.get('settlement_preview', prediction_id)
            settled = self.ledger.get('settlement', prediction_id)
            if settled is None or preview is None or self.ledger.get('receipt', 'prediction:' + prediction_id) is None:
                return {'status': 'PUBLISHED_PREDICTION_AND_SETTLEMENT_REQUIRED', 'sent': False}
            results = [self.ledger.get('leg_result', leg['observation_id']) for leg in combo['legs']]
            if any(result is None for result in results) or aggregate(combo, results, datetime.fromisoformat(settled['settled_at_utc'])) != settled:
                return {'status': 'SETTLEMENT_INTEGRITY_BLOCKED', 'sent': False}
            if preview['message'] != settlement_message(settled, preview['statistics']):
                return {'status': 'SETTLEMENT_MESSAGE_CONFLICT', 'sent': False}
        else:
            for leg in combo['legs']:
                current, blockers = load_leg(self.singles, leg['observation_id'], self.clock())
                if blockers or {k: v for k, v in (current or {}).items() if k != 'review'} != {k: v for k, v in leg.items() if k != 'review'}:
                    return {'status': 'SINGLE_REVIEW_BLOCKED', 'blockers': blockers, 'sent': False}
            preview = self.ledger.get('preview', prediction_id)
            if preview is None or preview['message'] != prediction_message(combo):
                return {'status': 'PREDICTION_MESSAGE_CONFLICT', 'sent': False}
        message = preview['message']
        if len(message) > 4096:
            return {'status': 'TELEGRAM_MESSAGE_TOO_LONG', 'sent': False}
        identity = ('settlement:' if settlement else 'prediction:') + prediction_id
        if not self.ledger.append('claim', identity, {'prediction_id': prediction_id, 'message': message, 'chat_id': LAB_CHAT_ID}):
            return {'status': 'DELIVERY_ALREADY_CLAIMED', 'sent': False}
        try:
            receipt = await asyncio.wait_for(transport.send_message_receipt(
                chat_id=LAB_CHAT_ID, text=message, parse_mode=None, timeout_seconds=10), timeout=11)
            if receipt.chat_id != LAB_CHAT_ID or type(receipt.message_id) is not int or receipt.message_id <= 0:
                raise ValueError('Invalid receipt')
        except Exception:
            self.ledger.append('delivery_unknown', identity, {'status': 'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED'})
            return {'status': 'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED', 'sent': False}
        value = {'status': 'SENT', 'sent': True, 'chat_id': receipt.chat_id, 'message_id': receipt.message_id}
        self.ledger.append('receipt', identity, value)
        return value

    async def check_results(self, client: object, *, maximum_calls: int = 20) -> dict:
        """One bounded result sweep, caching fixture responses across combos."""
        from app.current_odds_forward_test.provider import _require
        if not 1 <= maximum_calls <= 20:
            raise ValueError('Result sweep requires a 1–20 call ceiling')
        if hasattr(client, 'restrict_requests'):
            client.restrict_requests(client.request_count + maximum_calls)
        now = self.clock()
        cache, completed = {}, []
        start = client.request_count
        for combo in self.ledger.all('prediction'):
            identity = combo['prediction_id']
            if self.ledger.get('settlement', identity):
                continue
            results = []
            for leg in combo['legs']:
                result = self.ledger.get('leg_result', leg['observation_id'])
                if result is None and now >= datetime.fromisoformat(leg['kickoff_utc']):
                    fixture = leg['fixture_id']
                    if fixture not in cache:
                        if client.request_count - start >= maximum_calls:
                            continue
                        try:
                            _require(client, 1, 20)
                            cache[fixture] = await client.fixture(int(fixture))
                        except Exception:
                            cache[fixture] = {}
                    result = resolve_leg(leg, cache[fixture], now)
                    if result:
                        self.ledger.append('leg_result', leg['observation_id'], result)
                if result:
                    results.append(result)
            if len(results) == 3:
                value = aggregate(combo, results, now)
                self.ledger.append('settlement', identity, value)
                completed.append(identity)
        # Recover a crash between settlement persistence and preview preparation.
        for value in self.ledger.all('settlement'):
            identity = value['prediction_id']
            if not self.ledger.get('settlement_preview', identity):
                stats = statistics(self.ledger, published_only=True)
                self.ledger.append('settlement_preview', identity, {'message': settlement_message(value, stats), 'statistics': stats})
        return {'completed': completed, 'api_calls': client.request_count - start, 'statistics': statistics(self.ledger)}
