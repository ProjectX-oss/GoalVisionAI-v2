"""Registry tests use fictional statements and mappings. NO real reviewed evidence."""
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
import json
from pathlib import Path
import socket
import sqlite3

import httpx
import pytest

from app.prematch_football_context.capture.repository import ImmutableConflict
from app.prematch_football_context.evidence import replay_evidence
from app.prematch_football_context.fingerprint import canonical_bytes
from app.prematch_football_context.regulation_registry import (
    Registry, RetainedSource, ReviewedCompetitionRegulation, SourceType, Verdict,
    format_evidence, initialize, resolve,
)
from app.prematch_football_context.regulation_registry.__main__ import main
from app.prematch_football_context.regulation_registry.contracts import VERSION, decode, digest
from app.prematch_football_context.regulation_registry.repository import TABLE
from app.prematch_football_context.snapshot.contracts import project
from app.prematch_football_context.source_adapter import FormatEvidence
from tests.test_prematch_football_context_sources import T, binding, bundle, candidate, raw


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        pytest.fail('NETWORK_FORBIDDEN')
    monkeypatch.setattr(socket.socket, 'connect', fail)
    monkeypatch.setattr(socket, 'create_connection', fail)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', fail)


def record(**changes: object) -> ReviewedCompetitionRegulation:
    """Fictional text under an authority-shaped URL, never an actual source review."""
    doc = dict(review_id='SYNTHETIC_REVIEW_1', provider='API_FOOTBALL', competition_id=10,
        season=2026, regulation_minutes=90, organizer='UEFA', competition_name='SYNTHETIC CUP',
        source_type=SourceType.ORGANIZER_REGULATIONS, source_title='SYNTHETIC REGULATIONS',
        source_url='https://www.uefa.com/SYNTHETIC-NOT-A-REAL-DOCUMENT', source_edition='SYNTHETIC 2026',
        source_effective_from=T-timedelta(days=100), source_effective_until=T+timedelta(days=100),
        reviewed_statement='SYNTHETIC ONLY: this competition uses 90 regulation minutes.',
        retained_source_content=RetainedSource('SYNTHETIC DOCUMENT', 'SYNTHETIC article 1',
            'SYNTHETIC ONLY: matches have two 45 minute halves.',
            'SYNTHETIC CUP 2026 only; synthetic senior category.',
            'SYNTHETIC mapping fixture: API_FOOTBALL competition 10, season 2026 is SYNTHETIC CUP.'),
        reviewer='SYNTHETIC_REVIEWER', reviewed_at=T-timedelta(days=1),
        validity_start=None, validity_end=None, evidence_version=VERSION)
    doc.update(changes)
    doc['source_content_sha256'] = digest('FC_V2_REGULATION_SOURCE_V1', doc['retained_source_content'])
    doc['evidence_fingerprint'] = digest(VERSION, doc)
    return ReviewedCompetitionRegulation(**doc)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / 'synthetic-regulations.db'
    initialize(path)
    return path


def append(db: Path, *records: ReviewedCompetitionRegulation) -> None:
    with closing(Registry(db, writable=True)) as registry:
        for item in records:
            registry.append(item)


def lookup(db: Path, **changes: object):
    return resolve(db, **(dict(provider='API_FOOTBALL', competition_id=10, season=2026, cutoff=T) | changes))


@pytest.mark.parametrize('minutes,verdict', [(90, Verdict.VERIFIED_90), (80, Verdict.UNSUPPORTED_REGULATION)])
def test_reviewed_duration_bridge_and_offline_reproduction(db: Path, minutes: int, verdict: Verdict) -> None:
    reviewed = record(regulation_minutes=minutes, reviewed_statement=f'SYNTHETIC duration: {minutes} minutes.')
    append(db, reviewed)
    before = db.read_bytes()
    resolution = lookup(db)
    assert resolution.verdict == verdict
    assert resolution.records == (reviewed,)
    fmt = format_evidence(resolution, cutoff=T)
    assert fmt.minutes == minutes and fmt.verdict(T) == verdict
    assert fmt.proof_hash == resolution.fingerprint
    exported = json.loads(canonical_bytes(resolution))
    assert digest('FC_V2_REGULATION_RESOLUTION_V1', exported) == fmt.proof_hash
    assert tuple(decode(json.dumps(r)) for r in exported['records']) == resolution.records
    assert fmt.known_at == reviewed.reviewed_at
    with closing(Registry(db)) as registry:
        assert decode(canonical_bytes(registry.verify()[0]).decode()) == reviewed
    assert lookup(db) == resolution and db.read_bytes() == before
    with pytest.raises(FrozenInstanceError):
        reviewed.regulation_minutes = 70


def test_empty_missing_wrong_provider_and_identity(db: Path) -> None:
    assert lookup(db).verdict == Verdict.REGULATION_UNVERIFIED
    append(db, record())
    for changes in ({'provider': 'OTHER'}, {'competition_id': 11}, {'season': 2025}, {'season': 2027}):
        result = lookup(db, **changes)
        assert result.verdict == Verdict.REGULATION_UNVERIFIED and result.records == ()
    assert lookup(db.parent/'missing.db').verdict == Verdict.REGULATION_UNVERIFIED
    assert not (db.parent/'missing.db').exists()


def test_declared_season_interval_only(db: Path) -> None:
    content = replace(record().retained_source_content,
                      applicability_statement='SYNTHETIC explicit applicability: seasons 2025 through 2027.')
    append(db, record(validity_start=2025, validity_end=2027, retained_source_content=content))
    for season in (2025, 2026, 2027):
        assert lookup(db, season=season).verdict == Verdict.VERIFIED_90
    for season in (2024, 2028):
        assert lookup(db, season=season).verdict == Verdict.REGULATION_UNVERIFIED
    assert lookup(db, competition_id=11).verdict == Verdict.REGULATION_UNVERIFIED


@pytest.mark.parametrize('offset', [-1, 0, 1])
def test_review_strictly_before_cutoff(db: Path, offset: int) -> None:
    append(db, record(reviewed_at=T+timedelta(microseconds=offset)))
    expected = Verdict.VERIFIED_90 if offset < 0 else Verdict.REGULATION_UNVERIFIED
    assert lookup(db).verdict == expected
    assert lookup(db, cutoff=T+timedelta(seconds=2)).verdict == Verdict.VERIFIED_90
    assert lookup(db).verdict == expected


@pytest.mark.parametrize('changes', [
    {'source_effective_from': T+timedelta(seconds=1)}, {'source_effective_until': T},
])
def test_effective_interval_is_half_open(db: Path, changes: dict) -> None:
    append(db, record(**changes))
    assert lookup(db).verdict == Verdict.REGULATION_UNVERIFIED


def test_all_conflicting_authorities_fail_closed_and_order_is_stable(db: Path, tmp_path: Path) -> None:
    a = record()
    b = record(review_id='SYNTHETIC_REVIEW_2', organizer='FIFA',
               source_url='https://www.fifa.com/SYNTHETIC-NOT-A-REAL-DOCUMENT', regulation_minutes=80,
               reviewed_statement='SYNTHETIC duration: 80 minutes.')
    append(db, a, b)
    result = lookup(db)
    assert result.verdict == Verdict.CONFLICTING_REGULATION_EVIDENCE
    assert format_evidence(result, cutoff=T).verdict(T) == Verdict.REGULATION_UNVERIFIED
    second = tmp_path / 'second.db'
    initialize(second)
    append(second, b, a)
    assert lookup(second) == result
    # A future competing review cannot invalidate an earlier decision.
    future = tmp_path / 'future.db'
    initialize(future)
    append(future, a, record(review_id='FUTURE_SYNTHETIC', regulation_minutes=80, reviewed_at=T))
    assert lookup(future).verdict == Verdict.VERIFIED_90
    assert lookup(future, cutoff=T+timedelta(seconds=1)).verdict == Verdict.CONFLICTING_REGULATION_EVIDENCE


def test_same_duration_retains_all_proofs(db: Path) -> None:
    append(db, record(), record(review_id='SYNTHETIC_SECOND'))
    result = lookup(db)
    assert result.verdict == Verdict.VERIFIED_90 and len(result.records) == 2
    assert format_evidence(result, cutoff=T).proof_hash == result.fingerprint


def test_ifab_is_only_supporting_and_cannot_override_organizer(db: Path) -> None:
    append(db, record(review_id='SYNTHETIC_IFAB', organizer='IFAB', source_type=SourceType.IFAB_BASE_LAW,
                      source_url='https://www.theifab.com/SYNTHETIC-NOT-A-REAL-DOCUMENT'))
    assert lookup(db).verdict == Verdict.REGULATION_UNVERIFIED
    assert format_evidence(lookup(db), cutoff=T) == FormatEvidence(10, 2026)
    assert lookup(db, competition_id=12345).verdict == Verdict.REGULATION_UNVERIFIED
    append(db, record(regulation_minutes=80))
    assert lookup(db).verdict == Verdict.UNSUPPORTED_REGULATION


def test_replay_and_changed_identity_conflict(db: Path) -> None:
    reviewed = record()
    with closing(Registry(db, writable=True)) as registry:
        assert registry.append(reviewed) == registry.append(reviewed)
        with pytest.raises(ImmutableConflict):
            registry.append(record(reviewer='ANOTHER_SYNTHETIC_REVIEWER'))
        assert registry.verify() == (reviewed,)
    with closing(Registry(db)) as registry:
        with pytest.raises(ValueError, match='READ_ONLY'):
            registry.append(reviewed)


@pytest.mark.parametrize('sql', [f'UPDATE {TABLE} SET document=document', f'DELETE FROM {TABLE}',
    f'INSERT OR REPLACE INTO {TABLE} SELECT * FROM {TABLE}',
    f'REPLACE INTO {TABLE} SELECT * FROM {TABLE}'])
def test_sql_immutability_even_without_recursive_triggers(db: Path, sql: str) -> None:
    append(db, record())
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute('PRAGMA recursive_triggers').fetchone() == (0,)
        with pytest.raises(sqlite3.IntegrityError, match='IMMUTABLE'):
            connection.execute(sql)
    assert lookup(db).verdict == Verdict.VERIFIED_90


@pytest.mark.parametrize('field', ['source_content_sha256', 'evidence_fingerprint', 'retained_source_content'])
def test_tampered_import_rejected(field: str) -> None:
    doc = json.loads(canonical_bytes(record()))
    if field == 'retained_source_content':
        doc[field]['excerpt'] = 'SYNTHETIC altered source'
    else:
        doc[field] = '0'*64
    with pytest.raises(ValueError, match='INTEGRITY'):
        decode(json.dumps(doc))


@pytest.mark.parametrize('changes', [
    {'organizer': 'WIKIPEDIA'}, {'source_type': 'THIRD_PARTY'},
    {'source_url': 'https://en.wikipedia.org/wiki/Football'},
    {'source_url': 'https://uefa.com.example.org/rules'},
    {'source_url': 'https://example.org/uefa.com/rules'},
    {'source_url': 'http://www.uefa.com/rules'},
    {'source_url': 'https://user:password@uefa.com/rules'},
    {'source_url': 'https://uefa.com/rules?token=secret'},
    {'organizer': 'IFAB', 'source_url': 'https://theifab.com/laws'},
    {'source_type': SourceType.IFAB_BASE_LAW},
    {'reviewer': ''}, {'reviewed_statement': ''}, {'competition_id': True},
    {'validity_start': 2025}, {'validity_start': 2027, 'validity_end': 2025},
    {'source_effective_until': T-timedelta(days=101)}, {'reviewed_at': T.replace(tzinfo=None)},
])
def test_invalid_authority_or_incomplete_contract(changes: dict) -> None:
    with pytest.raises(ValueError):
        record(**changes)


def test_all_fields_required_and_bounded_content() -> None:
    document = json.loads(canonical_bytes(record()))
    for field in document:
        with pytest.raises(ValueError):
            decode(json.dumps({key: value for key, value in document.items() if key != field}))
    with pytest.raises(ValueError, match='EXCERPT_TOO_LONG'):
        replace(record().retained_source_content, excerpt='word '*26)
    with pytest.raises(ValueError):
        decode('{"a":1,"a":2}')
    with pytest.raises(ValueError):
        decode('x'*32769)


@pytest.mark.parametrize('damage', ['file', 'row', 'identity', 'guard', 'schema'])
def test_corrupt_registry_fails_closed(db: Path, damage: str) -> None:
    append(db, record())
    if damage == 'file':
        db.write_bytes(b'NOT SQLITE')
    else:
        with closing(sqlite3.connect(db)) as connection, connection:
            if damage == 'schema':
                connection.execute('CREATE TABLE unrelated(x)')
            else:
                connection.execute(f'DROP TRIGGER {TABLE}_no_update')
                if damage == 'row':
                    connection.execute(f"UPDATE {TABLE} SET document='{{}}'")
                if damage == 'identity':
                    connection.execute(f"UPDATE {TABLE} SET review_id='changed'")
                if damage != 'guard':
                    from app.prematch_football_context.regulation_registry.repository import SCHEMA
                    connection.execute(SCHEMA[1])
    assert lookup(db).verdict == Verdict.REGULATION_UNVERIFIED
    assert lookup(db).reason == 'REGISTRY_UNAVAILABLE_OR_INVALID'


def test_locked_registry_and_explicit_initialization(db: Path) -> None:
    append(db, record())
    original = db.read_bytes()
    with pytest.raises(FileExistsError):
        initialize(db)
    assert db.read_bytes() == original
    with closing(sqlite3.connect(db)) as connection:
        connection.execute('BEGIN EXCLUSIVE')
        assert lookup(db).verdict == Verdict.REGULATION_UNVERIFIED
        connection.rollback()
    assert lookup(db).verdict == Verdict.VERIFIED_90


def test_bridge_preserves_seven_feature_results(db: Path) -> None:
    append(db, record())
    fmt = format_evidence(lookup(db), cutoff=T)
    actual = replay_evidence(bundle(bind=binding(current_format=fmt))).result
    expected = replay_evidence(bundle()).result
    assert project(actual) == project(expected)
    assert len(actual.features) == 7
    with pytest.raises(ValueError, match='CUTOFF_MISMATCH'):
        format_evidence(lookup(db), cutoff=T+timedelta(seconds=1))


@pytest.mark.parametrize('status', ['AET', 'PEN'])
@pytest.mark.parametrize('explicit_score', [True, False])
def test_bridge_format_never_proves_regulation_score(db: Path, status: str, explicit_score: bool) -> None:
    append(db, record())
    rows = [raw(i, status=status, gf=1 if explicit_score else None,
                ga=1 if explicit_score else None) for i in range(1, 9)]
    for row in rows:
        row['goals'] = {'home': 4, 'away': 3}
    fmt = format_evidence(lookup(db), cutoff=T)
    result = replay_evidence(bundle(bind=binding(current_format=fmt), current=(candidate(rows),))).result
    if explicit_score:
        assert result.features[0].value == result.features[1].value == '1.000000'
    else:
        assert all(f.value is None for f in result.features)
        assert all('INVALID_REGULATION_SCORE_PAIR' in e.reasons for e in result.pool.exclusions)


def test_cli_complete_workflow_and_rejected_import(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    db = tmp_path/'cli.db'
    path = tmp_path/'review.json'
    path.write_bytes(canonical_bytes(record()))
    assert main(['init', '--db', str(db)]) == 0
    assert main(['validate', str(path)]) == 0
    assert main(['import', '--db', str(db), str(path)]) == 0
    assert main(['import', '--db', str(db), str(path)]) == 0
    assert main(['inspect', '--db', str(db), '--review-id', record().review_id]) == 0
    assert main(['verify', '--db', str(db)]) == 0
    assert main(['resolve', '--db', str(db), '--provider', 'API_FOOTBALL', '--competition-id', '10',
                 '--season', '2026', '--cutoff', T.isoformat()]) == 0
    assert 'VERIFIED_90' in capsys.readouterr().out
    path.write_text('{}')
    assert main(['import', '--db', str(db), str(path)]) == 1
    assert main(['init', '--db', str(db)]) == 1
    assert lookup(db).records == (record(),)


def test_registry_lookup_bridge_provider_request_parity(db: Path, tmp_path: Path) -> None:
    import asyncio
    from app.football.client import FootballClient
    from app.prematch_football_context.readiness.__main__ import initialize as initialize_readiness
    from app.prematch_football_context.readiness.composition import ProspectiveObservation
    from tests.test_prematch_football_context_readiness import ROW
    from tests.test_prematch_football_context_readiness_hardening import decide, target
    append(db, record())
    sequences = []
    for enabled in (False, True):
        root = tmp_path/str(enabled)
        initialize_readiness(root)
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
                assert client.request_count == 2
                for _ in range(3):
                    assert format_evidence(lookup(db), cutoff=T).verdict(T) == Verdict.VERIFIED_90
                assert client.request_count == 2
                if observer:
                    snapshot = decide(observer)
                    # No runtime wiring: a populated isolated registry cannot activate context.
                    assert snapshot.projection.values == (None,)*7
                    observer.finish(completed=True)
            finally:
                await client.close()
        asyncio.run(run())
        sequences.append(requests)
    assert sequences[0] == sequences[1] == [('/fixtures', (('id', '9999'),)),
        ('/fixtures', (('last', '99'), ('league', '10'), ('season', '2026'), ('status', 'FT')))]


def test_review_does_not_upgrade_historical_readiness(db: Path, tmp_path: Path) -> None:
    from app.prematch_football_context.readiness.report import coverage
    from app.prematch_football_context.snapshot.service import assemble, reproduce
    from tests.test_prematch_football_context_readiness import collect
    root = tmp_path/'readiness'
    root.mkdir()
    observer = collect(root)
    original = observer.snapshots.load('9999:HOME_WIN')
    original_bytes = canonical_bytes(original)
    append(db, record(reviewed_at=T+timedelta(seconds=1)))
    assert lookup(db).verdict == Verdict.REGULATION_UNVERIFIED
    future = lookup(db, cutoff=T+timedelta(seconds=2))
    assert future.verdict == Verdict.VERIFIED_90
    assert canonical_bytes(reproduce(observer.evidence, original)) == original_bytes
    assert original.projection.values == (None,)*7
    # Even an earlier synthetic review cannot overwrite an immutable snapshot.
    append(db, record(review_id='SYNTHETIC_EARLIER'))
    fmt = format_evidence(lookup(db), cutoff=T)
    changed = assemble(observer.evidence, original.opportunity, original.receipt,
                       replace(original.binding, current_format=fmt))
    with pytest.raises(ImmutableConflict):
        observer.snapshots.append(changed)
    assert canonical_bytes(observer.snapshots.load(original.opportunity.key)) == original_bytes
    observer.finish(completed=True)
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    report = coverage(root)
    assert report['phase_e_authorized'] is False
    assert report['reproduction']['VERIFIED'] == 1
    assert before == {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}


@pytest.mark.parametrize('document', [b'bytes', 'null', '[1]', '['*2000+']'*2000])
def test_malformed_document_fails_closed(document: object) -> None:
    with pytest.raises(ValueError):
        decode(document)
