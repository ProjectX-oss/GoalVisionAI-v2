"""API-Football boundary over supplied data only; no default format or status guess."""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import json
import re
from typing import Mapping

from .contracts import Classification, Fixture, Neutral, Regulation, SourceRef, positive_id, require_hash
from .fingerprint import canonical_bytes, utc
from .sources import Candidate, PARSER, Query, SourceHeader, SourceKind, Timing, digest, parse_candidate, token

STATUS_MAPPING = 'FC_API_FOOTBALL_STATUS_V1'
FORMAT_CONTRACT = 'FC_REGULATION_EVIDENCE_V1'


class TargetState(StrEnum):
    NOT_STARTED = 'NOT_STARTED'
    STARTED = 'STARTED'
    FINISHED = 'FINISHED'
    POSTPONED_OR_CANCELLED = 'POSTPONED_OR_CANCELLED'
    UNKNOWN = 'UNKNOWN'


def target_state(status: str) -> TargetState:
    """Only NS admitted. TBD remains UNKNOWN despite the broader legacy runner."""
    if status == 'NS':
        return TargetState.NOT_STARTED
    if status in ('1H', '2H'):
        return TargetState.STARTED
    if status in ('FT', 'AET', 'PEN'):
        return TargetState.FINISHED
    if status in ('PST', 'CANC'):
        return TargetState.POSTPONED_OR_CANCELLED
    return TargetState.UNKNOWN


@dataclass(frozen=True, slots=True)
class FormatEvidence:
    """Explicit reviewed competition-season assertion, not elapsed match minutes.

    proof_hash pins the reviewed source document; no provider field in the audited
    fixture/cache path proves duration. Real registry population is deferred.
    """
    competition_id: int
    season: int
    minutes: int | None = None
    proof_id: str | None = None
    proof_hash: str | None = None
    known_at: datetime | None = None
    version: str = FORMAT_CONTRACT

    def __post_init__(self) -> None:
        positive_id(self.competition_id)
        positive_id(self.season)
        if self.minutes is not None:
            positive_id(self.minutes)
        if (self.proof_id is None) != (self.proof_hash is None):
            raise ValueError('INCOMPLETE_FORMAT_PROOF')
        if self.proof_id is not None:
            token(self.proof_id)
            require_hash(self.proof_hash)
        if self.known_at is not None:
            object.__setattr__(self, 'known_at', utc(self.known_at))

    def regulation(self, cutoff: datetime) -> Regulation:
        """Unknown/unavailable review evidence never becomes a 90-minute default."""
        if self.version != FORMAT_CONTRACT:
            raise ValueError('FORMAT_VERSION_MISMATCH')
        # Equal-time format reviews have no transaction-order receipt in this contract.
        if self.proof_id is None or self.known_at is None or self.known_at >= utc(cutoff):
            return Regulation(None, None, None)
        return Regulation(self.minutes, self.proof_id, digest(self))

    def verdict(self, cutoff: datetime) -> str:
        """Three explicit source-side format states."""
        return self.regulation(cutoff).reason or 'VERIFIED_90'


def _get(value: object, *keys: str) -> object:
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _integer(value: object) -> int | str | None:
    return value if value is None or type(value) is int else 'INVALID'


def _date(value: object) -> str:
    try:
        if not isinstance(value, str):
            raise ValueError('DATE_TYPE')
        return utc(datetime.fromisoformat(value.replace('Z', '+00:00'))).isoformat(timespec='microseconds').replace('+00:00', 'Z')
    except (ValueError, OverflowError):
        return 'INVALID'


def _short(value: object) -> str:
    return value if isinstance(value, str) and re.fullmatch(r'[A-Z0-9]{1,8}', value) else 'INVALID'


def _phase(value: object) -> str | None:
    # Optional football designation text only; no free-form URLs, paths or metadata.
    return value if isinstance(value, str) and re.fullmatch(r'[\w .()-]{1,80}', value) else None


def sanitize_payload(payload: object) -> str:
    """Copy only bounded football facts; errors/types become fixed, secret-free codes.

    Accept the client's unwrapped list and the existing cache response envelope.
    Oversized responses retain count/error only and are never replay inputs.
    Invalid field values retain explicit INVALID markers, not arbitrary content.
    """
    rows = payload if isinstance(payload, list) else _get(payload, 'response')
    error = 'PROVIDER_ERROR' if isinstance(payload, Mapping) and payload.get('errors') else None
    if not isinstance(rows, list):
        return canonical_bytes({'error': error or 'MALFORMED', 'count': None, 'rows': ()}).decode()
    count = len(rows)
    if count > 99:
        return canonical_bytes({'error': 'OVERSIZED', 'count': count, 'rows': ()}).decode()
    if isinstance(payload, Mapping):
        declared = payload.get('results')
        if declared is not None and (type(declared) is not int or declared != count):
            error = error or 'MALFORMED'
        paging = payload.get('paging')
        if paging is not None and (not isinstance(paging, Mapping) or paging.get('total') != 1 or paging.get('current') != 1):
            error = error or 'INCOMPLETE_RESPONSE'
    facts = []
    for row in rows:
        neutral = _get(row, 'fixture', 'neutral')
        facts.append({
            'fixture_id': _integer(_get(row, 'fixture', 'id')),
            'competition_id': _integer(_get(row, 'league', 'id')),
            'season': _integer(_get(row, 'league', 'season')),
            'home_team_id': _integer(_get(row, 'teams', 'home', 'id')),
            'away_team_id': _integer(_get(row, 'teams', 'away', 'id')),
            'kickoff': _date(_get(row, 'fixture', 'date')),
            'status': _short(_get(row, 'fixture', 'status', 'short')),
            'fulltime_home': _integer(_get(row, 'score', 'fulltime', 'home')),
            'fulltime_away': _integer(_get(row, 'score', 'fulltime', 'away')),
            'goals_home': _integer(_get(row, 'goals', 'home')),
            'goals_away': _integer(_get(row, 'goals', 'away')),
            'neutral': 'TRUE' if neutral is True else 'FALSE' if neutral is False else 'UNKNOWN',
            'phase': _phase(_get(row, 'league', 'round')),
        })
    # Preserve multiplicity for the 99-row bound; ignore incidental provider order.
    return canonical_bytes({'error': error, 'count': count, 'rows': sorted(facts, key=canonical_bytes)}).decode()


def source_candidate(header: SourceHeader, payload: object) -> Candidate:
    """Sanitize an already-collected payload, requiring its retained-content hash.

    Compute that hash with digest(json.loads(sanitize_payload(payload))) when
    constructing the header. It is deliberately not the legacy raw-payload hash.
    """
    content = sanitize_payload(payload)
    if digest(json.loads(content)) != header.content_hash:
        raise ValueError('CONTENT_HASH_MISMATCH')
    return Candidate(header, content)


@dataclass(frozen=True, slots=True)
class AdaptedSource:
    verdict: str
    facts: tuple[Fixture, ...]
    normalized_facts_hash: str


def adapt_source(candidate: Candidate, classification: Classification, *, competition_id: int,
                 season: int) -> AdaptedSource:
    """Verify selected retained content, then parse strictly; never select another row."""
    try:
        facts, verdict = _parse(candidate, classification, competition_id, season)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        facts, verdict = (), 'MALFORMED'
    return AdaptedSource(verdict, facts, digest({'parser': PARSER, 'facts': facts, 'verdict': verdict}))


def _parse(candidate: Candidate, classification: Classification, competition_id: int,
           season: int) -> tuple[tuple[Fixture, ...], str]:
    facts, verdict = parse_candidate(candidate, classification.entity_scope)
    if verdict != 'VALID':
        return facts, verdict
    # Fail the whole response on a wrong scope, rather than borrow other divisions.
    if any(f.competition_id != competition_id for f in facts):
        return facts, 'WRONG_COMPETITION'
    if any(f.season != season for f in facts):
        return facts, 'WRONG_SEASON'
    return facts, 'VALID'


def source_ref(candidate: Candidate) -> SourceRef:
    """Pin full header identity (including timing), not just football score content."""
    h = candidate.header
    return SourceRef(h.namespace, h.source_id, digest(h), h.timing.known_at,
                     h.timing.before_capture is not None)


def legacy_cache_candidate(*, source_id: str, query: Query, kind: SourceKind,
                           retrieved_at: datetime, expiry: datetime, payload: object) -> Candidate:
    """Adapt a supplied legacy cache row without reinterpreting its timestamp.

    Even though the accepted client records completion, cached provenance does
    not distinguish that path from runner-clock fallback and has no commit time.
    The ambiguous legacy timestamp is intentionally NOT completion or start.
    No supplied old row can acquire ASOF proof through this adapter.
    """
    content = sanitize_payload(payload)
    header = SourceHeader(source_id, query, kind, Timing(None, None, None, expiry, legacy_retrieved_at=retrieved_at),
                          digest(json.loads(content)), namespace='LAB_V2_LEGACY_CACHE')
    return Candidate(header, content)
