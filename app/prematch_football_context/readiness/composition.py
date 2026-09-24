"""One explicit Test/Lab composition. No provider client or runtime state writes."""
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Mapping, TypeVar
from uuid import uuid4

from ..capture.adapter import CaptureAdapter, CaptureScope
from ..capture.repository import DecisionReceipt, EvidenceRepository
from ..contracts import Classification
from ..evidence import Binding
from ..policy import Profile
from ..source_adapter import FormatEvidence
from ..sources import SourceKind, diagnostics, history_query, select_source, target_query
from ..snapshot.observer import DecisionIdentity, SnapshotObserver
from ..snapshot.repository import SnapshotRepository
from ..snapshot.service import available_pins, KINDS
from .ledger import Ledger

Repository = TypeVar('Repository')


def scope_binding(row: tuple, cutoff: datetime) -> Binding:
    """Copy existing classifier assertions; missing entity categories stay UNKNOWN.

    No name classifier, registry expansion or male/senior default is introduced.
    The classifier does not prove regulation duration: both seasons are unverified.
    """
    fixture, league, season, profile, version, reason, hashed, age, flags = row
    p = Profile(profile)
    gender = 'WOMEN' if 'IS_WOMEN' in flags or p == Profile.SENIOR_WOMEN_PRO else (
        'MEN' if p == Profile.SENIOR_MEN_PRO else 'UNKNOWN')
    category = 'NATIONAL' if p in (Profile.INTERNATIONAL_SENIOR, Profile.INTERNATIONAL_YOUTH) else (
        'CLUB' if p in (Profile.SENIOR_MEN_PRO, Profile.SENIOR_WOMEN_PRO, Profile.INTERNATIONAL_CLUB,
                       Profile.LOWER_DIVISION_OR_SEMIPRO, Profile.RESERVE_OR_B_TEAM) else 'UNKNOWN')
    classification = Classification(p, version, reason, flags, gender, age or 'UNKNOWN', category, hashed)
    return Binding(fixture, league, season, cutoff, classification,
                   FormatEvidence(league, season), FormatEvidence(league, season - 1))


class ProspectiveObservation:
    """Failure-isolated decorator of accepted C capture and D snapshot observers.

    Only new canonical opportunities are eligible attempts. Old canonical rows
    are counted separately and never repaired. All stores are explicit, isolated,
    preinitialized, and optional failures cannot affect the PREMATCH return value.
    """

    def __init__(self, root: Path, *, environment: str, clock: Callable[[], datetime]) -> None:
        if environment not in ('TEST', 'LAB'):
            raise ValueError('EXPLICIT_TEST_LAB_REQUIRED')
        self.clock = clock
        self.run_id = uuid4().hex  # Operational only; never part of A/B/C/D hashes.
        self.counts: Counter[str] = Counter()
        self.activity = dict.fromkeys(('responses', 'preparations', 'decisions', 'opportunities', 'attempts'), 0)
        self.evidence = self._open('EVIDENCE_STORE_UNAVAILABLE', lambda: EvidenceRepository(root/'sources.db', writable=True, clock=clock))
        self.snapshots = self._open('SNAPSHOT_STORE_UNAVAILABLE', lambda: SnapshotRepository(root/'snapshots.db', writable=True))
        self.ledger = self._open('LEDGER_UNAVAILABLE', lambda: Ledger(root/'attempts.db', writable=True))
        self.adapter: CaptureAdapter | None = None
        self.observer: SnapshotObserver | None = None
        self.scopes: dict[int, Binding] = {}
        self.receipt: DecisionReceipt | None = None
        self.seen: set[str] = set()
        self._event('RUN', self.run_id, {'environment': environment, 'version': 'FC_READINESS_2'})

    def _open(self, code: str, factory: Callable[[], Repository]) -> Repository | None:
        try:
            return factory()
        except Exception:
            self.counts[code] += 1
            return None

    def _event(self, kind: str, identity: str, document: dict[str, object]) -> None:
        try:
            if self.ledger is None:
                raise ValueError('NO_LEDGER')
            self.ledger.append(kind, identity, document)
        except Exception:
            self.counts['LEDGER_WRITE_FAILURE'] += 1

    def prepare(self, rows: tuple[tuple, ...]) -> None:
        """Plan only queries already implied by discovered runtime scope, never fetch."""
        self.activity['preparations'] += 1
        self.scopes.clear()
        plans: dict[object, set[CaptureScope]] = {}
        for row in rows:
            try:
                scope = scope_binding(row, self.clock())
                self.scopes[scope.fixture_id] = scope
                for query, kind, ttl in (
                    (target_query(scope.fixture_id), SourceKind.TARGET, timedelta(minutes=2)),
                    (history_query(scope.competition_id, scope.season), SourceKind.CURRENT, timedelta(hours=6)),
                    (history_query(scope.competition_id, scope.season-1), SourceKind.PREVIOUS, timedelta(hours=24))):
                    plans.setdefault(query, set()).add(CaptureScope(query, kind, ttl))
            except Exception:
                self.counts['SCOPE_UNAVAILABLE'] += 1
        # Ambiguous multi-season role bindings are unavailable, never guessed.
        self.counts['AMBIGUOUS_QUERY_SCOPE'] += sum(len(v) != 1 for v in plans.values())
        scopes = tuple(next(iter(v)) for v in plans.values() if len(v) == 1)
        if self.evidence is not None:
            self.adapter = CaptureAdapter(self.evidence, scopes)
        if self.evidence is not None and self.snapshots is not None:
            self.observer = SnapshotObserver(self.evidence, self.snapshots, tuple(self.scopes.values()))

    def capture(self, endpoint: str, query: Mapping[str, object], payload: object, completed: datetime) -> None:
        """Persist exact responses immediately, even before classification is planned.

        An exact integer ID request is self-scoping; history roles still require
        prepare(). No discovery row or cache data is turned into an exact response.
        All reuse goes through the unchanged durable receipt and Phase B selector.
        """
        self.activity['responses'] += 1
        try:
            adapter = self.adapter
            if endpoint == '/fixtures' and 'id' in query and not (
                    set(query) == {'id'} and type(query['id']) is int and query['id'] > 0):
                self.counts['SOURCE_UNAVAILABLE_UNSCOPED_QUERY'] += 1
                return
            if (self.evidence is not None and endpoint == '/fixtures' and set(query) == {'id'}
                    and type(query['id']) is int and query['id'] > 0):
                scope = CaptureScope(target_query(query['id']), SourceKind.TARGET, timedelta(minutes=2))
                adapter = CaptureAdapter(self.evidence, (scope,))
            if adapter is None:
                self.counts['CAPTURE_NOT_SCOPED'] += 1
                return
            status = adapter(endpoint, query, payload, completed)
            self.counts['SOURCE_' + status.status] += 1
        except Exception:
            self.counts['SOURCE_CAPTURE_EXCEPTION'] += 1

    def begin(self) -> DecisionReceipt | None:
        """Reuse Phase D's precise final evaluation cutoff hook."""
        self.activity['decisions'] += 1
        self.receipt = None
        try:
            if self.observer is not None:
                self.receipt = self.observer.begin()
            elif self.evidence is not None:
                self.receipt = self.evidence.capture_cutoff()
        except Exception:
            pass
        if self.receipt is None:
            self.counts['DECISION_RECEIPT_FAILURE'] += 1
        return self.receipt

    def bind(self, receipt: DecisionReceipt | None, decisions: tuple[DecisionIdentity, ...]) -> None:
        """Keep associations inside the accepted observer; count final candidates."""
        self.counts['FINAL_EVALUATED_CANDIDATES'] += len(decisions)
        if self.observer is not None:
            self.observer.bind(receipt, decisions)

    def _sources(self, scope: Binding) -> tuple[dict[str, str], dict[str, dict[str, int]]]:
        if self.evidence is None or self.receipt is None:
            return {k.value: 'DECISION_UNAVAILABLE' for k in KINDS}, {}
        pins = available_pins(self.evidence, self.receipt, scope)
        queries = (target_query(scope.fixture_id), history_query(scope.competition_id, scope.season),
                   history_query(scope.competition_id, scope.season-1))
        selections = {kind.value: select_source(tuple(self.evidence.load(i, decision=self.receipt) for i in ids),
                query, cutoff=self.receipt.cutoff, source_kind=kind)
                for kind, query, ids in zip(KINDS, queries, pins)}
        return ({k: s.verdict for k, s in selections.items()},
                {k: dict(diagnostics(s)) for k, s in selections.items()})

    def observe(self, decision: DecisionIdentity, *, new_opportunity: bool) -> None:
        """Count a canonical opportunity once; never snapshot historical canonical rows."""
        self.activity['opportunities'] += 1
        key = f'{decision.fixture_id}:{decision.market}'
        if key in self.seen:
            return
        self.seen.add(key)
        self.activity['attempts'] += int(new_opportunity is True)
        scope = self.scopes.get(decision.fixture_id)
        record = {'run_id': self.run_id, 'key': key, 'candidate_id': decision.candidate_id,
                  'fixture_id': decision.fixture_id, 'competition_id': decision.competition_id,
                  'profile': scope.classification.profile.value if scope else 'UNKNOWN',
                  'attempted': new_opportunity is True,
                  'receipt': self.receipt.receipt_hash if self.receipt and new_opportunity else None}
        event_id = self.run_id + ':' + key
        self._event('OPPORTUNITY', event_id, record)
        if new_opportunity is not True:
            self.counts['OLD_CANONICAL_NOT_ATTEMPTED'] += 1
            return
        sources = {k.value: 'SCOPE_UNAVAILABLE' for k in KINDS}
        source_diagnostics = {}
        status, snapshot_id = 'SNAPSHOT_UNAVAILABLE', None
        try:
            if scope is not None:
                sources, source_diagnostics = self._sources(scope)
            if self.observer is not None:
                self.observer.observe(decision, new_opportunity=True)
            stored = self.snapshots.load(key) if self.snapshots is not None else None
            if stored is not None and stored.opportunity.candidate_id == decision.candidate_id and stored.receipt == self.receipt:
                status, snapshot_id = 'CAPTURED', stored.snapshot_id
            elif sources['TARGET'] != 'SELECTED':
                status = 'TARGET_SOURCE_UNAVAILABLE'
        except Exception:
            status = 'SNAPSHOT_EXCEPTION'
        self.counts[status] += 1
        self._event('RESULT', event_id, {'run_id': self.run_id, 'key': key, 'status': status,
                                       'sources': sources, 'source_diagnostics': source_diagnostics,
                                       'snapshot_id': snapshot_id})

    def finish(self, *, completed: bool, client_failures: int = 0,
               credential_failure: bool = False) -> dict[str, int]:
        """Persist bounded counters; return them for stderr even when stores fail."""
        self.counts['CLIENT_CAPTURE_FAILURE'] += client_failures
        if self.observer is not None:
            self.counts.update({'SNAPSHOT_' + k: v for k, v in self.observer.diagnostics().items()})
        counters = {k: v for k, v in sorted(self.counts.items()) if v}
        self._event('END', self.run_id, {'completed': completed, 'diagnostics': counters,
                                       'activity': self.activity,
                                       'credential_failure': credential_failure})
        counters = {k: v for k, v in sorted(self.counts.items()) if v}
        for repository in (self.evidence, self.snapshots, self.ledger):
            if repository is not None:
                repository.close()
        return counters

    def client_diagnostics(self, failures: int) -> None:
        """Retain the client's fixed counter without inspecting response payloads."""
        self.counts['CLIENT_CAPTURE_FAILURE'] += failures
