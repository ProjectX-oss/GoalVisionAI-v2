"""Allowlisted capture of already-required responses, with no provider dependency."""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from typing import Mapping

from ..fingerprint import canonical_bytes, utc
from ..source_adapter import sanitize_payload
from ..sources import PARSER, Query, SourceKind, digest, history_query, target_query, validate_retained_document
from .repository import EvidenceRepository, ImmutableConflict, Registration

CAPTURE = 'FC_DURABLE_CAPTURE_V1'
NAMESPACE = 'FC_DURABLE_SOURCE_V1'


@dataclass(frozen=True, slots=True)
class CaptureScope:
    """Explicit exact request and role; never infer current season from wall time.

    TTL is the existing collector's expiry policy, bounded by Phase B freshness.
    The audited exact-target path uses two minutes, histories six/24 hours.
    """
    query: Query
    kind: SourceKind
    ttl: timedelta

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SourceKind) or not isinstance(self.query, Query):
            raise ValueError('INVALID_CAPTURE_SCOPE')
        params = dict(self.query.parameters)
        maximum = timedelta(minutes=15) if self.kind == SourceKind.TARGET else timedelta(
            hours=6 if self.kind == SourceKind.CURRENT else 24)
        expected = target_query(params['id']) if self.kind == SourceKind.TARGET else history_query(params['league'], params['season'])
        if self.query != expected or not isinstance(self.ttl, timedelta) or not timedelta(0) < self.ttl <= maximum:
            raise ValueError('INVALID_CAPTURE_SCOPE')


@dataclass(frozen=True, slots=True)
class CaptureStatus:
    """Small secret-free diagnostic; absence/failure never supplies a source ID."""
    status: str
    registration: Registration | None = None


def prepare_source(scope: CaptureScope, payload: object, retrieval_completed_at: datetime,
                   *, provider_updated_at: datetime | None = None) -> dict[str, object]:
    """Build only Phase B sanitized facts and versioned provenance for registration."""
    end = utc(retrieval_completed_at)
    updated = utc(provider_updated_at) if provider_updated_at is not None else None
    if updated is not None and updated > end:
        raise ValueError('INVALID_PROVIDER_TIME')
    content = sanitize_payload(payload)
    document = json.loads(content)
    validate_retained_document(document)
    # Provider/application failure is not a successfully captured source.
    if document['error'] == 'PROVIDER_ERROR':
        raise ValueError('PROVIDER_ERROR')
    return json.loads(canonical_bytes({
        'version': CAPTURE, 'namespace': NAMESPACE, 'provider': 'API_FOOTBALL',
        'parser': PARSER, 'query': scope.query, 'kind': scope.kind,
        'retrieval_completed_at': end, 'expiry': end + scope.ttl,
        'provider_updated_at': updated, 'content_hash': digest(document), 'content': content,
    }))


class CaptureAdapter:
    """Synchronous opt-in FootballClient observer, scoped to an explicit Test plan.

    The plan labels current/previous relative to the intended target season. It
    does not request missing queries. Production composition is deliberately absent.
    Counters are process diagnostics; durable source counts come from the store.
    """

    def __init__(self, repository: EvidenceRepository, scopes: tuple[CaptureScope, ...]) -> None:
        if type(scopes) is not tuple or not all(isinstance(s, CaptureScope) for s in scopes):
            raise ValueError('IMMUTABLE_CAPTURE_PLAN_REQUIRED')
        if len({s.query for s in scopes}) != len(scopes):
            raise ValueError('AMBIGUOUS_CAPTURE_PLAN')
        self.repository = repository
        self.scopes = scopes
        self._counts: Counter[str] = Counter()

    def __call__(self, endpoint: str, query: Mapping[str, object], payload: object,
                 retrieval_completed_at: datetime) -> CaptureStatus:
        """Observe only matching existing HTTP responses; never mutate caller data."""
        scope = next((s for s in self.scopes if endpoint == '/fixtures' and dict(s.query.parameters) == query), None)
        if scope is None:
            status = CaptureStatus('UNAVAILABLE_UNSCOPED_QUERY')
        elif isinstance(payload, Mapping) and payload.get('errors'):
            status = CaptureStatus('UNAVAILABLE_PROVIDER_ERROR')
        else:
            try:
                material = prepare_source(scope, payload, retrieval_completed_at)
                registration = self.repository.register(material)
                status = CaptureStatus('REPLAY' if registration.replayed else 'CAPTURED', registration)
            except ImmutableConflict:
                status = CaptureStatus('UNAVAILABLE_CONFLICT')
            except Exception:
                # Never retain exception text, paths, credentials or raw provider data.
                status = CaptureStatus('UNAVAILABLE_CAPTURE_FAILURE')
        self._counts[status.status] += 1
        return status

    def diagnostics(self) -> dict[str, int]:
        """Return counts only; not a persisted completeness/coverage claim."""
        return dict(sorted(self._counts.items()))
