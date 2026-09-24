"""Frozen seven-value projection and compact reproducible decision bindings."""
from dataclasses import dataclass, replace
from decimal import Decimal

from ..capture.repository import DecisionReceipt
from ..contracts import ContextResult, positive_id, require_hash
from ..evidence import Binding
from ..fingerprint import feature_text, fingerprint, semantic_fingerprint
from ..policy import CONTRACT, FEATURE_NAMES, REASONS
from ..sources import token

SNAPSHOT = 'PREMATCH_FOOTBALL_CONTEXT_V2_SNAPSHOT_1'
PROJECTION = 'PREMATCH_FOOTBALL_CONTEXT_V2_PROJECTION_1'


@dataclass(frozen=True, slots=True)
class Projection:
    """Exactly seven Phase A decimal strings/nulls; never a V1 or model vector."""
    values: tuple[str | None, ...]
    missing: tuple[int, ...]
    reasons: tuple[tuple[str, ...], ...]
    names: tuple[str, ...] = FEATURE_NAMES
    contract: str = PROJECTION

    def __post_init__(self) -> None:
        if self.contract != PROJECTION or self.names != FEATURE_NAMES:
            raise ValueError('PROJECTION_CONTRACT')
        if any(type(v) is not tuple or len(v) != 7 for v in (self.values, self.missing, self.reasons)):
            raise ValueError('PROJECTION_SHAPE')
        for i, (value, missing, reasons) in enumerate(zip(self.values, self.missing, self.reasons)):
            if type(missing) is not int or missing != int(value is None):
                raise ValueError('PROJECTION_MASK')
            if type(reasons) is not tuple or reasons != tuple(r for r in REASONS if r in reasons):
                raise ValueError('PROJECTION_REASONS')
            if bool(reasons) != bool(missing):
                raise ValueError('PROJECTION_AVAILABILITY')
            if value is not None and (not isinstance(value, str) or feature_text(Decimal(value), i) != value):
                raise ValueError('PROJECTION_DECIMAL')

    @property
    def fingerprint(self) -> str:
        """Versioned, canonical ordered projection identity."""
        return fingerprint('LAB_VECTOR_V2', self)


def project(result: ContextResult) -> Projection:
    """Copy accepted Phase A values without rounding, floats or imputation."""
    if (result.contract != CONTRACT or result.semantic_fingerprint != semantic_fingerprint()
            or tuple(f.name for f in result.features) != FEATURE_NAMES):
        raise ValueError('CONTEXT_CONTRACT')
    return Projection(tuple(f.value for f in result.features),
                      tuple(int(f.value is None) for f in result.features),
                      tuple(f.reasons for f in result.features))


@dataclass(frozen=True, slots=True)
class Opportunity:
    """Existing PREMATCH canonical fixture:market key plus exact candidate identity.

    The canonical product admits one opportunity per fixture/market. Later
    decisions for another market may coexist; retries cannot replace the first.
    """
    fixture_id: int
    market: str
    candidate_id: str

    def __post_init__(self) -> None:
        positive_id(self.fixture_id)
        token(self.market)
        if not self.candidate_id.startswith('lab-v2-candidate-'):
            raise ValueError('CANDIDATE_IDENTITY')
        require_hash(self.candidate_id[len('lab-v2-candidate-'):])

    @property
    def key(self) -> str:
        """Reuse LearningCoordinator.shadow's exact canonical key."""
        return f'{self.fixture_id}:{self.market}'


@dataclass(frozen=True, slots=True)
class PrematchFootballContextV2Snapshot:
    opportunity: Opportunity
    receipt: DecisionReceipt
    binding: Binding
    home_team_id: int
    away_team_id: int
    # All exact candidates considered, in role order TARGET/CURRENT/PREVIOUS.
    source_candidates: tuple[tuple[str, ...], ...]
    selected_sources: tuple[str | None, ...]
    evidence_hash: str
    semantic_hash: str
    input_hash: str
    result_hash: str
    projection: Projection
    projection_hash: str
    # Small explanation summaries; complete facts remain in the Phase C store.
    validations: tuple[tuple[str, str, str], ...]
    source_decisions: tuple[tuple[str, str, str], ...]
    exclusions: tuple[tuple[int | None, tuple[str, ...]], ...]
    snapshot_hash: str = ''
    contract: str = SNAPSHOT
    stream: str = 'PREMATCH'

    def __post_init__(self) -> None:
        if (not isinstance(self.opportunity, Opportunity) or not isinstance(self.receipt, DecisionReceipt)
                or not isinstance(self.binding, Binding) or not isinstance(self.projection, Projection)):
            raise ValueError('SNAPSHOT_TYPES')
        if (type(self.validations) is not tuple or len(self.validations) != 3
                or any(type(v) is not tuple or len(v) != 3 or any(not isinstance(x, str) for x in v)
                       for v in self.validations)
                or tuple(v[0] for v in self.validations) != ('TARGET', 'CURRENT', 'PREVIOUS')):
            raise ValueError('SNAPSHOT_VALIDATIONS')
        if type(self.source_decisions) is not tuple:
            raise ValueError('SNAPSHOT_SOURCE_DECISIONS')
        for decision in self.source_decisions:
            if (type(decision) is not tuple or len(decision) != 3
                    or decision[0] not in ('TARGET', 'CURRENT', 'PREVIOUS')
                    or not isinstance(decision[2], str)):
                raise ValueError('SNAPSHOT_SOURCE_DECISIONS')
            require_hash(decision[1])
        if type(self.exclusions) is not tuple:
            raise ValueError('SNAPSHOT_EXCLUSIONS')
        for exclusion in self.exclusions:
            if (type(exclusion) is not tuple or len(exclusion) != 2
                    or type(exclusion[1]) is not tuple or any(not isinstance(r, str) for r in exclusion[1])):
                raise ValueError('SNAPSHOT_EXCLUSIONS')
            if exclusion[0] is not None:
                positive_id(exclusion[0])
        if self.contract != SNAPSHOT or self.stream != 'PREMATCH':
            raise ValueError('SNAPSHOT_CONTRACT')
        if self.opportunity.fixture_id != self.binding.fixture_id or self.receipt.cutoff != self.binding.cutoff:
            raise ValueError('DECISION_BINDING')
        for value in (self.home_team_id, self.away_team_id):
            positive_id(value)
        if self.home_team_id == self.away_team_id:
            raise ValueError('TEAM_BINDING')
        require_hash(self.receipt.receipt_hash)
        if type(self.receipt.ordering) is not int or self.receipt.ordering < 1:
            raise ValueError('DECISION_ORDER')
        if type(self.source_candidates) is not tuple or len(self.source_candidates) != 3:
            raise ValueError('SOURCE_PINS')
        if type(self.selected_sources) is not tuple or len(self.selected_sources) != 3:
            raise ValueError('SOURCE_PINS')
        for candidates, selected in zip(self.source_candidates, self.selected_sources):
            if type(candidates) is not tuple or candidates != tuple(sorted(set(candidates))):
                raise ValueError('SOURCE_PINS')
            for identity in candidates:
                require_hash(identity)
            if selected is not None and selected not in candidates:
                raise ValueError('SELECTED_PIN')
        if self.selected_sources[0] is None:
            raise ValueError('TARGET_REQUIRED')
        for value in (self.evidence_hash, self.semantic_hash, self.input_hash, self.result_hash, self.projection_hash):
            require_hash(value)
        if self.semantic_hash != semantic_fingerprint() or self.projection_hash != self.projection.fingerprint:
            raise ValueError('SNAPSHOT_FINGERPRINT')
        if self.snapshot_hash and self.snapshot_hash != snapshot_fingerprint(self):
            raise ValueError('SNAPSHOT_FINGERPRINT')

    @property
    def snapshot_id(self) -> str:
        """Content addressed, with no write-time or database surrogate inputs."""
        return 'fc-v2-' + self.snapshot_hash


def snapshot_fingerprint(snapshot: PrematchFootballContextV2Snapshot) -> str:
    """Hash all bindings, values and diagnostics, excluding the self hash."""
    return fingerprint('FC_SNAPSHOT_V1', replace(snapshot, snapshot_hash=''))
