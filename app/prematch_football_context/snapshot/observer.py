"""Explicit local-only bridge from final evaluation to first canonical opportunity.

Inject the SAME instance into runner and LearningCoordinator in Test composition.
No default wiring, scheduler, provider reference, clock fallback or V1 mutation.
"""
from collections import Counter
from dataclasses import dataclass, replace
from typing import Callable, Mapping

from ..capture.repository import DecisionReceipt, EvidenceRepository, ImmutableConflict
from ..evidence import Binding
from .contracts import Opportunity, PrematchFootballContextV2Snapshot
from .repository import SnapshotRepository
from .service import assemble, reproduce


@dataclass(frozen=True, slots=True)
class DecisionIdentity:
    """Only immutable scalar identities cross the runtime observation boundary."""
    fixture_id: int
    market: str
    candidate_id: str
    home_team_id: int
    away_team_id: int
    competition_id: int
    season: int


def identity(candidate: Mapping[str, object]) -> DecisionIdentity:
    """Copy exact existing candidate identity; no V1 feature access or conversion."""
    return DecisionIdentity(*(candidate[k] for k in ('fixture_id', 'market', 'candidate_id',
                            'home_team_id', 'away_team_id', 'league_id', 'season')))


class SnapshotObserver:
    """Failure-isolated research collector; returns no prediction inputs.

    Scope bindings contain explicit reviewed classification/format assertions.
    Their placeholder cutoff is replaced ONLY by the durable Phase C receipt.
    Pending associations are limited to the latest final-evaluation batch. Lost
    associations are unavailable: no late cutoff, cache reconstruction or repair.
    """

    def __init__(self, evidence: EvidenceRepository, snapshots: SnapshotRepository,
                 scopes: tuple[Binding, ...], *,
                 resolve_binding: Callable[[Binding, DecisionReceipt], Binding] | None = None,
                 retain_snapshot: Callable[[PrematchFootballContextV2Snapshot], None] | None = None) -> None:
        if type(scopes) is not tuple or len({b.fixture_id for b in scopes}) != len(scopes):
            raise ValueError('EXPLICIT_UNAMBIGUOUS_SCOPE_REQUIRED')
        self.evidence, self.snapshots = evidence, snapshots
        self.resolve_binding, self.retain_snapshot = resolve_binding, retain_snapshot
        self.scopes = {b.fixture_id: b for b in scopes}
        self.pending: dict[str, tuple[DecisionIdentity, DecisionReceipt]] = {}
        self.counts: Counter[str] = Counter()

    def begin(self) -> DecisionReceipt | None:
        """Immediately before FINAL evaluation; preliminary passes never call this."""
        self.pending.clear()
        try:
            return self.evidence.capture_cutoff()
        except Exception:
            self.counts['UNAVAILABLE_DECISION_RECEIPT'] += 1
            return None

    def bind(self, receipt: DecisionReceipt | None, decisions: tuple[DecisionIdentity, ...]) -> None:
        """Associate already-computed candidate IDs; never mutate candidate documents."""
        try:
            if receipt is None or self.evidence.load_cutoff(receipt.receipt_hash) != receipt:
                raise ValueError('RECEIPT_UNAVAILABLE')
            for decision in decisions:
                if decision.fixture_id in self.scopes:
                    previous = self.pending.get(decision.candidate_id)
                    if previous is not None and previous != (decision, receipt):
                        raise ValueError('CANDIDATE_CONFLICT')
                    self.pending[decision.candidate_id] = (decision, receipt)
        except Exception:
            self.pending.clear()
            self.counts['UNAVAILABLE_DECISION_BINDING'] += 1

    def observe(self, decision: DecisionIdentity, *, new_opportunity: bool) -> None:
        """Called for the exact already-frozen canonical opportunity; no V1 writes."""
        try:
            opportunity = Opportunity(decision.fixture_id, decision.market, decision.candidate_id)
            old = self.snapshots.load(opportunity.key)
            if old is not None:
                if old.opportunity != opportunity:
                    raise ImmutableConflict('IMMUTABLE_DECISION_CONFLICT')
                reproduce(self.evidence, old)
                self.counts['REPLAY'] += 1
                return
            if new_opportunity is not True:
                raise ValueError('ORIGINAL_DECISION_ASSOCIATION_UNAVAILABLE')
            original, receipt = self.pending[decision.candidate_id]
            if original != decision:
                raise ValueError('DECISION_IDENTITY_MISMATCH')
            scope = self.scopes[decision.fixture_id]
            if (scope.competition_id, scope.season) != (decision.competition_id, decision.season):
                raise ValueError('DECISION_SCOPE_MISMATCH')
            if self.resolve_binding is not None:
                scope = self.resolve_binding(scope, receipt)
            snapshot = assemble(self.evidence, opportunity, receipt, replace(scope, cutoff=receipt.cutoff),
                                expected_teams=(decision.home_team_id, decision.away_team_id))
            if self.retain_snapshot is not None:
                self.retain_snapshot(snapshot)
            self.snapshots.append(snapshot)
            self.counts['CAPTURED'] += 1
        except ImmutableConflict:
            self.counts['UNAVAILABLE_CONFLICT'] += 1
        except Exception:
            self.counts['UNAVAILABLE_SNAPSHOT'] += 1

    def diagnostics(self) -> dict[str, int]:
        """Fixed bounded secret-free status counters; failures need no working DB."""
        return dict(sorted(self.counts.items()))
