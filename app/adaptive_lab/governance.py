"""Shadow evidence, atomic LAB champion activation and evidence-based rollback."""
from __future__ import annotations
from datetime import datetime
from .contracts import digest, number, stream_name, utc
from .comparison import compare
from .models import predict, validate_artifact
from .policy import POLICY, eligibility
from .repository import AuditRepository

INTEGRITY_REASONS=frozenset({'ARTIFACT_INTEGRITY_FAILURE','PROBABILITY_CONTRACT_VIOLATION',
                            'MODEL_STREAM_MISMATCH','SYSTEMATIC_RUNTIME_FAILURE'})


class Governance:
    """No caller-supplied pass flags; decisions are recomputed from persisted evidence."""
    def __init__(self, repository: AuditRepository) -> None:
        self.repository=repository

    def bootstrap(self, artifact: dict, *, now: datetime) -> dict:
        """Explicit future operator bootstrap; never called by reports or research."""
        validate_artifact(artifact)
        stream=stream_name(artifact['stream'])
        repo=self.repository
        stamp=utc(now).isoformat()
        with repo.transaction():
            if repo.champion(stream):
                raise ValueError('CHAMPION_ALREADY_EXISTS')
            cid='bootstrap-'+digest(artifact)
            repo.append('learning_cycles',cid,stream,{'created_at':stamp,'kind':'REVIEWED_BOOTSTRAP'},stamp)
            sid='bootstrap-spec-'+digest(artifact)
            repo.append('model_specs',sid,stream,artifact.get('spec') or {'family':artifact['family']},stamp,cycle_id=cid)
            rid='bootstrap-run-'+digest(artifact)
            repo.append('training_runs',rid,stream,{'status':'REVIEWED_BOOTSTRAP','created_at':stamp},stamp,spec_id=sid)
            aid='bootstrap-artifact-'+digest(artifact)
            repo.append('model_artifacts',aid,stream,artifact,stamp,run_id=rid)
            return self._activate(stream,aid,None,'BOOTSTRAP',{'artifact_fingerprint':digest(artifact)},stamp)

    def resolve(self, stream: str, row: dict) -> tuple[float, dict | None]:
        champion=self.repository.champion(stream)
        if champion is None:
            return number(row['frozen_model_probability'],low=0,high=1),None
        artifact=self.repository.get('model_artifacts',champion['artifact_id'])
        return predict(artifact,row),champion

    def safe_resolve(self, stream: str, row: dict, *, now: datetime) -> tuple[float, dict | None]:
        """Reproduce an integrity failure and restore a verified previous champion first."""
        try:
            return self.resolve(stream,row)
        except (ValueError,KeyError,TypeError,ZeroDivisionError):
            outcome=self.rollback(stream,now=now,incident={'input':row})
            if outcome.get('reason')!='ROLLBACK':
                raise ValueError('MODEL_INTEGRITY_PUBLICATION_BLOCKED') from None
            return self.resolve(stream,row)

    def monitor_opportunity(self, stream: str, row: dict, probability: float, *,
                            opportunity_key: str, now: datetime) -> None:
        """Freeze throughput evidence, including no-selections, against the previous model."""
        current=self.repository.champion(stream)
        if not current or not current['previous_generation'] or current['reason']=='ROLLBACK':
            return
        previous=self.repository.get('champion_generations',current['previous_generation'])
        artifact=self.repository.get('model_artifacts',previous['artifact_id'])
        previous_probability=predict(artifact,row)
        odds=number(row['offered_decimal_odds'])
        uncertainty=number(row.get('uncertainty') or 0)
        identity=digest([current['generation_id'],opportunity_key])
        if self.repository.get('champion_predictions',identity):
            return
        value={'generation_id':current['generation_id'],'created_at':utc(now).isoformat(),
               'opportunity_key':opportunity_key,'frozen_input':row,'fixture_id':row['fixture_id'],
               'champion_probability':probability,'previous_probability':previous_probability,
               'champion_selected':probability-1/odds>uncertainty,
               'previous_selected':previous_probability-1/odds>uncertainty}
        self.repository.append('champion_predictions',identity,stream,value,value['created_at'],
                               generation_id=current['generation_id'])

    def observe(self, stream: str, opportunity: dict, *, now: datetime) -> list[str]:
        """Freeze future matched shadow predictions before outcome; no send capability."""
        if opportunity['stream']!=stream or opportunity.get('target') is not None or opportunity.get('outcome') in {'WON','LOST','VOID'}:
            raise ValueError('SHADOW_MUST_PRECEDE_OUTCOME')
        stamp=utc(now).isoformat()
        if utc(opportunity['prediction_created_at'])>utc(now) or (stream=='PREMATCH' and utc(now)>=utc(opportunity['kickoff_utc'])):
            raise ValueError('SHADOW_CHRONOLOGY_INVALID')
        champion_probability,champion=self.resolve(stream,opportunity)
        champion_id=champion['generation_id'] if champion else None
        identities=[]
        for run in self.repository.all('shadow_runs',stream):
            if utc(now)<=utc(run['created_at']) or run['champion_generation']!=champion_id:
                continue
            artifact=self.repository.get('model_artifacts',run['artifact_id'])
            challenger_probability=predict(artifact,opportunity)
            identity='shadow-prediction-'+digest([run['shadow_id'],opportunity['opportunity_key']])
            if self.repository.get('shadow_predictions', identity) is not None:
                identities.append(identity)
                continue
            document={'prediction_id':identity,'shadow_id':run['shadow_id'],'opportunity_key':opportunity['opportunity_key'],
                      'created_at':stamp,'frozen_opportunity':opportunity,'champion_probability':champion_probability,
                      'challenger_probability':challenger_probability,
                      'champion_generation':champion_id,
                      'probability_disagreement':challenger_probability-champion_probability,
                      'direction_disagreement':(challenger_probability>.5)!=(champion_probability>.5),
                      'champion_selected':champion_probability*number(opportunity['offered_decimal_odds'])>1,
                      'challenger_selected':challenger_probability*number(opportunity['offered_decimal_odds'])>1}
            self.repository.append('shadow_predictions',identity,stream,document,stamp,shadow_id=run['shadow_id'])
            identities.append(identity)
        return identities

    def settle_shadow(self, observation: dict) -> None:
        """Join by immutable opportunity identity and recheck the exact frozen inputs."""
        stream=observation['stream']
        for pred in self.repository.all('shadow_predictions',stream):
            if pred['opportunity_key']!=observation['opportunity_key']:
                continue
            frozen=pred['frozen_opportunity']
            for key in ('fixture_id','market','quote_fingerprint','offered_decimal_odds','prediction_created_at'):
                if frozen[key]!=observation[key]:
                    raise ValueError('SHADOW_SETTLEMENT_IDENTITY_CONFLICT')
            if utc(pred['created_at'])>=utc(observation['settled_at']):
                raise ValueError('SHADOW_SETTLEMENT_CHRONOLOGY_CONFLICT')
            existing=self.repository.get('shadow_settlements',pred['prediction_id'])
            if existing and existing['observation_id'] is None:
                if existing['target'] != observation['target']:
                    raise ValueError('CONFLICTING_SHADOW_SETTLEMENT')
                continue
            value={'prediction_id':pred['prediction_id'],'observation_id':observation['observation_id'],
                   'observation_fingerprint':observation['observation_fingerprint'],
                   'settled_at':observation['settled_at'],'target':observation['target']}
            self.repository.append('shadow_settlements',pred['prediction_id'],stream,value,
                                   observation['settled_at'],prediction_id=pred['prediction_id'])

    def settle_shadow_result(self, prediction_id: str, payload: dict, *, now: datetime) -> dict | None:
        """Resolve unpublished matched opportunities without creating learning observations."""
        pred=self.repository.get('shadow_predictions',prediction_id)
        if pred is None:
            raise ValueError('SHADOW_NOT_FOUND')
        row=pred['frozen_opportunity']
        if utc(now)<=utc(pred['created_at']):
            raise ValueError('SHADOW_RESULT_BEFORE_PREDICTION')
        from app.lab_combo.settlement import resolve_leg
        result=resolve_leg({**row,'observation_id':prediction_id,'odds':row['offered_decimal_odds']},payload,now)
        if result is None:
            return None
        old=self.repository.get('shadow_settlements',prediction_id)
        if old:
            if old['target']!=(None if result['outcome']=='VOID' else int(result['outcome']=='WON')):
                raise ValueError('CONFLICTING_SHADOW_SETTLEMENT')
            return old
        outcome=result['outcome']
        observation={**row,'observation_id':'shadow-only-'+prediction_id,'settled_at':utc(now).isoformat(),
                     'target':None if outcome=='VOID' else int(outcome=='WON'),'outcome':outcome,
                     'flat_unit_pnl':number(row['offered_decimal_odds'])-1 if outcome=='WON' else -1 if outcome=='LOST' else 0,
                     'source_result_fingerprint':digest(payload),'result_evidence':result}
        observation['observation_fingerprint']=digest(observation)
        value={'prediction_id':prediction_id,'observation_id':None,'shadow_observation':observation,
               'observation_fingerprint':observation['observation_fingerprint'],'target':observation['target'],
               'settled_at':observation['settled_at']}
        self.repository.append('shadow_settlements',prediction_id,row['stream'],value,
                               observation['settled_at'],prediction_id=prediction_id)
        return value

    def evidence(self, shadow_id: str) -> dict:
        run=self.repository.get('shadow_runs',shadow_id)
        if not run:
            raise ValueError('SHADOW_NOT_FOUND')
        rows,old,new=[],[],[]
        for pred in self.repository.all('shadow_predictions',run['stream']):
            if pred['shadow_id']!=shadow_id:
                continue
            settled=self.repository.get('shadow_settlements',pred['prediction_id'])
            if not settled or settled['target'] is None:
                continue
            row=(self.repository.get('learning_observations',settled['observation_id'])
                 if settled['observation_id'] else settled.get('shadow_observation'))
            if row is None or row['observation_fingerprint']!=settled['observation_fingerprint']:
                raise ValueError('SHADOW_SOURCE_INTEGRITY_FAILURE')
            rows.append(row); old.append(pred['champion_probability']); new.append(pred['challenger_probability'])
        days=(max(utc(r['prediction_created_at']) for r in rows)-min(utc(r['prediction_created_at']) for r in rows)).days if rows else 0
        comparison=compare(rows,old,new,minimum=POLICY.shadow_min) if rows else {'passed':False,'blocked_by':['NO_SHADOW_EVIDENCE']}
        return {'shadow_id':shadow_id,'resolved':len(rows),'days':days,'comparison':comparison,
                'observations':[r['observation_id'] for r in rows],
                'passed':comparison['passed'] and days>=POLICY.shadow_days}

    def promote(self, shadow_id: str, *, now: datetime) -> dict:
        repo=self.repository
        with repo.transaction():
            run=repo.get('shadow_runs',shadow_id)
            if not run:
                raise ValueError('SHADOW_NOT_FOUND')
            stream=run['stream']
            current=repo.champion(stream)
            if current and current.get('evidence',{}).get('shadow_id')==shadow_id:
                return current
            evidence=self.evidence(shadow_id)
            holds=[h for h in repo.all('holdout_results',stream) if h['artifact_id']==run['artifact_id']]
            eligible=eligibility(repo.all('learning_observations',stream),stream,now)
            gates={'global_evidence':eligible['automatic_eligible'],
                   'research_was_eligible':bool(len(holds)==1 and
                       (repo.get('learning_cycles',holds[0]['cycle_id']) or {}).get('eligibility',{}).get('resolved',0)>=POLICY.research_min),
                   'shadow_evidence':evidence['passed'],
                   'verified_previous_champion':current is not None,
                   'champion_unchanged':bool(current and current['generation_id']==run['champion_generation']),
                   'holdout_passed':len(holds)==1 and holds[0]['passed'] and holds[0]['chronology_verified'] and holds[0]['deterministic_reproduction']}
            stamp=utc(now).isoformat()
            gate={'shadow_id':shadow_id,'created_at':stamp,'gates':gates,'evidence':evidence,'passed':all(gates.values())}
            repo.append('promotion_gates',digest(gate),stream,gate,stamp,shadow_id=shadow_id)
            if not gate['passed']:
                return {'status':'PROMOTION_BLOCKED','blocked_by':sorted(k for k,v in gates.items() if not v)}
            artifact=repo.get('model_artifacts',run['artifact_id'])
            validate_artifact(artifact)
            for status in ('SHADOW_EVIDENCE_READY','PROMOTION_ELIGIBLE'):
                event={'artifact_id':run['artifact_id'],'status':status,'created_at':stamp,'gate_fingerprint':digest(gate)}
                repo.append('candidate_events',digest(event),stream,event,stamp,artifact_id=run['artifact_id'])
            return self._activate(stream,run['artifact_id'],current['generation_id'],'PROMOTION',
                                  {'shadow_id':shadow_id,'promotion_gate':digest(gate),
                                   'holdout_fingerprint':digest(holds[0]),'shadow_evidence':evidence},stamp)

    def _activate(self, stream: str, artifact_id: str, previous: str | None, reason: str,
                  evidence: dict, stamp: str) -> dict:
        value={'stream':stream,'artifact_id':artifact_id,'previous_generation':previous,'reason':reason,
               'evidence':evidence,'created_at':stamp,'scope':'LAB_ONLY'}
        gid='generation-'+digest(value)
        value['generation_id']=gid
        self.repository.append('champion_generations',gid,stream,value,stamp,artifact_id=artifact_id)
        self.repository.connection.execute('''INSERT INTO champion_pointers VALUES (?,?) ON CONFLICT(stream)
            DO UPDATE SET generation_id=excluded.generation_id''',(stream,gid))
        table='rollback_events' if reason=='ROLLBACK' else 'activation_events'
        self.repository.append(table,gid,stream,value,stamp,generation_id=gid)
        event={'artifact_id':artifact_id,'status':'ACTIVE_CHAMPION','created_at':stamp,'generation_id':gid}
        self.repository.append('candidate_events',digest(event),stream,event,stamp,artifact_id=artifact_id)
        return value

    def rollback(self, stream: str, *, now: datetime, incident: dict | None = None) -> dict:
        """Integrity rollback needs persisted reproducible failure, performance needs 200/30d."""
        repo=self.repository
        with repo.transaction():
            current=repo.champion(stream)
            if not current or current['reason']=='ROLLBACK':
                return {'status':'NO_ROLLBACK_REQUIRED'}
            previous=repo.get('champion_generations',current['previous_generation']) if current['previous_generation'] else None
            if not previous:
                return {'status':'NO_PREVIOUS_VERIFIED_CHAMPION'}
            evidence={}
            try:
                artifact=repo.get('model_artifacts',current['artifact_id'])
                validate_artifact(artifact)
            except (ValueError,KeyError,TypeError):
                evidence={'reason':'ARTIFACT_INTEGRITY_FAILURE','generation_id':current['generation_id']}
            if incident and not evidence:
                from .features import features
                if incident.get('input', {}).get('stream') != stream:
                    raise ValueError('INCIDENT_STREAM_INVALID')
                features(incident['input'])  # Invalid input is not evidence of model failure.
                # Reproduce supplied failed input; a reason string alone cannot force rollback.
                try:
                    predict(artifact,incident['input'])
                except (ValueError,KeyError,TypeError):
                    evidence={'reason':'PROBABILITY_CONTRACT_VIOLATION','incident_fingerprint':digest(incident)}
            if not evidence:
                monitoring=[r for r in repo.all('champion_predictions',stream)
                            if r['generation_id']==current['generation_id'] and utc(r['created_at'])<=utc(now)]
                span=(max(utc(r['created_at']) for r in monitoring)-min(utc(r['created_at']) for r in monitoring)).days if monitoring else 0
                if len(monitoring)>=POLICY.performance_rollback_min and span>=POLICY.performance_rollback_days and len({r['fixture_id'] for r in monitoring})>=50:
                    old_count=sum(r['previous_selected'] for r in monitoring)
                    new_count=sum(r['champion_selected'] for r in monitoring)
                    ratio=new_count/max(1,old_count)
                    if old_count>=50 and (ratio<POLICY.selection_ratio_min or ratio>POLICY.selection_ratio_max):
                        evidence={'reason':'SELECTION_THROUGHPUT_DEGRADATION','opportunities':len(monitoring),
                                  'days':span,'selection_ratio':ratio,'previous_selected':old_count,
                                  'champion_selected':new_count,'opportunity_keys':[r['opportunity_key'] for r in monitoring]}
            if not evidence:
                rows=[r for r in repo.all('learning_observations',stream) if r.get('model_generation')==current['generation_id'] and r['target'] is not None and utc(r['settled_at'])<=utc(now)]
                days=(max(utc(r['prediction_created_at']) for r in rows)-min(utc(r['prediction_created_at']) for r in rows)).days if rows else 0
                if len(rows)<POLICY.performance_rollback_min or days<POLICY.performance_rollback_days:
                    return {'status':'INSUFFICIENT_ROLLBACK_EVIDENCE','resolved':len(rows),'days':days}
                old_artifact=repo.get('model_artifacts',previous['artifact_id'])
                old=[predict(old_artifact,r) for r in rows]
                new=[number(r['frozen_model_probability']) for r in rows]
                result=compare(rows,old,new,minimum=POLICY.performance_rollback_min)
                harmful=(result['challenger']['brier']>result['champion']['brier']+.05 and
                         result['brier_delta_bootstrap_95'][0]>.02)
                severe_risk=result['challenger_betting']['maximum_drawdown']>max(20,result['champion_betting']['maximum_drawdown']*2)
                calibration_harm=(result['challenger']['ece']>result['champion']['ece']+.1 and result['brier_delta_bootstrap_95'][0]>0)
                unstable=not result['gates']['no_catastrophic_subgroup'] and result['brier_delta_bootstrap_95'][0]>.02
                if not (harmful or severe_risk or calibration_harm or unstable):
                    return {'status':'NO_SIGNIFICANT_DEGRADATION'}
                evidence={'reason':'PERFORMANCE_DEGRADATION','comparison':result,'observations':[r['observation_id'] for r in rows]}
            validate_artifact(repo.get('model_artifacts',previous['artifact_id']))
            return self._activate(stream,previous['artifact_id'],current['generation_id'],'ROLLBACK',evidence,utc(now).isoformat())
