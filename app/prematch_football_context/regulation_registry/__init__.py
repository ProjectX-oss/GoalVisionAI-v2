"""Dormant V2 manual regulation registry; import has no persistence/network effects."""
from .contracts import (
    Incorporation, IncorporatedCompetitionRegulation, RetainedSource,
    ReviewedCompetitionRegulation, SourceType, Verdict,
)
from .repository import Registry, initialize
from .service import Resolution, format_evidence, resolve

__all__ = ['Incorporation', 'IncorporatedCompetitionRegulation', 'RetainedSource',
           'ReviewedCompetitionRegulation', 'SourceType', 'Verdict', 'Registry',
           'initialize', 'Resolution', 'format_evidence', 'resolve']
