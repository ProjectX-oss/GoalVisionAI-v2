"""Versioned, reviewed output contracts; independent of incident identity version."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .model import DISCOVERY, UNITS, SCHEMA, epoch


@dataclass(frozen=True)
class OutputContract:
    version: int
    source: str
    association: str
    description: str


CONTRACTS = {
    DISCOVERY: OutputContract(1, 'COMPACT_STDOUT', 'TIME_WINDOW_ONLY', 'operator-cycle-v1; stdout has no InvocationID'),
    UNITS[1]: OutputContract(1, 'NONE', 'UNAVAILABLE', 'settle prints final JSON to discarded stdout (StandardOutput=null)'),
    UNITS[2]: OutputContract(1, 'STRUCTURED_JOURNAL_JSON', 'EXACT_INVOCATION', 'observe final PREMATCH observer document'),
    UNITS[3]: OutputContract(1, 'STRUCTURED_JOURNAL_JSON', 'EXACT_INVOCATION', 'research final eligibility or research outcome'),
    UNITS[4]: OutputContract(1, 'STRUCTURED_JOURNAL_JSON', 'EXACT_INVOCATION', 'weekly final status and sent boolean'),
}
RESEARCH_OUTCOMES = frozenset({
    'CONCURRENT_RESEARCH_OR_CHAMPION_CHANGE', 'CHALLENGER_ALREADY_IN_SHADOW',
    'CYCLE_ALREADY_RECORDED', 'CONCURRENT_CYCLE_COMPLETED', 'EARLY_RESEARCH_COMPLETE',
    'NO_VALIDATION_CHALLENGER', 'INSUFFICIENT_FRESH_HOLDOUT', 'HOLDOUT_REJECTED', 'SHADOW_RUNNING',
})
WEEKLY_OUTCOMES = frozenset({'SENT', 'ALREADY_SENT', 'PREVIEW_ONLY',
    'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED', 'LAB_CONFIGURATION_REJECTED', 'LAB_BOT_IDENTITY_MISMATCH'})


def _split_counts(value: object) -> bool:
    return (isinstance(value, dict) and all(type(value.get(k)) is int and value[k] >= 0
            for k in ('TRAIN', 'VALIDATION', 'SEALED_HOLDOUT', 'PURGED')))


def _blocked(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(v, str) and v for v in value)


def _readiness_outcome(doc: dict) -> bool:
    """New no-training outcomes must carry their structured blocking evidence."""
    if doc.get('status') == 'RESEARCH_DATASET_NOT_READY':
        if not _blocked(doc.get('blocked_by')):
            return False
        if doc.get('split_unavailable') is True:
            return 'counts' in doc and doc['counts'] is None
        return (_split_counts(doc.get('counts')) and _split_counts(doc.get('required_minimums'))
                and isinstance(doc.get('dataset_fingerprint'), str) and bool(doc['dataset_fingerprint'])
                and isinstance(doc.get('training_contract'), dict))
    if doc.get('status') == 'CALIBRATION_DATASET_NOT_READY':
        calibration = doc.get('calibration_readiness')
        return (_split_counts(doc.get('counts')) and isinstance(calibration, dict)
                and _blocked(calibration.get('blocked_by'))
                and doc.get('research_cycle_consumed') is False and doc.get('holdout_consumed') is False)
    return False


def expected_document(unit: str, doc: dict) -> bool:
    """Recognize final artifacts, never arbitrary JSON diagnostics or provider data."""
    if unit == DISCOVERY:
        return doc.get('schema_version') == SCHEMA and bool(epoch(doc.get('evaluated_at_utc')))
    if unit == UNITS[2]:
        return (doc.get('stream') == 'PREMATCH' and bool(epoch(doc.get('created_at')))
                and all(isinstance(doc.get(k), dict) for k in ('linkage', 'state', 'metrics'))
                and doc.get('LIVE') == 'DISABLED' and doc.get('heavy_training') is False
                and doc.get('api_calls') == 0 and doc.get('telegram_sends') == 0)
    if unit == UNITS[3]:
        status = doc.get('status')
        return (_readiness_outcome(doc) or (isinstance(status, str) and status in RESEARCH_OUTCOMES) or
                (doc.get('stream') == 'PREMATCH' and type(doc.get('research_due')) is bool
                 and isinstance(doc.get('next_threshold'), dict) and isinstance(status, str)
                 and all(k in doc for k in ('stage', 'resolved', 'days_covered'))))
    if unit == UNITS[4]:
        status = doc.get('status')
        return isinstance(status, str) and status in WEEKLY_OUTCOMES and type(doc.get('sent')) is bool
    return False


def contract_report() -> dict:
    return {unit: asdict(contract) for unit, contract in CONTRACTS.items()}
