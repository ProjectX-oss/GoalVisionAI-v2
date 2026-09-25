"""Regulation evidence audit regressions; all asserted proofs here are synthetic.

No resolver or reviewed registry is introduced by this audit. These tests pin the
existing trusted assertion boundary and prove that runtime metadata cannot fill it.
"""
import asyncio
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import socket

import httpx
import pytest

from app.football.client import FootballClient
from app.prematch_football_context.capture.repository import ImmutableConflict
from app.prematch_football_context.evidence import EvidenceUnavailable, replay_evidence
from app.prematch_football_context.fingerprint import canonical_bytes
from app.prematch_football_context.policy import Profile
from app.prematch_football_context.readiness.__main__ import initialize
from app.prematch_football_context.readiness.composition import ProspectiveObservation, scope_binding
from app.prematch_football_context.readiness.report import coverage
from app.prematch_football_context.snapshot.service import assemble, reproduce
from app.prematch_football_context.source_adapter import FormatEvidence, legacy_cache_candidate, sanitize_payload
from app.prematch_football_context.sources import SourceKind, history_query, select_source
from tests.test_prematch_football_context_readiness import ROW, collect
from tests.test_prematch_football_context_readiness_hardening import decide, target
from tests.test_prematch_football_context_sources import T, binding, bundle, candidate, raw


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        pytest.fail('REAL_NETWORK_FORBIDDEN')
    monkeypatch.setattr(socket.socket, 'connect', fail)
    monkeypatch.setattr(socket, 'create_connection', fail)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', fail)


@pytest.mark.parametrize('profile', tuple(Profile))
def test_category_assertions_never_supply_format(profile: Profile) -> None:
    scope = scope_binding(ROW[:3] + (profile.value,) + ROW[4:], T)
    assert scope.current_format == FormatEvidence(10, 2026)
    assert scope.previous_format == FormatEvidence(10, 2025)
    assert scope.current_format.verdict(T) == 'REGULATION_UNVERIFIED'


@pytest.mark.parametrize('hint', ['name', 'elapsed', 'periods', 'extra_time_absent', 'unattested_minutes'])
def test_fixture_hints_do_not_prove_duration(hint: str) -> None:
    rows = [raw(i) for i in range(1, 9)]
    baseline = sanitize_payload(rows)
    for row in rows:
        if hint == 'name':
            row['league'].update(name='Premier League', type='League', country='England')
        elif hint == 'elapsed':
            row['fixture']['status']['elapsed'] = 90
        elif hint == 'periods':
            row['fixture']['periods'] = {'first': 1000000000, 'second': 1000002700}
        elif hint == 'extra_time_absent':
            row['score']['extratime'] = {'home': None, 'away': None}
        else:
            row['league']['regulation_minutes'] = 90  # Invented/unattested field.
    assert sanitize_payload(rows) == baseline
    retained = bundle(current=(candidate(rows),), bind=scope_binding(ROW, T))
    result = replay_evidence(retained).result
    assert all(f.value is None and 'REGULATION_UNVERIFIED' in f.reasons for f in result.features)


@pytest.mark.parametrize('competition,season,slot', [
    (11, 2026, 'current_format'), (10, 2025, 'current_format'),
    (10, 2026, 'previous_format'), (11, 2025, 'previous_format'),
])
def test_proven_format_cannot_cross_scope(competition: int, season: int, slot: str) -> None:
    proof = replace(binding().current_format, competition_id=competition, season=season)
    assert proof.verdict(T) == 'VERIFIED_90'  # Verdict alone is not scope validation.
    with pytest.raises(ValueError, match='FORMAT_SCOPE_MISMATCH'):
        binding(**{slot: proof})


def test_current_proof_does_not_upgrade_previous_season() -> None:
    scope = binding(previous_format=FormatEvidence(10, 2025))
    retained = bundle(bind=scope, previous=(candidate(kind=SourceKind.PREVIOUS),))
    verdicts = {v.kind: v.format_verdict for v in retained.validations}
    assert verdicts[SourceKind.CURRENT] == 'VERIFIED_90'
    assert verdicts[SourceKind.PREVIOUS] == 'REGULATION_UNVERIFIED'


@pytest.mark.parametrize('offset', [-1, 0, 1])
def test_format_cutoff_and_later_reuse(offset: int) -> None:
    proof = replace(binding().current_format, known_at=T + timedelta(seconds=offset))
    expected = 'VERIFIED_90' if offset < 0 else 'REGULATION_UNVERIFIED'
    assert proof.verdict(T) == expected
    # The accepted supplied assertion has exact-season scope and no expiry field.
    assert proof.verdict(T + timedelta(seconds=2)) == 'VERIFIED_90'
    assert proof.verdict(T) == expected  # Later use does not rewrite earlier truth.


@pytest.mark.parametrize('field,value', [('minutes', 80), ('proof_hash', 'c'*64),
                                       ('proof_id', 'OTHER'), ('known_at', T)])
def test_modified_format_invalidates_retained_bundle(field: str, value: object) -> None:
    retained = bundle()
    modified = replace(retained, binding=replace(retained.binding,
        current_format=replace(retained.binding.current_format, **{field: value})))
    with pytest.raises(EvidenceUnavailable, match='BUNDLE_INTEGRITY'):
        replay_evidence(modified)
    assert replay_evidence(retained) == replay_evidence(retained)


def test_plausible_legacy_value_is_not_proof() -> None:
    row = raw()
    row['league']['regulation_minutes'] = 90
    legacy = legacy_cache_candidate(source_id='legacy', query=history_query(10, 2026),
        kind=SourceKind.CURRENT, retrieved_at=T-timedelta(minutes=1),
        expiry=T+timedelta(hours=1), payload=[row])
    selection = select_source((legacy,), history_query(10, 2026), cutoff=T, source_kind=SourceKind.CURRENT)
    assert selection.selected is None
    assert selection.decisions[0].verdict == 'ASOF_UNPROVEN'
    assert scope_binding(ROW, T).current_format.verdict(T) == 'REGULATION_UNVERIFIED'


@pytest.mark.parametrize('status', ['AET', 'PEN'])
@pytest.mark.parametrize('explicit_score', [False, True])
def test_format_proof_never_fabricates_regulation_score(status: str, explicit_score: bool) -> None:
    rows = [raw(i, status=status, gf=1 if explicit_score else None,
                ga=1 if explicit_score else None) for i in range(1, 9)]
    for row in rows:
        row['goals'] = {'home': 4, 'away': 3}
    replay = replay_evidence(bundle(current=(candidate(rows),)))
    assert binding().current_format.verdict(T) == 'VERIFIED_90'
    if explicit_score:
        assert replay.result.features[0].value == '1.000000'
        assert replay.result.features[1].value == '1.000000'
    else:
        assert all(f.value is None for f in replay.result.features)
        assert len(replay.result.pool.exclusions) == 8
        assert all('INVALID_REGULATION_SCORE_PAIR' in e.reasons for e in replay.result.pool.exclusions)


def test_later_assertion_cannot_replace_immutable_snapshot(tmp_path: Path) -> None:
    observer = collect(tmp_path)
    original = observer.snapshots.load('9999:HOME_WIN')
    original_bytes = canonical_bytes(original)
    assert observer.snapshots.append(original) == observer.snapshots.append(original)
    for minutes in (90, 80):
        scope = replace(original.binding, current_format=replace(binding().current_format, minutes=minutes))
        changed = assemble(observer.evidence, original.opportunity, original.receipt, scope)
        with pytest.raises(ImmutableConflict):
            observer.snapshots.append(changed)
    assert canonical_bytes(reproduce(observer.evidence, original)) == original_bytes
    assert canonical_bytes(observer.snapshots.load(original.opportunity.key)) == original_bytes
    assert original.projection.values == (None,)*7
    observer.finish(completed=True)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    assert coverage(tmp_path)['reproduction']['VERIFIED'] == 1
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}


def test_observation_and_format_checks_add_zero_provider_requests(tmp_path: Path) -> None:
    sequences = []
    for enabled in (False, True):
        root = tmp_path / str(enabled)
        initialize(root)
        observer = ProspectiveObservation(root, environment='TEST', clock=lambda: T) if enabled else None
        if observer:
            observer.prepare((ROW,))
        requests = []
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append((request.url.path, tuple(sorted(request.url.params.items()))))
            payload = target() if 'id' in request.url.params else {'response': [raw(i) for i in range(1, 9)]}
            return httpx.Response(200, json=payload)
        async def run() -> None:
            client = FootballClient(api_key='SYNTHETIC_ONLY', response_observer=observer.capture if observer else None,
                                    completion_clock=lambda: T)
            await client._client.aclose()
            client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=client.BASE_URL)
            client.MIN_REQUEST_INTERVAL_SECONDS = 0
            try:
                await client.fixture(9999)
                await client.finished_matches(10, 2026, last=99)
                count = client.request_count
                assert count == 2
                for _ in range(3):
                    assert scope_binding(ROW, T).current_format.verdict(T) == 'REGULATION_UNVERIFIED'
                if observer:
                    snapshot = decide(observer)
                    assert snapshot.projection.values == (None,)*7
                    assert reproduce(observer.evidence, snapshot) == snapshot
                    observer.finish(completed=True)
                    assert coverage(root)['reproduction']['VERIFIED'] == 1
                assert client.request_count == count
            finally:
                await client.close()
        asyncio.run(run())
        sequences.append(requests)
    assert sequences[0] == sequences[1] == [
        ('/fixtures', (('id', '9999'),)),
        ('/fixtures', (('last', '99'), ('league', '10'), ('season', '2026'), ('status', 'FT'))),
    ]
