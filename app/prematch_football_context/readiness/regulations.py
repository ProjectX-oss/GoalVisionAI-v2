"""Opt-in retained registry evidence inside the existing isolated readiness ledger."""
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..capture.repository import DecisionReceipt
from ..evidence import Binding
from ..fingerprint import canonical_bytes, canonical_data, utc
from ..regulation_registry.contracts import ReviewedCompetitionRegulation, decode
from ..regulation_registry.repository import Registry
from ..regulation_registry.service import Resolution, evaluate, format_evidence
from ..snapshot.contracts import PrematchFootballContextV2Snapshot
from ..source_adapter import FormatEvidence
from ..sources import digest
from .ledger import Ledger


@dataclass(frozen=True, slots=True)
class PinnedRegistry:
    """Complete verified inventory possessed locally before any associated decision."""
    records: tuple[ReviewedCompetitionRegulation, ...]
    view_id: str
    acquisition_id: str
    acquired_clock: datetime

    @classmethod
    def acquire(cls, path: Path, ledger: Ledger, run_id: str,
                clock: Callable[[], datetime]) -> 'PinnedRegistry':
        """One SQLite read transaction; close the live registry before decisions."""
        started = datetime.now(timezone.utc)
        with closing(Registry(path)) as registry:
            registry.connection.execute('BEGIN')
            records = registry.verify()
            registry.connection.rollback()
        view = canonical_data({'version': 'FC_REGISTRY_VIEW_1', 'records': records})
        view_id = digest(view)
        ledger.append('REGISTRY_VIEW', view_id, view)
        acquired_clock = utc(clock())
        acquisition = canonical_data({'run_id': run_id, 'view_id': view_id,
            'method': 'SQLITE_READ_TRANSACTION_VERIFY_ALL', 'registry_path': str(path.resolve()),
            'started_at_utc': started, 'completed_at_utc': datetime.now(timezone.utc),
            'acquired_clock': acquired_clock})
        acquisition_id = digest(acquisition)
        ledger.append('REGISTRY_ACQUISITION', acquisition_id, acquisition)
        return cls(records, view_id, acquisition_id, acquired_clock)

    def decision(self, ledger: Ledger, receipt: DecisionReceipt) -> None:
        """Persist the acquisition-to-receipt association before using any bridge."""
        if receipt.cutoff < self.acquired_clock:
            raise ValueError('REGISTRY_ACQUIRED_AFTER_CUTOFF')
        ledger.append('REGISTRY_DECISION', receipt.receipt_hash, canonical_data({
            'acquisition_id': self.acquisition_id, 'receipt': receipt}))

    def resolution(self, competition: int, season: int, cutoff: datetime) -> Resolution:
        """Evaluate EVERY applicable record; each new cutoff checks applicability."""
        records = tuple(r for r in self.records if r.applies('API_FOOTBALL', competition, season, cutoff))
        verdict, reason, _ = evaluate(records, 'API_FOOTBALL', competition, season, cutoff)
        return Resolution('API_FOOTBALL', competition, season, cutoff, verdict, records, reason)

    def bind(self, binding: Binding, receipt: DecisionReceipt) -> Binding:
        """Independently resolve current and previous season at the persisted cutoff."""
        formats = tuple(format_evidence(self.resolution(binding.competition_id, season, receipt.cutoff),
                                        cutoff=receipt.cutoff)
                        for season in (binding.season, binding.season - 1))
        return replace(binding, cutoff=receipt.cutoff, current_format=formats[0], previous_format=formats[1])

    def retain(self, ledger: Ledger, snapshot: PrematchFootballContextV2Snapshot) -> None:
        """Durable full proof then exact snapshot link; errors prevent snapshot append."""
        proofs = {}
        for role, fmt in formats(snapshot):
            if not registry_format(fmt):
                continue
            resolution = self.resolution(fmt.competition_id, fmt.season, snapshot.receipt.cutoff)
            if format_evidence(resolution, cutoff=resolution.cutoff) != fmt:
                raise ValueError('REGULATION_BRIDGE_MISMATCH')
            proof = canonical_data({'view_id': self.view_id, 'resolution': resolution,
                                    'resolution_fingerprint': resolution.fingerprint,
                                    'format_evidence': format_evidence(resolution, cutoff=resolution.cutoff)})
            proof_id = digest(proof)
            ledger.append('REGULATION_PROOF', proof_id, proof)
            proofs[role] = proof_id
        if proofs:
            ledger.append('REGULATION_LINK', snapshot.snapshot_id, canonical_data({
                'receipt': snapshot.receipt, 'opportunity': snapshot.opportunity,
                'acquisition_id': self.acquisition_id, 'proofs': proofs}))


def formats(snapshot: PrematchFootballContextV2Snapshot) -> tuple[tuple[str, FormatEvidence], ...]:
    """The two independently scoped format assertions in an unchanged snapshot."""
    return (('current', snapshot.binding.current_format), ('previous', snapshot.binding.previous_format))


def registry_format(fmt: FormatEvidence) -> bool:
    """Registry bridge identity distinguishes new proofs from legacy assertions."""
    return bool(fmt.proof_id and fmt.proof_id.startswith('FC_V2_REGISTRY.'))


def verify_retained(snapshot: PrematchFootballContextV2Snapshot,
                    events: list[tuple[str, str, dict[str, object]]], run_id: str) -> None:
    """Reevaluate complete retained inventory offline; never open the live registry."""
    required = {role: fmt for role, fmt in formats(snapshot) if registry_format(fmt)}
    if not required:
        return  # Legacy snapshots retain their exact contract and stored bytes.
    indexed = {(kind, key): doc for kind, key, doc in events}
    link = indexed['REGULATION_LINK', snapshot.snapshot_id]
    acquisition_id = link['acquisition_id']
    acquisition = indexed['REGISTRY_ACQUISITION', acquisition_id]
    view_id = acquisition['view_id']
    view = indexed['REGISTRY_VIEW', view_id]
    decision = indexed['REGISTRY_DECISION', snapshot.receipt.receipt_hash]
    if (digest(acquisition) != acquisition_id or digest(view) != view_id
            or view['version'] != 'FC_REGISTRY_VIEW_1' or acquisition['run_id'] != run_id
            or acquisition['method'] != 'SQLITE_READ_TRANSACTION_VERIFY_ALL'
            or datetime.fromisoformat(acquisition['acquired_clock']) > snapshot.receipt.cutoff
            or datetime.fromisoformat(acquisition['started_at_utc']) > datetime.fromisoformat(acquisition['completed_at_utc'])
            or decision != canonical_data({'acquisition_id': acquisition_id, 'receipt': snapshot.receipt})
            or link['receipt'] != canonical_data(snapshot.receipt)
            or link['opportunity'] != canonical_data(snapshot.opportunity)
            or set(link['proofs']) != set(required)):
        raise ValueError('REGULATION_BINDING_INTEGRITY')
    records = tuple(decode(canonical_bytes(r).decode()) for r in view['records'])
    if tuple(r.review_id for r in records) != tuple(sorted({r.review_id for r in records})):
        raise ValueError('REGULATION_INVENTORY_INTEGRITY')
    pinned = PinnedRegistry(records, view_id, acquisition_id, datetime.fromisoformat(acquisition['acquired_clock']))
    for role, fmt in required.items():
        proof_id = link['proofs'][role]
        proof = indexed['REGULATION_PROOF', proof_id]
        resolution = pinned.resolution(snapshot.binding.competition_id, fmt.season, snapshot.receipt.cutoff)
        expected = canonical_data({'view_id': view_id, 'resolution': resolution,
            'resolution_fingerprint': resolution.fingerprint,
            'format_evidence': format_evidence(resolution, cutoff=resolution.cutoff)})
        if digest(proof) != proof_id or proof != expected or canonical_data(fmt) != expected['format_evidence']:
            raise ValueError('REGULATION_PROOF_INTEGRITY')
