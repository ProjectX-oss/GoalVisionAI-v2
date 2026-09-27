"""Real SQLite writers and fake HTTP; no provider or Telegram capabilities."""
from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import sqlite3
from threading import Barrier
import time
import httpx
import pytest
from app.adaptive_lab.quota import SharedQuota, QuotaDBContentionError, CONTENTION_WINDOW_SECONDS
from app.adaptive_lab.repository import AuditRepository
from app.adaptive_lab.prepared import PreparedAudit, AuditSnapshotChanged
from app.adaptive_lab.observations import ingest
from app.football.client import FootballClient
from app.football.quota import FootballQuotaError
from .conftest import START, frozen
from .test_quota_cli import quota


@contextmanager
def competing_writer(repo):
    path = repo.connection.execute('PRAGMA database_list').fetchone()[2]
    other = sqlite3.connect(path, isolation_level=None, timeout=0)
    other.execute('BEGIN IMMEDIATE')
    try:
        yield other
    finally:
        other.rollback()
        other.close()


async def client_for(repo, seen):
    client = FootballClient(api_key='synthetic', request_limit=5)
    await client._client.aclose()
    path = repo.connection.execute('PRAGMA database_list').fetchone()[2]
    def response(request):
        with sqlite3.connect('file:' + path + '?mode=ro', uri=True) as reader:
            # An independent connection sees COMMITTED evidence before transport.
            assert reader.execute('SELECT count(*) FROM quota_claims').fetchone()[0] == len(seen) + 1
        seen.append(request.url.path)
        return httpx.Response(200, json={'response': []}, headers={
            'x-ratelimit-requests-limit':'7500', 'x-ratelimit-requests-remaining':'7400',
            'x-ratelimit-limit':'300', 'x-ratelimit-remaining':'299'})
    client._client = httpx.AsyncClient(base_url=client.BASE_URL, transport=httpx.MockTransport(response))
    SharedQuota(repo).bind(client, lambda: START, allow_status_preflight=True)
    return client


def test_short_real_writer_releases_before_http_exactly_once(repo, monkeypatch, capsys):
    async def run():
        seen = []
        client = await client_for(repo, seen)
        retry = asyncio.Event()
        original = SharedQuota._retry_delay
        def notice(self, *args):
            retry.set()
            return original(self, *args)
        monkeypatch.setattr(SharedQuota, '_retry_delay', notice)
        with competing_writer(repo) as writer:
            task = asyncio.create_task(SharedQuota(repo).call('STATUS', client.account_status))
            await asyncio.wait_for(retry.wait(), 1)
            assert seen == [] and client.request_count == 0
            writer.commit()
            await task
        assert seen == ['/status'] and client.request_count == 1
        assert len(repo.all('quota_claims')) == 1
        assert repo.connection.execute('PRAGMA busy_timeout').fetchone()[0] == 5000
        await client.close()
    asyncio.run(run())
    records = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert records and all(r['code'] == 'QUOTA_DB_CONTENTION_RETRY' for r in records)
    assert all(set(r) == {'code', 'attempt', 'elapsed_ms', 'category', 'stage'} for r in records)


def test_persistent_real_lock_fails_closed_no_http_or_partial_claim(repo, capsys):
    async def run():
        seen = []
        client = await client_for(repo, seen)
        with competing_writer(repo):
            start = time.monotonic()
            with pytest.raises(QuotaDBContentionError, match='QUOTA_DB_CONTENTION_EXHAUSTED'):
                await SharedQuota(repo).call('STATUS', client.account_status)
            elapsed = time.monotonic() - start
        assert CONTENTION_WINDOW_SECONDS <= elapsed < CONTENTION_WINDOW_SECONDS + .3
        assert seen == [] and client.request_count == 0
        assert not repo.connection.in_transaction and repo.all('quota_claims') == []
        await client.close()
    asyncio.run(run())
    records = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert sum(r['code'] == 'QUOTA_DB_CONTENTION_EXHAUSTED' for r in records) == 1
    assert len(records) <= 22


def test_cancel_during_real_contention_has_no_claim_or_transport(repo, monkeypatch):
    async def run():
        seen = []
        client = await client_for(repo, seen)
        retry = asyncio.Event()
        original = SharedQuota._retry_delay
        def notice(self, *args):
            retry.set()
            return original(self, *args)
        monkeypatch.setattr(SharedQuota, '_retry_delay', notice)
        with competing_writer(repo):
            task = asyncio.create_task(SharedQuota(repo).call('STATUS', client.account_status))
            await asyncio.wait_for(retry.wait(), 1)
            start = time.monotonic()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert time.monotonic() - start < .1
        assert seen == [] and client.request_count == 0 and repo.all('quota_claims') == []
        assert not repo.connection.in_transaction
        assert repo.connection.execute('PRAGMA busy_timeout').fetchone()[0] == 5000
        await client.close()
    asyncio.run(run())


@pytest.mark.parametrize('failure', ['constraint', 'schema', 'integrity', 'programming'])
def test_nonlock_failures_not_retried(repo, monkeypatch, failure, capsys):
    attempts = []
    original = SharedQuota._claim_once
    def counted(self, *args, **kwargs):
        attempts.append(True)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(SharedQuota, '_claim_once', counted)
    expected = sqlite3.DatabaseError
    if failure == 'constraint':
        repo.connection.execute("CREATE TRIGGER reject_quota BEFORE INSERT ON quota_claims BEGIN SELECT RAISE(ABORT,'synthetic'); END")
    elif failure == 'schema':
        repo.connection.execute('DROP TABLE quota_claims')
    elif failure == 'integrity':
        repo.append('quota_claims', 'corrupt', 'PREMATCH', {'created_at': START.isoformat()}, START.isoformat())
        repo.connection.execute('DROP TRIGGER quota_claims_no_update')
        repo.connection.execute("UPDATE quota_claims SET fingerprint='invalid'")
        expected = ValueError
    else:
        repo.connection.close()
    with pytest.raises(expected):
        SharedQuota(repo).claim('SETTLEMENT', now=START, provider=quota())
    assert len(attempts) == (0 if failure == 'programming' else 1)
    assert 'CONTENTION_RETRY' not in capsys.readouterr().err


def test_commit_busy_rolls_back_before_retry(repo, monkeypatch):
    path = repo.connection.execute('PRAGMA database_list').fetchone()[2]
    reader = sqlite3.connect(path, isolation_level=None)
    reader.execute('BEGIN')
    reader.execute('SELECT count(*) FROM quota_claims').fetchone()
    original = SharedQuota._retry_delay
    retries = []
    def release(self, *args):
        assert not repo.connection.in_transaction
        assert repo.all('quota_claims') == []  # INSERT was rolled back after COMMIT BUSY.
        retries.append(True)
        reader.rollback()
        return original(self, *args)
    monkeypatch.setattr(SharedQuota, '_retry_delay', release)
    try:
        SharedQuota(repo).claim('SETTLEMENT', now=START, provider=quota())
    finally:
        reader.close()
    assert len(retries) == 1 and len(repo.all('quota_claims')) == 1


def test_nested_transaction_atomicity_and_quota_durability_guard(repo):
    with pytest.raises(RuntimeError):
        with repo.transaction():
            repo.append('source_records', 'outer', 'PREMATCH', {}, START.isoformat())
            with repo.transaction():
                repo.append('source_records', 'inner', 'PREMATCH', {}, START.isoformat())
            raise RuntimeError('rollback outer')
    assert repo.all('source_records') == []
    with repo.transaction():
        with pytest.raises(ValueError, match='OWN_DURABLE_TRANSACTION'):
            SharedQuota(repo).claim('SETTLEMENT', now=START, provider=quota())
    assert repo.all('quota_claims') == []


@pytest.mark.parametrize('daily,minute,attempts,expected', [(103, 300, 130, 103), (7500, 2, 8, 2)])
def test_concurrent_discovery_settlement_preserve_limits(tmp_path, daily, minute, attempts, expected):
    path = tmp_path / 'race.db'
    AuditRepository(path).close()
    barrier = Barrier(2)
    def worker(category):
        repo = AuditRepository(path)
        shared = SharedQuota(repo, daily_limit=daily, minute_limit=minute)
        barrier.wait(timeout=5)
        successes = 0
        try:
            for _ in range(attempts):
                try:
                    shared.claim(category, now=START, provider=quota())
                    successes += 1
                except (FootballQuotaError, QuotaDBContentionError):
                    # Saturation may refuse a reservation; it must never undercount.
                    pass
            return successes
        finally:
            repo.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, c) for c in ('PREMATCH_DISCOVERY', 'SETTLEMENT')]
        successes = sum(future.result(timeout=20) for future in futures)
    repo = AuditRepository(path)
    try:
        rows = repo.all('quota_claims')
        assert len(rows) == successes <= expected
        # Use any safely unconsumed slots, then prove the exact boundary.
        shared = SharedQuota(repo, daily_limit=daily, minute_limit=minute)
        for _ in range(expected - len(rows)):
            shared.claim('SETTLEMENT', now=START, provider=quota())
        with pytest.raises(FootballQuotaError):
            shared.claim('SETTLEMENT', now=START, provider=quota())
        rows = repo.all('quota_claims')
        assert len(rows) == expected
        discovery = [r for r in rows if r['category'] == 'PREMATCH_DISCOVERY']
        assert all(r['remaining_daily_before'] >= 101 for r in discovery)
        assert all(r['remaining_minute_before'] >= 1 for r in rows)
        assert len(rows) == repo.connection.execute('SELECT count(DISTINCT id) FROM quota_claims').fetchone()[0]
        assert repo.connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert repo.connection.execute('PRAGMA foreign_key_check').fetchall() == []
    finally:
        repo.close()


def test_prepared_conflict_rolls_back_whole_batch(repo):
    batch = PreparedAudit(repo)
    batch.all('source_records')
    batch.append('source_records', 'prepared', 'PREMATCH', {}, START.isoformat())
    path = repo.connection.execute('PRAGMA database_list').fetchone()[2]
    other = AuditRepository(path)
    other.append('source_records', 'concurrent', 'PREMATCH', {}, START.isoformat())
    other.close()
    with pytest.raises(AuditSnapshotChanged):
        batch.commit()
    assert repo.get('source_records', 'prepared') is None


def test_observer_replay_acquires_no_write_transaction(repo):
    p, r, s = frozen()
    expected = ingest(repo, p, r, s, stream='PREMATCH', publication_id='p')
    with competing_writer(repo):
        assert ingest(repo, p, r, s, stream='PREMATCH', publication_id='p') == expected


def test_history_decode_and_hash_outside_quota_write_lock(repo, monkeypatch):
    shared = SharedQuota(repo)
    shared.claim('SETTLEMENT', now=START, provider=quota())
    original = repo.quota_since
    def checked(*args):
        assert not repo.connection.in_transaction
        return original(*args)
    monkeypatch.setattr(repo, 'quota_since', checked)
    shared.claim('SETTLEMENT', now=START, provider=quota())
    assert len(repo.all('quota_claims')) == 2


def test_pointer_failure_rolls_back_prepared_evidence(repo, monkeypatch):
    from app.adaptive_lab.governance import Governance
    from .test_governance_rehearsal import baseline
    original = repo.set_champion
    def fail(stream, identity):
        original(stream, identity)
        raise RuntimeError('after pointer write')
    monkeypatch.setattr(repo, 'set_champion', fail)
    with pytest.raises(RuntimeError):
        Governance(repo).bootstrap(baseline('PREMATCH'), now=START)
    assert repo.champion('PREMATCH') is None
    assert repo.all('model_artifacts') == [] and repo.all('activation_events') == []


def test_governance_history_and_comparison_outside_writer(repo, monkeypatch):
    from datetime import timedelta
    from app.adaptive_lab.governance import Governance
    from .test_governance_rehearsal import baseline
    governance = Governance(repo)
    original = governance.bootstrap(baseline('PREMATCH'), now=START)
    with repo.transaction():
        governance._activate('PREMATCH', original['artifact_id'], original['generation_id'],
                             'PROMOTION', {}, START.isoformat())
    read = repo.all
    def checked(*args):
        assert not repo.connection.in_transaction
        return read(*args)
    monkeypatch.setattr(repo, 'all', checked)
    assert governance.rollback('PREMATCH', now=START+timedelta(days=1))['status'] == 'INSUFFICIENT_ROLLBACK_EVIDENCE'


def test_weekly_statistics_never_owns_audit_writer(repo, monkeypatch):
    from app.adaptive_lab import weekly
    original = weekly.statistics
    class Ledger:
        def all(self, kind):
            assert not repo.connection.in_transaction
            return []
        def get(self, kind, identity):
            assert not repo.connection.in_transaction
            return None
    weekly.freeze(repo, Ledger(), now=START)
    assert len(repo.all('weekly_reports')) == 1


def test_no_http_retry_when_reservation_fails_after_prior_transport(repo):
    async def run():
        seen = []
        client = await client_for(repo, seen)
        await SharedQuota(repo).call('STATUS', client.account_status)
        with competing_writer(repo):
            with pytest.raises(QuotaDBContentionError):
                await client.fixture(123)
        assert client.request_count == 1 and seen == ['/status']
        assert len(repo.all('quota_claims')) == 1
        await client.close()
    asyncio.run(run())


def test_real_sqlite_locked_shared_cache_is_retried(repo, monkeypatch, capsys):
    path = repo.connection.execute('PRAGMA database_list').fetchone()[2]
    repo.connection.close()
    uri = 'file:' + path + '?cache=shared'
    repo.connection = sqlite3.connect(uri, uri=True, isolation_level=None)
    repo.connection.row_factory = sqlite3.Row
    repo.connection.execute('PRAGMA foreign_keys=ON')
    writer = sqlite3.connect(uri, uri=True, isolation_level=None)
    writer.execute('BEGIN IMMEDIATE')
    document = json.dumps({'category': 'SETTLEMENT', 'created_at': START.isoformat()}, sort_keys=True, separators=(',', ':'))
    from app.adaptive_lab.contracts import digest
    writer.execute('INSERT INTO quota_claims VALUES (?,?,?,?,?)',
                   ('competitor', 'PREMATCH', START.isoformat(), digest(json.loads(document)), document))
    try:
        with pytest.raises(sqlite3.OperationalError) as caught:
            repo.connection.execute('SELECT count(*) FROM quota_claims').fetchone()
        assert caught.value.sqlite_errorcode & 0xff == sqlite3.SQLITE_LOCKED
        original = SharedQuota._retry_delay
        def release(self, *args):
            writer.commit()
            return original(self, *args)
        monkeypatch.setattr(SharedQuota, '_retry_delay', release)
        SharedQuota(repo).claim('SETTLEMENT', now=START, provider=quota())
        assert len(repo.all('quota_claims')) == 2
        assert 'QUOTA_DB_CONTENTION_RETRY' in capsys.readouterr().err
    finally:
        writer.close()


def test_prepared_batch_replay_checks_links_and_stream(repo):
    batch = PreparedAudit(repo)
    assert batch.append('source_records', 'id', 'PREMATCH', {}, START.isoformat())
    assert not batch.append('source_records', 'id', 'PREMATCH', {}, START.isoformat())
    with pytest.raises(ValueError, match='CONFLICTING_REPLAY'):
        batch.append('source_records', 'id', 'LIVE', {}, START.isoformat())
    batch.commit()
    batch = PreparedAudit(repo)
    with competing_writer(repo):
        assert not batch.append('source_records', 'id', 'PREMATCH', {}, START.isoformat())
        batch.commit()


def test_error_after_commit_never_creates_a_second_reservation(repo, monkeypatch):
    @contextmanager
    def faulty_restore(self):
        yield
        error = sqlite3.OperationalError('synthetic cleanup error')
        error.sqlite_errorcode = sqlite3.SQLITE_BUSY
        raise error
    monkeypatch.setattr(SharedQuota, '_nonblocking', faulty_restore)
    with pytest.raises(sqlite3.OperationalError):
        SharedQuota(repo).claim('SETTLEMENT', now=START, provider=quota())
    assert len(repo.all('quota_claims')) == 1


@pytest.mark.parametrize('failure', [QuotaDBContentionError(), sqlite3.OperationalError('synthetic')])
def test_failed_discovery_health_keeps_actual_consumed_calls(tmp_path, monkeypatch, failure):
    from types import SimpleNamespace
    from app.lab_v2_shadow import cli
    class Client:
        request_count = 7
        def __init__(self, **kwargs):
            pass
        async def close(self):
            pass
    class Runner:
        def __init__(self, *args, **kwargs):
            pass
        async def run(self, **kwargs):
            raise failure
    monkeypatch.setattr(cli, 'FootballClient', Client)
    monkeypatch.setattr(cli, 'LabV2ShadowRunner', Runner)
    monkeypatch.setattr(cli, 'discovery_state', lambda now: 'DAY')
    args = SimpleNamespace(shadow_database=tmp_path/'shadow.db', adaptive_database=tmp_path/'audit.db',
                           max_calls=400, capability_cache=tmp_path/'cache.json', analysis_database=tmp_path/'analysis.db',
                           daily_reserve=100, horizon_days=3, send=False)
    with pytest.raises(type(failure)):
        asyncio.run(cli._cycle(args))
    repo = AuditRepository(args.adaptive_database, readonly=True)
    try:
        row, = repo.all('cycle_health')
        assert row['provider_calls'] == 7 and row['result'] == 'FAILED'
        assert row['failure'] == ({'code': failure.code} if isinstance(failure, QuotaDBContentionError)
                                  else 'OperationalError')
    finally:
        repo.close()
