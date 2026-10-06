"""Read-only, as-of Watch reconciliation. No coordinator, fit, provider or transport."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import timedelta
import json
from pathlib import Path
import time
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.adaptive_lab.calendar_audit import read_snapshot, readiness_report
from app.adaptive_lab.calendar_monitor import load_plan
from app.adaptive_lab.contracts import digest, utc, learning_source
from app.adaptive_lab.features import FEATURE_SCHEMA
from app.adaptive_lab.observations import ReadOnlyLedger
from app.adaptive_lab.performance import performance_snapshot
from app.adaptive_lab.policy import eligibility
from app.adaptive_lab.repository import AuditRepository

GOVERNANCE = ('learning_cycles', 'training_runs', 'model_artifacts', 'validation_results',
              'holdout_results', 'shadow_runs', 'shadow_predictions', 'shadow_settlements',
              'promotion_gates', 'candidate_comparisons', 'activation_events', 'rollback_events')


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n')


def add_bias(value: dict) -> dict:
    n = value.get('probability_observations', 0)
    value['calibration_bias_predicted_minus_observed'] = (
        sum(b['n']*b['error'] for b in value.get('reliability_bins', []))/n if n else None)
    return value


class Filtered:
    def __init__(self, ledger, predicate):
        self.ledger, self.predicate = ledger, predicate

    def get(self, kind, identity):
        return self.ledger.get(kind, identity)

    def all(self, kind):
        values = self.ledger.all(kind)
        return [v for v in values if self.predicate(v)] if kind in {'single_prediction', 'prediction'} else values


def cohort_name(prediction: dict, product: str) -> str:
    if product == 'COMBO':
        return prediction.get('statistics_cohort') or prediction.get('combo_selection_policy') or 'LEGACY_COMBO'
    return prediction.get('single_selection_policy') or prediction.get('policy') or 'LEGACY_SINGLE'


def quality_name(prediction: dict) -> str:
    review = prediction.get('accuracy_publication_review')
    if not isinstance(review, dict):
        return 'FROZEN_ACCURACY_REVIEW_UNAVAILABLE'
    if review.get('eligible') is True:
        return 'FROZEN_ACCURACY_REVIEW_ELIGIBLE'
    return 'FROZEN_ACCURACY_REVIEW_OTHER_OR_UNAVAILABLE'


def performance(ledger, *, now) -> dict:
    result = performance_snapshot(ledger, now=now)
    add_bias(result['SINGLE'])
    result['cohorts'] = {}
    for product, kind in (('SINGLE', 'single_prediction'), ('COMBO', 'prediction')):
        names = sorted({cohort_name(v, product) for v in ledger.all(kind)})
        result['cohorts'][product] = {}
        for name in names:
            subset = Filtered(ledger, lambda v, name=name: cohort_name(v, product) == name)
            summary = performance_snapshot(subset, now=now)[product]
            if summary['total_published']:
                result['cohorts'][product][name] = add_bias(summary)
    result['data_quality_segments'] = []
    for name in sorted({quality_name(v) for v in ledger.all('single_prediction')}):
        subset = Filtered(ledger, lambda v, name=name: quality_name(v) == name)
        summary = performance_snapshot(subset, now=now)['SINGLE']
        if summary['total_published']:
            result['data_quality_segments'].append({'state':name, **add_bias(summary)})
    result['segment_display_minimum_settled_tickets'] = 30
    result['segments_with_30_settled'] = {
        p:[add_bias(dict(v)) for v in groups if v['total_settled'] >= 30]
        for p, groups in result['segments'].items()}
    result['limitations'] = [
        'Descriptive historical mixtures are not the current policy forecast.',
        'Thirty settled tickets is a display threshold, not statistical significance.',
        'SINGLE probabilities are frozen published ensemble values, not proof of calibrated champion inference.',
        'Early COMBO losses mature before winners; pending cohorts cannot establish superiority.',
        'COMBO probabilities are never independent calibration or learning observations.',
    ]
    return result


def learning(database: Path, *, now) -> dict:
    snapshot = read_snapshot(database)
    rows = [r for r in snapshot['rows'] if utc(r['prediction_created_at']) <= now and utc(r['settled_at']) <= now]
    snapshot['rows'] = rows
    snapshot['snapshot_fingerprint'] = digest([[r['observation_id'],r['observation_fingerprint']] for r in rows])
    calendar = readiness_report(snapshot, load_plan(), now=now)
    repo = AuditRepository(database, readonly=True)
    try:
        deadline = time.monotonic()+5
        repo.connection.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
        repo.connection.execute('BEGIN')
        governance = {table:repo.connection.execute('SELECT count(*) FROM '+table+
            " WHERE stream='PREMATCH' AND created_at<=?", (now.isoformat(),)).fetchone()[0] for table in GOVERNANCE}
        champion = repo.champion('PREMATCH')
        artifact = repo.get('model_artifacts', champion['artifact_id'])
        last = repo.connection.execute("SELECT id FROM observer_runs WHERE stream='PREMATCH' AND created_at<=? ORDER BY created_at DESC LIMIT 1",(now.isoformat(),)).fetchone()
        observer = repo.get('observer_runs',last[0]) if last else None
        previous = repo.connection.execute("SELECT id FROM learning_cycles WHERE stream='PREMATCH' AND created_at<=? ORDER BY created_at DESC LIMIT 1",(now.isoformat(),)).fetchone()
        previous = repo.get('learning_cycles',previous[0]) if previous else None
        models = [v for v in repo.all('model_artifacts','PREMATCH')]
        calibrators = [v for v in models if isinstance(v.get('calibrator'),dict)]
        training_status = Counter(v.get('status','UNSPECIFIED') for v in repo.all('training_runs','PREMATCH'))
        model_families = Counter(v.get('family') or (v.get('spec') or {}).get('family','UNSPECIFIED') for v in models)
    finally:
        repo.close()
    resolved = [r for r in rows if learning_source(r) and r.get('outcome') in {'WON','LOST'}]
    return {'as_of':now.isoformat(),'champion':champion,'champion_artifact':artifact,
        'current_feature_schema':FEATURE_SCHEMA,'bootstrap_unchanged':champion.get('reason')=='BOOTSTRAP' and champion.get('previous_generation') is None,
        'learning':{'total_observations':len(rows),'resolved_eligible_observations':len(resolved),
            'independent_resolved_fixtures':len({r['fixture_id'] for r in resolved}),
            'source_product_counts':dict(Counter(r.get('source_product','SINGLE') for r in rows)),
            'eligibility':eligibility(rows,'PREMATCH',now,previous=previous)},
        'calendar':calendar,'governance_counts':governance,
        'calibration_artifacts':len(calibrators),'training_status':dict(training_status),'artifact_families':dict(model_families),
        'latest_observer':{k:observer[k] for k in ('created_at','state','LIVE','heavy_training','api_calls','telegram_sends') if observer and k in observer},
        'provider_calls':0,'telegram_sends':0,'fit_invoked':False,'holdout_evaluated':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of',required=True)
    parser.add_argument('--database',required=True,type=Path)
    parser.add_argument('--ledger',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    now=utc(args.as_of)
    args.output.mkdir(parents=True,exist_ok=True)
    learn=learning(args.database,now=now)
    write(args.output/'learning_champion.json',learn)
    ledger=ReadOnlyLedger(args.ledger)
    try:
        perf=performance(ledger,now=now)
        # Fingerprint authoritative evidence without disclosing private recipient/message content.
        perf['source_evidence_fingerprint']=digest([list(r) for r in ledger.connection.execute(
            "SELECT kind,identity,fingerprint FROM evidence WHERE kind IN ('single_prediction','prediction','receipt','single_settlement','settlement') ORDER BY kind,identity")])
        perf['claims_without_receipt']=sum(ledger.get('receipt',r[0]) is None for r in ledger.connection.execute("SELECT identity FROM evidence WHERE kind='claim'"))
        write(args.output/'performance.json',perf)
    finally:ledger.close()
    print(json.dumps({'status':'READ_ONLY_SNAPSHOT_COMPLETE','as_of':now.isoformat(),
        'learning':learn['learning'],'partitions':learn['calendar']['calendar_candidate']['counts'],
        'independent_partition_fixtures':learn['calendar']['calendar_candidate']['independent_fixture_counts'],
        'SINGLE':perf['SINGLE'],'COMBO':perf['COMBO'],'cohorts':perf['cohorts']},sort_keys=True))


if __name__=='__main__':main()
