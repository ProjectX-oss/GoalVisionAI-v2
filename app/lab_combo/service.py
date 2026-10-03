"""Bounded Lab Combo coordination; no scheduler or production activation."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.current_odds_forward_test.repository import SQLiteForwardTestRepository
from app.real_match_lab_analysis.models import LAB_CHAT_ID

from .engine import load_leg, select_combo, prediction_message
from .experimental import (
    FINAL_REVIEW_REFRESH_MAX_AGE, POLICY_VERSION, SETTLEMENT_RELEVANCE_AFTER_KICKOFF,
    evaluate_snapshot, publication_key, select_combo_batch, select_single_predictions,
)
from .presentation import (
    ResultImagePaths, combo_message, combo_result_message, single_message,
    single_result_message,
)
from .repository import ComboRepository
from .bot_routing import (
    RoutingBlocked, delivery_route, validate_delivery, route_message,
    cohort_statistics, frozen_route, BOT_USERNAME as COMBO_BOT_USERNAME,
)
from .settlement_reply import settlement_reply, reply_confirmation
from .publication_window import publication_blocker
from .odds_policy import combo_odds_blocker, minimum_combo_leg_odds
from .settlement import (
    resolve_leg, resolve_single, aggregate, statistics, single_statistics,
    settlement_message, economic_settlement, combo_needs_results, EARLY_LOSS_VERSION,
)


@dataclass
class DeliveryFacts:
    """Known facts for one invocation; acknowledgement is not a durable receipt."""

    kind: str
    prediction_id: str
    stage: str = 'BEFORE_TRANSPORT'
    claim_persisted: bool = False
    transport_attempted: bool = False
    transport_failure_kind: str | None = None
    acknowledgement_received: bool = False
    acknowledgement: dict | None = None
    receipt_persisted: bool = False
    reconciliation_required: bool = False
    unknown_marker_persisted: bool = False
    persistence_failure: str | None = None


class DeliveryFailure(Exception):
    """Bounded, secret-free failure evidence retained across the CLI boundary."""

    def __init__(self, facts: DeliveryFacts) -> None:
        code = ('LAB_DELIVERY_PERSISTENCE_FAILED' if facts.persistence_failure
                else 'LAB_DELIVERY_STAGE_FAILED')
        self.outcome = {'status': code, 'sent': False, **asdict(facts)}
        super().__init__(code)


class LabComboService:
    """Compose existing single review, immutable ledger and explicit Lab delivery."""

    def __init__(self, ledger: ComboRepository, singles: SQLiteForwardTestRepository,
                 *, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 result_images: ResultImagePaths | None = None,
                 early_combo_loss: bool = False) -> None:
        self.ledger, self.singles, self.clock = ledger, singles, clock
        self.result_images = result_images or ResultImagePaths()
        self.early_combo_loss = early_combo_loss

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

    def prepare_experimental(self, snapshots: list[object]) -> dict:
        """Evaluate CMI snapshots under the isolated Lab experimental policy."""
        now = self.clock()
        evaluated = [candidate for snapshot in snapshots for candidate in evaluate_snapshot(snapshot, now=now)]
        existing_single_keys = {value['publication_key'] for value in self.ledger.all('single_prediction')
                                if self.ledger.get('receipt', 'single_prediction:' + value['prediction_id'])}
        existing_single_fixtures = {value['fixture_id'] for value in self.ledger.all('single_prediction')
                                    if self.ledger.get('receipt', 'single_prediction:' + value['prediction_id'])}
        singles = select_single_predictions(
            evaluated, existing_keys=existing_single_keys,
            existing_fixtures=existing_single_fixtures, now=now,
        )
        prior_combos = [combo for combo in self.ledger.all('prediction')
                        if combo.get('policy') == POLICY_VERSION
                        and self.ledger.get('receipt', 'combo_prediction:' + combo['prediction_id'])]
        used_leg_keys = {publication_key(leg) for combo in prior_combos for leg in combo['legs']}
        used_fixtures = {leg['fixture_id'] for combo in prior_combos for leg in combo['legs']}
        used_teams = {str(leg[key]) for combo in prior_combos for leg in combo['legs']
                      for key in ('home_team_id', 'away_team_id')}
        combo_pool = [item for item in evaluated if item['fixture_id'] not in used_fixtures
                      and not used_teams.intersection({str(item['home_team_id']), str(item['away_team_id'])})]
        combos = select_combo_batch(combo_pool, used_leg_keys=used_leg_keys, now=now)
        single_ids = {value['candidate_id'] for value in singles}
        combo_ids = {leg['candidate_id'] for combo in combos for leg in combo['legs']}
        for candidate in evaluated:
            candidate['relation'] = (candidate['stage'] if candidate['stage'] != 'READY_TO_PUBLISH' else
                                     'BOTH' if candidate['candidate_id'] in single_ids & combo_ids else
                                     'SINGLE_ONLY' if candidate['candidate_id'] in single_ids else
                                     'COMBO_ELIGIBLE' if candidate['candidate_id'] in combo_ids else
                                     'REJECTED' if candidate['decision'] == 'REJECTED' else 'COMBO_ELIGIBLE')
            self.ledger.append('single_candidate', candidate['candidate_id'], candidate)
        for snapshot in snapshots:
            fixture_candidates = [item for item in evaluated if item['fixture_id'] == snapshot.fixture_id]
            stages = {item['stage'] for item in fixture_candidates}
            stage = next((value for value in ('READY_TO_PUBLISH', 'FINAL_REVIEW_REQUIRED', 'EARLY_CANDIDATE')
                          if value in stages), 'REJECTED')
            self.ledger.append('fixture_watch', snapshot.snapshot_id, {
                'fixture_id': snapshot.fixture_id, 'snapshot_id': snapshot.snapshot_id,
                'kickoff_utc': snapshot.kickoff_utc.isoformat(),
                'lineup_status': next((x.status.value for x in snapshot.freshness if x.signal == 'confirmed_lineups'), 'MISSING'),
                'candidate_stage': stage,
                'evaluated_at_utc': snapshot.evaluated_at.isoformat(),
            })
        for value in singles:
            self.ledger.append('single_prediction', value['prediction_id'], value)
            self.ledger.append('single_preview', value['prediction_id'], {'message': single_message(value)})
        for number, value in enumerate(combos, 1):
            self.ledger.append('prediction', value['prediction_id'], value)
            self.ledger.append('preview', value['prediction_id'], {'message': combo_message(value, number)})
        rejected = {}
        for candidate in evaluated:
            for reason in candidate['rejection_reasons']:
                rejected[reason] = rejected.get(reason, 0) + 1
        return {'policy': POLICY_VERSION, 'candidate_markets_evaluated': len(evaluated),
                'approved_single_candidates': sum(item['decision'] == 'APPROVED' for item in evaluated),
                'rejected_single_candidates': sum(item['decision'] == 'REJECTED' for item in evaluated),
                'early_candidates': sum(item['stage'] == 'EARLY_CANDIDATE' for item in evaluated),
                'final_review_candidates': sum(item['stage'] == 'FINAL_REVIEW_REQUIRED' for item in evaluated),
                'ready_to_publish_candidates': sum(item['stage'] == 'READY_TO_PUBLISH' for item in evaluated),
                'rejection_reasons': dict(sorted(rejected.items())),
                'singles': singles, 'combos': combos,
                'combo_eligible_legs': len({item['candidate_id'] for item in evaluated
                                           if item['decision'] == 'APPROVED'
                                           and item['stage'] == 'READY_TO_PUBLISH'}),
                'single_statistics': single_statistics(self.ledger),
                'combo_statistics': statistics(self.ledger, published_only=True)}

    async def publish_experimental(self, kind: str, prediction_id: str, config: object, transport: object) -> dict:
        facts = DeliveryFacts(kind, prediction_id)
        try:
            result = await self._publish_experimental(kind, prediction_id, config, transport, facts)
        except Exception:
            # Do not carry arbitrary transport/database exception text or secrets.
            raise DeliveryFailure(facts) from None
        if not facts.transport_attempted:
            facts.stage = ('NO_TRANSPORT_EXISTING_CLAIM' if result['status'] == 'DELIVERY_ALREADY_CLAIMED'
                           else 'REJECTED_BEFORE_TRANSPORT')
        return {**result, **asdict(facts)}

    async def _publish_experimental(self, kind: str, prediction_id: str, config: object,
                                    transport: object, facts: DeliveryFacts) -> dict:
        if self.ledger.get('claim', kind + ':' + prediction_id) is not None:
            return {'status': 'DELIVERY_ALREADY_CLAIMED', 'sent': False}
        try:
            route = delivery_route(self.ledger, kind, prediction_id)
        except RoutingBlocked as exc:
            return {'status': str(exc), 'sent': False}
        blocker = validate_delivery(config, transport, route, now=self.clock())
        if blocker:
            return {'status': blocker, 'sent': False}
        destination = route['chat_id'] if route else LAB_CHAT_ID
        from app.real_match_lab_analysis.models import LAB_BOT_USERNAME
        expected_bot = COMBO_BOT_USERNAME if route else LAB_BOT_USERNAME
        mapping = {
            'single_prediction': ('single_prediction', 'single_preview'),
            'combo_prediction': ('prediction', 'preview'),
            'single_settlement': ('single_settlement', 'single_settlement_preview'),
            'combo_settlement': ('settlement', 'settlement_preview'),
        }
        if kind not in mapping:
            raise ValueError('Unsupported Lab delivery kind')
        evidence_kind, preview_kind = mapping[kind]
        value, preview = self.ledger.get(evidence_kind, prediction_id), self.ledger.get(preview_kind, prediction_id)
        if value is None or preview is None:
            return {'status': 'LAB_EVIDENCE_NOT_READY', 'sent': False}
        if kind in {'single_settlement', 'combo_settlement'}:
            prefix = 'single_prediction:' if kind == 'single_settlement' else 'combo_prediction:'
            receipt = self.ledger.get('receipt', prefix + prediction_id)
            if not (receipt and receipt.get('sent') is True and receipt.get('status') == 'SENT'
                    and str(receipt.get('chat_id')) == str(destination)
                    and type(receipt.get('message_id')) is int and receipt['message_id'] > 0):
                return {'status': 'PUBLISHED_PREDICTION_AND_SETTLEMENT_REQUIRED', 'sent': False}
            if kind == 'combo_settlement' and value.get('settlement_version') == EARLY_LOSS_VERSION:
                combo = self.ledger.get('prediction', prediction_id)
                # Reproduce the frozen partial decision even after later legs finish.
                if (combo is None
                        or economic_settlement(combo, value['legs'],
                                               datetime.fromisoformat(value['settled_at_utc'])) != value
                        or any(self.ledger.get('leg_result', r['observation_id']) != r
                               for r in value['legs'])
                        or preview['message'] != combo_result_message(value, preview['statistics'])):
                    return {'status': 'COMBO_SETTLEMENT_EVIDENCE_INVALID', 'sent': False}
        if kind in {'single_prediction', 'combo_prediction'}:
            from app.lab_v2_shadow.origin import is_labelled
            from app.lab_v2_shadow.publication import SINGLE_SELECTION_POLICY
            from app.lab_v2_shadow.single_odds_policy import (
                FLOOR_SELECTION_POLICY, minimum_single_odds, single_odds_blocker,
            )
            if kind == 'single_prediction':
                if self.ledger.get('claim', kind + ':' + prediction_id) is not None:
                    return {'status': 'DELIVERY_ALREADY_CLAIMED', 'sent': False}
                blocker = single_odds_blocker(value.get('captured_odds'), minimum=minimum_single_odds())
                if blocker:
                    return {'status': blocker, 'sent': False}
            accuracy_single = (kind == 'single_prediction'
                               and value.get('single_selection_policy') in {SINGLE_SELECTION_POLICY, FLOOR_SELECTION_POLICY})
            if kind == 'combo_prediction':
                if self.ledger.get('claim', kind + ':' + prediction_id) is not None:
                    return {'status': 'DELIVERY_ALREADY_CLAIMED', 'sent': False}
                blocker = combo_odds_blocker(value, minimum=minimum_combo_leg_odds())
                if blocker:
                    return {'status': blocker, 'sent': False}
            from app.lab_v2_shadow.accuracy_combo import SUPPORTED_POLICIES as ACCURACY_COMBO_POLICIES
            accuracy_combo = (kind == 'combo_prediction'
                              and value.get('combo_selection_policy') in ACCURACY_COMBO_POLICIES)
            if kind == 'combo_prediction' and (
                    'combo_selection_policy' in value or prediction_id.startswith('lab-v2-combo-accuracy-')
                    or value.get('policy') in ACCURACY_COMBO_POLICIES) and not accuracy_combo:
                return {'status': 'COMBO_POLICY_OR_IDENTITY_INVALID', 'sent': False}
            if (accuracy_single or 'selection_origin' in value) and not is_labelled(value):
                return {'status': 'SELECTION_ORIGIN_OR_APPROVAL_INVALID', 'sent': False}
            if is_labelled(value):
                from app.lab_v2_shadow.publication import v2_single_message
                from app.adaptive_lab.contracts import MARKETS
                from app.real_match_lab_analysis.models import LAB_BOT_USERNAME
                origin = value['selection_origin']
                bot = getattr(transport, 'bot', None)
                if '@' + (getattr(bot, 'username', None) or '') != expected_bot:
                    return {'status': 'LAB_BOT_IDENTITY_MISMATCH', 'sent': False}
                if ((not accuracy_single and value.get('decision') != 'APPROVED')
                        or value.get('market') not in MARKETS
                        or value.get('candidate_lane') == 'TRACKING'
                        or not value.get('quote_provenance_fingerprint')
                        or (not accuracy_single and not value.get('predictive_family_count'))
                        or origin['selector_policy'] != value.get('policy')
                        or origin['model_artifact'] != value.get('model_artifact_identity')
                        or origin['model_generation'] != value.get('model_generation')
                        or origin['independent_context_model'] is not None
                        or preview['message'] != v2_single_message(value)):
                    return {'status': 'SELECTION_ORIGIN_OR_APPROVAL_INVALID', 'sent': False}
            candidates = [value] if kind == 'single_prediction' else value['legs']
            # Only the existing Lab V2 composition; settlements bypass new-pick policy.
            if accuracy_single:
                # A retained claim is terminal even after its review expires.
                # The atomic claim below still owns concurrent first attempts.
                if self.ledger.get('claim', kind + ':' + prediction_id) is not None:
                    return {'status': 'DELIVERY_ALREADY_CLAIMED', 'sent': False}
                review = _accuracy_delivery_review(value, self.clock())
                if not review['eligible']:
                    return {'status': 'LAB_PUBLICATION_POLICY_REJECTED', 'sent': False,
                            'publication_reviews': [review]}
            elif accuracy_combo:
                from app.lab_v2_shadow.accuracy_combo import review_accuracy_combo
                from app.lab_v2_shadow.publication import v2_combo_message
                from app.real_match_lab_analysis.models import LAB_BOT_USERNAME
                if self.ledger.get('claim', kind + ':' + prediction_id) is not None:
                    return {'status': 'DELIVERY_ALREADY_CLAIMED', 'sent': False}
                review = review_accuracy_combo(value, now=self.clock())
                if not review['eligible']:
                    return {'status': 'LAB_PUBLICATION_POLICY_REJECTED', 'sent': False,
                            'publication_reviews': [review]}
                if '@' + (getattr(getattr(transport, 'bot', None), 'username', None) or '') != expected_bot:
                    return {'status': 'LAB_BOT_IDENTITY_MISMATCH', 'sent': False}
                if preview['message'] != v2_combo_message(value, value['combo_number']):
                    return {'status': 'COMBO_PREVIEW_MISMATCH', 'sent': False}
            elif prediction_id.startswith('lab-v2-'):
                from app.lab_v2_shadow.publication_policy import review_publication
                reviews = [review_publication(item, now=self.clock()) for item in candidates]
                if any(not review['eligible'] for review in reviews):
                    return {'status': 'LAB_PUBLICATION_POLICY_REJECTED', 'sent': False,
                            'publication_reviews': reviews}
            blocker=publication_blocker(self.clock(),[item['kickoff_utc'] for item in candidates])
            if blocker:return {'status':blocker,'sent':False}
            kickoff = (datetime.fromisoformat(value['kickoff_utc']) if kind == 'single_prediction'
                       else min(datetime.fromisoformat(leg['kickoff_utc']) for leg in value['legs']))
            if self.clock() >= kickoff:
                return {'status': 'FIXTURE_ALREADY_STARTED', 'sent': False}
            candidates = [value] if kind == 'single_prediction' else value['legs']
            if not (accuracy_single or accuracy_combo) and any(item.get('stage') != 'READY_TO_PUBLISH' for item in candidates):
                return {'status': 'FINAL_REVIEW_REQUIRED', 'sent': False}
            review_field = ('accuracy_review_completed_at_utc' if accuracy_single or accuracy_combo
                            else 'final_review_completed_at_utc')
            review_times = [item.get(review_field) for item in candidates]
            if any(not review for review in review_times):
                return {'status': 'FINAL_REVIEW_REQUIRED', 'sent': False}
            if any(not timedelta(0) <= self.clock() - datetime.fromisoformat(review)
                   <= FINAL_REVIEW_REFRESH_MAX_AGE for review in review_times):
                return {'status': 'FINAL_REVIEW_EXPIRED', 'sent': False}
            if any(not _fresh_captured_odds(item, self.clock()) for item in candidates):
                return {'status': 'STALE_CURRENT_ODDS', 'sent': False}
        identity = kind + ':' + prediction_id
        try:
            reply = settlement_reply(self.ledger, kind, prediction_id, destination)
        except ValueError as exc:
            return {'status': str(exc), 'sent': False}
        reply_arguments = {'reply_to_message_id': reply['message_id']} if reply else {}
        message = route_message(preview['message'], route)
        if len(message) > 4096:
            return {'status': 'TELEGRAM_MESSAGE_TOO_LONG', 'sent': False}
        claim = {'prediction_id': prediction_id, 'message': message, 'chat_id': destination}
        if reply is not None:
            claim['reply_to'] = reply
        if route is not None:
            claim['delivery_route'] = route
        claimed = (self.ledger.claim_publication(kind, value, claim)
                   if kind in {'single_prediction', 'combo_prediction'}
                   else self.ledger.append('claim', identity, claim))
        if not claimed:
            return {'status': 'DELIVERY_ALREADY_CLAIMED', 'sent': False}
        facts.claim_persisted = True
        if kind in {'single_prediction','combo_prediction'}:
            blocker=publication_blocker(self.clock(),[item['kickoff_utc'] for item in candidates])
            if blocker:
                self.ledger.append('publication_blocked',identity,{'status':blocker,'sent':False})
                return {'status':blocker,'sent':False}
        image = self.result_images.available_for(value['status']) if kind in {'single_settlement', 'combo_settlement'} else None
        use_photo = image is not None and hasattr(transport, 'send_photo_receipt')
        facts.stage = 'TRANSPORT'
        facts.transport_attempted = True
        try:
            if use_photo:
                operation = transport.send_photo_receipt(
                    chat_id=destination, image_path=image, caption=message, timeout_seconds=10, **reply_arguments)
            else:
                operation = transport.send_message_receipt(
                    chat_id=destination, text=message, parse_mode=None, timeout_seconds=10, **reply_arguments)
            receipt = await asyncio.wait_for(operation, timeout=11)
            if receipt.chat_id != destination or type(receipt.message_id) is not int or receipt.message_id <= 0:
                raise ValueError('Invalid receipt')
            reply_evidence = reply_confirmation(receipt, reply)
        except Exception as exc:
            from telegram.error import TimedOut
            facts.transport_failure_kind = 'TIMEOUT' if isinstance(exc, (TimedOut, TimeoutError)) else 'ERROR'
            facts.stage = 'UNKNOWN_MARKER_PERSISTENCE'
            facts.reconciliation_required = True
            try:
                self.ledger.append('delivery_unknown', identity, {'status': 'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED'})
            except Exception:
                facts.persistence_failure = 'DELIVERY_UNKNOWN'
                raise
            facts.unknown_marker_persisted = True
            facts.stage = 'DELIVERY_UNKNOWN'
            return {'status': 'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED', 'sent': False}
        facts.acknowledgement_received = True
        facts.acknowledgement = {'chat_id': receipt.chat_id, 'message_id': receipt.message_id}
        facts.reconciliation_required = True
        facts.stage = 'RECEIPT_PERSISTENCE'
        result = {'status': 'SENT', 'sent': True, 'chat_id': receipt.chat_id,
                  'message_id': receipt.message_id, 'sent_at_utc': self.clock().isoformat()}
        result.update(reply_evidence)
        if route is not None:
            result['delivery_route'] = route
        try:
            self.ledger.append('receipt', identity, result)
        except Exception:
            facts.persistence_failure = 'RECEIPT'
            raise
        facts.receipt_persisted = True
        facts.reconciliation_required = False
        facts.stage = 'RECEIPT_PERSISTED'
        return result

    async def publish(self, prediction_id: str, config: object, transport: object, *, settlement: bool = False) -> dict:
        """Recheck gates, durably claim once, never retry an ambiguous Telegram send."""
        if self.ledger.get('claim', ('settlement:' if settlement else 'prediction:') + prediction_id) is not None:
            return {'status': 'DELIVERY_ALREADY_CLAIMED', 'sent': False}
        try:
            route = delivery_route(self.ledger, 'settlement' if settlement else 'prediction', prediction_id)
        except RoutingBlocked as exc:
            return {'status': str(exc), 'sent': False}
        blocker = validate_delivery(config, transport, route, now=self.clock())
        if blocker:
            return {'status': blocker, 'sent': False}
        destination = route['chat_id'] if route else LAB_CHAT_ID
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
            if self.ledger.get('claim', 'prediction:' + prediction_id) is not None:
                return {'status': 'DELIVERY_ALREADY_CLAIMED', 'sent': False}
            blocker = combo_odds_blocker(combo, minimum=minimum_combo_leg_odds())
            if blocker:
                return {'status': blocker, 'sent': False}
            blocker=publication_blocker(self.clock(),[leg['kickoff_utc'] for leg in combo['legs']])
            if blocker:return {'status':blocker,'sent':False}
            for leg in combo['legs']:
                current, blockers = load_leg(self.singles, leg['observation_id'], self.clock())
                if blockers or {k: v for k, v in (current or {}).items() if k != 'review'} != {k: v for k, v in leg.items() if k != 'review'}:
                    return {'status': 'SINGLE_REVIEW_BLOCKED', 'blockers': blockers, 'sent': False}
            preview = self.ledger.get('preview', prediction_id)
            if preview is None or preview['message'] != prediction_message(combo):
                return {'status': 'PREDICTION_MESSAGE_CONFLICT', 'sent': False}
        try:
            reply = settlement_reply(self.ledger, 'settlement' if settlement else 'prediction', prediction_id, destination)
        except ValueError as exc:
            return {'status': str(exc), 'sent': False}
        reply_arguments = {'reply_to_message_id': reply['message_id']} if reply else {}
        message = route_message(preview['message'], route)
        if len(message) > 4096:
            return {'status': 'TELEGRAM_MESSAGE_TOO_LONG', 'sent': False}
        identity = ('settlement:' if settlement else 'prediction:') + prediction_id
        claim = {'prediction_id': prediction_id, 'message': message, 'chat_id': destination}
        if reply is not None:
            claim['reply_to'] = reply
        if route is not None:
            claim['delivery_route'] = route
        claimed = (self.ledger.append('claim', identity, claim) if settlement
                   else self.ledger.claim_publication('prediction', combo, claim))
        if not claimed:
            return {'status': 'DELIVERY_ALREADY_CLAIMED', 'sent': False}
        try:
            if not settlement:
                blocker=publication_blocker(self.clock(),[leg['kickoff_utc'] for leg in combo['legs']])
                if blocker:
                    self.ledger.append('publication_blocked',identity,{'status':blocker,'sent':False})
                    return {'status':blocker,'sent':False}
            receipt = await asyncio.wait_for(transport.send_message_receipt(
                chat_id=destination, text=message, parse_mode=None, timeout_seconds=10, **reply_arguments), timeout=11)
            if receipt.chat_id != destination or type(receipt.message_id) is not int or receipt.message_id <= 0:
                raise ValueError('Invalid receipt')
            reply_evidence = reply_confirmation(receipt, reply)
        except Exception:
            self.ledger.append('delivery_unknown', identity, {'status': 'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED'})
            return {'status': 'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED', 'sent': False}
        value = {'status': 'SENT', 'sent': True, 'chat_id': receipt.chat_id, 'message_id': receipt.message_id,
                 'sent_at_utc':self.clock().isoformat()}
        value.update(reply_evidence)
        if route is not None:
            value['delivery_route'] = route
        self.ledger.append('receipt', identity, value)
        return value

    async def check_results(self, client: object, *, maximum_calls: int = 20, adaptive_learning: object | None = None) -> dict:
        """One bounded result sweep, caching fixture responses across combos."""
        from app.current_odds_forward_test.provider import _require
        if not 1 <= maximum_calls <= 20:
            raise ValueError('Result sweep requires a 1–20 call ceiling')
        if hasattr(client, 'restrict_requests'):
            client.restrict_requests(client.request_count + maximum_calls)
        now = self.clock()
        from .result_diagnostics import MAX_RECORDS, VERSION, unresolved_result
        from app.real_match_lab_analysis.fingerprint import fingerprint
        cache, completed, single_completed, detail_completed = {}, [], [], []
        failed_requests, diagnostics, diagnostic_count = set(), [], 0
        start = client.request_count

        def unresolved(prediction):
            nonlocal diagnostic_count
            diagnostic_count += 1
            fixture = str(prediction['fixture_id'])
            state = ('REQUEST_FAILED' if fixture in failed_requests else
                     'CALL_BUDGET_EXHAUSTED' if fixture not in cache else 'RESPONSE_RECEIVED')
            if len(diagnostics) < MAX_RECORDS:
                diagnostics.append(unresolved_result(prediction, cache.get(fixture), now,
                                                     request_state=state))
        for prediction in self.ledger.all('single_prediction'):
            identity = prediction['prediction_id']
            if (self.ledger.get('single_settlement', identity)
                    or self.ledger.get('receipt', 'single_prediction:' + identity) is None
                    or now < datetime.fromisoformat(prediction['kickoff_utc']) + SETTLEMENT_RELEVANCE_AFTER_KICKOFF):
                continue
            fixture = str(prediction['fixture_id'])
            if fixture not in cache and client.request_count - start < maximum_calls:
                try:
                    _require(client, 1, 20)
                    cache[fixture] = await client.fixture(int(fixture))
                except Exception:
                    cache[fixture] = {}
                    failed_requests.add(fixture)
            result = resolve_single(prediction, cache.get(fixture, {}), now)
            if result is None:
                unresolved(prediction)
            if result and self.ledger.append('single_settlement', identity, result):
                single_completed.append(identity)
                stats = self._single_preview_statistics(result)
                self.ledger.append('single_settlement_preview', identity, {
                    'message': self._single_result_message(result, stats), 'statistics': stats})
        for combo in self.ledger.all('prediction'):
            identity = combo['prediction_id']
            if (not combo_needs_results(self.ledger, combo)
                    or self.ledger.get('receipt', 'combo_prediction:' + identity) is None
                    or now < min(datetime.fromisoformat(leg['kickoff_utc']) for leg in combo['legs']) + SETTLEMENT_RELEVANCE_AFTER_KICKOFF):
                continue
            results = []
            for leg in combo['legs']:
                result = self.ledger.get('leg_result', leg['observation_id'])
                if result is None and now >= datetime.fromisoformat(leg['kickoff_utc']) + SETTLEMENT_RELEVANCE_AFTER_KICKOFF:
                    fixture = str(leg['fixture_id'])
                    if fixture not in cache:
                        if client.request_count - start >= maximum_calls:
                            unresolved(leg)
                            continue
                        try:
                            _require(client, 1, 20)
                            cache[fixture] = await client.fixture(int(fixture))
                        except Exception:
                            cache[fixture] = {}
                            failed_requests.add(fixture)
                    result = resolve_leg(leg, cache[fixture], now)
                    if result:
                        self.ledger.append('leg_result', leg['observation_id'], result)
                    else:
                        unresolved(leg)
                if result:
                    results.append(result)
            existing = self.ledger.get('settlement', identity)
            if existing is None:
                value = (economic_settlement(combo, results, now) if self.early_combo_loss
                         else aggregate(combo, results, now) if len(results) == 3 else None)
                if value and self.ledger.append('settlement', identity, value):
                    completed.append(identity)
            elif existing.get('settlement_version') == EARLY_LOSS_VERSION and len(results) == 3:
                detail = aggregate(combo, results, now)
                if detail['status'] != existing['status'] or detail['unit_result'] != existing['unit_result']:
                    raise ValueError('COMBO_FINAL_DETAIL_ACCOUNTING_CONFLICT')
                if self.ledger.append('combo_result_detail', identity, detail):
                    detail_completed.append(identity)
        # Recover a crash between settlement persistence and preview preparation.
        for value in self.ledger.all('single_settlement'):
            identity = value['prediction_id']
            if not self.ledger.get('single_settlement_preview', identity):
                stats = self._single_preview_statistics(value)
                self.ledger.append('single_settlement_preview', identity, {
                    'message': self._single_result_message(value, stats), 'statistics': stats})
        for value in self.ledger.all('settlement'):
            identity = value['prediction_id']
            if not self.ledger.get('settlement_preview', identity):
                route = frozen_route(self.ledger, identity)
                stats = cohort_statistics(self.ledger, route)
                self.ledger.append('settlement_preview', identity, {'message': combo_result_message(value, stats), 'statistics': stats})
        if adaptive_learning is not None:
            adaptive_learning.sync_prematch(self.ledger, now=self.clock(), train=False)
        diagnostic_report = {'version': VERSION, 'observed_at_utc': now.isoformat(),
                             'records': diagnostics, 'total_unresolved': diagnostic_count,
                             'truncated': diagnostic_count > len(diagnostics)}
        if diagnostics:
            self.ledger.append('settlement_diagnostic', fingerprint(diagnostic_report), diagnostic_report)
        return {'completed': completed, 'single_completed': single_completed,
                'combo_detail_completed': detail_completed,
                'settlement_diagnostics': diagnostic_report,
                'api_calls': client.request_count - start,
                'single_statistics': single_statistics(self.ledger),
                'combo_statistics': statistics(self.ledger, published_only=True),
                'statistics': statistics(self.ledger, published_only=True)}

    def _single_preview_statistics(self, result: dict) -> dict:
        """Snapshot after settlement acceptance, only for a new preview."""
        from app.lab_v2_shadow.origin import is_labelled
        from app.lab_v2_shadow.statistics import public_single_snapshot
        if is_labelled(result):
            return public_single_snapshot(self.ledger, as_of=self.clock())
        return single_statistics(self.ledger)

    def _single_result_message(self, result: dict, stats: dict) -> str:
        """New attributed outcomes retain the label; historical previews stay frozen."""
        from app.lab_v2_shadow.origin import is_labelled
        from app.lab_v2_shadow.public_presentation import result_message
        if is_labelled(result):
            receipt = self.ledger.get('receipt', 'single_prediction:' + result['prediction_id'])
            if receipt is None:
                raise ValueError('CONFIRMED_PUBLICATION_REQUIRED')
            return result_message(result, stats)
        return single_result_message(result, stats)


def _fresh_captured_odds(value: dict, now: datetime) -> bool:
    from app.current_odds_forward_test.freshness import current_odds_freshness
    try:
        retrieved = datetime.fromisoformat(value['goalvision_retrieved_at_utc'])
        origin = datetime.fromisoformat(value['provider_origin_timestamp_utc'])
        return current_odds_freshness(
            provider_type=value['provider_type'], provider_origin=origin,
            captured=retrieved, retrieved=retrieved, now=now,
        ) == 'FRESH'
    except (KeyError, TypeError, ValueError):
        return False


def _accuracy_delivery_review(value: dict, now: datetime) -> dict:
    """Revalidate frozen accuracy evidence without rewriting source decisions."""
    from decimal import Decimal, InvalidOperation
    from app.lab_v2_shadow.publication import (
        MIN_PUBLISHED_MARKET_PROBABILITY, SINGLE_SELECTION_POLICY, LEGACY_SINGLE_SELECTION_POLICY,
    )
    from app.lab_v2_shadow.publication_policy import (
        ACCURACY_PUBLICATION_POLICY_VERSION, review_accuracy_publication,
    )

    from app.lab_v2_shadow.single_odds_policy import FLOOR_SELECTION_POLICY, SINGLE_ODDS_FLOOR

    review = review_accuracy_publication(value, now=now)
    reasons = set(review['rejection_reasons'])
    if (value.get('accuracy_publication_policy_version') != ACCURACY_PUBLICATION_POLICY_VERSION
            or value.get('accuracy_publication_review') != {
                'version': ACCURACY_PUBLICATION_POLICY_VERSION,
                'eligible': True, 'rejection_reasons': []}):
        reasons.add('ACCURACY_REVIEW_EVIDENCE_REQUIRED')
    source_state = (value.get('decision'), value.get('stage'))
    hard = set(value.get('hard_failures') or ()) | set(value.get('rejection_reasons') or ())
    if (source_state != ('APPROVED', 'READY_TO_PUBLISH')
            and not (source_state == ('REJECTED', 'REJECTED') and hard == {'NON_POSITIVE_VALUE'})):
        reasons.add('ACCURACY_SOURCE_DECISION_INVALID')
    try:
        probability = Decimal(str(value['ensemble_probability']))
        odds = Decimal(str(value['captured_odds']))
        if not probability.is_finite() or probability < MIN_PUBLISHED_MARKET_PROBABILITY:
            reasons.add('LAB_PUBLICATION_PROBABILITY_BELOW_0_55')
        if not odds.is_finite() or odds <= 1:
            reasons.add('INVALID_CURRENT_DECIMAL_ODDS')
        selection_policy = value.get('single_selection_policy')
        if selection_policy == LEGACY_SINGLE_SELECTION_POLICY:
            if value.get('minimum_published_decimal_odds') != '1.30' or odds < Decimal('1.30'):
                reasons.add('FROZEN_LEGACY_ODDS_CONTRACT_INVALID')
        elif selection_policy == FLOOR_SELECTION_POLICY:
            if value.get('minimum_published_decimal_odds') != str(SINGLE_ODDS_FLOOR) or odds < SINGLE_ODDS_FLOOR:
                reasons.add('FROZEN_SINGLE_ODDS_CONTRACT_INVALID')
        elif selection_policy != SINGLE_SELECTION_POLICY or value.get('minimum_published_decimal_odds') is not None:
            reasons.add('ACCURACY_SELECTION_POLICY_INVALID')
        reviewed = datetime.fromisoformat(value['accuracy_review_completed_at_utc'])
        if not timedelta(0) <= now - reviewed <= FINAL_REVIEW_REFRESH_MAX_AGE:
            reasons.add('ACCURACY_REVIEW_EXPIRED')
    except (KeyError, TypeError, ValueError, InvalidOperation):
        reasons.add('ACCURACY_REVIEW_EVIDENCE_INVALID_OR_MISSING')
    return {**review, 'eligible': review['eligible'] and not reasons,
            'rejection_reasons': sorted(reasons)}
