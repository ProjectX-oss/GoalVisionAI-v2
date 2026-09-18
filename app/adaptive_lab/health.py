"""Read-only production health: operational silence is distinct from model rejection."""
from __future__ import annotations
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import json
import sqlite3
import subprocess
from .contracts import digest,utc


def cycle_health(report: dict, *, started: datetime, completed: datetime) -> dict:
    """Compact, deterministic internal health summary with no messaging dependency."""
    rows=report.get('candidate_markets',[])
    quota=report.get('adaptive_quota_budget') or {}
    failures=report.get('terminal_error') or report.get('error')
    result='FAILED' if failures else 'DEGRADED' if quota.get('status') in {
        'REDUCED_TO_PRESERVE_QUOTA','QUOTA_UNAVAILABLE_STOP_AFTER_STATUS'} else 'HEALTHY'
    return {'started_at':utc(started).isoformat(),'completed_at':utc(completed).isoformat(),
            'result':result,'failure':failures,'evidence_at':report.get('evaluated_at_utc'),'provider_calls':report.get('api_calls_consumed',0),
            'provider_rows':report.get('provider_fixture_rows',0),
            'fixtures':report.get('fixtures_discovered',0),
            'fixtures_considered':report.get('fixtures_considered_for_evaluation',0),
            'fixtures_evaluated':report.get('throughput',{}).get('fixtures_scored',len({r.get('fixture_id') for r in rows})),
            'odds_fixtures':report.get('current_odds_fixtures',0),
            'markets':report.get('candidate_markets_evaluated',len(rows)),
            'lanes':dict(Counter(r.get('candidate_lane','UNKNOWN') for r in rows)) if rows else
                dict(sum((Counter(g.get('lanes',{})) for g in report.get('grouped_throughput',{}).get('competition_profile',{}).values()),Counter())),
            'tracking':report.get('global_state_counts',{}).get('TRACKING',0),
            'readiness_lanes':report.get('readiness_lanes',{}),
            'ready':report.get('ready_candidate_count',0),'published':report.get('telegram_sends',0),
            'rejections':report.get('rejection_reasons',{}),'fixture_blockers':report.get('fixture_reason_counts',{}),
            'readiness_blockers':report.get('readiness_reasons',{}),'quota':quota,
            'quota_remaining':report.get('current_remaining_daily_quota'),
            'publication':report.get('controlled_publication',{}),'LIVE':'DISABLED'}


def persist_health(repository: object, report: dict, *, started: datetime, completed: datetime) -> dict:
    value=cycle_health(report,started=started,completed=completed)
    repository.append('cycle_health',digest(value),'PREMATCH',value,value['completed_at'])
    return value


def timer_state(unit: str) -> dict:
    """Read systemd properties only; this function cannot start/stop a unit."""
    try:
        r=subprocess.run(['systemctl','show',unit,'--property=ActiveState,UnitFileState,Result,ExecMainStatus,ExecMainStartTimestamp,ExecMainExitTimestamp,LastTriggerUSec,NextElapseUSecRealtime'],
                         capture_output=True,text=True,timeout=5,check=False)
        return dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line)
    except (OSError,subprocess.TimeoutExpired):
        return {'status':'SYSTEMD_UNAVAILABLE'}


def persisted_cycles(path: Path, *, since: str) -> dict:
    """Read only existing immutable summaries; never hydrate the entire discovery DB."""
    if not path.is_file(): return {'discovery':[],'publication_cycles':0,'published':0}
    c=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        c.execute('PRAGMA query_only=ON')
        values=[]
        for stamp,body in c.execute("SELECT created_at_utc,document_json FROM lab_v2_shadow_evidence WHERE kind='rehearsal' AND created_at_utc>=? ORDER BY created_at_utc",(since,)):
            r=json.loads(body)
            value=cycle_health(r,started=utc(stamp),completed=utc(stamp))
            value['published']=None # Publication happens after the immutable discovery summary.
            values.append(value)
        receipts=[json.loads(row[0]) for row in c.execute("SELECT document_json FROM lab_v2_shadow_evidence WHERE kind='publication_cycle' AND created_at_utc>=? ORDER BY created_at_utc",(since,))]
        # Counts remain separate: do not fabricate exact joins without a cycle key.
        return {'discovery':values,'publication_cycles':len(receipts),
                'published':sum(r.get('telegram_sends',0) for r in receipts)}
    finally:c.close()


def status(repository: object, ledger: object, shadow_database: Path, *, now: datetime) -> dict:
    from .policy import eligibility
    from .metrics import metrics
    from .governance import Governance
    from app.lab_combo.settlement import single_statistics,statistics
    rows=repository.all('learning_observations','PREMATCH')
    today=utc(now).replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
    legacy=persisted_cycles(shadow_database,since=today) or {'discovery':[],'publication_cycles':0,'published':0}
    health=repository.all('cycle_health','PREMATCH')
    recent=[h for h in health if h['started_at']>=today]
    combined={h.get('evidence_at') or h['started_at']:h for h in legacy['discovery']}
    combined.update({h.get('evidence_at') or h['started_at']:h for h in recent})
    values=sorted(combined.values(),key=lambda h:h['started_at'])
    blockers=Counter()
    for h in values:blockers.update(h['rejections'])
    last=health[-1] if health else values[-1] if values else None
    research=repository.all('learning_cycles','PREMATCH')
    from app.lab_combo.publication_window import window_status
    from .weekly import statistics as weekly_statistics,week_bounds,next_scheduled
    receipts=repository.all('weekly_receipts','PREMATCH')
    weekly=weekly_statistics(ledger,week_start=week_bounds(now)[0],as_of=now)
    return {'PUBLICATION_WINDOW':window_status(now),
      'WEEKLY_REPORT':{'last_sent':receipts[-1] if receipts else None,
        'next_scheduled':next_scheduled(now).isoformat(),'statistics':weekly,
        'timer':timer_state('goalvision-lab-weekly-stats.timer')},
      'PREMATCH_TIMER':timer_state('goalvision-lab-v2-discover.timer'),
      'PREMATCH_SERVICE':timer_state('goalvision-lab-v2-discover.service'),
      'last_discovery':last,'last_successful_discovery':next((h for h in reversed(values) if h['result']!='FAILED'),None),
      'today':{'timezone':'UTC','cycles':len(values),'provider_fixtures':sum(h['provider_rows'] for h in values),
        'evaluated_fixtures':sum(h['fixtures_evaluated'] for h in values),'markets':sum(h['markets'] for h in values),
        'tracking':sum(h['tracking'] for h in values),
        'lanes':dict(sum((Counter(h['lanes']) for h in values),Counter())),
        'ready':sum(h['ready'] for h in values),'published':legacy['published'],
        'top_rejection_reasons':blockers.most_common(10),'new_health_records':len(recent)},
      'raw_product_statistics':single_statistics(ledger),'valid_learning_metrics':metrics(rows,'PREMATCH'),
      'champion':repository.champion('PREMATCH'),'learning':eligibility(rows,'PREMATCH',now,
        previous=next((c for c in reversed(research) if c.get('kind')!='REVIEWED_BOOTSTRAP'),None)),
      'last_learning_cycle':research[-1] if research else None,
      'shadow':[Governance(repository).evidence(r['shadow_id']) for r in repository.all('shadow_runs','PREMATCH')],
      'COMBO':statistics(ledger,published_only=True),'COMBO_TIMER':timer_state('goalvision-lab-combo-settle.timer'),
      'OBSERVER_TIMER':timer_state('goalvision-adaptive-learning-observer.timer'),
      'LEARNING_TIMER':timer_state('goalvision-adaptive-learning.timer'),
      'LIVE':'DISABLED','LIVE_TIMER':timer_state('goalvision-live-lab.timer')}
