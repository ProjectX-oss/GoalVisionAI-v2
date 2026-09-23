"""Retained, sanitized Phase B evidence and offline verification. No persistence.

Build with explicit selections and reviewed scope/format assertions. Replay uses
only this immutable bundle; it never accepts a cache reader or provider callback.
"""
from dataclasses import dataclass, replace
from datetime import datetime
import json
from typing import NoReturn

from .calculations import calculate_context, result_fingerprint
from .contracts import Classification, ContextInput, ContextResult, Exclusion, Freshness, History, Target
from .fingerprint import canonical_bytes, semantic_fingerprint, utc
from .source_adapter import (
    FormatEvidence, STATUS_MAPPING, TargetState, adapt_source, source_ref, target_state,
)
from .sources import (
    PARSER, SELECTION, Selection, SourceKind, choose_header, digest, history_query, selected_verdict, target_query, validate_retained_document,
)

BUNDLE_CONTRACT = 'FC_RETAINED_EVIDENCE_V1'


class EvidenceUnavailable(ValueError):
    """Missing, inconsistent or unsupported evidence; callers must never refresh replay."""


@dataclass(frozen=True, slots=True)
class Binding:
    """Explicit expected fixture/competition/season and reviewed classification evidence."""
    fixture_id: int
    competition_id: int
    season: int
    cutoff: datetime
    classification: Classification
    current_format: FormatEvidence
    previous_format: FormatEvidence

    def __post_init__(self) -> None:
        target_query(self.fixture_id)
        history_query(self.competition_id, self.season)
        if self.season <= 1 or not isinstance(self.classification, Classification):
            raise ValueError('INVALID_BINDING')
        object.__setattr__(self, 'cutoff', utc(self.cutoff))
        for fmt, season in ((self.current_format, self.season), (self.previous_format, self.season - 1)):
            if not isinstance(fmt, FormatEvidence) or (fmt.competition_id, fmt.season) != (self.competition_id, season):
                raise ValueError('FORMAT_SCOPE_MISMATCH')


@dataclass(frozen=True, slots=True)
class Validation:
    kind: SourceKind
    verdict: str
    normalized_facts_hash: str | None
    format_verdict: str
    target_state: TargetState | None = None


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    binding: Binding
    selections: tuple[Selection, ...]
    validations: tuple[Validation, ...]
    exclusions: tuple[Exclusion, ...]
    input_hash: str
    result_hash: str
    semantic_hash: str
    evidence_hash: str
    contract: str = BUNDLE_CONTRACT
    status_mapping: str = STATUS_MAPPING


@dataclass(frozen=True, slots=True)
class Replay:
    inputs: ContextInput
    result: ContextResult


def _fail(reason: str) -> NoReturn:
    raise EvidenceUnavailable('EVIDENCE_UNAVAILABLE: ' + reason)


def _verify_selection(selection: Selection) -> None:
    if selection.version != SELECTION or type(selection.decisions) is not tuple:
        _fail('SELECTION_VERSION_OR_CONTRACT')
    decisions, winner, verdict = choose_header(tuple(d.header for d in selection.decisions),
                                              selection.query, selection.cutoff, selection.kind)
    if winner is not None and verdict == 'SELECTED' and selection.selected is not None:
        verdict = selected_verdict(selection.selected)
    if decisions != selection.decisions or verdict != selection.verdict:
        _fail('SELECTION_INTEGRITY')
    actual = selection.selected.header if selection.selected is not None else None
    if actual != winner:
        _fail('SELECTED_SOURCE_INTEGRITY')
    if selection.selected is not None:
        if selection.selected.header.parser != PARSER:
            _fail('SOURCE_VERSION_MISMATCH')
        doc = json.loads(selection.selected.content)
        validate_retained_document(doc)
        if digest(doc) != actual.content_hash or canonical_bytes(doc).decode() != selection.selected.content:
            _fail('CONTENT_INTEGRITY')


def _reconstruct(binding: Binding, selections: tuple[Selection, ...]) -> tuple[ContextInput, tuple[Validation, ...]]:
    if type(selections) is not tuple or len(selections) != 3:
        _fail('THREE_EXPLICIT_SOURCE_SELECTIONS_REQUIRED')
    target_selection, current, previous = selections
    expected = ((SourceKind.TARGET, target_query(binding.fixture_id)),
                (SourceKind.CURRENT, history_query(binding.competition_id, binding.season)),
                (SourceKind.PREVIOUS, history_query(binding.competition_id, binding.season - 1)))
    identities = {}
    for selection, (kind, query) in zip(selections, expected):
        if (selection.kind, selection.query, selection.cutoff) != (kind, query, binding.cutoff):
            _fail('SOURCE_BINDING')
        _verify_selection(selection)
        for decision in selection.decisions:
            header = decision.header
            identity = (header.namespace, header.source_id)
            if identity in identities and identities[identity] != header:
                _fail('IMMUTABLE_SOURCE_CONFLICT')
            identities[identity] = header
    if target_selection.verdict != 'SELECTED' or target_selection.selected is None:
        _fail('TARGET_SOURCE_UNAVAILABLE')
    target_source = target_selection.selected
    adapted = adapt_source(target_source, binding.classification, competition_id=binding.competition_id, season=binding.season)
    if adapted.verdict != 'VALID' or len(adapted.facts) != 1:
        _fail('TARGET_' + adapted.verdict)
    fact = adapted.facts[0]
    state = target_state(fact.status)
    if fact.fixture_id != binding.fixture_id or state != TargetState.NOT_STARTED:
        _fail('TARGET_STATUS_OR_IDENTITY_REJECTED_' + state.value)
    target = Target('API_FOOTBALL', fact.fixture_id, fact.competition_id, fact.season,
                    fact.home_team_id, fact.away_team_id, fact.kickoff, binding.cutoff,
                    binding.classification, binding.current_format.regulation(binding.cutoff),
                    source_ref(target_source), fact.neutral, fact.status)
    validations = [Validation(SourceKind.TARGET, 'VALID', adapted.normalized_facts_hash,
                              binding.current_format.verdict(binding.cutoff), state)]
    histories = []
    for selection, fmt in ((current, binding.current_format), (previous, binding.previous_format)):
        regulation = fmt.regulation(binding.cutoff)
        if selection.verdict != 'SELECTED' or selection.selected is None:
            stale = any(d.verdict == 'STALE' for d in selection.decisions)
            histories.append(History(fmt.season, None, regulation, (),
                                     Freshness.STALE_COLLECTION if stale else Freshness.UNAVAILABLE))
            validations.append(Validation(selection.kind, selection.verdict, None, fmt.verdict(binding.cutoff)))
            continue
        adapted = adapt_source(selection.selected, binding.classification,
                               competition_id=binding.competition_id, season=fmt.season)
        validations.append(Validation(selection.kind, adapted.verdict, adapted.normalized_facts_hash, fmt.verdict(binding.cutoff)))
        if adapted.verdict == 'VALID':
            histories.append(History(fmt.season, source_ref(selection.selected), regulation, adapted.facts))
        else:
            histories.append(History(fmt.season, None, regulation, (), Freshness.UNAVAILABLE))
    # Explicit empty PREVIOUS selection records omission, while preserving Phase A optional semantics.
    previous_history = None if not previous.decisions else histories[1]
    return ContextInput(target, histories[0], previous_history), tuple(validations)


def evidence_fingerprint(bundle: EvidenceBundle) -> str:
    """Hash all semantic retained evidence, excluding only its own fingerprint."""
    return digest(replace(bundle, evidence_hash=''))


def retain_evidence(binding: Binding, selections: tuple[Selection, ...]) -> EvidenceBundle:
    """Validate and retain replay facts in memory; no snapshot service or database."""
    try:
        inputs, validations = _reconstruct(binding, selections)
        result = calculate_context(inputs)
        bundle = EvidenceBundle(binding, selections, validations, result.pool.exclusions,
                                digest(inputs), result_fingerprint(result), semantic_fingerprint(), '')
        return replace(bundle, evidence_hash=evidence_fingerprint(bundle))
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        if isinstance(exc, EvidenceUnavailable):
            raise
        _fail('INVALID_RETAINED_SOURCE')


def replay_evidence(bundle: EvidenceBundle) -> Replay:
    """Verify versions, hashes, decisions, exclusions and exact Phase A reproduction.

    Absence/corruption raises EVIDENCE_UNAVAILABLE. This API cannot fetch, consult
    a latest reader, repair evidence, or persist anything.
    """
    try:
        if not isinstance(bundle, EvidenceBundle):
            _fail('MISSING_BUNDLE')
        if (bundle.contract, bundle.status_mapping, bundle.semantic_hash) != (
                BUNDLE_CONTRACT, STATUS_MAPPING, semantic_fingerprint()):
            _fail('VERSION_MISMATCH')
        if bundle.evidence_hash != evidence_fingerprint(bundle):
            _fail('BUNDLE_INTEGRITY')
        inputs, validations = _reconstruct(bundle.binding, bundle.selections)
        result = calculate_context(inputs)
        if (validations, result.pool.exclusions, digest(inputs), result_fingerprint(result)) != (
                bundle.validations, bundle.exclusions, bundle.input_hash, bundle.result_hash):
            _fail('REPLAY_INTEGRITY')
        return Replay(inputs, result)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        if isinstance(exc, EvidenceUnavailable):
            raise
        _fail('CORRUPT_RETAINED_EVIDENCE')
