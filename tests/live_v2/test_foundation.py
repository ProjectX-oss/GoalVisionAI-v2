"""Offline LIVE contracts and service replays. Every provider/Telegram is fake."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.live_v2.contracts import digest
from app.live_v2.delivery import PrivateConfig, preview, deliver, reconcile, CONFIRM, result_preview
from app.live_v2.markets import review_catalogue, normalize, consensus
from app.live_v2.policy import evaluate
from app.live_v2.quota import Governor, budget, read_prematch
from app.live_v2.runner import Runner
from app.live_v2.schedule import opportunities, opportunity, prematch_remaining, RIGA
from app.live_v2.settlement import resolve, settle, statistics
from app.live_v2.state import fixture_state, features, shortlist
from app.live_v2.store import Store
from app.live_v2.__main__ import main

NOW = datetime(2026, 9, 26, 17, tzinfo=timezone.utc)  # 20:00 Riga


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path/'live.sqlite')
    yield value
    value.close()


def evidence(now=NOW):
    # Synthetic exclusive provider permit. Production adapter never invents this.
    return {'installed_contract': {'verified': True, 'cycle_ceiling': 400}, 'cycle_24h': {'count': 28, 'max': 270}, 'latest_cycle_at': now.isoformat(),
            'last_claim_at': now.isoformat(), 'daily_remaining_upper_bound': 7500,
            'minute_remaining_upper_bound': 300, 'provider_headers_verified': True,
            'shared_token_exclusive_until': (now+timedelta(seconds=50)).isoformat(),
            'settlement_24h': 200, 'settlement_max_utc_day': 200}


def row(identity=100):
    return {'fixture': {'id': identity, 'date': (NOW-timedelta(minutes=75)).isoformat(),
                        'status': {'short': '2H', 'elapsed': 60}},
            'league': {'id': 39, 'name': 'Premier League', 'season': 2026},
            'teams': {'home': {'id': 1, 'name': 'Team A'}, 'away': {'id': 2, 'name': 'Team B'}},
            'goals': {'home': 1, 'away': 0}}


def state():
    return fixture_state(row(), NOW, frozenset({39}))


def stats():
    return [{'team': {'id': t}, 'statistics': [
        {'type': 'Shots on Goal', 'value': 3 if t == 1 else 2},
        {'type': 'Total Shots', 'value': 6}, {'type': 'Red Cards', 'value': 0},
        {'type': 'Corner Kicks', 'value': 4}, {'type': 'Ball Possession', 'value': '50%'}]} for t in (1, 2)]


def mapping():
    # Deliberately fictional IDs; not a claim about provider mapping.
    rows = [{'id': 901, 'name': 'Fulltime Result', 'family': '1X2'},
            {'id': 902, 'name': 'Goals Over/Under', 'family': 'TOTALS'},
            {'id': 903, 'name': 'Both Teams To Score', 'family': 'BTTS'}]
    return review_catalogue({'endpoint': '/odds/live/bets', 'response': rows},
                            [dict(r, period='REGULATION_FULL_MATCH', review_reference='FICTIONAL_TEST') for r in rows])


def odds():
    return {'response': [{'fixture': {'id': 100, 'status': {'elapsed': 60}},
             'teams': {'home': {'id': 1, 'goals': 1}, 'away': {'id': 2, 'goals': 0}},
             'status': {'stopped': False, 'blocked': False, 'finished': False},
             'bookmaker': {'id': b, 'name': f'Fictional {b}'}, 'update': NOW.isoformat(),
             'odds': [{'id': 902, 'name': 'Goals Over/Under', 'values': [
                 {'value': 'Over', 'handicap': '2.5', 'main': True, 'suspended': False, 'odd': '2.50' if b == 1 else '1.90'},
                 {'value': 'Under', 'handicap': '2.5', 'main': True, 'suspended': False, 'odd': '1.50' if b == 1 else '1.90'}]}]}
            for b in (1, 2, 3)]}


def events():
    return [{'team': {'id': 1}, 'time': {'elapsed': 25}, 'type': 'Goal', 'detail': 'Normal Goal'}]


def candidate():
    s = state()
    q, _ = normalize(odds(), s, mapping(), retrieved_at=NOW)
    return next(e for e in evaluate(s, features(s, stats(), events()), q, now=NOW, safe_quota=True) if e['qualified'])


def config(**changes):
    return PrivateConfig(**{'token': '123:fictional_secret', 'chat_id': '42', 'expected_username': 'LiveBot',
                            'expected_bot_id': '123', 'started': True, 'enabled': True, **changes})


class FakeTelegram:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def identity(self):
        return {'ok': True, 'result': {'id': 123, 'username': 'LiveBot', 'is_bot': True}}

    def send(self, chat_id, text):
        self.calls.append((chat_id, text))
        if self.fail:
            raise RuntimeError('123:fictional_secret')
        return acknowledgement(text)


def acknowledgement(text):
    return {'ok': True, 'result': {'message_id': 17, 'chat': {'id': 42, 'type': 'private'},
            'from': {'id': 123, 'username': 'LiveBot', 'is_bot': True}, 'text': text}}


def freeze(store):
    c = candidate()
    store.append('candidate', 'c', c, NOW)
    return preview(store, 'c', config(), NOW)


@pytest.mark.parametrize('day,offset', [(date(2026, 3, 29), 3), (date(2026, 10, 25), 2), (date(2026, 9, 26), 3)])
def test_eight_riga_opportunities_dst(day, offset):
    slots = opportunities(day)
    assert len(slots) == len({s.astimezone(timezone.utc) for s in slots}) == 8
    assert [s.hour for s in slots] == [8, 10, 12, 14, 16, 18, 20, 22]
    assert slots[0].utcoffset() == timedelta(hours=offset)
    assert all(opportunity(s) == s.isoformat() for s in slots)
    assert opportunity(slots[-1].replace(hour=23)) is None
    assert opportunity(slots[0]+timedelta(minutes=5)) is None


def test_remaining_prematch_includes_current_cycle():
    assert prematch_remaining(NOW) == 6
    assert prematch_remaining(NOW.replace(hour=20)) == 0
    assert prematch_remaining(NOW.replace(hour=3)) == 28


@pytest.mark.parametrize('change,reason', [
    ({'cycle_24h': {}}, 'INSUFFICIENT_RECENT_PREMATCH_EVIDENCE'),
    ({'provider_headers_verified': False}, 'FRESH_PROVIDER_QUOTA_REQUIRED'),
    ({'shared_token_exclusive_until': None}, 'SHARED_TOKEN_CONCURRENCY_UNPROVEN'),
    ({'daily_remaining_upper_bound': 1}, 'PROTECTED_CAPACITY_EXHAUSTED'),
    ({'minute_remaining_upper_bound': 0}, 'PROTECTED_CAPACITY_EXHAUSTED'),
    ({'minute_remaining_upper_bound': 301}, 'INVALID_QUOTA_EVIDENCE')])
def test_quota_fail_closed(change, reason):
    report = budget({**evidence(), **change}, now=NOW, daily_calls=0, slot_calls=0)
    assert report['safe_calls'] == 0
    assert reason in report['reasons']


def test_daily_slot_and_minute_caps():
    for daily, slot, minute in [(40, 0, 0), (0, 5, 0), (0, 0, 300)]:
        assert budget(evidence(), now=NOW, daily_calls=daily, slot_calls=slot, minute_calls=minute)['safe_calls'] == 0
    assert budget(evidence(), now=NOW, daily_calls=39, slot_calls=0)['safe_calls'] == 1
    assert budget(evidence(), now=NOW, daily_calls=0, slot_calls=0)['safe_calls'] == 5


def test_claims_deduct_quota_and_failed_attempts_count(store):
    e = evidence()
    protected = budget(e, now=NOW, daily_calls=0, slot_calls=0)['protected_remaining_requirement']
    e['daily_remaining_upper_bound'] = protected + 2
    gov = Governor(store, lambda _: e)
    assert gov.claim('slot', '/fixtures', {}, NOW)
    assert gov.claim('slot', '/odds/live', {}, NOW)
    assert gov.claim('slot', '/fixtures/events', {}, NOW) is None
    assert len(store.all('api_claim')) == 2
    assert len(store.all('quota_decision')) == 3


def test_concurrent_claims_cannot_exceed_slot(tmp_path):
    path = tmp_path/'live.sqlite'
    Store(path).close()
    def claim(i):
        s = Store(path)
        try:
            return Governor(s, lambda _: evidence()).claim('slot', '/fixtures', {'i': i}, NOW)
        finally:
            s.close()
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert sum(bool(x) for x in pool.map(claim, range(12))) == 5


@pytest.mark.parametrize('status', ['FT', 'PST', 'ABD', 'SUSP', 'HT', 'ET', 'P', 'NS'])
def test_invalid_statuses_filtered(status):
    r = row(); r['fixture']['status']['short'] = status
    assert shortlist([r], NOW, frozenset({39}))[0] is None


@pytest.mark.parametrize('change', ['negative_score', 'bool_score', 'early', 'late', 'wrong_team', 'future_kickoff', 'unsupported'])
def test_invalid_states(change):
    r = row()
    if change == 'negative_score': r['goals']['home'] = -1
    if change == 'bool_score': r['goals']['home'] = True
    if change == 'early': r['fixture']['status']['elapsed'] = 9
    if change == 'late': r['fixture']['status']['elapsed'] = 83
    if change == 'wrong_team': r['teams']['away']['id'] = 1
    if change == 'future_kickoff': r['fixture']['date'] = (NOW+timedelta(minutes=1)).isoformat()
    if change == 'unsupported': r['league']['id'] = 999
    assert shortlist([r], NOW, frozenset({39}))[0] is None


def test_global_identity_conflict_and_one_shortlist():
    r = row(); r['teams']['home']['id'] = 8
    assert shortlist([row(), r], NOW, frozenset({39}))[0] is None
    selected, decisions = shortlist([row(100), row(101)], NOW, frozenset({39}))
    assert selected['fixture_id'] == 100 and len(decisions) == 2


def test_red_cards_and_missing_features():
    events = [{'team': {'id': 1}, 'player': {'id': 10}, 'time': {'elapsed': 50},
               'type': 'Card', 'detail': detail} for detail in ('Second Yellow card', 'Red Card')]
    f = features(state(), stats(), events)
    assert f['red_cards'] == {'home': 1, 'away': 0}
    assert 'RED_CARD_DISAGREEMENT' in f['contradictions']
    missing = features(state(), [], None)
    assert missing['red_cards'] is None and missing['home']['Shots on Goal'] is None
    assert 'xG' not in missing['home']


def test_shots_parse_and_invalid_sot():
    f = features(state(), stats(), [])
    assert f['home']['Shots on Goal'] == 3 and f['away']['Total Shots'] == 6
    assert f['home']['Shots insidebox'] is None
    s = stats(); s[0]['statistics'][0]['value'] = 20
    assert 'SOT_EXCEEDS_SHOTS' in features(state(), s, [])['contradictions']


def test_mapping_is_reviewed_not_guessed():
    bad = {'endpoint': '/odds/bets', 'response': []}
    with pytest.raises(ValueError): review_catalogue(bad, [])
    m = mapping(); assert [r['id'] for r in m['mappings']] == [901, 902, 903]
    p = odds(); p['response'][0]['odds'][0]['id'] = 1
    q, reasons = normalize(p, state(), m, retrieved_at=NOW)
    assert len(q) == 4 and 'UNSUPPORTED_LIVE_BET_ID' in reasons
    m['review_status'] = 'PENDING'
    assert normalize(odds(), state(), m, retrieved_at=NOW)[0] == []


def test_consensus_overround_best_price_and_bookmaker_count():
    q, _ = normalize(odds(), state(), mapping(), retrieved_at=NOW)
    over = next(x for x in consensus(q, NOW) if x['quote']['side'] == 'OVER')
    assert Decimal(over['probability']) == Decimal('.5')
    assert Decimal(over['edge']) == Decimal('.1')
    assert over['quote']['bookmaker_id'] == 1 and over['consensus_bookmakers'] == [2, 3]
    assert consensus(q[:2], NOW) == []
    assert consensus(q[:4], NOW) == []
    assert consensus(q+q, NOW) == []  # duplicate book/side cannot create observations


@pytest.mark.parametrize('problem', ['stale', 'future', 'blocked', 'stopped', 'suspended', 'origin_missing', 'book_missing', 'wrong_score', 'non_main'])
def test_unusable_odds(problem):
    p = odds()
    for r in p['response']:
        if problem == 'stale': r['update'] = (NOW-timedelta(seconds=31)).isoformat()
        if problem == 'future': r['update'] = (NOW+timedelta(seconds=1)).isoformat()
        if problem in ('blocked', 'stopped'): r['status'][problem] = True
        if problem == 'suspended':
            for v in r['odds'][0]['values']: v['suspended'] = True
        if problem == 'non_main':
            for v in r['odds'][0]['values']: v['main'] = False
        if problem == 'origin_missing': r.pop('update')
        if problem == 'book_missing': r.pop('bookmaker')
        if problem == 'wrong_score': r['teams']['home']['goals'] = 2
    q, _ = normalize(p, state(), mapping(), retrieved_at=NOW)
    assert consensus(q, NOW) == []


def test_prematch_prior_never_blended_and_corners_cannot_create_pick():
    s = state(); q, _ = normalize(odds(), s, mapping(), retrieved_at=NOW)
    f = features(s, stats(), events())
    a = evaluate(s, f, q, now=NOW, safe_quota=True, prematch_context={'probability': '.01'})
    b = evaluate(s, f, q, now=NOW, safe_quota=True, prematch_context={'probability': '.99'})
    assert [x['market']['probability'] for x in a] == [x['market']['probability'] for x in b]
    for side in ('home', 'away'):
        f[side]['Shots on Goal'] = f[side]['Total Shots'] = 0
        f[side]['Corner Kicks'] = 100
        f[side]['Ball Possession'] = 99
    assert not any(e['qualified'] for e in evaluate(s, f, q, now=NOW, safe_quota=True))


def test_candidate_replay_and_economic_duplicate():
    assert digest(candidate()) == digest(candidate())
    c = candidate()
    q, _ = normalize(odds(), c['state'], mapping(), retrieved_at=NOW)
    rows = evaluate(c['state'], c['features'], q, now=NOW, safe_quota=True, published=frozenset({c['economic_key']}))
    assert all(not e['qualified'] for e in rows)


class FakeAPI:
    def __init__(self, fixtures=None, fail_odds=False):
        self.calls, self.fixtures, self.fail_odds = [], fixtures if fixtures is not None else [row()], fail_odds

    def get(self, endpoint, query):
        self.calls.append((endpoint, query))
        if endpoint == '/odds/live' and self.fail_odds:
            raise RuntimeError('secret_token_not_printed')
        payload = {'/fixtures': {'response': self.fixtures}, '/odds/live': odds(),
                   '/fixtures/statistics': {'response': stats()}, '/fixtures/events': {'response': events()},
                   '/odds/live/bets': {'response': []}}[endpoint]
        return payload, {'interpretation_status': 'NORMALIZED', 'daily_remaining': 7000, 'minute_remaining': 290}


def run(store, api, e=None, m=None):
    return Runner(store, Governor(store, lambda _: e if e is not None else evidence()), api,
                  m if m is not None else mapping(), frozenset({39}), clock=lambda: NOW).run()


def test_empty_discovery_exactly_one_call(store):
    api = FakeAPI([])
    assert run(store, api)['status'] == 'NO_LIVE_FIXTURES'
    assert api.calls == [('/fixtures', {'live': 'all'})]


def test_unsafe_zero_calls(store):
    api = FakeAPI()
    assert run(store, api, {})['status'] == 'QUOTA_RESERVED_FOR_PREMATCH'
    assert api.calls == [] and store.all('quota_decision')


def test_one_fixture_four_calls_and_no_duplicate_opportunity(store):
    api = FakeAPI([row(100), row(101)])
    report = run(store, api)
    assert report['api_calls'] == 4 and report['candidate_qualified']
    assert {q['fixture'] for _, q in api.calls if 'fixture' in q} == {100}
    assert report['telegram_sends'] == 0
    assert run(store, api)['status'] == 'OPPORTUNITY_ALREADY_CLAIMED'
    assert len(api.calls) == 4


def test_embedded_events_avoid_duplicate_call(store):
    r = row(); r['events'] = events()
    api = FakeAPI([r])
    assert run(store, api)['api_calls'] == 3
    assert '/fixtures/events' not in [e for e, _ in api.calls]


def test_unknown_catalogue_only_useful_calls(store):
    api = FakeAPI()
    report = run(store, api, m={'review_status': 'UNVERIFIED'})
    assert report['api_calls'] == 3 and not report['candidate_qualified']
    assert store.all('market_catalogue')


def test_refresh_failure_never_reuses_old_quotes(store):
    store.append('normalized_odds', 'old', {'quotes': odds()}, NOW-timedelta(hours=2))
    api = FakeAPI(fail_odds=True)
    assert run(store, api)['status'] == 'CURRENT_ODDS_UNAVAILABLE'
    assert len(api.calls) == 2 and not store.all('candidate')


def test_store_immutable_replay_and_prematch_untouched(tmp_path, store):
    assert store.append('test', 'id', {'x': 1}, NOW)
    assert not store.append('test', 'id', {'x': 1}, NOW)
    with pytest.raises(ValueError): store.append('test', 'id', {'x': 2}, NOW)
    with pytest.raises(sqlite3.IntegrityError): store.connection.execute('DELETE FROM live_documents')
    with pytest.raises(sqlite3.IntegrityError): store.connection.execute("UPDATE live_documents SET document='{}'")
    p = tmp_path/'prematch.sqlite'
    with sqlite3.connect(p) as db: db.execute('CREATE TABLE predictions(id INTEGER)')
    before = p.read_bytes()
    with pytest.raises(ValueError): Store(p)
    assert p.read_bytes() == before


@pytest.mark.parametrize('change', [{'chat_id': '-1003510920417'}, {'chat_id': '-42'}, {'contract': 'CHANNEL'},
                                   {'expected_username': ''}, {'expected_bot_id': ''}, {'started': False}, {'token': ''}])
def test_private_config_fail_closed(change):
    c = config(**change)
    assert c.check()['status'] == 'PRIVATE_CONFIG_BLOCKED'
    assert c.token not in json.dumps(c.check()) if c.token else True
    assert 'fictional_secret' not in repr(c)


def test_delivery_receipt_exactly_once_private_and_secret_safe(store):
    key = freeze(store)
    api = FakeTelegram()
    assert deliver(store, key, config(), api, confirmation=CONFIRM, now=NOW) == 'DELIVERED'
    assert deliver(store, key, config(), api, confirmation=CONFIRM, now=NOW) == 'ALREADY_CLAIMED_NO_RESEND'
    assert len(api.calls) == 1 and api.calls[0][0] == '42'
    assert store.get('receipt', key) and not store.all('delivery_unknown')
    text = api.calls[0][1]
    assert 'LIVE tirgus novērtējums' in text and 'TOTALS' not in text
    assert 'fictional_secret' not in store.path.read_bytes().decode('utf-8', errors='ignore')


def test_ambiguous_delivery_reconciliation_no_resend(store):
    key = freeze(store); api = FakeTelegram(fail=True)
    assert deliver(store, key, config(), api, confirmation=CONFIRM, now=NOW) == 'DELIVERY_UNKNOWN_NO_RESEND'
    assert deliver(store, key, config(), api, confirmation=CONFIRM, now=NOW) == 'ALREADY_CLAIMED_NO_RESEND'
    reconcile(store, key, acknowledgement(store.get('preview', key)['text']), config(), operator_reference='manual-proof', now=NOW)
    assert store.get('receipt', key) and len(api.calls) == 1


def test_wrong_ack_or_destination_never_receipt(store):
    key = freeze(store); api = FakeTelegram()
    with pytest.raises(ValueError): deliver(store, key, config(chat_id='43'), api, confirmation=CONFIRM, now=NOW)
    api.send = lambda chat, text: {'ok': True, 'result': {'message_id': 5, 'chat': {'id': -42}}}
    assert deliver(store, key, config(), api, confirmation=CONFIRM, now=NOW) == 'DELIVERY_UNKNOWN_NO_RESEND'
    assert not store.all('receipt')


def test_disabled_and_stale_delivery_no_transport(store):
    key = freeze(store); api = FakeTelegram()
    with pytest.raises(ValueError): deliver(store, key, config(enabled=False), api, confirmation=CONFIRM, now=NOW)
    with pytest.raises(ValueError): deliver(store, key, config(), api, confirmation=CONFIRM, now=NOW+timedelta(seconds=31))
    assert not api.calls and not store.all('claim')


def final_result(score=(2, 1)):
    return {'fixture_id': 100, 'home_id': 1, 'away_id': 2, 'season': 2026, 'league_id': 39, 'status': 'FT',
            'regulation_score': list(score), 'source_fingerprint': 'fixture-result-proof',
            'retrieved_at': (NOW+timedelta(hours=1)).isoformat()}


@pytest.mark.parametrize('family,side,line,expected', [('1X2', '1', None, 'WON'), ('1X2', 'X', None, 'LOST'),
    ('1X2', '2', None, 'LOST'), ('TOTALS', 'OVER', '2.5', 'WON'), ('TOTALS', 'UNDER', '2.5', 'LOST'),
    ('BTTS', 'YES', None, 'WON'), ('BTTS', 'NO', None, 'LOST')])
def test_supported_settlement(family, side, line, expected):
    c = candidate(); c['market']['quote'].update(family=family, side=side, line=line)
    settled = resolve(c, final_result())
    assert settled['outcome'] == expected
    assert settled['unit_result'] == ('1.50' if expected == 'WON' else '-1')


def test_void_and_regulation_only_no_correct_score():
    c = candidate(); r = final_result(); r.update(status='CANC', void_review_reference='review')
    assert resolve(c, r)['outcome'] == 'VOID'
    r = final_result(); r['status'] = 'AET'; r['extra_time_score'] = [4, 1]
    assert resolve(c, r)['regulation_score'] == [2, 1]
    r['regulation_score'] = None
    with pytest.raises(ValueError): resolve(c, r)
    c['market']['quote']['family'] = 'CORRECT_SCORE'
    with pytest.raises(ValueError): resolve(c, final_result())


def test_separate_statistics_settlement_and_result_preview(store):
    key = freeze(store)
    with pytest.raises(ValueError): settle(store, key, final_result(), NOW)
    deliver(store, key, config(), FakeTelegram(), confirmation=CONFIRM, now=NOW)
    settled = settle(store, key, final_result(), NOW+timedelta(hours=1))
    assert settle(store, key, final_result(), NOW+timedelta(hours=2)) == settled
    stats = statistics(store.all('settlement'))
    assert stats['product'] == 'LIVE_V2_PRIVATE' and stats['overall']['WON'] == 1
    assert set(stats) >= {'market', 'minute_band', 'odds_band', 'completeness_band'}
    rid = result_preview(store, key, config(), NOW+timedelta(hours=1))
    assert 'V2 LIVE statistika' in store.get('preview', rid)['text']
    assert set(r[0] for r in store.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")) == {'live_schema', 'live_documents'}


def test_readonly_prematch_adapter_and_cli_no_transport(tmp_path, monkeypatch, capsys):
    p = tmp_path/'audit.sqlite'
    with sqlite3.connect(p) as db:
        for table in ('cycle_health', 'quota_claims'):
            db.execute(f'CREATE TABLE {table}(stream TEXT,created_at TEXT,document TEXT)')
        for i in range(10):
            d = {'completed_at': NOW.isoformat(), 'provider_calls': 250}
            db.execute('INSERT INTO cycle_health VALUES(?,?,?)', ('PREMATCH', NOW.isoformat(), json.dumps(d)))
        d = {'category': 'SETTLEMENT', 'created_at': NOW.isoformat(), 'remaining_daily_before': 1000, 'remaining_minute_before': 290}
        db.execute('INSERT INTO quota_claims VALUES(?,?,?)', ('PREMATCH', NOW.isoformat(), json.dumps(d)))
    before = p.read_bytes()
    e = read_prematch(p, NOW)
    assert e['cycle_24h']['count'] == 10 and e['settlement_24h'] == 1
    assert not e['provider_headers_verified'] and not e['shared_token_exclusive_until']
    assert p.read_bytes() == before
    import urllib.request
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: pytest.fail('network'))
    monkeypatch.setenv('LIVE_BOT_TOKEN', '123:fictional_secret')
    for command in ('status', 'discover', 'markets', 'candidates', 'fixtures', 'statistics', 'settlements', 'telegram-config-check', 'quota'):
        assert main([command, '--store', str(tmp_path/'missing.sqlite')]) == 0
    assert not (tmp_path/'missing.sqlite').exists()
    assert 'fictional_secret' not in capsys.readouterr().out


def test_source_isolation_and_inert_systemd():
    root = Path('app/live_v2')
    for file in root.glob('*.py'):
        assert 'from app.lab_v2_shadow' not in file.read_text()
        assert 'from app.adaptive_lab' not in file.read_text()
    timer = (root/'deployment/goalvision-live-v2-private.timer').read_text()
    assert '08,10,12,14,16,18,20,22:00:00 Europe/Riga' in timer
    assert 'Persistent=false' in timer and '23:' not in timer
    service = (root/'deployment/goalvision-live-v2-private.service').read_text()
    assert 'Type=oneshot' in service and '--send' not in service


def test_event_goal_and_var_contradictions():
    f = features(state(), stats(), [])
    assert 'EVENT_SCORE_DISAGREEMENT' in f['contradictions']
    assert not features(state(), stats(), events())['contradictions']
    f = features(state(), stats(), events()+[{'team': {'id': 1}, 'time': {'elapsed': 60}, 'type': 'Var', 'detail': 'Goal cancelled'}])
    assert 'VAR_REQUIRES_STATE_REVIEW' in f['contradictions']


def test_duplicate_bookmaker_name_cannot_create_consensus():
    p = odds()
    for r in p['response']: r['bookmaker']['name'] = 'Same feed'
    q, _ = normalize(p, state(), mapping(), retrieved_at=NOW)
    assert consensus(q, NOW) == []


def test_forty_durable_daily_claims_and_cross_slot_minute(store):
    gov = Governor(store, lambda _: evidence())
    for i in range(40):
        assert gov.claim(str(i//5), '/fixtures', {}, NOW)
    assert not gov.claim('ninth', '/fixtures', {}, NOW)
    assert len(store.all('api_claim')) == 40


def test_schema_rejects_foreign_database_without_config_changes(tmp_path):
    config_file = tmp_path/'prematch.env'
    config_file.write_text('new_picks=true\nobserve=true\nlabels=true\n')
    original = config_file.read_bytes()
    p = tmp_path/'prematch.db'
    with sqlite3.connect(p) as db: db.execute('CREATE TABLE quota_claims(id INTEGER)')
    assert main(['discover', '--real-api', '--store', str(p), '--prematch-audit', str(p)]) == 2
    assert config_file.read_bytes() == original


def test_rehearsal_lifetime_bound(store):
    api = FakeAPI([])
    runner = Runner(store, Governor(store, lambda _: evidence()), api, mapping(), frozenset({39}), clock=lambda: NOW)
    assert runner.run(rehearsal=True)['api_calls'] == 1
    assert runner.run(rehearsal=True)['api_calls'] == 0


def test_receipt_persistence_failure_claim_still_blocks(store, monkeypatch):
    key = freeze(store); api = FakeTelegram()
    append = store.append
    def fail(kind, *args, **kwargs):
        if kind in {'receipt', 'delivery_unknown'}:
            raise sqlite3.OperationalError('disk full')
        return append(kind, *args, **kwargs)
    monkeypatch.setattr(store, 'append', fail)
    with pytest.raises(sqlite3.OperationalError):
        deliver(store, key, config(), api, confirmation=CONFIRM, now=NOW)
    assert store.get('claim', key)
    assert deliver(store, key, config(), api, confirmation=CONFIRM, now=NOW) == 'ALREADY_CLAIMED_NO_RESEND'
    assert len(api.calls) == 1


def test_provider_failure_redacts_secrets(monkeypatch):
    from app.live_v2.provider import FootballHTTP
    import urllib.request
    class Opener:
        def open(self, *args, **kwargs):
            raise RuntimeError('secret_token')
    monkeypatch.setattr(urllib.request, 'build_opener', lambda *args: Opener())
    with pytest.raises(RuntimeError, match='^LIVE_PROVIDER_REQUEST_FAILED$'):
        FootballHTTP('secret_token').get('/fixtures', {'live': 'all'})


def test_directly_replayed_statistical_evidence_is_identical():
    # Fictional chronological settlement replay; not a real predictive backtest.
    c = candidate()
    first = resolve(c, final_result())
    second = resolve(deepcopy(c), deepcopy(final_result()))
    assert digest(first) == digest(second)
    assert statistics([first]) == statistics([second])
    with pytest.raises(ValueError): statistics([first, second])


def test_provider_response_quota_rechecked_before_every_call(store):
    class Exhausted(FakeAPI):
        def get(self, endpoint, query):
            payload, quota = super().get(endpoint, query)
            quota['daily_remaining'] = 0
            return payload, quota
    api = Exhausted()
    report = run(store, api)
    assert len(api.calls) == 1 and report['api_calls'] == 1
    assert not report['candidate_qualified']


def test_changed_prematch_cadence_fails_closed():
    e = evidence(); e['installed_contract']['verified'] = False
    assert budget(e, now=NOW, daily_calls=0, slot_calls=0)['safe_calls'] == 0


def test_void_cannot_bypass_unsupported_market():
    c = candidate(); c['market']['quote']['family'] = 'CORRECT_SCORE'
    r = final_result(); r.update(status='CANC', void_review_reference='cancelled')
    with pytest.raises(ValueError): resolve(c, r)


def test_no_minimum_decimal_odds_floor():
    p = odds()
    for i, r in enumerate(p['response']):
        r['odds'][0]['values'][0]['odd'] = '1.50' if i == 0 else '1.20'
        r['odds'][0]['values'][1]['odd'] = '2.50' if i == 0 else '4.00'
    s = state(); q, _ = normalize(p, s, mapping(), retrieved_at=NOW)
    results = evaluate(s, features(s, stats(), events()), q, now=NOW, safe_quota=True)
    assert any(c['qualified'] and c['market']['quote']['odds'] == '1.50' for c in results)


def test_remaining_future_slots_distinct_from_current_protection():
    now = NOW.replace(hour=19, minute=46)
    assert prematch_remaining(now) == 1
    assert prematch_remaining(now, include_current=False) == 0


def test_current_only_provider_endpoint_contract():
    from app.live_v2.provider import FootballHTTP
    with pytest.raises(ValueError, match='UNSUPPORTED_LIVE_ENDPOINT'):
        FootballHTTP('never_used').get('/odds', {'fixture': 100})


def test_pending_telegram_claim_prevents_second_transport_even_without_unknown_row(store):
    key = freeze(store)
    store.append('claim', key, {'economic_key': key}, NOW, ('preview', key))
    api = FakeTelegram()
    assert deliver(store, key, config(), api, confirmation=CONFIRM, now=NOW) == 'ALREADY_CLAIMED_NO_RESEND'
    assert not api.calls


def test_candidate_destination_cannot_override_private_config(store):
    c = candidate(); c['chat_id'] = '-999'; c['destination'] = '-999'
    store.append('candidate', 'untrusted_destination', c, NOW)
    key = preview(store, 'untrusted_destination', config(), NOW)
    assert store.get('preview', key)['chat_id'] == '42'


def test_reconciliation_must_match_frozen_destination(store):
    key = freeze(store)
    deliver(store, key, config(), FakeTelegram(fail=True), confirmation=CONFIRM, now=NOW)
    ack = acknowledgement(store.get('preview', key)['text'])
    ack['result']['chat']['id'] = 43
    with pytest.raises(ValueError):
        reconcile(store, key, ack, config(chat_id='43'), operator_reference='wrong-chat', now=NOW)
    assert not store.get('receipt', key)


def test_malformed_provider_rows_fail_closed_with_durable_report(store):
    api = FakeAPI([None])
    report = run(store, api)
    assert report['status'] == 'INVALID_LIVE_EVIDENCE'
    assert report['api_calls'] == 1 and not report['candidate_qualified']
    assert store.all('rejection') and store.all('run')


def test_global_snapshot_keeps_provider_quota_evidence(store):
    run(store, FakeAPI([]))
    global_snapshot = store.all('global_snapshot')[0]
    assert global_snapshot['provider_quota']['daily_remaining'] == 7000
    assert global_snapshot['source_fingerprint']
