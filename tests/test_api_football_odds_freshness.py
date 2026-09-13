"""Focused provider cadence and HTTP-200 rejection regression evidence."""
import asyncio
from datetime import timedelta

import httpx
import pytest

from app.current_odds_forward_test.input import normalize_api_football_current_odds, parse_current_odds, CurrentOddsValidationError
from app.current_odds_forward_test.discovery import discover_current_fixture
from app.football.client import FootballClient
from app.football.quota import FootballQuotaError
from tests.test_api_football_adaptive_discovery import NOW, odds, fixture
from tests.test_api_football_discovery_efficiency import CostProvider


def contract(update):
    return normalize_api_football_current_odds(odds(1, updated=update), fixture_id='1',
        kickoff_utc=(NOW + timedelta(hours=8)).isoformat(), retrieved_at_utc=NOW.isoformat(),
        source_selected_at_utc=NOW.isoformat())


@pytest.mark.parametrize('seconds', [0, 900, 10800, 12600])
def test_provider_cadence_preserves_distinct_timestamps(seconds):
    origin = NOW - timedelta(seconds=seconds)
    snapshot = parse_current_odds(contract(origin.isoformat()), now=NOW)
    assert snapshot.freshness_status == 'FRESH'
    assert snapshot.quotes[0].provider_origin_timestamp_utc == origin
    assert snapshot.quotes[0].source_retrieval_timestamp_utc == NOW
    assert snapshot.quotes[0].captured_at_utc == NOW


@pytest.mark.parametrize('update', [None, '', 'invalid', '2026-08-01T09:00:00', (NOW + timedelta(seconds=1)).isoformat()])
def test_invalid_origin_fails_closed(update):
    with pytest.raises(CurrentOddsValidationError):
        parse_current_odds(contract(update), now=NOW)


def test_stale_provider_and_retrieval_are_independent():
    with pytest.raises(CurrentOddsValidationError, match='STALE_CURRENT_ODDS'):
        parse_current_odds(contract((NOW - timedelta(seconds=12601)).isoformat()), now=NOW)
    with pytest.raises(CurrentOddsValidationError, match='STALE_CURRENT_ODDS'):
        parse_current_odds(contract(NOW.isoformat()), now=NOW + timedelta(seconds=901))
    a = parse_current_odds(contract(NOW.isoformat()), now=NOW)
    b = parse_current_odds(contract((NOW-timedelta(seconds=1)).isoformat()), now=NOW)
    assert a.quotes[0].quote_fingerprint != b.quotes[0].quote_fingerprint


def test_rejection_reports_actual_subreason_before_history():
    payload = {'errors': {'rateLimit': 'Too many requests per minute'}, 'response': []}
    client = CostProvider({'2026-08-01': [fixture(1)]}, {1: payload})
    value = asyncio.run(discover_current_fixture(client, now=NOW, horizon_days=1))
    assert value['request_cost_report'][0]['provider_errors'] == payload['errors']
    assert client.history_calls == []
    with pytest.raises(CurrentOddsValidationError, match='PROVIDER_ODDS_QUERY_REJECTED'):
        normalize_api_football_current_odds(payload, fixture_id='1', kickoff_utc=NOW.isoformat(),
            retrieved_at_utc=NOW.isoformat(), source_selected_at_utc=NOW.isoformat())


@pytest.mark.parametrize('headers', [{}, {'x-ratelimit-remaining': 'invalid'}, {
    'x-ratelimit-requests-limit': '7500', 'x-ratelimit-requests-remaining': '98',
    'x-ratelimit-limit': '300', 'x-ratelimit-remaining': '298'}])
def test_http_200_errors_preserve_quota_and_diagnostics(headers):
    async def run():
        client = FootballClient(api_key='fictional', request_limit=5)
        await client.close()
        calls = []
        initial = {'x-ratelimit-requests-limit': '7500', 'x-ratelimit-requests-remaining': '99',
                   'x-ratelimit-limit': '300', 'x-ratelimit-remaining': '299'}
        def respond(request):
            calls.append(request)
            return httpx.Response(200, headers=initial if len(calls) == 1 else headers,
                json={'errors': [] if len(calls) == 1 else {'rateLimit': 'Too many requests per minute'}, 'response': []})
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url=client.BASE_URL)
        client.restrict_requests(5)
        await client.account_status()
        before = client.quota_snapshot()
        response = await client.current_odds(1)
        metadata = client.response_metadata()
        assert metadata['errors'] == response['errors']
        assert metadata['http_status'] == 200
        if headers.get('x-ratelimit-remaining') == '298':
            assert client.quota_snapshot()['daily_remaining'] == 98
        else:
            assert client.quota_snapshot() == before
            assert metadata['quota_state_preserved'] is True
            with pytest.raises(FootballQuotaError, match='QUOTA_HEADERS_MISSING_OR_INVALID'):
                await client.current_odds(2)
            assert len(calls) == 2
        await client.close()
    asyncio.run(run())


def test_discovery_accepts_provider_cadence_before_history():
    client = CostProvider({'2026-08-01': [fixture(1)]},
        {1: odds(1, updated=(NOW-timedelta(hours=3)).isoformat())})
    value = asyncio.run(discover_current_fixture(client, now=NOW, horizon_days=1))
    assert value['fresh_odds_candidates'] == 1
    assert client.history_calls


def test_missing_provider_timestamp_skips_histories():
    client = CostProvider({'2026-08-01': [fixture(1)]}, {1: odds(1, updated=None)})
    value = asyncio.run(discover_current_fixture(client, now=NOW, horizon_days=1))
    assert value['skip_reasons']['MISSING_PROVIDER_ODDS_TIMESTAMP'] == 1
    assert not client.history_calls


def test_exact_quote_timestamps_are_immutable(tmp_path):
    import json
    from app.database import Database
    from app.current_odds_forward_test.repository import SQLiteForwardTestRepository
    database = Database(tmp_path / 'evidence.db')
    try:
        repo = SQLiteForwardTestRepository(database)
        origin = NOW-timedelta(hours=3, microseconds=123)
        snapshot = parse_current_odds(contract(origin.isoformat()), now=NOW)
        row, _ = repo.append_odds_snapshot(snapshot)
        quote = json.loads(row['snapshot_json'])['quotes'][0]
        assert quote['provider_origin_timestamp_utc'] == origin.isoformat()
        assert quote['source_retrieval_timestamp_utc'] == NOW.isoformat()
        with pytest.raises(Exception):
            repo.connection.execute('UPDATE forward_test_odds_snapshots SET freshness_status=?', ('STALE',))
    finally:
        database.close()


def test_discovery_records_response_time_not_run_start():
    retrieved = NOW + timedelta(seconds=12, microseconds=345)
    class TimedProvider(CostProvider):
        async def current_odds(self, fixture_id):
            payload = await super().current_odds(fixture_id)
            self._metadata['retrieved_at_utc'] = retrieved.isoformat()
            return payload
    client = TimedProvider({'2026-08-01': [fixture(1)]}, {1: odds(1)})
    value = asyncio.run(discover_current_fixture(client, now=NOW, horizon_days=1))
    evidence = value['request_cost_report'][0]['odds_timestamp_evidence']
    assert evidence['source_retrieval_timestamp_utc'] == retrieved.isoformat()
    assert evidence['provider_origin_timestamp_utc'] == NOW.isoformat()
