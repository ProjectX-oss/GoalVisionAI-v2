"""Offline regression for the 2026-10-01 three-page starvation incident."""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import socket
from unittest.mock import patch

import pytest

from app.lab_v2_shadow.quota import protected_odds_page_calls
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from app.lab_v2_shadow.runner import LabV2ShadowRunner
from test_lab_v2_global import fixture
from test_lab_v2_shadow import FakeClient, NOW, odds_payload, coverage


class PageClient(FakeClient):
    def __init__(self, totals=(10, 6, 1)):
        super().__init__()
        self.totals = totals
        self.requests = []

    def _hit(self, endpoint, query, payload):
        self.requests.append((endpoint, query))
        return super()._hit(endpoint, query, payload)

    def quota_snapshot(self):
        return dict(interpretation_status='NORMALIZED',
                    daily_remaining=4212, minute_remaining=300)

    async def leagues(self, *, current=True):
        return self._hit('/leagues', {}, {'response': [coverage()]})

    async def fixtures_by_date(self, day, *, timezone_name='UTC'):
        offset = (datetime.fromisoformat(day).date() - NOW.date()).days
        rows = []
        for identity in range(1 + offset * 34, 35 + offset * 34):
            row = fixture('World Cup', identity)
            row['league']['id'] = 999
            row['fixture']['date'] = day + 'T18:00:00+00:00'
            rows.append(row)
        return self._hit('/fixtures', {'date': day}, {'response': rows})

    async def current_odds_by_date(self, day, *, page=1):
        offset = (datetime.fromisoformat(day).date() - NOW.date()).days
        total = self.totals[offset]
        rows = odds_payload(fixture_id=(offset + 1) * 34)['response'] if page == total else []
        return self._hit('/odds', {'date': day, 'page': page},
                         dict(response=rows, paging=dict(current=page, total=total)))

    async def current_odds(self, identity):
        return self._hit('/odds', {'fixture': identity}, {'response': []})

    async def finished_matches(self, league_id, season, last=99):
        return self._hit('/fixtures', {'league': league_id}, [])


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Unexpected real network request')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def run_cycle(path, *, legacy=False, totals=(10, 6, 1), restart=False):
    repo = ShadowEvidenceRepository(path / 'shadow.db')
    client = PageClient(totals)
    if restart:
        for day, page in ((NOW.date().isoformat(), 9),
                          ((NOW + timedelta(days=1)).date().isoformat(), 4)):
            repo.append('odds_page_cursor', day, {'date': day, 'next_page': page},
                        created_at=NOW - timedelta(minutes=30))
    runner = LabV2ShadowRunner(client, repo, capability_cache_path=Path.cwd() / 'var' / path.name / 'cap.json',
                              maximum_calls=400)
    try:
        if legacy:
            with patch('app.lab_v2_shadow.runner.protected_odds_page_calls',
                       side_effect=lambda remaining, days, reserve: min(remaining, days)):
                report = asyncio.run(runner.run(now=NOW, horizon_days=3))
        else:
            report = asyncio.run(runner.run(now=NOW, horizon_days=3))
        return report, client
    finally:
        repo.close()


@pytest.mark.parametrize('restart', [False, True])
def test_full_three_day_sweep_replaces_three_page_starvation(tmp_path, monkeypatch, restart):
    monkeypatch.chdir(tmp_path)
    before, _ = run_cycle(tmp_path / 'before', legacy=True)
    after, client = run_cycle(tmp_path / 'after', restart=restart)
    assert before['odds_pagination']['page_calls'] == 3
    assert before['current_odds_fixtures'] == 0
    assert after['odds_pagination']['page_calls'] == 17
    assert after['current_odds_fixtures'] == 3
    assert after['odds_pagination']['protected_page_call_allowance'] == 32
    assert all(d['stable_complete_sweep'] for d in
               after['odds_pagination']['coverage_by_date'].values())
    assert after['priority_fixtures_discovered'] == 102
    assert after['model_analysis_attempts'] == 102
    assert after['api_calls_consumed'] <= after['adaptive_quota_budget']['effective_cycle_maximum'] == 258
    assert after['daily_safety_reserve'] == 100
    assert after['telegram_sends'] == 0
    pages = [i for i, (endpoint, q) in enumerate(client.requests) if endpoint == '/odds' and 'date' in q]
    predictions = [i for i, (endpoint, q) in enumerate(client.requests) if endpoint == '/predictions']
    assert max(pages) < min(predictions)


def test_large_page_catalogue_remains_bounded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    report, _ = run_cycle(tmp_path, totals=(100, 100, 100))
    pagination = report['odds_pagination']
    assert pagination['page_calls'] == 32
    assert pagination['fixtures_with_incomplete_odds_page_coverage'] > 0
    assert report['api_calls_consumed'] <= 258
    assert report['api_call_allocation']['/predictions'] > 0


@pytest.mark.parametrize('remaining,days,reserve,expected', [
    (232, 3, 39, 32), (232, 3, 220, 12), (40, 3, 10, 10),
    (10, 3, 4, 3), (2, 3, 2, 0), (0, 3, 0, 0), (232, 0, 39, 0),
])
def test_low_budget_and_final_review_reserve(remaining, days, reserve, expected):
    allocated = protected_odds_page_calls(remaining, days, reserve)
    assert allocated == expected
    assert allocated <= max(0, remaining - reserve)
