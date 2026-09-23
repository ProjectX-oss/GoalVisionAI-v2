"""Pure bounded source selection. No cache reader, writer, clock or provider client.

Times are evidence supplied by a trusted collector, never inferred from TTLs.
Legacy cache rows cannot populate completion/registration proof (see Phase B audit).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
import re
import json

from .contracts import Fixture, Neutral, positive_id, require_hash
from .fingerprint import canonical_bytes, fingerprint, utc

PARSER = 'FC_API_FOOTBALL_FACTS_V1'
SELECTION = 'FC_ASOF_SELECTION_V1'


def token(value: str) -> None:
    """Require a bounded opaque identity, never a path, URL or arbitrary payload."""
    if not isinstance(value, str) or re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', value) is None:
        raise ValueError('INVALID_EVIDENCE_IDENTITY')


def digest(value: object) -> str:
    """Reuse Phase A canonical bytes and the RFC source domain."""
    return fingerprint('FC_SOURCE_BUNDLE_V1', value)


class SourceKind(StrEnum):
    CURRENT = 'CURRENT'
    PREVIOUS = 'PREVIOUS'
    TARGET = 'TARGET'


@dataclass(frozen=True, slots=True)
class Query:
    """Exact cache endpoint and query; results alias is the existing cache namespace."""
    endpoint: str
    parameters: tuple[tuple[str, int | str], ...]

    def __post_init__(self) -> None:
        if self.endpoint not in ('/fixtures', '/fixtures(results)') or type(self.parameters) is not tuple:
            raise ValueError('INVALID_QUERY')
        allowed = {'id', 'league', 'season', 'status', 'last'}
        keys = []
        for pair in self.parameters:
            if type(pair) is not tuple or len(pair) != 2 or pair[0] not in allowed:
                raise ValueError('INVALID_QUERY')
            key, value = pair
            if key == 'status':
                if value != 'FT':
                    raise ValueError('INVALID_QUERY')
            else:
                positive_id(value)
            keys.append(key)
        if len(set(keys)) != len(keys):
            raise ValueError('DUPLICATE_QUERY_KEY')
        object.__setattr__(self, 'parameters', tuple(sorted(self.parameters)))


def history_query(competition_id: int, season: int) -> Query:
    """The only admitted result-history query, including the exact last-99 bound."""
    return Query('/fixtures(results)', (('league', competition_id), ('season', season), ('status', 'FT'), ('last', 99)))


def target_query(fixture_id: int) -> Query:
    """Existing exact-fixture endpoint; this function does not request it."""
    return Query('/fixtures', (('id', fixture_id),))


@dataclass(frozen=True, slots=True)
class CaptureOrder:
    """Trusted durable registration receipt bound to this cutoff and source content.

    The collector must establish transaction ordering; a wall-clock equality or
    a boolean alone is not a receipt. Phase B verifies bindings, not storage truth.
    """
    cutoff: datetime
    source_id: str
    content_hash: str
    receipt_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, 'cutoff', utc(self.cutoff))
        token(self.source_id)
        require_hash(self.content_hash)
        require_hash(self.receipt_hash)


@dataclass(frozen=True, slots=True)
class Timing:
    retrieval_completed_at: datetime | None
    registered_at: datetime | None
    known_at: datetime | None
    expiry: datetime | None
    request_started_at: datetime | None = None
    provider_updated_at: datetime | None = None
    before_capture: CaptureOrder | None = None
    legacy_retrieved_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ('retrieval_completed_at', 'registered_at', 'known_at', 'expiry',
                     'request_started_at', 'provider_updated_at', 'legacy_retrieved_at'):
            if getattr(self, name) is not None:
                object.__setattr__(self, name, utc(getattr(self, name)))
        if self.before_capture is not None and not isinstance(self.before_capture, CaptureOrder):
            raise ValueError('INVALID_CAPTURE_PROOF')

    @property
    def provider_freshness(self) -> str:
        """Collection freshness never asserts provider update freshness."""
        return 'UNKNOWN' if self.provider_updated_at is None else 'TIMESTAMP_KNOWN'


@dataclass(frozen=True, slots=True)
class SourceHeader:
    source_id: str
    query: Query
    kind: SourceKind
    timing: Timing
    content_hash: str
    provider: str = 'API_FOOTBALL'
    namespace: str = 'FC_SUPPLIED_SOURCE_V1'
    parser: str = PARSER

    def __post_init__(self) -> None:
        for value in (self.source_id, self.namespace, self.parser):
            token(value)
        require_hash(self.content_hash)
        if self.provider != 'API_FOOTBALL' or not isinstance(self.query, Query) or not isinstance(self.kind, SourceKind) or not isinstance(self.timing, Timing):
            raise ValueError('INVALID_SOURCE_HEADER')


@dataclass(frozen=True, slots=True)
class Candidate:
    """Only sanitized canonical football JSON is retained; raw provider data stays outside."""
    header: SourceHeader
    content: str

    def __post_init__(self) -> None:
        if not isinstance(self.header, SourceHeader) or not isinstance(self.content, str):
            raise ValueError('INVALID_CANDIDATE')


@dataclass(frozen=True, slots=True)
class Decision:
    header: SourceHeader
    verdict: str


@dataclass(frozen=True, slots=True)
class Selection:
    query: Query
    kind: SourceKind
    cutoff: datetime
    decisions: tuple[Decision, ...]
    selected: Candidate | None
    verdict: str
    version: str = SELECTION

    def __post_init__(self) -> None:
        if not isinstance(self.query, Query) or not isinstance(self.kind, SourceKind) or type(self.decisions) is not tuple or not all(isinstance(d, Decision) for d in self.decisions):
            raise ValueError('INVALID_SELECTION')
        if self.selected is not None and not isinstance(self.selected, Candidate):
            raise ValueError('INVALID_SELECTION')
        object.__setattr__(self, 'cutoff', utc(self.cutoff))


def asof_verdict(header: SourceHeader, query: Query, cutoff: datetime, kind: SourceKind) -> str:
    """Eligibility before payload validation; future/stale rows cannot compete."""
    if header.query != query or header.kind != kind:
        return 'WRONG_QUERY'
    timing = header.timing
    end, registered, known = timing.retrieval_completed_at, timing.registered_at, timing.known_at
    if end is None or registered is None or known is None:
        return 'ASOF_UNPROVEN'
    if max(end, registered, known) > cutoff:
        return 'AFTER_CUTOFF'
    if max(end, registered, known) == cutoff:
        proof = timing.before_capture
        if proof is None or (proof.cutoff, proof.source_id, proof.content_hash) != (cutoff, header.source_id, header.content_hash):
            return 'ASOF_UNPROVEN'
    if timing.expiry is None:
        return 'ASOF_UNPROVEN'
    if cutoff >= timing.expiry:
        return 'EXPIRED'
    ttl = timedelta(minutes=15) if kind == SourceKind.TARGET else timedelta(hours=6 if kind == SourceKind.CURRENT else 24)
    if cutoff - end >= ttl:
        return 'STALE'
    return 'ELIGIBLE'


def validate_header(header: SourceHeader) -> str:
    """Validate the chosen version; inconsistent latest evidence never causes fallback."""
    if header.parser != PARSER:
        return 'VERSION_MISMATCH'
    t = header.timing
    if t.retrieval_completed_at is None or t.registered_at is None or t.known_at is None:
        return 'ASOF_UNPROVEN'
    if (t.registered_at < t.retrieval_completed_at or t.known_at < t.registered_at
            or (t.request_started_at is not None and t.request_started_at > t.retrieval_completed_at)
            or (t.provider_updated_at is not None and t.provider_updated_at > t.retrieval_completed_at)):
        return 'INVALID_TIMING'
    return 'SELECTED'


def choose_header(headers: tuple[SourceHeader, ...], query: Query, cutoff: datetime,
                  kind: SourceKind) -> tuple[tuple[Decision, ...], SourceHeader | None, str]:
    """Retain deterministic metadata decisions, excluding unrelated payloads."""
    if not isinstance(query, Query) or not isinstance(kind, SourceKind):
        raise ValueError('INVALID_SELECTION_QUERY_OR_KIND')
    cutoff = utc(cutoff)
    unique = {canonical_bytes(h): h for h in headers}
    decisions = tuple(Decision(unique[key], asof_verdict(unique[key], query, cutoff, kind)) for key in sorted(unique))
    identities: dict[tuple[str, str], SourceHeader] = {}
    for h in unique.values():
        key = (h.namespace, h.source_id)
        if key in identities and identities[key] != h:
            return decisions, None, 'IMMUTABLE_SOURCE_CONFLICT'
        identities[key] = h
    eligible = [d.header for d in decisions if d.verdict == 'ELIGIBLE']
    if not eligible:
        return decisions, None, 'UNAVAILABLE'
    # Stable sorts avoid floating timestamps or locale-dependent ordering.
    eligible.sort(key=lambda h: (h.content_hash, h.source_id, h.namespace))
    eligible.sort(key=lambda h: h.timing.registered_at, reverse=True)
    eligible.sort(key=lambda h: h.timing.retrieval_completed_at, reverse=True)
    winner = eligible[0]
    return decisions, winner, validate_header(winner)


def select_source(candidates: tuple[Candidate, ...], exact_query_identity: Query, *,
                  cutoff: datetime, source_kind: SourceKind) -> Selection:
    """Select once, read-only, from supplied immutable records. Never fetch or fall back."""
    if type(candidates) is not tuple or not all(isinstance(c, Candidate) for c in candidates):
        raise ValueError('IMMUTABLE_CANDIDATES_REQUIRED')
    cutoff = utc(cutoff)
    decisions, winner, verdict = choose_header(tuple(c.header for c in candidates), exact_query_identity, cutoff, source_kind)
    matching = [c for c in candidates if c.header == winner]
    selected = matching[0] if matching else None
    if len({c.content for c in matching}) > 1:
        selected, verdict = None, 'IMMUTABLE_SOURCE_CONFLICT'
    if selected is not None and verdict == 'SELECTED':
        verdict = selected_verdict(selected)
    return Selection(exact_query_identity, source_kind, cutoff, decisions, selected, verdict)


def diagnostics(selection: Selection) -> tuple[tuple[str, int], ...]:
    """Small deterministic source counts, never a prospective coverage claim."""
    counts = {'candidates': len(selection.decisions), 'selected': int(selection.selected is not None),
              'unavailable': int(selection.verdict != 'SELECTED')}
    if selection.verdict != 'SELECTED':
        counts[selection.verdict] = 1
    for decision in selection.decisions:
        counts[decision.verdict] = counts.get(decision.verdict, 0) + 1
    return tuple(sorted(counts.items()))


def validate_retained_document(doc: object) -> None:
    """Reject unsanitized trees, including payloads claiming an error verdict."""
    if not isinstance(doc, dict) or set(doc) != {'error', 'count', 'rows'}:
        raise ValueError('UNSANITIZED_DOCUMENT')
    if doc['error'] not in (None, 'PROVIDER_ERROR', 'MALFORMED', 'OVERSIZED', 'INCOMPLETE_RESPONSE'):
        raise ValueError('UNSANITIZED_ERROR')
    rows, count = doc['rows'], doc['count']
    if type(rows) is not list or len(rows) > 99:
        raise ValueError('UNSANITIZED_ROWS')
    if count is None:
        if rows or doc['error'] not in ('MALFORMED', 'PROVIDER_ERROR'):
            raise ValueError('INVALID_RESPONSE_COUNT')
    elif type(count) is not int or count < 0 or (count > 99 and (rows or doc['error'] != 'OVERSIZED')) or (count <= 99 and count != len(rows)):
        raise ValueError('INVALID_RESPONSE_COUNT')
    integers = ('fixture_id', 'competition_id', 'season', 'home_team_id', 'away_team_id',
                'fulltime_home', 'fulltime_away', 'goals_home', 'goals_away')
    keys = set(integers) | {'kickoff', 'status', 'neutral', 'phase'}
    for row in rows:
        if type(row) is not dict or set(row) != keys:
            raise ValueError('UNSANITIZED_FACT')
        if any(v is not None and type(v) is not int and v != 'INVALID' for v in (row[k] for k in integers)):
            raise ValueError('UNSANITIZED_NUMBER')
        if not isinstance(row['status'], str) or re.fullmatch(r'[A-Z0-9]{1,8}', row['status']) is None:
            raise ValueError('UNSANITIZED_STATUS')
        if row['neutral'] not in ('TRUE', 'FALSE', 'UNKNOWN'):
            raise ValueError('UNSANITIZED_NEUTRAL')
        if row['phase'] is not None and (not isinstance(row['phase'], str) or re.fullmatch(r'[\w .()-]{1,80}', row['phase']) is None):
            raise ValueError('UNSANITIZED_PHASE')
        if row['kickoff'] != 'INVALID':
            stamp = utc(datetime.fromisoformat(row['kickoff'].replace('Z', '+00:00')))
            if stamp.isoformat(timespec='microseconds').replace('+00:00', 'Z') != row['kickoff']:
                raise ValueError('UNSANITIZED_KICKOFF')


def parse_candidate(candidate: Candidate, entity_scope: tuple[str, str, str]) -> tuple[tuple[Fixture, ...], str]:
    """Verify the retained schema and parse facts without provider I/O or fallback."""
    try:
        if candidate.header.parser != PARSER:
            return (), 'VERSION_MISMATCH'
        doc = json.loads(candidate.content)
        if digest(doc) != candidate.header.content_hash:
            return (), 'INTEGRITY_ERROR'
        if canonical_bytes(doc).decode() != candidate.content or set(doc) != {'error', 'count', 'rows'}:
            return (), 'MALFORMED'
        validate_retained_document(doc)
        if doc['error'] is not None:
            return (), doc['error']
        facts = []
        for row in doc['rows']:
            if row['status'] == 'INVALID':
                return (), 'MALFORMED'
            facts.append(Fixture(provider='API_FOOTBALL', entity_scope=entity_scope,
                                 **(row | {'kickoff': datetime.fromisoformat(row['kickoff'].replace('Z', '+00:00')),
                                           'neutral': Neutral(row['neutral'])})))
        return tuple(sorted(facts, key=canonical_bytes)), 'VALID'
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return (), 'MALFORMED'


def selected_verdict(candidate: Candidate) -> str:
    """Validate the winning payload/query binding only, never older candidates."""
    verdict = validate_header(candidate.header)
    if verdict != 'SELECTED':
        return verdict
    facts, verdict = parse_candidate(candidate, ('UNBOUND', 'UNBOUND', 'UNBOUND'))
    if verdict != 'VALID':
        return verdict
    query = dict(candidate.header.query.parameters)
    if candidate.header.kind == SourceKind.TARGET:
        if set(query) != {'id'}:
            return 'WRONG_QUERY'
        if candidate.header.query != target_query(query['id']) or len(facts) != 1 or facts[0].fixture_id != query['id']:
            return 'WRONG_TARGET'
    else:
        if set(query) != {'league', 'season', 'status', 'last'}:
            return 'WRONG_QUERY'
        if candidate.header.query != history_query(query['league'], query['season']):
            return 'WRONG_QUERY'
        if any(f.competition_id != query['league'] for f in facts):
            return 'WRONG_COMPETITION'
        if any(f.season != query['season'] for f in facts):
            return 'WRONG_SEASON'
    return 'SELECTED'
