"""Offline as-of resolution and narrow Phase B bridge; no runtime wiring."""
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3

from ..contracts import positive_id
from ..fingerprint import canonical_bytes, utc
from ..source_adapter import FormatEvidence
from .contracts import (
    IncorporatedCompetitionRegulation, ReviewedCompetitionRegulation, SourceType, Verdict, decode, digest,
)
from .repository import Registry


@dataclass(frozen=True, slots=True)
class Resolution:
    """Retained proof lineage for one exact as-of decision, including conflicts."""
    provider: str
    competition_id: int
    season: int
    cutoff: datetime
    verdict: Verdict
    records: tuple[ReviewedCompetitionRegulation, ...]
    reason: str

    @property
    def fingerprint(self) -> str:
        """Identity of the complete scoped resolution, including retained content."""
        return digest('FC_V2_REGULATION_RESOLUTION_V1', self)


def evaluate(records: tuple[ReviewedCompetitionRegulation, ...], provider: str,
             competition_id: int, season: int, cutoff: datetime) -> tuple[Verdict, str, int | None]:
    """Reproduce duration from retained reviews; incomplete edges fail closed.

    Unlinked base laws never establish duration or override a competition rule.
    """
    indexed: dict[str, ReviewedCompetitionRegulation] = {}
    for record in records:
        decode(canonical_bytes(record).decode())
        if record.review_id in indexed or not record.applies(provider, competition_id, season, cutoff):
            raise ValueError('INVALID_RESOLUTION_RECORDS')
        indexed[record.review_id] = record
    durations: set[int] = set()
    incomplete = False
    for record in records:
        if record.source_type != SourceType.ORGANIZER_REGULATIONS:
            continue
        if record.regulation_minutes is not None:
            durations.add(record.regulation_minutes)
        if isinstance(record, IncorporatedCompetitionRegulation):
            link = record.incorporation
            base = indexed.get(link.base_review_id)
            if (base is None or base.source_type != SourceType.IFAB_BASE_LAW
                    or base.evidence_fingerprint != link.base_evidence_fingerprint
                    or base.regulation_minutes is None):
                incomplete = True
            else:
                durations.add(base.regulation_minutes)
    if len(durations) > 1:
        return Verdict.CONFLICTING_REGULATION_EVIDENCE, 'AUTHORITATIVE_DURATION_CONFLICT', None
    if incomplete:
        return Verdict.REGULATION_UNVERIFIED, 'INCOMPLETE_INCORPORATION_CHAIN', None
    if not durations:
        return Verdict.REGULATION_UNVERIFIED, 'NO_QUALIFYING_COMPETITION_EVIDENCE', None
    minutes = next(iter(durations))
    verdict = Verdict.VERIFIED_90 if minutes == 90 else Verdict.UNSUPPORTED_REGULATION
    incorporated = any(isinstance(r, IncorporatedCompetitionRegulation) for r in records)
    return verdict, 'REVIEWED_INCORPORATED_LAW' if incorporated else 'REVIEWED_COMPETITION_REGULATIONS', minutes


def resolve(path: Path, *, provider: str, competition_id: int, season: int, cutoff: datetime) -> Resolution:
    """No initialization or repair. Missing/locked/corrupt stores fail closed."""
    cutoff = utc(cutoff)
    positive_id(competition_id)
    positive_id(season)
    records: tuple[ReviewedCompetitionRegulation, ...] = ()
    verdict, reason = Verdict.REGULATION_UNVERIFIED, 'NO_QUALIFYING_COMPETITION_EVIDENCE'
    try:
        with closing(Registry(path)) as registry:
            records = tuple(r for r in registry.verify() if r.applies(provider, competition_id, season, cutoff))
        verdict, reason, _ = evaluate(records, provider, competition_id, season, cutoff)
    except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError):
        records, reason = (), 'REGISTRY_UNAVAILABLE_OR_INVALID'
    return Resolution(provider, competition_id, season, cutoff, verdict, records, reason)


def format_evidence(resolution: Resolution, *, cutoff: datetime) -> FormatEvidence:
    """Bridge only at the resolved cutoff; retain Resolution alongside the bundle.

    FormatEvidence cannot encode expiry/conflicts. Reusing the bridge for a new
    decision requires a fresh resolution. Its proof hash pins the full lineage.
    """
    if utc(cutoff) != resolution.cutoff:
        raise ValueError('RESOLUTION_CUTOFF_MISMATCH')
    empty = FormatEvidence(resolution.competition_id, resolution.season)
    if resolution.verdict not in (Verdict.VERIFIED_90, Verdict.UNSUPPORTED_REGULATION):
        return empty
    try:
        verdict, _, minutes = evaluate(resolution.records, resolution.provider,
                                      resolution.competition_id, resolution.season, resolution.cutoff)
    except (ValueError, TypeError):
        return empty
    if verdict != resolution.verdict or minutes is None:
        return empty
    targets = {r.incorporation.base_review_id for r in resolution.records
               if isinstance(r, IncorporatedCompetitionRegulation)}
    supporting = tuple(r for r in resolution.records
                       if r.source_type == SourceType.ORGANIZER_REGULATIONS or r.review_id in targets)
    return FormatEvidence(resolution.competition_id, resolution.season, minutes,
                          'FC_V2_REGISTRY.' + resolution.fingerprint, resolution.fingerprint,
                          max(r.reviewed_at for r in supporting))
