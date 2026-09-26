"""Read-only hypothetical single cohorts from immutable confirmed publications."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.adaptive_lab.contracts import utc
from app.real_match_lab_analysis.models import LAB_CHAT_ID
from .origin import SELECTOR, is_labelled


def _totals(rows: list[dict]) -> dict:
    counts = {key: sum(r['status'] == key for r in rows) for key in ('PENDING', 'WON', 'LOST', 'VOID')}
    settled = counts['WON'] + counts['LOST'] + counts['VOID']
    pnl = sum((Decimal(r['net_units']) for r in rows if r['net_units'] is not None), Decimal(0))
    binary = counts['WON'] + counts['LOST']
    return {'published': len(rows), 'pending': counts.pop('PENDING'), **counts,
            'settled': settled, 'sample_size': len(rows), 'flat_unit_pnl': str(pnl),
            'flat_unit_roi': str(pnl / settled) if settled else None,
            'roi_denominator_units': settled, 'roi_convention': '1u per settled single including VOID; pending excluded',
            'hit_rate': str(Decimal(counts['WON']) / binary) if binary else None}


def single_cohorts(ledger: object, *, start: datetime, end: datetime, as_of: datetime) -> dict:
    """Publication interval [start,end); no inference from labels or outcome history.

    Cohorts may overlap. The union total counts each confirmed economic selection
    once; duplicate confirmed receipts are exposed and block a combined total.
    Historical selector IDs are a separate dated segment, never a context model.
    """
    rows, historical, diagnostics = [], [], []
    for prediction in ledger.all('single_prediction'):
        pid = prediction['prediction_id']
        if prediction.get('stream') in {'LIVE', 'OFFICIAL'} or prediction.get('product') in {'LIVE', 'OFFICIAL'}:
            continue
        labelled = is_labelled(prediction)
        historical_selector = pid.startswith('lab-v2-single-') and ledger.get('v2_segmentation', pid)
        if not labelled and not historical_selector:
            continue
        receipt = ledger.get('receipt', 'single_prediction:' + pid)
        if not (receipt and receipt.get('status') == 'SENT' and receipt.get('sent') is True
                and str(receipt.get('chat_id')) == str(LAB_CHAT_ID)
                and type(receipt.get('message_id')) is int and receipt['message_id'] > 0
                and receipt.get('sent_at_utc')):
            continue
        published = utc(receipt['sent_at_utc'])
        if not utc(start) <= published < utc(end) or published > utc(as_of):
            continue
        result = ledger.get('single_settlement', pid)
        if result and utc(result['settled_at_utc']) > utc(as_of):
            result = None
        status = result['status'] if result else 'PENDING'
        if status not in {'PENDING', 'WON', 'LOST', 'VOID'}:
            raise ValueError('INVALID_SINGLE_OUTCOME')
        odds = Decimal(prediction['captured_odds'])
        if not odds.is_finite() or odds <= 1:
            raise ValueError('INVALID_CAPTURED_ODDS')
        net = odds - 1 if status == 'WON' else Decimal(-1) if status == 'LOST' else Decimal(0)
        if result and Decimal(result['unit_result']) != net:
            raise ValueError('SETTLEMENT_ACCOUNTING_CONFLICT')
        row = {'prediction_id': pid, 'economic_key': f"{prediction['fixture_id']}:{prediction['market']}",
               'published_at': receipt['sent_at_utc'], 'settled_at': result['settled_at_utc'] if result else None,
               'captured_odds': str(odds), 'status': status,
               'net_units': str(net) if result else None, 'origin': prediction.get('selection_origin')}
        if labelled:
            rows.append(row)
        elif historical_selector:
            historical.append(row)
    keys = [r['economic_key'] for r in rows]
    duplicate = sorted({key for key in keys if keys.count(key) > 1})
    if duplicate:
        diagnostics.append({'status': 'DUPLICATE_CONFIRMED_ECONOMIC_SELECTION', 'keys': duplicate})
    origins = sorted({name for r in rows for name in r['origin']['origins']})
    return {'version': 'LAB_SINGLE_COHORTS_V1', 'start': utc(start).isoformat(), 'end_exclusive': utc(end).isoformat(),
            'as_of': utc(as_of).isoformat(), 'accounting': 'HYPOTHETICAL_SIGNALS_NOT_REALIZED_CASH',
            'forward_union': _totals(rows) if not duplicate else None,
            'cohorts_overlap_do_not_sum': {name: _totals([r for r in rows if name in r['origin']['origins']]) for name in origins},
            'selector_exclusive': _totals([r for r in rows if r['origin']['origins'] == [SELECTOR]]),
            'multi_origin_overlap': _totals([r for r in rows if len(set(r['origin']['origins'])) > 1]),
            'context_linked_observation_only': _totals([r for r in rows if r['origin'].get('context')]),
            'independent_football_context_model': _totals([]),
            'historical_selector_segment': _totals(historical),
            'records': rows, 'diagnostics': diagnostics}


def public_single_snapshot(ledger: object, *, as_of: datetime) -> dict:
    """Freeze all-time confirmed labelled SINGLE evidence using existing formulas.

    Records and cutoffs stay internal for reproduction. Duplicate economic
    selections fail closed through the existing cohort contract.
    """
    cohort = single_cohorts(ledger, start=datetime.min.replace(tzinfo=timezone.utc),
                           end=datetime.max.replace(tzinfo=timezone.utc), as_of=as_of)
    if cohort['forward_union'] is None:
        raise ValueError('DUPLICATE_CONFIRMED_ECONOMIC_SELECTION')
    return {'version': 'LAB_V2_PUBLIC_SINGLE_STATISTICS_V1', 'as_of': cohort['as_of'],
            'totals': cohort['forward_union'], 'records': cohort['records']}
