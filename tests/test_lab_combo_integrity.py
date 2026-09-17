"""Offline regressions for blocked analyses and immutable repeated evidence."""
import asyncio
import json
import sqlite3
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

import httpx
import pytest

from app.database import Database
from app.current_odds_forward_test.input import parse_current_odds
from app.current_odds_forward_test.repository import SQLiteForwardTestRepository
from app.current_odds_forward_test.service import ForwardTestService
from app.forward_test_governance.service import GovernanceService
from app.football.client import FootballClient, FootballRequestLimitError
from app.real_match_lab_analysis import SQLiteRealMatchLabRepository, parse_input
from app.real_match_lab_analysis.service import RealMatchLabAnalysisService
from tests.test_real_match_lab_analysis import FakeEngine, NOW, raw_input
from tests.test_current_odds_forward_test import odds_raw


@pytest.fixture
def database():
    db = Database(':memory:')
    SQLiteForwardTestRepository(db)
    yield db
    db.close()


def blocked_observation(database):
    raw = raw_input()
    raw['collected_at'] = NOW.isoformat()
    quote = raw['odds'][0]
    contract = odds_raw(
        fixture_id=raw['match_id'], kickoff_utc=raw['kickoff_utc'],
        provider_source_id=quote['source_provider'], bookmaker=quote['bookmaker_id'],
        provider_event_id=quote['source_event_id'],
        source_selected_at_utc=(NOW - timedelta(minutes=2)).isoformat(),
        captured_at_utc=quote['captured_at'], source_retrieval_timestamp_utc=quote['captured_at'],
    )
    contract['markets'] = [{'market': item['market'], 'decimal_odds': item['decimal_odds']} for item in raw['odds']]
    forward = ForwardTestService(SQLiteForwardTestRepository(database))
    odds = parse_current_odds(contract, now=NOW)
    forward.capture_odds(odds)
    analyzer = RealMatchLabAnalysisService(SQLiteRealMatchLabRepository(database), FakeEngine('MODEL_INPUT_SCHEMA_INCOMPATIBLE'))
    analysis = analyzer.analyze(parse_input(raw, now=NOW))
    return forward.create_observation('blocked-combo', analysis.analysis_id, odds.snapshot_id)


def test_blocked_analysis_governance_exact_constraint_and_replay(database):
    observation = blocked_observation(database)
    repo = SQLiteForwardTestRepository(database)
    original = dict(repo.load_observation(observation.observation_id))
    assert observation.model_artifact_id is None
    assert observation.calibration_id is None
    service = GovernanceService(database)
    cutoff = NOW.isoformat()
    records = service.records(cutoff)
    assert records[0]['model_generation'] == records[0]['calibration_artifact'] == 'UNKNOWN'
    # Reproduce the old projection's exact failure, including atomic rollback.
    legacy = tuple({**row, 'model_generation': None, 'calibration_artifact': None} for row in records)
    with pytest.raises(sqlite3.IntegrityError, match=r'NOT NULL constraint failed: forward_test_governance_scope_statuses.scope_value'):
        service.evaluate(cutoff, controlled_records=legacy)
    assert not service.repository.history()
    first = service.evaluate(cutoff)
    assert service.evaluate(cutoff)['replayed']
    second = service.evaluate((NOW + timedelta(minutes=1)).isoformat())
    assert first['evaluation_id'] != second['evaluation_id']
    assert len(service.repository.history()) == 2
    assert first['decision']['publication_impact'] == 'BLOCK'
    assert dict(repo.load_observation(observation.observation_id)) == original
    assert service.reproduce(first['evaluation_id'], cutoff)['status'] == 'GOVERNANCE_REPRODUCED'
    assert database.connection.execute('PRAGMA foreign_key_check').fetchall() == []
    with pytest.raises(sqlite3.IntegrityError):
        with database.connection:
            database.connection.execute('DELETE FROM forward_test_governance_scope_statuses')


def test_identical_market_evaluations_belong_to_distinct_analyses(database):
    repository = SQLiteRealMatchLabRepository(database)
    service = RealMatchLabAnalysisService(repository, FakeEngine())
    command = parse_input(raw_input(), now=NOW)
    first = service.analyze(command)
    before = tuple(tuple(row) for row in repository.market_evaluations(first.analysis_id))
    second = service.analyze(replace(command, request_id='another-analysis'))
    assert first.evidence.evaluations == second.evidence.evaluations
    assert first.analysis_id != second.analysis_id
    service.analyze(command)
    service.analyze(replace(command, request_id='another-analysis'))
    assert before == tuple(tuple(row) for row in repository.market_evaluations(first.analysis_id))
    assert database.connection.execute('SELECT COUNT(*) FROM real_match_lab_market_evaluations').fetchone()[0] == 2 * len(first.evidence.evaluations)


def test_paced_concurrent_calls_respect_start_interval_and_ceiling():
    async def run():
        client = FootballClient(api_key='fictional', request_limit=2)
        await client.close()
        starts = []
        def respond(request):
            starts.append(asyncio.get_running_loop().time())
            return httpx.Response(200, json={'response': []})
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url=client.BASE_URL)
        try:
            results = await asyncio.gather(*(client.current_odds(i) for i in range(3)), return_exceptions=True)
            assert len(starts) == client.request_count == 2
            assert starts[1] - starts[0] >= 0.49
            assert sum(isinstance(value, FootballRequestLimitError) for value in results) == 1
        finally:
            await client.close()
    asyncio.run(run())


@pytest.mark.parametrize('message,retained', [
    ('NOT NULL constraint failed: forward_test_governance_scope_statuses.scope_value', True),
    ('fictional-credential-in-trigger-message', False),
])
def test_cycle_sqlite_diagnostics_are_allowlisted(tmp_path, monkeypatch, message, retained):
    from argparse import Namespace
    from unittest.mock import AsyncMock
    from app.lab_combo.cli import cycle
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'var/lab_combo'
    root.mkdir(parents=True)
    path = root / 'analysis.db'
    Database(path).close()
    error = sqlite3.IntegrityError(message)
    error.sqlite_errorcode = sqlite3.SQLITE_CONSTRAINT_NOTNULL
    client = AsyncMock()
    client.request_count = 0
    from unittest.mock import Mock
    client.restrict_requests = Mock()
    args = Namespace(command='discover', database=path, ledger=root / 'ledger.db', send=False)
    with patch('app.lab_combo.cli.FootballClient', return_value=client), patch(
        'app.lab_combo.cli.discover_current_fixture', new=AsyncMock(side_effect=error)
    ):
        value = asyncio.run(cycle(args))
    assert value['terminal_stage'] == 'DISCOVERY'
    assert value['sqlite_constraint'] == 'SQLITE_CONSTRAINT_NOTNULL'
    assert ('sqlite_message' in value) == retained
    if not retained:
        assert message not in json.dumps(value)
    assert value['api_calls_consumed'] == 0
    assert value['lab_telegram_sent'] is False
