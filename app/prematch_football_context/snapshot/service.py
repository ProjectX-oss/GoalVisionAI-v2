"""Offline Phase C → B → A assembly and exact pinned reproduction."""
from dataclasses import replace

from ..capture.repository import DecisionReceipt, EvidenceRepository
from ..evidence import Binding, EvidenceUnavailable, replay_evidence, retain_evidence
from ..sources import SourceKind, history_query, select_source, target_query
from .contracts import Opportunity, PrematchFootballContextV2Snapshot, project, snapshot_fingerprint

KINDS = (SourceKind.TARGET, SourceKind.CURRENT, SourceKind.PREVIOUS)


def _receipt(repository: EvidenceRepository, receipt: DecisionReceipt) -> None:
    if repository.load_cutoff(receipt.receipt_hash) != receipt:
        raise EvidenceUnavailable('EVIDENCE_UNAVAILABLE: DECISION_MISMATCH')


def available_pins(repository: EvidenceRepository, receipt: DecisionReceipt,
                   binding: Binding) -> tuple[tuple[str, ...], ...]:
    """Read committed receipts strictly before T's durable marker; never wall time.

    Candidates are restricted to the three exact scope queries. Unregistered
    sources and later acknowledgements never enter the candidate universe.
    Loading verifies the Phase C receipt and material, even at unequal times.
    """
    _receipt(repository, receipt)
    queries = (target_query(binding.fixture_id), history_query(binding.competition_id, binding.season),
               history_query(binding.competition_id, binding.season - 1))
    pins: list[list[str]] = [[], [], []]
    rows = repository.connection.execute(
        "SELECT source_id FROM fc_receipts WHERE event='SOURCE' AND ordering<? ORDER BY ordering",
        (receipt.ordering,))
    for (identity,) in rows:
        candidate = repository.load(identity, decision=receipt)
        for index, (kind, query) in enumerate(zip(KINDS, queries)):
            if (candidate.header.kind, candidate.header.query) == (kind, query):
                pins[index].append(identity)
    return tuple(tuple(sorted(group)) for group in pins)


def assemble(repository: EvidenceRepository, opportunity: Opportunity, receipt: DecisionReceipt,
             binding: Binding, *, source_candidates: tuple[tuple[str, ...], ...] | None = None,
             expected_teams: tuple[int, int] | None = None) -> PrematchFootballContextV2Snapshot:
    """Build only from verified durable evidence and explicit scope assertions.

    The optional exact candidate manifest is for reproduction. Every pin still
    requires Phase C ordering proof. TARGET unavailable is a hard failure;
    CURRENT/PREVIOUS unavailable retain the accepted Phase A/B missingness.
    """
    _receipt(repository, receipt)
    if binding.cutoff != receipt.cutoff or opportunity.fixture_id != binding.fixture_id:
        raise EvidenceUnavailable('EVIDENCE_UNAVAILABLE: DECISION_BINDING')
    pins = available_pins(repository, receipt, binding) if source_candidates is None else source_candidates
    if type(pins) is not tuple or len(pins) != 3:
        raise EvidenceUnavailable('EVIDENCE_UNAVAILABLE: SOURCE_PINS')
    queries = (target_query(binding.fixture_id), history_query(binding.competition_id, binding.season),
               history_query(binding.competition_id, binding.season - 1))
    selections = []
    for identities, kind, query in zip(pins, KINDS, queries):
        if type(identities) is not tuple or identities != tuple(sorted(set(identities))):
            raise EvidenceUnavailable('EVIDENCE_UNAVAILABLE: SOURCE_PINS')
        candidates = tuple(repository.load(identity, decision=receipt) for identity in identities)
        # Require verified strict receipt ordering for EVERY source, not merely
        # the timestamp test used by Phase B for ordinary <T supplied inputs.
        if any(c.header.timing.before_capture is None or (c.header.kind, c.header.query) != (kind, query)
               for c in candidates):
            raise EvidenceUnavailable('EVIDENCE_UNAVAILABLE: SOURCE_ORDER_OR_SCOPE')
        selections.append(select_source(candidates, query, cutoff=receipt.cutoff, source_kind=kind))
    bundle = retain_evidence(binding, tuple(selections))
    replay = replay_evidence(bundle)
    target = replay.inputs.target
    if expected_teams is not None and expected_teams != (target.home_team_id, target.away_team_id):
        raise EvidenceUnavailable('EVIDENCE_UNAVAILABLE: TARGET_TEAMS')
    projection = project(replay.result)
    snapshot = PrematchFootballContextV2Snapshot(
        opportunity, receipt, binding, target.home_team_id, target.away_team_id, pins,
        tuple(s.selected.header.source_id if s.selected is not None else None for s in selections),
        bundle.evidence_hash, bundle.semantic_hash, bundle.input_hash, bundle.result_hash,
        projection, projection.fingerprint,
        tuple((v.kind.value, v.verdict, v.format_verdict) for v in bundle.validations),
        tuple((s.kind.value, d.header.source_id, d.verdict) for s in selections for d in s.decisions),
        tuple((e.fixture_id, e.reasons) for e in bundle.exclusions))
    return replace(snapshot, snapshot_hash=snapshot_fingerprint(snapshot))


def reproduce(repository: EvidenceRepository, snapshot: PrematchFootballContextV2Snapshot) -> PrematchFootballContextV2Snapshot:
    """Rebuild from exact retained pins; fail closed on any missing/corrupt binding."""
    try:
        if not snapshot.snapshot_hash or snapshot_fingerprint(snapshot) != snapshot.snapshot_hash:
            raise ValueError('SNAPSHOT_HASH')
        actual = assemble(repository, snapshot.opportunity, snapshot.receipt, snapshot.binding,
                          source_candidates=snapshot.source_candidates,
                          expected_teams=(snapshot.home_team_id, snapshot.away_team_id))
        if actual != snapshot:
            raise ValueError('REPRODUCTION_MISMATCH')
        return actual
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise EvidenceUnavailable('EVIDENCE_UNAVAILABLE: SNAPSHOT_REPRODUCTION') from exc
