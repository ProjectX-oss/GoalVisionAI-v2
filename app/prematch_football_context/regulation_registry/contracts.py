"""Manual review contracts. Validation checks declarations, never performs research."""
from dataclasses import dataclass, fields
from datetime import datetime
from enum import StrEnum
import hashlib
import json
import unicodedata
from urllib.parse import urlsplit

from ..contracts import positive_id, require_hash
from ..fingerprint import canonical_bytes, utc

VERSION = 'FC_V2_REVIEWED_REGULATION_V1'
INCORPORATED_VERSION = 'FC_V2_INCORPORATED_REGULATION_V1'
LINK_VERSION = 'FC_V2_INCORPORATION_V1'
# Deliberately small admission policy, not a claim that any document proves format.
# Adding an organizer requires a separately reviewed code/policy change.
AUTHORITIES = (('UEFA', 'uefa.com'), ('FIFA', 'fifa.com'), ('IFAB', 'theifab.com'),
               ('THE_FA', 'thefa.com'), ('DFB', 'dfb.de'))


class SourceType(StrEnum):
    ORGANIZER_REGULATIONS = 'ORGANIZER_REGULATIONS'
    IFAB_BASE_LAW = 'IFAB_BASE_LAW'


class Verdict(StrEnum):
    VERIFIED_90 = 'VERIFIED_90'
    UNSUPPORTED_REGULATION = 'UNSUPPORTED_REGULATION'
    REGULATION_UNVERIFIED = 'REGULATION_UNVERIFIED'
    CONFLICTING_REGULATION_EVIDENCE = 'CONFLICTING_REGULATION_EVIDENCE'


def digest(domain: str, value: object) -> str:
    """Domain-separated canonical SHA-256, independent of feature semantics."""
    return hashlib.sha256(domain.encode('ascii') + b'\n' + canonical_bytes(value)).hexdigest()


def bounded(value: str, maximum: int = 1000) -> None:
    """Require bounded NFC text; never silently rewrite the reviewed content."""
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or value != unicodedata.normalize('NFC', value) or '\x00' in value):
        raise ValueError('INVALID_REVIEW_TEXT')


@dataclass(frozen=True, slots=True)
class RetainedSource:
    """Minimum offline review material; excerpt capped at 25 whitespace words.

    Mapping evidence is a retained reviewer summary of already supplied mapping
    material, with its identity, not an invitation to query the provider.
    """
    document_identity: str
    section: str
    excerpt: str
    applicability_statement: str
    provider_mapping_evidence: str

    def __post_init__(self) -> None:
        for field in fields(self):
            bounded(getattr(self, field.name))
        if len(self.excerpt.split()) > 25:
            raise ValueError('EXCERPT_TOO_LONG')


@dataclass(frozen=True, slots=True)
class ReviewedCompetitionRegulation:
    """One immutable operator assertion; identity is review_id, not its hash.

    validity_start/end are inclusive provider season labels. Both omitted means
    exact season. Source effective timestamps form a half-open decision interval.
    The operator must explicitly review duration, applicability and ID mapping.
    """
    review_id: str
    provider: str
    competition_id: int
    season: int
    regulation_minutes: int | None
    organizer: str
    competition_name: str
    source_type: SourceType
    source_title: str
    source_url: str
    source_edition: str
    source_effective_from: datetime
    source_effective_until: datetime
    reviewed_statement: str
    retained_source_content: RetainedSource
    source_content_sha256: str
    reviewer: str
    reviewed_at: datetime
    validity_start: int | None
    validity_end: int | None
    evidence_version: str
    evidence_fingerprint: str

    def __post_init__(self) -> None:
        for name in ('review_id', 'organizer', 'competition_name', 'source_title', 'source_url',
                     'source_edition', 'reviewed_statement', 'reviewer'):
            bounded(getattr(self, name))
        expected = INCORPORATED_VERSION if isinstance(self, IncorporatedCompetitionRegulation) else VERSION
        if self.provider != 'API_FOOTBALL' or self.evidence_version != expected:
            raise ValueError('UNSUPPORTED_PROVIDER_OR_VERSION')
        for number in (self.competition_id, self.season):
            positive_id(number)
        if self.regulation_minutes is not None or expected == VERSION:
            positive_id(self.regulation_minutes)
        if not isinstance(self.source_type, SourceType) or not isinstance(self.retained_source_content, RetainedSource):
            raise ValueError('INVALID_REVIEW_CONTRACT')
        if (self.validity_start is None) != (self.validity_end is None):
            raise ValueError('INCOMPLETE_SEASON_INTERVAL')
        if self.validity_start is not None:
            positive_id(self.validity_start)
            positive_id(self.validity_end)
            if not self.validity_start <= self.season <= self.validity_end:
                raise ValueError('INVALID_SEASON_INTERVAL')
        for name in ('source_effective_from', 'source_effective_until', 'reviewed_at'):
            object.__setattr__(self, name, utc(getattr(self, name)))
        if self.source_effective_from >= self.source_effective_until:
            raise ValueError('INVALID_EFFECTIVE_INTERVAL')
        self._authority()
        require_hash(self.source_content_sha256)
        require_hash(self.evidence_fingerprint)
        if self.source_content_sha256 != digest('FC_V2_REGULATION_SOURCE_V1', self.retained_source_content):
            raise ValueError('SOURCE_CONTENT_INTEGRITY')
        if self.evidence_fingerprint != digest(self.evidence_version, self.fingerprint_material()):
            raise ValueError('EVIDENCE_FINGERPRINT_INTEGRITY')

    def _authority(self) -> None:
        url = urlsplit(self.source_url)
        hosts = tuple(host for name, host in AUTHORITIES if name == self.organizer)
        if (url.scheme != 'https' or url.username or url.password or url.port not in (None, 443)
                or not url.path or url.path == '/' or url.query or url.fragment
                or not any(url.hostname == host or (url.hostname or '').endswith('.' + host) for host in hosts)):
            raise ValueError('UNSUPPORTED_AUTHORITY')
        if (self.organizer == 'IFAB') != (self.source_type == SourceType.IFAB_BASE_LAW):
            raise ValueError('BASE_LAW_IS_NOT_COMPETITION_AUTHORITY')

    def fingerprint_material(self) -> dict[str, object]:
        """All review content except its self-referential fingerprint."""
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name != 'evidence_fingerprint'}

    def applies(self, provider: str, competition_id: int, season: int, cutoff: datetime) -> bool:
        """Exact identity by default; no cross-competition or implicit season reuse."""
        start = self.season if self.validity_start is None else self.validity_start
        end = self.season if self.validity_end is None else self.validity_end
        return (self.provider == provider and self.competition_id == competition_id and start <= season <= end
                and self.reviewed_at < cutoff and self.source_effective_from <= cutoff < self.source_effective_until)


@dataclass(frozen=True, slots=True)
class Incorporation:
    """Explicit edge owned by a competition review, pinned to one reviewed law.

    The owner supplies retained provenance, review time and effective interval.
    Its immutable review_id identifies this single relationship.
    """
    competition_review_id: str
    base_review_id: str
    base_evidence_fingerprint: str
    reviewed_statement: str
    relationship: str
    fingerprint: str

    def __post_init__(self) -> None:
        for name in ('competition_review_id', 'base_review_id', 'reviewed_statement'):
            bounded(getattr(self, name))
        require_hash(self.base_evidence_fingerprint)
        require_hash(self.fingerprint)
        if self.relationship != 'INCORPORATES' or self.competition_review_id == self.base_review_id:
            raise ValueError('INVALID_INCORPORATION')
        material = {f.name: getattr(self, f.name) for f in fields(self) if f.name != 'fingerprint'}
        if self.fingerprint != digest(LINK_VERSION, material):
            raise ValueError('INCORPORATION_INTEGRITY')


@dataclass(frozen=True, slots=True)
class IncorporatedCompetitionRegulation(ReviewedCompetitionRegulation):
    """Null duration avoids falsely attributing base-law duration to the organizer."""
    incorporation: Incorporation

    def __post_init__(self) -> None:
        ReviewedCompetitionRegulation.__post_init__(self)
        if (self.source_type != SourceType.ORGANIZER_REGULATIONS
                or not isinstance(self.incorporation, Incorporation)
                or self.incorporation.competition_review_id != self.review_id):
            raise ValueError('INVALID_INCORPORATION_OWNER')


def decode(document: str) -> ReviewedCompetitionRegulation:
    """Strict JSON import: complete keys, no duplicate keys, verified supplied hashes."""
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('DUPLICATE_KEY')
            result[key] = value
        return result
    if not isinstance(document, str):
        raise ValueError('INVALID_REVIEW_DOCUMENT')
    if len(document.encode('utf-8')) > 32768:
        raise ValueError('RECORD_TOO_LARGE')
    try:
        doc = json.loads(document, object_pairs_hook=unique)
        if not isinstance(doc, dict):
            raise ValueError('INVALID_REVIEW_DOCUMENT')
        kind = (IncorporatedCompetitionRegulation
                if doc.get('evidence_version') == INCORPORATED_VERSION
                else ReviewedCompetitionRegulation)
        if set(doc) != {f.name for f in fields(kind)}:
            raise ValueError('INCOMPLETE_REVIEW')
        if kind is IncorporatedCompetitionRegulation:
            doc['incorporation'] = Incorporation(**doc['incorporation'])
        doc['source_type'] = SourceType(doc['source_type'])
        doc['retained_source_content'] = RetainedSource(**doc['retained_source_content'])
        for name in ('source_effective_from', 'source_effective_until', 'reviewed_at'):
            doc[name] = datetime.fromisoformat(doc[name].replace('Z', '+00:00'))
        return kind(**doc)
    except (TypeError, KeyError, AttributeError, RecursionError) as exc:
        raise ValueError('INVALID_REVIEW_DOCUMENT') from exc
