"""Offline as-of resolution and narrow Phase B bridge; no runtime wiring."""
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3

from ..contracts import positive_id
from ..fingerprint import utc
from ..source_adapter import FormatEvidence
from .contracts import ReviewedCompetitionRegulation, SourceType, Verdict, digest
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
        authoritative = tuple(r for r in records if r.source_type == SourceType.ORGANIZER_REGULATIONS)
        durations = {r.regulation_minutes for r in authoritative}
        if len(durations) > 1:
            verdict, reason = Verdict.CONFLICTING_REGULATION_EVIDENCE, 'AUTHORITATIVE_DURATION_CONFLICT'
        elif durations:
            verdict = Verdict.VERIFIED_90 if durations == {90} else Verdict.UNSUPPORTED_REGULATION
            reason = 'REVIEWED_COMPETITION_REGULATIONS'
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
    records = tuple(r for r in resolution.records if r.source_type == SourceType.ORGANIZER_REGULATIONS)
    # Recheck the supplied resolution so manually constructed verdicts cannot bypass review.
    if (resolution.provider != 'API_FOOTBALL' or not records or
            any(not r.applies(resolution.provider, resolution.competition_id, resolution.season, resolution.cutoff)
                for r in records) or len({r.regulation_minutes for r in records}) != 1):
        return empty
    minutes = records[0].regulation_minutes
    if (minutes == 90) != (resolution.verdict == Verdict.VERIFIED_90):
        return empty
    return FormatEvidence(resolution.competition_id, resolution.season, minutes,
                          'FC_V2_REGISTRY.' + resolution.fingerprint, resolution.fingerprint,
                          max(r.reviewed_at for r in records))
