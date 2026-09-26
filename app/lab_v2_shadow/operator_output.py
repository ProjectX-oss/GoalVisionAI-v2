"""Bounded stdout projection; immutable evidence remains owned by the cycle."""
from __future__ import annotations

from datetime import datetime
import re

from app.real_match_lab_analysis.fingerprint import fingerprint

SCHEMA_VERSION = 'goalvision-lab-v2-operator-cycle-v1'
COUNTERS = (
    'publication_attempt_count', 'telegram_sends', 'fixtures_discovered',
    'current_odds_fixtures', 'candidate_markets_evaluated', 'early_candidate_count',
    'final_review_candidate_count', 'ready_candidate_count', 'api_calls_consumed',
)
DELIVERY_FLAGS = (
    'claim_persisted', 'transport_attempted', 'acknowledgement_received',
    'receipt_persisted', 'reconciliation_required', 'unknown_marker_persisted', 'sent',
)


def _code(value: object) -> str | None:
    # Only machine codes, never arbitrary text, exception messages or URLs.
    return value if isinstance(value, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,95}', value) else None


def _identity(value: object) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', value) else None


def _integer(value: object) -> int | None:
    return value if type(value) is int and abs(value) < 10**20 else None


def _chat_id(value: object) -> str | int | None:
    if isinstance(value, str) and re.fullmatch(r'-?[0-9]{1,20}', value):
        return value
    return _integer(value)


def _timestamp(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return None
    return value


def _failure(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    result = {key: _code(value.get(key)) for key in ('stage', 'code', 'cleanup') if key in value}
    for key in ('kind', 'prediction_id'):
        if key in value:
            result[key] = _identity(value[key])
    lifecycle = value.get('lifecycle_failure')
    if isinstance(lifecycle, dict):
        result['lifecycle_failure'] = {key: _code(lifecycle.get(key)) for key in ('stage', 'code', 'kind')}
    return result


def _delivery(value: dict) -> dict:
    result = {key: _identity(value.get(key)) for key in ('kind', 'prediction_id')}
    result.update({key: _code(value.get(key)) for key in (
        'stage', 'transport_failure_kind', 'persistence_failure', 'status',
    )})
    result.update({key: value.get(key) is True for key in DELIVERY_FLAGS})
    acknowledgement = value.get('acknowledgement')
    result['acknowledgement'] = ({
        'chat_id': _chat_id(acknowledgement.get('chat_id')),
        'message_id': _integer(acknowledgement.get('message_id')),
    } if isinstance(acknowledgement, dict) else None)
    # Preserve the existing receipt aliases for operator tooling.
    for key, convert in (('chat_id', _chat_id), ('message_id', _integer), ('sent_at_utc', _timestamp)):
        if key in value:
            result[key] = convert(value[key])
    return result


def operator_cycle_summary(report: dict[str, object]) -> dict[str, object]:
    """Project one cycle without mutating it or truncating delivery records.

    Size is fixed apart from service delivery invocations. Each invocation keeps
    every reconciliation fact, including successes before a later batch failure.
    Report/provider/candidate dictionaries are never copied into this contract.
    """
    paused = report.get('discovery_state') == 'NIGHT_DISCOVERY_PAUSED'
    publication = report.get('controlled_publication') or {}
    persistence = report.get('publication_cycle_persistence') or {}
    evaluated_at = _timestamp(report.get('evaluated_at_utc'))
    identity = None
    if evaluated_at is not None:
        clock = datetime.fromisoformat(evaluated_at)
        identity = ('lab-v2-night-' + fingerprint(clock) if paused else 'lab-v2-cycle-' + fingerprint((
            clock, report.get('fixtures_discovered'), report.get('api_calls_consumed'),
        )))
    result = {
        'schema_version': SCHEMA_VERSION,
        'cycle_id': identity,
        'evaluated_at_utc': evaluated_at,
        'analysis_status': _code(report.get('analysis_status')) or ('SKIPPED' if paused else 'UNKNOWN'),
        'delivery_status': _code(report.get('delivery_status')) or ('NOT_REQUESTED' if paused else 'UNKNOWN'),
        'analysis_mode': _code(report.get('analysis_mode')),
        'mode': _code(report.get('mode')),
        'publication_requested': report.get('publication_requested') is True,
        'publication_enabled': report.get('publication_enabled') is True,
        'telegram_transport_constructed': report.get('telegram_transport_constructed') is True,
        'publication_cycle_persistence': {
            'persisted': persistence.get('persisted') if type(persistence.get('persisted')) is bool else None,
        },
        # Preserve the failure signal and exit semantics, never raw exception text.
        'terminal_error': {'code': 'CYCLE_TERMINAL_ERROR'} if report.get('terminal_error') else None,
    }
    if 'code' in persistence:
        result['publication_cycle_persistence']['code'] = _code(persistence['code'])
    result.update({key: _integer(report.get(key)) or 0 for key in COUNTERS})
    result['controlled_publication'] = {
        'reason': _code(publication.get('reason')) or ('NIGHT_DISCOVERY_PAUSED' if paused else None),
        'status': _code(publication.get('status')) or result['delivery_status'],
        'send_attempted': publication.get('send_attempted') is True,
        'publication_attempt_count': _integer(publication.get('publication_attempt_count')) or 0,
        'singles_sent': _integer(publication.get('singles_sent')) or 0,
        'combos_sent': _integer(publication.get('combos_sent')) or 0,
        'failure': _failure(publication.get('failure')),
        'deliveries': [_delivery(item) for item in publication.get('deliveries', ())],
    }
    return result
