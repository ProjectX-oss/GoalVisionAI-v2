"""Pagination, classification and decision audit contracts for the global Lab."""
import asyncio
from datetime import timedelta
from pathlib import Path

import pytest

from app.lab_v2_shadow.odds_coverage import DateOddsCoverage, quote_absence_reason
from app.lab_v2_shadow.runner import LabV2ShadowRunner
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from test_lab_v2_shadow import FakeClient, NOW, odds_payload


@pytest.mark.parametrize('payload,reason', [
    ({'response': [], 'errors': {'request': 'timeout'}}, 'ODDS_API_ERROR'),
    ({'response': []}, 'ODDS_PAGINATION_METADATA_INVALID'),
    ({'response': [], 'paging': {'current': 2, 'total': 3}}, 'ODDS_PAGINATION_PAGE_MISMATCH'),
    ({'response': None}, 'ODDS_RESPONSE_MALFORMED'),
])
def test_bad_pages_never_prove_absence(payload, reason):
    audit = DateOddsCoverage()
    assert not audit.observe(1, payload)
    assert audit.reason() == reason


def test_shrinking_pagination_still_fetches_high_water_mark(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    class Client(FakeClient):
        pages = []
        async def current_odds_by_date(self, day, *, page=1):
            self.pages.append(page)
            return self._hit('/odds', {}, {'response': [], 'paging': {'current': page, 'total': 4 if page == 1 else 2}})
    client = Client()
    with_repo = ShadowEvidenceRepository(Path('var/audit.db'))
    runner = LabV2ShadowRunner(client, with_repo, capability_cache_path=Path('var/cap.json'), maximum_calls=20)
    _, report = asyncio.run(runner._date_odds([NOW.date().isoformat()], [{'fixture_id': 7, 'kickoff_utc': NOW + timedelta(hours=4)}], NOW))
    assert client.pages == [1, 2, 3, 4]
    assert report['fixture_coverage_reasons']['7'] == 'ODDS_PAGINATION_CHANGED_DURING_SWEEP'
    assert report['fixtures_with_no_current_odds'] == 0
    assert report['fixtures_with_incomplete_odds_page_coverage'] == 1
    with_repo.close()


def test_filter_absence_reasons():
    row = odds_payload()['response'][0]
    assert quote_absence_reason(row, frozenset()) == 'ODDS_BOOKMAKER_FILTER_REMOVED_ALL'
    assert quote_absence_reason({'bookmakers': []}, None) == 'ODDS_RECORD_WITHOUT_BOOKMAKERS'
    assert quote_absence_reason({'bookmakers': [{'id': 3, 'bets': [{'name': 'Correct Score', 'values': [{'value': '1:0', 'odd': '7'}]}]}]}, None) == 'ODDS_MARKET_FILTER_REMOVED_ALL'


@pytest.mark.parametrize('name,country', [
    ('Oberliga - Bayern Süd', 'Germany'), ('Regionalliga - Ost', 'Austria'),
    ('Ligue 2', 'Algeria'), ('Ligue 3', 'France'), ('Liga II', 'Romania'),
    ('Liga III - Group 1', 'Romania'), ('Serie B', 'Brazil'), ('Serie C - Girone A', 'Italy'),
    ('Second League', 'Egypt'), ('Second NL', 'Croatia'), ('National 2 - Group A', 'France'),
    ('Tercera División RFEF - Group 1', 'Spain'), ('Primera División RFEF - Group 1', 'Spain'),
    ('Segunda División RFEF - Group 2', 'Spain'), ('Non League Premier - Southern', 'England'),
    ('Division 2 - Norra', 'Sweden'), ('2. Division', 'Cyprus'), ('3. Lig', 'Turkey'),
    ('J2 League', 'Japan'), ('J3 League', 'Japan'), ('League One', 'China'), ('League Two', 'China'),
    ('Eerste Divisie', 'Netherlands'), ('Tweede Divisie', 'Netherlands'), ('Derde Divisie', 'Netherlands'),
    ('III Liga - Group 2', 'Poland'), ('II Liga', 'Poland'), ('Primera B Metropolitana', 'Argentina'),
    ('Primera Nacional', 'Argentina'), ('Primera C', 'Argentina'), ('USL Championship', 'USA'),
    ('USL League One', 'USA'), ('1. Lig', 'Turkey'), ('Superettan', 'Sweden'), ('Ettan - Norra', 'Sweden'),
    ('NB II', 'Hungary'), ('NB III', 'Hungary'), ('Thai League 2', 'Thailand'),
    ('Liga Expansión MX', 'Mexico'), ('Liga Premier Serie A', 'Mexico'),
    ('Division Intermedia', 'Paraguay'), ('Segunda División', 'Uruguay'), ('Segunda Division', 'Venezuela'),
    ('2. SNL', 'Slovenia'), ('3. SNL - East', 'Slovenia'),
    ('Football League - Lowland League', 'Scotland'), ('Football League - Highland League', 'Scotland'),
])
def test_real_metadata_lower_division_rules(name, country):
    from test_lab_v2_global import fixture, discovered
    row = fixture(name); row['league']['country'] = country
    assert discovered(row)[0][0]['competition_profile'] == 'LOWER_DIVISION_OR_SEMIPRO'


@pytest.mark.parametrize('name', ['Primera División Femenina', 'Liga MX Femenil', 'Liga 1 Feminin',
    'Division Feminine', 'Liga Feminina', 'Frauen Bundesliga', 'Frauenliga', 'Campeonato Feminino'])
def test_multilingual_women_metadata(name):
    from test_lab_v2_global import fixture, discovered
    item = discovered(fixture(name))[0][0]
    assert item['competition_profile'] == 'SENIOR_WOMEN_PRO'
    assert 'IS_WOMEN' in item['flags']


@pytest.mark.parametrize('name', ['Division One League', 'Premier League', '1. Liga', 'League One'])
def test_ambiguous_metadata_remains_unknown(name):
    from test_lab_v2_global import fixture, discovered
    assert discovered(fixture(name))[0][0]['competition_profile'] == 'UNKNOWN'


def test_club_junior_is_not_an_age_group_and_b_is_suffix_only():
    from test_lab_v2_global import fixture, discovered
    row = fixture('CONCACAF Caribbean Club Championship')
    row['teams']['home']['name'] = 'Junior Stars'
    assert discovered(row)[0][0]['competition_profile'] == 'INTERNATIONAL_CLUB'
    row = fixture(); row['teams']['home']['name'] = 'Club B United'
    assert discovered(row)[0][0]['competition_profile'] == 'UNKNOWN'
    row['teams']['home']['name'] = 'Club II'
    assert discovered(row)[0][0]['competition_profile'] == 'RESERVE_OR_B_TEAM'


def test_missing_context_and_probability_are_distinct():
    from dataclasses import replace
    from app.lab_v2_shadow.profiles import fallback_capability
    from app.lab_v2_shadow.signal_evidence import signal_requirements
    cap = fallback_capability({'id': 1, 'season': 2026})
    rows = signal_requirements(('lineup', 'advanced_stats', 'recent_form'), cap, independent_probability=False)
    assert rows[0]['reason_code'] == 'MANDATORY_SIGNAL_MISSING'
    assert {r['reason_code'] for r in rows[1:]} == {'PROVIDER_DOES_NOT_SUPPORT_SIGNAL', 'OPTIONAL_SIGNAL_MISSING'}
    assert all(r['gate_type'] == 'SOFT' for r in rows[1:])
    rows = signal_requirements(('lineup',), replace(cap, lineups=True), independent_probability=True)
    assert rows[0]['reason_code'] == 'PASSED' and rows[1]['reason_code'] == 'SIGNAL_NOT_YET_AVAILABLE'


@pytest.mark.parametrize('side,odds', [('HOME_WIN', '2.1'), ('DRAW', '3.3'), ('AWAY_WIN', '4.2'), ('BTTS_YES', '1.9'), ('BTTS_NO', '2.2'), ('OVER_2_5', '1.8'), ('UNDER_2_5', '2.4')])
def test_value_arithmetic_uses_exact_market_side(side, odds):
    from decimal import Decimal
    from app.lab_v2_shadow.ensemble import EnsembleSignal, evaluate_ensemble
    p = Decimal('.61'); price = Decimal(odds)
    signals = [EnsembleSignal(name, side, p, side, Decimal(1), 'AVAILABLE', 'test')
               for name in ('CURRENT_MARKET_CONSENSUS', 'CURRENT_MATCH_INTELLIGENCE')]
    decision = evaluate_ensemble(side, price, signals)
    assert decision.ensemble_probability == p
    assert decision.offered_implied_probability == 1 / price
    assert decision.edge == p - 1 / price
    assert abs((p * price - 1) - decision.edge * price) < Decimal('1e-25')


def test_nonfinite_vig_input_fails_closed():
    from decimal import Decimal
    from app.lab_v2_shadow.market_consensus import remove_margin_multiplicative
    assert remove_margin_multiplicative({'BTTS_YES': Decimal('NaN'), 'BTTS_NO': Decimal('2')}) is None


def test_adaptive_sweep_preserves_due_reserve_despite_broad_absence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    days = [(NOW + timedelta(days=i)).date().isoformat() for i in range(3)]
    class Client(FakeClient):
        order = []
        async def current_odds_by_date(self, day, *, page=1):
            self.order.append((day, page))
            return self._hit('/odds', {}, {'response': [], 'paging': {'current': page, 'total': 1 if day == days[0] else 40}})
    client = Client(); client.limit = 100
    repo = ShadowEvidenceRepository(Path('var/audit.db'))
    runner = LabV2ShadowRunner(client, repo, capability_cache_path=Path('var/cap.json'), maximum_calls=100)
    fixtures = [{'fixture_id': 1, 'kickoff_utc': NOW + timedelta(minutes=40)}]
    fixtures += [{'fixture_id': i, 'kickoff_utc': NOW + timedelta(days=2, hours=4)} for i in range(2, 202)]
    fixtures += [{'fixture_id': 203, 'kickoff_utc': NOW + timedelta(days=1, hours=4)}]
    _, report = asyncio.run(runner._date_odds(days, fixtures, NOW, reserve_calls=45))
    assert client.order[:4] == [(days[0], 1), (days[1], 1), (days[1], 2), (days[1], 3)]
    assert report['coverage_by_date'][days[1]]['stable_complete_sweep']
    assert report['fixtures_with_incomplete_odds_page_coverage'] == 200
    assert report['initial_final_review_reserve'] == 45
    assert report['remaining_final_review_reserve'] == 45
    assert client.request_count == 55 and runner._remaining() == 45
    repo.close()


def test_page_errors_do_not_discard_discovered_fixtures(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    class Client(FakeClient):
        async def current_odds_by_date(self, day, *, page=1):
            return self._hit('/odds', {}, {'errors': {'request': 'ODDS_API_TIMEOUT'}, 'response': []})
    client = Client(); repo = ShadowEvidenceRepository(Path('var/audit.db'))
    runner = LabV2ShadowRunner(client, repo, capability_cache_path=Path('var/cap.json'), maximum_calls=10)
    fixtures = [{'fixture_id': i, 'kickoff_utc': NOW + timedelta(hours=4)} for i in range(225)]
    _, report = asyncio.run(runner._date_odds([NOW.date().isoformat()], fixtures, NOW))
    assert report['fixtures_with_incomplete_odds_page_coverage'] == 225
    assert report['coverage_reason_counts'] == {'ODDS_API_TIMEOUT': 225}
    assert len(report['fixture_statuses']) == 225
    assert report['pages_not_fetched_due_to_budget'] == 0
    repo.close()


def test_malformed_optional_quote_containers_do_not_crash():
    assert quote_absence_reason({'bookmakers': [{'id': 3, 'bets': 12}]}, None) == 'ODDS_RECORD_WITHOUT_QUOTES'
    assert quote_absence_reason({'bookmakers': [{'id': 3, 'bets': [{'values': 12}]}]}, None) == 'ODDS_RECORD_WITHOUT_QUOTES'
