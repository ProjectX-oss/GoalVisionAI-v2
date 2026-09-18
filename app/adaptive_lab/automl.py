"""Bounded chronological research. Only validation chooses the holdout candidate."""
from __future__ import annotations
from datetime import datetime
from .contracts import digest, number, utc
from .datasets import chronological_dataset
from .models import candidate_specs, predict, train
from .policy import POLICY, eligibility
from .comparison import compare, evaluated
from .metrics import metrics
from .repository import AuditRepository


class AutoLearner:
    """Explicitly invoked service; imports and operator reports cannot start training."""
    def __init__(self, repository: AuditRepository) -> None:
        self.repository=repository

    def run(self, stream: str, *, now: datetime) -> dict:
        repo=self.repository
        rows=repo.all('learning_observations',stream)
        prior=repo.all('learning_cycles',stream)
        eligible=eligibility(rows,stream,now,previous=prior[-1] if prior else None)
        if not eligible['research_due']:
            return eligible
        # Do not repeatedly test the same sealed evidence across research cycles.
        consumed={oid for h in repo.all('holdout_results',stream) for oid in h['observation_ids']}
        dataset=chronological_dataset(rows,stream,now=now,consumed_holdout=consumed)
        parts=dataset.pop('partitions')
        cycle_id='cycle-'+digest([stream,dataset['dataset_fingerprint'],POLICY.fingerprint])
        stamp=utc(now).isoformat()
        cycle={'cycle_id':cycle_id,'stream':stream,'created_at':stamp,'eligibility':eligible,
               'dataset_fingerprint':dataset['dataset_fingerprint'],'policy_fingerprint':POLICY.fingerprint}
        dataset_id='dataset-'+dataset['dataset_fingerprint']
        # Serializes concurrent workers and commits a complete research audit atomically.
        with repo.transaction():
            if repo.get('learning_cycles',cycle_id):
                return {'status':'CYCLE_ALREADY_RECORDED','cycle_id':cycle_id}
            latest=repo.all('learning_cycles',stream)
            if latest!=prior:
                return {'status':'CONCURRENT_CYCLE_COMPLETED'}
            repo.append('learning_cycles',cycle_id,stream,cycle,stamp)
            repo.append('learning_datasets',dataset_id,stream,dataset,stamp,cycle_id=cycle_id)
            for partition,items in parts.items():
                for row in items:
                    assignment={'observation_id':row['observation_id'],'fingerprint':row['observation_fingerprint'],
                                'partition':partition,'dataset_id':dataset_id}
                    repo.append('split_assignments',digest(assignment),stream,assignment,stamp,
                                dataset_id=dataset_id,observation_id=row['observation_id'])
            candidates=[]
            operations=0
            for spec in candidate_specs(stream):
                spec_id='spec-'+digest([cycle_id,spec])
                repo.append('model_specs',spec_id,stream,spec,stamp,cycle_id=cycle_id)
                try:
                    operations += 4*len(parts['TRAIN'])*spec['iterations']*(len(spec['features'])+len(spec['interactions']))
                    if operations > POLICY.operation_budget:
                        raise ValueError('CYCLE_RESOURCE_BUDGET_EXHAUSTED')
                    artifact=train(spec,parts['TRAIN'])
                    # A complete independent retrain must produce identical bytes.
                    reproduced=train(spec,parts['TRAIN'])
                    if artifact!=reproduced:
                        raise ValueError('DETERMINISTIC_REPRODUCTION_FAILED')
                    run_id='training-'+digest([spec_id,artifact['training_fingerprint']])
                    repo.append('training_runs',run_id,stream,{'run_id':run_id,'status':'TRAINED',
                        'training_fingerprint':artifact['training_fingerprint'],'reproduced':True},stamp,spec_id=spec_id)
                    aid='artifact-'+digest([run_id,artifact['artifact_fingerprint']])
                    repo.append('model_artifacts',aid,stream,artifact,stamp,run_id=run_id)
                    self.event(aid,stream,'CREATED',stamp)
                    self.event(aid,stream,'TRAINED',stamp)
                    probs=[predict(artifact,r) for r in parts['VALIDATION']]
                    if not probs:
                        raise ValueError('VALIDATION_EMPTY')
                    m=metrics(evaluated(parts['VALIDATION'],probs),stream)
                    baseline=[number(r['frozen_model_probability']) for r in parts['VALIDATION']]
                    comparison=compare(parts['VALIDATION'],baseline,probs,minimum=30)
                    repo.append('validation_results',digest([aid,'validation']),stream,comparison,stamp,artifact_id=aid)
                    self.event(aid,stream,'VALIDATION_ELIGIBLE' if comparison['passed'] else 'REJECTED',stamp)
                    if comparison['passed']:
                        candidates.append((m['brier']+m['log_loss']/4+m['ece']/4,aid,artifact))
                except ValueError as exc:
                    # Reviewed failures are auditable; no provider/error text enters artifacts.
                    failure={'status':'REJECTED','reason':str(exc),'spec_id':spec_id}
                    repo.append('training_runs',digest(failure),stream,failure,stamp,spec_id=spec_id)
            if not candidates:
                return {'status':'NO_VALIDATION_CHALLENGER','cycle_id':cycle_id}
            _,aid,artifact=min(candidates,key=lambda x:(x[0],x[1]))
            self.event(aid,stream,'HOLDOUT_ELIGIBLE',stamp)
            holdout=parts['SEALED_HOLDOUT']
            if len(holdout)<POLICY.holdout_min:
                self.event(aid,stream,'REJECTED',stamp,reason='INSUFFICIENT_FRESH_HOLDOUT')
                return {'status':'INSUFFICIENT_FRESH_HOLDOUT','cycle_id':cycle_id}
            probabilities=[predict(artifact,r) for r in holdout]
            baseline=[number(r['frozen_model_probability']) for r in holdout]
            result=compare(holdout,baseline,probabilities,minimum=POLICY.holdout_min)
            result.update(observation_ids=[r['observation_id'] for r in holdout],dataset_id=dataset_id,
                          cycle_id=cycle_id,artifact_id=aid,created_at=stamp,
                          chronology_verified=True,deterministic_reproduction=True,
                          automatic_eligible=eligible['automatic_eligible'])
            repo.append('holdout_results',digest([cycle_id,aid,'holdout']),stream,result,stamp,artifact_id=aid)
            repo.append('candidate_comparisons',digest([cycle_id,aid,'comparison']),stream,result,stamp,artifact_id=aid)
            if not result['passed']:
                self.event(aid,stream,'REJECTED',stamp,reason='HOLDOUT_GATES_FAILED')
                return {'status':'HOLDOUT_REJECTED','cycle_id':cycle_id,'blocked_by':result['blocked_by']}
            self.event(aid,stream,'CHALLENGER_APPROVED',stamp)
            shadow_id='shadow-'+digest([aid,cycle_id])
            champion=repo.champion(stream)
            shadow={'shadow_id':shadow_id,'artifact_id':aid,'stream':stream,'created_at':stamp,
                    'champion_generation':champion['generation_id'] if champion else None,
                    'holdout_fingerprint':digest(result),'automatic_eligible':eligible['automatic_eligible']}
            repo.append('shadow_runs',shadow_id,stream,shadow,stamp,artifact_id=aid)
            self.event(aid,stream,'SHADOW_RUNNING',stamp)
            return {'status':'SHADOW_RUNNING','cycle_id':cycle_id,'shadow_id':shadow_id,'artifact_id':aid}

    def event(self, artifact_id: str, stream: str, status: str, now: str, **extra: object) -> None:
        value={'artifact_id':artifact_id,'status':status,'created_at':now,**extra}
        self.repository.append('candidate_events',digest(value),stream,value,now,artifact_id=artifact_id)
