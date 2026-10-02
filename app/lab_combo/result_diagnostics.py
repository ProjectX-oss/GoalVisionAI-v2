"""Bounded, credential-free evidence from already scheduled result requests."""
from __future__ import annotations

from datetime import datetime, timezone


VERSION = 'LAB_UNRESOLVED_RESULT_V1'
MAX_RECORDS = 100
STATUSES = frozenset(('TBD', 'NS', '1H', 'HT', '2H', 'ET', 'BT', 'P', 'SUSP',
                      'INT', 'FT', 'AET', 'PEN', 'PST', 'CANC', 'ABD', 'AWD', 'WO', 'LIVE'))


def _timestamp(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(timezone.utc).isoformat() if parsed.tzinfo else None
    except ValueError:
        return None


def unresolved_result(prediction: dict, payload: object, now: datetime,
                      *, request_state: str = 'RESPONSE_RECEIVED') -> dict:
    """Classify without persisting raw errors, arbitrary provider text or scores."""
    frozen = _timestamp(prediction.get('kickoff_utc'))
    diagnostic = {'fixture_id': int(prediction['fixture_id']),
                  'frozen_kickoff_utc': frozen, 'observed_at_utc': now.isoformat(),
                  'provider_status': None, 'provider_kickoff_utc': None,
                  'schedule_changed': False, 'reason': 'MALFORMED_RESPONSE'}
    if request_state in {'REQUEST_FAILED', 'CALL_BUDGET_EXHAUSTED'}:
        return {**diagnostic, 'reason': request_state}
    if not isinstance(payload, dict):
        return diagnostic
    if payload.get('errors'):
        return {**diagnostic, 'reason': 'PROVIDER_REPORTED_ERROR'}
    rows = payload.get('response')
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        return {**diagnostic, 'reason': 'FIXTURE_RESPONSE_NOT_UNIQUE'}
    fixture = rows[0].get('fixture')
    if not isinstance(fixture, dict) or str(fixture.get('id')) != str(prediction['fixture_id']):
        return {**diagnostic, 'reason': 'FIXTURE_ID_MISMATCH'}
    status_doc = fixture.get('status')
    status = status_doc.get('short') if isinstance(status_doc, dict) else None
    status = status if isinstance(status, str) and status in STATUSES else 'UNKNOWN'
    kickoff = _timestamp(fixture.get('date'))
    changed = bool(kickoff and frozen and kickoff != frozen)
    reason = ('POSTPONED' if status == 'PST' else 'NOT_STARTED' if status in {'NS', 'TBD'}
              else 'FULLTIME_SCORE_UNAVAILABLE' if status in {'FT', 'AET', 'PEN'}
              else 'NONTERMINAL_OR_UNSUPPORTED_STATUS')
    if kickoff and datetime.fromisoformat(kickoff) > now:
        reason = 'RESCHEDULED_FUTURE_KICKOFF' if changed else 'FUTURE_PROVIDER_KICKOFF'
    return {**diagnostic, 'provider_status': status, 'provider_kickoff_utc': kickoff,
            'schedule_changed': changed, 'reason': reason}
