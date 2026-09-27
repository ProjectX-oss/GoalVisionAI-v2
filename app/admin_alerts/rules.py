"""Rules consume existing evidence without importing a PREMATCH runner."""
from __future__ import annotations

from .model import DISCOVERY, SCHEMA, Event, coverage, epoch, identity


def compact(record: dict, reference: str, now: float, *, invocation: str = 'UNKNOWN') -> list[Event]:
    """Interpret the deployed compact contract; zero READY is never a fault."""
    if record.get('schema_version') != SCHEMA:
        return [coverage('stdout', now, 'UNSUPPORTED_RECORD')]
    if (not isinstance(record.get('publication_cycle_persistence', {}), (dict, type(None))) or
            not isinstance(record.get('controlled_publication', {}), (dict, type(None)))):
        return [coverage('stdout', now, 'INVALID_RECORD_SHAPE')]
    publication_shape = record.get('controlled_publication') or {}
    if (not isinstance(publication_shape.get('deliveries', []), (list, type(None))) or
            not isinstance(publication_shape.get('failure'), (dict, type(None)))):
        return [coverage('stdout', now, 'INVALID_RECORD_SHAPE')]
    cycle = identity(record.get('cycle_id'))
    stamp = epoch(record.get('evaluated_at_utc'))
    if not stamp:
        return [coverage('stdout', now, 'MISSING_TIMESTAMP')]
    if stamp > now + 300:
        return [coverage('stdout', now, 'SOURCE_CLOCK_SKEW')]
    events: list[Event] = []

    def add(rule: str, obj: str = 'pipeline', severity: int = 2, facts: dict | None = None,
            healthy: bool = False) -> None:
        events.append(Event(DISCOVERY, rule, obj, cycle if cycle != 'UNKNOWN' else reference,
                            stamp, reference, severity, invocation, cycle, facts or {}, healthy))

    if record.get('terminal_error') or record.get('analysis_status') == 'FAILED':
        add('ANALYSIS_FAILURE')
    elif record.get('analysis_status') in ('OK', 'SUCCESS', 'COMPLETED', 'HEALTHY'):
        add('ANALYSIS_FAILURE', healthy=True)
    persistence = record.get('publication_cycle_persistence') or {}
    if persistence.get('persisted') is False:
        add('CYCLE_PERSISTENCE', severity=3)
    publication = record.get('controlled_publication') or {}
    deliveries = publication.get('deliveries') or []
    for item in deliveries[:200]:
        if not isinstance(item, dict):
            events.append(coverage('stdout', now, 'INVALID_DELIVERY'))
            continue
        obj = identity(item.get('prediction_id'))
        if obj == 'UNKNOWN':
            obj = cycle + '-unknown-' + str(deliveries.index(item))
        facts = {k: item.get(k) is True for k in ('transport_attempted', 'acknowledgement_received',
                  'receipt_persisted', 'reconciliation_required')}
        uncertain = (facts['reconciliation_required'] or
                     (facts['acknowledgement_received'] and not facts['receipt_persisted']) or
                     (facts['transport_attempted'] and not facts['receipt_persisted']))
        if uncertain:
            add('DELIVERY_UNCERTAIN', obj, 3, facts)
        elif item.get('persistence_failure'):
            add('CYCLE_PERSISTENCE', obj, 3, facts)
        elif item.get('receipt_persisted') is True:
            add('DELIVERY_UNCERTAIN', obj, facts=facts, healthy=True)
            add('DELIVERY_FAILURE', obj, facts=facts, healthy=True)
        if item.get('status') in ('FAILED', 'DEGRADED') and not uncertain:
            add('DELIVERY_FAILURE', obj, facts=facts)
    if len(deliveries) > 200:
        events.append(coverage('stdout', now, 'DELIVERY_RECORD_LIMIT'))
    if (record.get('delivery_status') in ('FAILED', 'DEGRADED', 'UNKNOWN') or publication.get('failure')) and not any(
            e.rule in ('DELIVERY_FAILURE', 'DELIVERY_UNCERTAIN') and not e.healthy for e in events):
        add('DELIVERY_FAILURE', identity((publication.get('failure') or {}).get('prediction_id')))
    # Only classify fixed codes. Arbitrary exception text is discarded before retention.
    for failure in (publication.get('failure'), persistence, record.get('terminal_error')):
        if isinstance(failure, dict):
            events.extend(code_events(failure.get('code'), DISCOVERY, cycle, stamp, reference, invocation=invocation))
    return events


CODE_RULES = {
    'OBSERVATION_CONSTRUCTION_FAILED': ('OBSERVATION_FAILURE', 3, 1),
    'OBSERVATION_FINISH_FAILED': ('OBSERVATION_FAILURE', 3, 1),
    'INTEGRITY_FAILURE': ('INTEGRITY_FAILURE', 3, 1),
    'SCHEMA_MISMATCH': ('INTEGRITY_FAILURE', 3, 1),
    'IDENTITY_MISMATCH': ('INTEGRITY_FAILURE', 3, 1),
    'STATISTICS_INTEGRITY_BLOCKER': ('INTEGRITY_FAILURE', 3, 1),
    'SETTLEMENT_INTEGRITY_BLOCKER': ('INTEGRITY_FAILURE', 3, 1),
    'LAB_BOT_IDENTITY_MISMATCH': ('INTEGRITY_FAILURE', 3, 1),
    'SETTLEMENT_INTEGRITY_BLOCKED': ('INTEGRITY_FAILURE', 3, 1),
    'CONFLICTING_FIXTURE_RESULTS': ('INTEGRITY_FAILURE', 3, 1),
    'AUTHENTICATION_FAILED': ('AUTH_FAILURE', 3, 1),
    'PROVIDER_FAILURE': ('PROVIDER_FAILURE', 2, 2),
    'RATE_LIMITED': ('PROVIDER_FAILURE', 2, 2),
    'QUOTA_DB_CONTENTION_EXHAUSTED': ('QUOTA_DB_CONTENTION', 3, 1),
    'DATABASE_LOCKED': ('DATABASE_LOCK', 2, 2),
    'QUOTA_UNAVAILABLE_STOP_AFTER_STATUS': ('QUOTA_FAILURE', 2, 2),
    'UNUSABLE_DATA': ('QUOTA_FAILURE', 2, 2),
}


def code_events(code: object, service: str, occurrence: str, stamp: float, source: str, *, invocation: str = 'UNKNOWN') -> list[Event]:
    if not isinstance(code, str) or code not in CODE_RULES:
        return []
    rule, severity, debounce = CODE_RULES[code]
    return [Event(service, rule, 'pipeline', occurrence, stamp, source, severity,
                  invocation=invocation, facts={'code': code}, debounce=debounce)]


def completed_health(value: dict, service: str, key: str, now: float, source: str) -> list[Event]:
    """Persisted health is independent evidence, never joined to the latest stdout."""
    stamp = epoch(value.get('completed_at') or value.get('created_at')) or now
    codes = [(value.get('quota') or {}).get('status'), value.get('code')]
    failure = value.get('failure')
    if isinstance(failure, dict):
        codes.append(failure.get('code'))
    events = [e for code in codes for e in code_events(code, service, key, stamp, source)]
    if value.get('result') == 'FAILED' and not events:
        events.append(Event(service, 'ANALYSIS_FAILURE', 'pipeline', key, stamp, source))
    publication = value.get('publication')
    if isinstance(publication, dict):
        projection = {'schema_version': SCHEMA, 'cycle_id': 'health-' + key,
            'evaluated_at_utc': value.get('evidence_at') or value.get('completed_at'),
            'analysis_status': 'UNKNOWN', 'delivery_status': publication.get('status', 'NOT_REQUESTED'),
            'controlled_publication': publication}
        events.extend(compact(projection, source, now))
    # An explicit usable completed run resets only recoverable health rules.
    if value.get('result') == 'HEALTHY':
        for rule in ('PROVIDER_FAILURE', 'DATABASE_LOCK', 'QUOTA_FAILURE', 'ANALYSIS_FAILURE'):
            events.append(Event(service, rule, 'pipeline', key, stamp, source, healthy=True))
    return events
