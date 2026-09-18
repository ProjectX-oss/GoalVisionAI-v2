"""Explicitly constructed LIVE Lab single service with final refresh and durable sends."""
from __future__ import annotations
import asyncio
from datetime import datetime
from typing import Callable
from app.adaptive_lab.contracts import digest, number, utc
from app.adaptive_lab.governance import Governance
from app.adaptive_lab.repository import AuditRepository
from app.adaptive_lab.observations import ingest
from app.adaptive_lab.metrics import metrics
from app.lab_telegram.models import LAB_TELEGRAM_CHAT_ID
from app.lab_telegram.service import validate_lab_telegram_config
from .engine import readiness, remaining_goal_probabilities
from .policy import POLICY
from .presentation import prediction_message, settlement_message


class LiveService:
    """No combos and no configurable destination; only the existing Lab transport contract."""
    def __init__(self, repository: AuditRepository, *, clock: Callable[[],datetime],
                 after_settlement: Callable[[dict],object] | None = None) -> None:
        self.repository,self.clock,self.after_settlement=repository,clock,after_settlement
        self.governance=Governance(repository)

    def candidate(self, state: dict, quote: dict, rates: dict, *, now: datetime) -> dict:
        probabilities=remaining_goal_probabilities(state,rates,as_of=now)
        p=probabilities.get(quote['market'],.5)
        uncertainty=.07 + (.04 if (state['red_cards_home'] or state['red_cards_away']) else 0)
        # Optional features remain absent; presence is never fabricated for inference.
        frozen_features={**state.get('optional_features',{}),'baseline_probability':p,
                         'home_goal_rate':rates['home_goal_rate'], 'away_goal_rate':rates['away_goal_rate'],
                         'red_card_difference':state['red_cards_home']-state['red_cards_away']}
        observation={'stream':'LIVE','frozen_model_probability':p,'implied_probability':1/number(quote['decimal_odds']),
                     'uncertainty':uncertainty,'evidence_family_count':1,'frozen_features':frozen_features,
                     'live_minute':state['minute'],'live_score_home':state['home_score'],'live_score_away':state['away_score'],
                     'competition_profile':state['competition_profile'],'market':quote['market']}
        p,champion=self.governance.safe_resolve('LIVE',observation,now=now)
        previous=[self.repository.get('live_candidates',c['selection_id']) for c in self.repository.all('live_claims','LIVE')]
        reasons=readiness(state,quote,p,uncertainty=uncertainty,now=now,previous=previous)
        observation.update(fixture_id=state['fixture_id'],offered_decimal_odds=quote['decimal_odds'])
        if not set(reasons)-{'NON_POSITIVE_EV','SEVERE_MODEL_MARKET_CONTRADICTION'}:
            self.governance.monitor_opportunity('LIVE',observation,p,
                opportunity_key=digest([state['state_fingerprint'],quote['quote_fingerprint']]),now=now)
        generation=champion['generation_id'] if champion else 'LIVE_POISSON_BASELINE_V1'
        key=digest([state['fixture_id'],quote['market'],state['state_fingerprint'],quote['quote_fingerprint'],generation])
        stamp=utc(now).isoformat()
        value={'prediction_id':'live-'+key,'candidate_id':'live-'+key,'opportunity_key':key,
               'fixture_id':state['fixture_id'],'league_id':state['league_id'],
               'competition_profile':state['competition_profile'],'kickoff_utc':state['kickoff_utc'],
               'home_team':state['home_team'],'away_team':state['away_team'],'market':quote['market'],
               'candidate_lane':'LIVE_EXPERIMENTAL','readiness':'LIVE_EXPERIMENTAL_READY' if not reasons else 'LIVE_TRACKING',
               'captured_odds':quote['decimal_odds'],'ensemble_probability':str(p),'expected_value':p*number(quote['decimal_odds'])-1,
               'edge':p-1/number(quote['decimal_odds']),'uncertainty_penalty':uncertainty,
               'predictive_families':['LIVE_REMAINING_GOALS' if not champion else 'LIVE_ADAPTIVE_MODEL'],
               'bookmaker_id':quote.get('bookmaker_id'),'bookmaker':quote.get('bookmaker'),
               'quote_provenance_fingerprint':quote['quote_fingerprint'],'provider_type':'API_FOOTBALL_LIVE_ODDS',
               'provider_origin_timestamp_utc':quote['origin_timestamp'],'goalvision_retrieved_at_utc':quote['retrieved_at'],
               'prepared_at_utc':stamp,'policy':POLICY.version,'classifier_version':'LIVE_PROVIDER_PROFILE_V1',
               'model_generation':generation,'model_artifact_identity':champion['artifact_id'] if champion else digest(['LIVE_POISSON_BASELINE_V1',rates]),
               'live_minute':state['minute'],'live_score_home':state['home_score'],'live_score_away':state['away_score'],
               'live_match_state_fingerprint':state['state_fingerprint'],
               'red_card_state':[state['red_cards_home'],state['red_cards_away']],
               'state':state,'quote':quote,'rates':rates,'blockers':reasons,'adaptive_features':observation['frozen_features'],
               'baseline_probability':probabilities.get(quote['market']),
               'reasoning':'Remaining-time goal model uses observed team scoring history, current score and minute; value is compared with captured LIVE odds.'}
        existing = self.repository.get('live_candidates', value['prediction_id'])
        if existing is not None:
            return existing
        with self.repository.transaction():
            self.repository.append('live_snapshots' ,state['state_fingerprint'],'LIVE',state,state['retrieved_at'])
            self.repository.append('live_candidates',value['prediction_id'],'LIVE',value,stamp,snapshot_id=state['state_fingerprint'])
        if not set(reasons)-{'NON_POSITIVE_EV','SEVERE_MODEL_MARKET_CONTRADICTION'}:
            from app.adaptive_lab.coordinator import opportunity
            self.governance.observe('LIVE', opportunity(value, 'LIVE'), now=now)
        return value

    async def publish(self, identity: str, config: object, transport: object, *, refresh: Callable) -> dict:
        """Refresh fixture/events/odds before claiming; unknown delivery is never retried."""
        if validate_lab_telegram_config(config) is not None:
            return {'status':'LAB_CONFIGURATION_REJECTED','sent':False}
        original=self.repository.get('live_candidates',identity)
        if original is None:
            return {'status':'LIVE_CANDIDATE_MISSING','sent':False}
        try:
            state,quotes,rates=await refresh(original['fixture_id'])
            quote=next((q for q in quotes if q['market']==original['market']),None)
            if quote is None:
                return {'status':'LIVE_REFRESH_QUOTE_MISSING','sent':False}
            candidate=self.candidate(state,quote,rates,now=self.clock())
        except Exception:
            return {'status':'LIVE_FINAL_REFRESH_FAILED','sent':False}
        stamp=utc(self.clock()).isoformat()
        identity=candidate['prediction_id']
        with self.repository.transaction():
            active=self.repository.champion('LIVE')
            generation=active['generation_id'] if active else 'LIVE_POISSON_BASELINE_V1'
            if generation != candidate['model_generation']:
                return {'status':'LIVE_CHAMPION_CHANGED_REVIEW_REQUIRED','sent':False}
            prior=[self.repository.get('live_candidates',c['selection_id']) for c in self.repository.all('live_claims','LIVE')]
            reasons=readiness(state,quote,number(candidate['ensemble_probability']),
                              uncertainty=candidate['uncertainty_penalty'],now=self.clock(),previous=prior)
            if reasons:
                return {'status':'LIVE_READINESS_BLOCKED','blockers':reasons,'sent':False}
            message=prediction_message(candidate)
            claim={'selection_id':identity,'created_at':stamp,'message_fingerprint':digest(message)}
            if not self.repository.append('live_claims',identity,'LIVE',claim,stamp,selection_id=identity):
                return {'status':'DELIVERY_ALREADY_CLAIMED','sent':False}
        return await self._send(identity,message,transport,table='live_publications',claim_id=identity)

    async def _send(self, identity: str, message: str, transport: object, *, table: str, claim_id: str) -> dict:
        try:
            receipt=await asyncio.wait_for(transport.send_message_receipt(chat_id=LAB_TELEGRAM_CHAT_ID,
                text=message,parse_mode=None,timeout_seconds=10),timeout=11)
            if receipt.chat_id!=LAB_TELEGRAM_CHAT_ID or type(receipt.message_id) is not int or receipt.message_id<=0:
                raise ValueError('INVALID_LAB_RECEIPT')
        except Exception:
            return {'status':'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED','sent':False}
        value={'status':'SENT','sent':True,'selection_id':identity,'chat_id':receipt.chat_id,
               'message_id':receipt.message_id,'sent_at_utc':utc(self.clock()).isoformat()}
        self.repository.append(table,identity,'LIVE',value,value['sent_at_utc'],claim_id=claim_id)
        return value

    def settle(self, identity: str, payload: dict, *, now: datetime) -> dict | None:
        """Existing regulation-time result rules; LIVE has its own ledger and observation."""
        existing=self.repository.get('live_settlements',identity)
        prediction=self.repository.get('live_candidates',identity)
        receipt=self.repository.get('live_publications',identity)
        if not prediction or not receipt:
            return None
        from app.lab_combo.settlement import resolve_leg
        result=resolve_leg({**prediction,'observation_id':identity,'odds':prediction['captured_odds']},payload,now)
        if result is None:
            return existing
        if existing:
            if any(existing[k] != result[k] for k in ('outcome','fixture_id','market','captured_odds','fulltime_home','fulltime_away')):
                raise ValueError('CONFLICTING_SETTLEMENT')
            return existing
        value={**result,'prediction_id':identity,'status':result['outcome'],'settled_at_utc':utc(now).isoformat()}
        with self.repository.transaction():
            self.repository.append('live_settlements',identity,'LIVE',value,value['settled_at_utc'],publication_id=identity)
            observation=ingest(self.repository,prediction,receipt,value,stream='LIVE',publication_id=identity)
        self.governance.settle_shadow(observation)
        if self.after_settlement:
            self.after_settlement(observation)
        return value

    async def publish_result(self, identity: str, config: object, transport: object) -> dict:
        if validate_lab_telegram_config(config) is not None:
            return {'status':'LAB_CONFIGURATION_REJECTED','sent':False}
        result=self.repository.get('live_settlements',identity)
        if result is None:
            return {'status':'LIVE_SETTLEMENT_MISSING','sent':False}
        stats=metrics(self.repository.all('learning_observations','LIVE'),'LIVE')
        message=settlement_message(result,stats)
        with self.repository.transaction():
            if self.repository.get('live_result_claims',identity):
                return {'status':'DELIVERY_ALREADY_CLAIMED','sent':False}
            self.repository.append('live_result_claims',identity,'LIVE',{'settlement_id':identity,'message':message},
                                   utc(self.clock()).isoformat(),settlement_id=identity)
        return await self._send(identity,message,transport,table='live_result_receipts',claim_id=identity)
