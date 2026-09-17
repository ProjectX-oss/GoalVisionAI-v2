"""Current-date pagination accounting; absence is established only by a stable sweep."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from enum import StrEnum

from .market_consensus import _market


class OddsCoverageStatus(StrEnum):
    """Stable external vocabulary; detailed legacy reasons remain available."""
    COMPLETE = 'ODDS_COMPLETE'
    BUDGET_LIMITED = 'ODDS_BUDGET_LIMITED'
    PROVIDER_ERROR = 'ODDS_PROVIDER_ERROR'
    TIMEOUT = 'ODDS_TIMEOUT'
    RATE_LIMIT = 'ODDS_RATE_LIMIT'
    MALFORMED_PAGE = 'ODDS_MALFORMED_PAGE'
    PAGE_TOTAL_DRIFT = 'ODDS_PAGE_TOTAL_DRIFT'
    RESTART_GAP = 'ODDS_RESTART_GAP'
    UNKNOWN_INCOMPLETE = 'ODDS_UNKNOWN_INCOMPLETE'


@dataclass
class DateOddsCoverage:
    """Per-cycle mutable request ledger, never a cache of reusable quotes."""

    previous_maximum: int = 1
    restart_gap: bool = False
    attempted: set[int] = field(default_factory=set)
    totals: set[int] = field(default_factory=set)
    pages: set[int] = field(default_factory=set)
    errors: set[str] = field(default_factory=set)

    def observe(self, page: int, payload: Any) -> bool:
        self.attempted.add(page)
        if not isinstance(payload, dict) or not isinstance(payload.get('response'), list):
            self.errors.add('ODDS_RESPONSE_MALFORMED')
            return False
        if payload.get('errors'):
            code = (payload['errors'].get('request') if isinstance(payload['errors'], dict) else None)
            self.errors.add(code if code in {'ODDS_QUOTA_OR_REQUEST_LIMIT', 'ODDS_API_TIMEOUT', 'ODDS_RESPONSE_MALFORMED'} else 'ODDS_API_ERROR')
            return False
        paging = payload.get('paging')
        if (not isinstance(paging, dict) or type(paging.get('current')) is not int
                or type(paging.get('total')) is not int or paging['total'] < 1):
            self.errors.add('ODDS_PAGINATION_METADATA_INVALID')
            return False
        if paging['current'] != page:
            self.errors.add('ODDS_PAGINATION_PAGE_MISMATCH')
            return False
        self.pages.add(page)
        self.totals.add(paging['total'])
        return True

    @property
    def maximum(self) -> int:
        return max(self.previous_maximum, max(self.totals, default=1))

    def reason(self, *, reserve_limited: bool = False) -> str | None:
        if self.errors:
            return sorted(self.errors)[0]
        if len(self.totals) > 1:
            return 'ODDS_PAGINATION_CHANGED_DURING_SWEEP'
        if set(range(1, self.maximum + 1)) - self.pages:
            return ('ODDS_FINAL_REVIEW_RESERVE_LIMITED_PAGINATION' if reserve_limited
                    else 'ODDS_DISCOVERY_BUDGET_LIMITED_PAGINATION')
        return None

    def document(self) -> dict:
        reason = self.reason()
        canonical = ('ODDS_COMPLETE' if reason is None else
                     'ODDS_PAGE_TOTAL_DRIFT' if len(self.totals) > 1 else
                     'ODDS_TIMEOUT' if 'ODDS_API_TIMEOUT' in self.errors else
                     'ODDS_RATE_LIMIT' if 'ODDS_QUOTA_OR_REQUEST_LIMIT' in self.errors else
                     'ODDS_MALFORMED_PAGE' if any('MALFORMED' in r or 'METADATA' in r or 'MISMATCH' in r for r in self.errors) else
                     'ODDS_PROVIDER_ERROR' if self.errors else
                     'ODDS_RESTART_GAP' if self.restart_gap else 'ODDS_BUDGET_LIMITED')
        return {'maximum_advertised_total': self.maximum, 'coverage_status': OddsCoverageStatus(canonical).value,
                'incomplete_reason': reason, 'failed_pages': sorted(self.attempted - self.pages),
                'advertised_totals': sorted(self.totals), 'requested_pages': sorted(self.attempted), 'valid_pages': sorted(self.pages),
                'unrequested_pages': sorted(set(range(1, self.maximum + 1)) - self.attempted),
                'errors': sorted(self.errors), 'stable_complete_sweep': self.reason() is None}


def quote_absence_reason(row: dict, allowed: frozenset[int] | None) -> str:
    """Explain raw filtering separately from provider absence and normalization."""
    books = row.get('bookmakers')
    if not isinstance(books, list):
        return 'ODDS_RESPONSE_MALFORMED'
    if not books:
        return 'ODDS_RECORD_WITHOUT_BOOKMAKERS'
    books = [b for b in books if isinstance(b, dict) and (allowed is None or b.get('id') in allowed)]
    if not books:
        return 'ODDS_BOOKMAKER_FILTER_REMOVED_ALL'
    values = [(b.get('name', ''), v) for book in books for b in _objects(book.get('bets'))
              for v in _objects(b.get('values'))]
    if not values:
        return 'ODDS_RECORD_WITHOUT_QUOTES'
    if not any(_market(str(name), str(v.get('value', ''))) for name, v in values):
        return 'ODDS_MARKET_FILTER_REMOVED_ALL'
    return 'ODDS_QUOTES_INVALID_OR_INCOMPLETE'


def _objects(value: Any) -> tuple[dict, ...]:
    return tuple(item for item in value if isinstance(item, dict)) if isinstance(value, list) else ()
