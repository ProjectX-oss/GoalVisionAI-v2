"""Opt-in future runtime composition; no timers, configuration edits or default activation."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from .automl import AutoLearner
from .contracts import digest, number, utc
from .governance import Governance
from .features import captured_features
from .observations import import_prematch
from .policy import eligibility
from .repository import AuditRepository


def opportunity(prediction: dict, stream: str) -> dict:
    """Build a pre-outcome view using the same key as the immutable observation linker."""
    p,odds=number(prediction['ensemble_probability']),number(prediction['captured_odds'])
    key=digest([stream,prediction['fixture_id'],prediction['market'],
                prediction.get('candidate_id',prediction.get('observation_id')),
                prediction['quote_provenance_fingerprint'],prediction['ensemble_probability']])
    row={'stream':stream,'opportunity_key':key,'fixture_id':prediction['fixture_id'],
         'market':prediction['market'],'kickoff_utc':prediction['kickoff_utc'],
         'quote_fingerprint':prediction['quote_provenance_fingerprint'],
         'offered_decimal_odds':prediction['captured_odds'],'frozen_model_probability':prediction['ensemble_probability'],
         'implied_probability':1/odds,'edge':p-1/odds,'EV':p*odds-1,
         'prediction_created_at':prediction['prepared_at_utc'],'target':None,
         'uncertainty':prediction.get('uncertainty_penalty'),'evidence_family_count':len(prediction.get('predictive_families',[])),
         'competition_profile':prediction.get('competition_profile'),'league_id':prediction.get('league_id'),
         'frozen_features':captured_features(prediction), 'source_prediction':prediction}
    for key in ('live_minute','live_score_home','live_score_away'):
        if key in prediction:
            row[key]=prediction[key]
    return row


class LearningCoordinator:
    """Call after durable settlements. Replays also recover an interrupted learning step."""
    def __init__(self, repository: AuditRepository) -> None:
        self.repository=repository
        self.governance=Governance(repository)

    def after_settlement(self, stream: str, *, now: datetime, train: bool = True) -> dict:
        rows=self.repository.all('learning_observations',stream)
        for row in rows:
            self.governance.settle_shadow(row)
        rollback=self.governance.rollback(stream,now=now)
        promotions=[]
        for run in self.repository.all('shadow_runs',stream):
            promotions.append(self.governance.promote(run['shadow_id'],now=now))
        research=AutoLearner(self.repository).run(stream,now=now) if train else {'status':'DAILY_LEARNING_JOB_ONLY'}
        return {'eligibility':eligibility(rows,stream,now),'research':research,'promotions':promotions,'rollback':rollback}

    def sync_prematch(self, ledger: object, *, now: datetime, train: bool = True) -> dict:
        linkage=import_prematch(ledger,self.repository,now=utc(now).isoformat())
        return {'linkage':linkage,**self.after_settlement('PREMATCH',now=now,train=train)}

    def shadow(self, predictions: list[dict], *, stream: str, now: datetime) -> None:
        for prediction in predictions:
            if not prediction.get('ensemble_probability') or not prediction.get('captured_odds'):
                continue
            self.governance.observe(stream,opportunity(prediction,stream),now=now)

    def prematch_signals(self, signals: list, baseline: object, profile_evidence: dict,
                         fixture: dict, market: str, odds: Decimal, *, now: datetime, quote_fingerprint: str, missing: tuple = (),
                         contradiction: bool = False) -> tuple[list,dict]:
        """Replace only predictive family; existing profile/EV/quote/readiness gates rerun."""
        champion=self.repository.champion('PREMATCH')
        if champion is None or baseline.ensemble_probability is None:
            return signals,{}
        from dataclasses import asdict
        captured = captured_features({'signals':[asdict(s) for s in signals], 'market':market})
        captured['baseline_probability']=float(baseline.ensemble_probability)
        from .baseline import context
        captured['baseline_context']=context(signals,fixture.get('competition_profile','UNKNOWN'),
                                             missing,market,odds,contradiction=contradiction)
        row={'stream':'PREMATCH','frozen_model_probability':float(baseline.ensemble_probability),
             'implied_probability':1/float(odds),'uncertainty':profile_evidence['uncertainty_penalty'],
             'evidence_family_count':profile_evidence['predictive_family_count'],
             'competition_profile':fixture.get('competition_profile'),'market':market,'frozen_features':captured}
        row.update(fixture_id=fixture['fixture_id'],offered_decimal_odds=str(odds))
        p,champion=self.governance.safe_resolve('PREMATCH',row,now=now)
        self.governance.monitor_opportunity('PREMATCH',row,p,
            opportunity_key=digest([fixture['fixture_id'],market,quote_fingerprint]),now=now)
        registered=self.repository.get('model_artifacts',champion['artifact_id'])
        provenance={'model_generation':champion['generation_id'],
                    'model_artifact_identity':champion['artifact_id'],
                    'baseline_probability':str(baseline.ensemble_probability),'adaptive_features':captured}
        if registered.get('family')=='EXISTING_PREMATCH_BASELINE_V1':
            # Preserve every original family, reliability, lane and readiness gate.
            return signals,provenance
        from app.lab_v2_shadow.ensemble import EnsembleSignal
        market_signals=[s for s in signals if s.name=='CURRENT_MARKET_CONSENSUS']
        adapted=EnsembleSignal('LAB_ADAPTIVE_MODEL',market,Decimal(str(p)),None,Decimal(1),'AVAILABLE',
                               champion['artifact_id'],'LAB_ADAPTIVE_MODEL')
        return [*market_signals,adapted],{'model_generation':champion['generation_id'],
                'model_artifact_identity':champion['artifact_id'],'baseline_probability':str(baseline.ensemble_probability),
                'adaptive_features':captured}
