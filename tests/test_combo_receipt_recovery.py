"""Offline checks: exact Reply binding, immutable reconciliation and no send capability."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[1] / 'operations/combo-receipt-recovery/recover.py'
spec = importlib.util.spec_from_file_location('combo_receipt_recovery', PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('NETWORK_FORBIDDEN')
    monkeypatch.setattr('socket.socket.connect', deny)
    monkeypatch.setattr('socket.create_connection', deny)


@pytest.fixture
def rig(tmp_path):
    route = {'chat_id': '111', 'bot_id': '222', 'bot_username': '@' + m.USERNAME,
             'product': 'COMBO', 'chat_type': 'private',
             'version': 'GOALVISION_COMBO_PRIVATE_ROUTE_V1',
             'statistics_period': 'COMBO_BOT_20261003_V1',
             'period_started_at': '2026-10-03T10:50:00+00:00'}
    values = {'prediction': {'prediction_id': 'test-combo'},
              'claim': {'prediction_id': 'test-combo', 'chat_id': '111',
                        'delivery_route': route, 'message': 'Frozen COMBO #1'},
              'delivery_unknown': {'status': 'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED'}}
    case = {'version': m.VERSION, 'prediction_id': 'test-combo', 'issued_at': 200,
            'expires_at': 1000, 'challenge': 'GV-CASE-NONCE', 'original_min_date': 100,
            'original_max_date': 120, 'route_sha256': m.digest(route),
            'message_sha256': m.text_digest(values['claim']['message']),
            'fingerprints': {k: m.digest(v) for k, v in values.items()}}
    original = {'message_id': 10, 'date': 110, 'text': values['claim']['message'],
                'from': {'id': 222, 'is_bot': True, 'username': m.USERNAME},
                'chat': {'id': 111, 'type': 'private'}}
    update = {'update_id': 20, 'message': {'message_id': 11, 'date': 250,
        'text': case['challenge'], 'from': {'id': 111, 'is_bot': False},
        'chat': {'id': 111, 'type': 'private'}, 'reply_to_message': original}}
    db = tmp_path / 'ledger.db'
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE evidence(kind TEXT,identity TEXT,fingerprint TEXT,document TEXT,
                              PRIMARY KEY(kind,identity));
        CREATE TRIGGER immutable_update BEFORE UPDATE ON evidence BEGIN
          SELECT RAISE(ABORT,'Immutable Lab Combo evidence'); END;
        CREATE TRIGGER immutable_delete BEFORE DELETE ON evidence BEGIN
          SELECT RAISE(ABORT,'Immutable Lab Combo evidence'); END;
    """)
    for kind, value in values.items():
        key = 'test-combo' if kind == 'prediction' else 'combo_prediction:test-combo'
        conn.execute('INSERT INTO evidence VALUES(?,?,?,?)', (kind, key, m.digest(value), m.canonical(value)))
    conn.commit()
    yield SimpleNamespace(case=case, route=route, update=update, conn=conn, db=db, values=values)
    conn.close()


def proof(r):
    return m.find_reply([r.update], r.case, r.route, 300)


def test_correct_reply_and_atomic_append_are_idempotent(rig):
    before = rig.conn.execute('SELECT * FROM evidence').fetchall()
    p = proof(rig)
    assert m.append_reconciliation(rig.conn, rig.case, p, 300)
    assert not m.append_reconciliation(rig.conn, rig.case, p, 301)
    after = rig.conn.execute('SELECT * FROM evidence').fetchall()
    assert len(after) == len(before) + 2
    assert all(row in after for row in before)
    receipt = m.evidence(rig.conn, 'receipt', 'combo_prediction:test-combo')
    assert receipt['message_id'] == 10
    assert receipt['sent_at_utc'] == '1970-01-01T00:01:50+00:00'
    assert receipt['delivery_route'] == rig.route
    assert m.verify_case(rig.conn, rig.case)[1] is True


@pytest.mark.parametrize('where,key,value', [
    ('parent','text','Another COMBO'), ('parent','message_id',True),
    ('parent','date',121), ('parent','date',True), ('parent','edit_date',111),
    ('parent','forward_origin',{}), ('parent','external_reply',{}),
    ('parent','via_bot',{}), ('reply','edit_date',251), ('reply','forward_origin',{}),
    ('reply','external_reply',{}), ('reply','date',199), ('reply','date',999),
    ('reply','message_id',True), ('reply','reply_to_message',None),
    ('parent_sender','id',333), ('parent_sender','is_bot',False),
    ('parent_sender','username','different_bot'), ('parent_chat','id',333),
    ('parent_chat','type','group'), ('sender','id',333), ('sender','is_bot',True),
    ('chat','id',333), ('chat','type','group'), ('reply','text','wrong nonce'),
])
def test_wrong_reply_fails_closed(rig, where, key, value):
    message = rig.update['message']
    places = {'parent': message['reply_to_message'], 'reply': message,
              'parent_sender': message['reply_to_message']['from'],
              'parent_chat': message['reply_to_message']['chat'],
              'sender': message['from'], 'chat': message['chat']}
    places[where][key] = value
    with pytest.raises(m.Blocked):
        proof(rig)


def test_expired_empty_and_ambiguous_replies(rig):
    with pytest.raises(m.Blocked, match='EXPIRED'):
        m.find_reply([rig.update], rig.case, rig.route, 1001)
    with pytest.raises(m.Blocked, match='NOT_FOUND'):
        m.find_reply([], rig.case, rig.route, 300)
    other = deepcopy(rig.update)
    other['message']['reply_to_message']['message_id'] = 99
    with pytest.raises(m.Blocked, match='AMBIGUOUS'):
        m.find_reply([rig.update, other], rig.case, rig.route, 300)


def test_repeat_reply_to_same_parent_is_deterministic(rig):
    second = deepcopy(rig.update)
    second['update_id'] += 1
    second['message']['message_id'] += 1
    assert m.find_reply([second, rig.update], rig.case, rig.route, 300) == proof(rig)


def test_telegram_reads_are_bounded_and_do_not_acknowledge(rig):
    calls = []
    def reader(token, method, parameters=None):
        calls.append((method, parameters))
        return {'getMe': rig.update['message']['reply_to_message']['from'],
                'getWebhookInfo': {'url': ''}, 'getUpdates': [rig.update]}[method]
    p = m.capture_reply(rig.case, {'route': rig.route, 'token': 'fake'}, 300, reader)
    assert p == proof(rig)
    assert calls == [('getMe', None), ('getWebhookInfo', None),
                     ('getUpdates', {'limit': 100, 'timeout': 0})]


def test_webhook_does_not_get_removed_or_polled(rig):
    calls = []
    def reader(token, method, parameters=None):
        calls.append(method)
        return (rig.update['message']['reply_to_message']['from'] if method == 'getMe'
                else {'url': 'https://example.invalid/webhook'})
    with pytest.raises(m.Blocked, match='WEBHOOK'):
        m.capture_reply(rig.case, {'route': rig.route, 'token': 'fake'}, 300, reader)
    assert calls == ['getMe', 'getWebhookInfo']


@pytest.mark.parametrize('method,params', [
    ('sendMessage', {}), ('forwardMessage', {}), ('deleteWebhook', {}),
    ('getUpdates', {'offset': 1}), ('getUpdates', {'limit': 100,'timeout': 0,'allowed_updates': []}),
])
def test_mutating_or_queue_changing_api_calls_are_unavailable(method, params):
    with pytest.raises(m.Blocked, match='READ_METHOD'):
        m.telegram_read('fake', method, params)


def test_http_error_is_secret_free(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('https://api.telegram.org/botSECRET/getMe')
    monkeypatch.setattr(m.urllib.request, 'build_opener', fail)
    with pytest.raises(m.Blocked, match='^TELEGRAM_READ_FAILED$'):
        m.telegram_read('SECRET', 'getMe')


def test_redirects_blocked():
    with pytest.raises(m.Blocked, match='REDIRECT'):
        m.NoRedirect().redirect_request()


@pytest.mark.parametrize('tamper', ['fingerprint','route','body','proof_case','proof_parent'])
def test_case_drift_blocks_without_writes(rig, tamper):
    p = proof(rig)
    before = rig.conn.execute('SELECT * FROM evidence').fetchall()
    if tamper == 'fingerprint':
        rig.case['fingerprints']['claim'] = 'bad'
    elif tamper == 'route':
        rig.case['route_sha256'] = 'bad'
    elif tamper == 'body':
        rig.case['message_sha256'] = 'bad'
    elif tamper == 'proof_case':
        p['case_sha256'] = 'bad'
    else:
        p['original']['chat_id'] = '333'
    with pytest.raises(m.Blocked):
        m.append_reconciliation(rig.conn, rig.case, p, 300)
    assert rig.conn.execute('SELECT * FROM evidence').fetchall() == before


def test_second_append_failure_rolls_back_first(rig):
    rig.conn.execute("""CREATE TRIGGER reject_receipt BEFORE INSERT ON evidence
       WHEN NEW.kind='receipt' BEGIN SELECT RAISE(ABORT,'test rejection'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        m.append_reconciliation(rig.conn, rig.case, proof(rig), 300)
    assert rig.conn.execute('SELECT count(*) FROM evidence').fetchone()[0] == 3


def test_existing_unrelated_receipt_blocks(rig):
    value = {'status':'SENT', 'message_id': 999}
    rig.conn.execute('INSERT INTO evidence VALUES(?,?,?,?)',
        ('receipt','combo_prediction:test-combo',m.digest(value),m.canonical(value)))
    rig.conn.commit()
    with pytest.raises(m.Blocked, match='REQUIRES_REVIEW'):
        m.append_reconciliation(rig.conn, rig.case, proof(rig), 300)


def test_missing_ledger_is_not_created_and_symlink_refused(rig, tmp_path):
    missing = tmp_path / 'missing.db'
    with pytest.raises(FileNotFoundError):
        m.connect(missing, writable=True)
    assert not missing.exists()
    link = tmp_path / 'link.db'
    link.symlink_to(rig.db)
    with pytest.raises(m.Blocked, match='SYMLINK'):
        m.connect(link, writable=True)


def test_missing_immutability_guard_blocks(rig):
    rig.conn.execute('DROP TRIGGER immutable_delete')
    with pytest.raises(m.Blocked, match='IMMUTABILITY'):
        m.append_reconciliation(rig.conn, rig.case, proof(rig), 300)


def test_plan_does_not_read_telegram_or_write_ledger(rig, monkeypatch, capsys):
    monkeypatch.setattr(m, 'LEDGER', rig.db)
    monkeypatch.setattr(m, 'runtime_guard', lambda case: None)
    monkeypatch.setattr(m, 'load_config', lambda case: {'route': rig.route})
    monkeypatch.setattr(m.time, 'time', lambda: 300)
    monkeypatch.setattr(m, 'capture_reply', lambda *args: pytest.fail('UNEXPECTED_TELEGRAM_READ'))
    m.run(rig.case, 'plan')
    assert 'PLAN_VALIDATED' in capsys.readouterr().out
    assert rig.conn.execute('SELECT count(*) FROM evidence').fetchone()[0] == 3


def test_apply_requires_root_before_guard_or_reads(rig, monkeypatch):
    monkeypatch.setattr(m.os, 'geteuid', lambda: 1001)
    monkeypatch.setattr(m, 'runtime_guard', lambda *args: pytest.fail('UNEXPECTED_GUARD'))
    with pytest.raises(m.Blocked, match='OPERATOR_ROOT'):
        m.run(rig.case, 'apply')


def test_apply_does_not_trust_saved_capture(rig, monkeypatch):
    monkeypatch.setattr(m.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(m, 'LEDGER', rig.db)
    monkeypatch.setattr(m, 'runtime_guard', lambda case: None)
    monkeypatch.setattr(m, 'load_config', lambda case: {'route': rig.route})
    monkeypatch.setattr(m.time, 'time', lambda: 300)
    monkeypatch.setattr(m, 'private_json', lambda path: {'forged': True})
    monkeypatch.setattr(m, 'capture_reply', lambda *args: proof(rig))
    with pytest.raises(m.Blocked, match='LIVE_PROOF_CHANGED'):
        m.run(rig.case, 'apply')
    assert rig.conn.execute('SELECT count(*) FROM evidence').fetchone()[0] == 3


def test_reconciled_receipt_satisfies_existing_result_reply_contract(rig, monkeypatch):
    from app.lab_combo.bot_routing import frozen_route
    from app.lab_combo.settlement_reply import settlement_reply
    monkeypatch.setenv('GOALVISION_LAB_SETTLEMENT_REPLIES', '1')
    m.append_reconciliation(rig.conn, rig.case, proof(rig), 300)
    ledger = SimpleNamespace(get=lambda kind, identity: m.evidence(rig.conn, kind, identity))
    assert frozen_route(ledger, 'test-combo') == rig.route
    binding = settlement_reply(ledger, 'combo_settlement', 'test-combo', '111')
    assert binding['message_id'] == 10
    assert binding['publication_identity'] == 'combo_prediction:test-combo'


def test_apply_drops_root_before_opening_writable_ledger(rig, monkeypatch):
    monkeypatch.setattr(m.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(m, 'LEDGER', rig.db)
    calls = []
    monkeypatch.setattr(m, 'runtime_guard', lambda case: calls.append('guard'))
    monkeypatch.setattr(m, 'load_config', lambda case: {'route': rig.route})
    monkeypatch.setattr(m.time, 'time', lambda: 300)
    monkeypatch.setattr(m, 'private_json', lambda path: proof(rig))
    monkeypatch.setattr(m, 'capture_reply', lambda *args: proof(rig))
    monkeypatch.setattr(m.pwd, 'getpwnam', lambda user: SimpleNamespace(
        pw_uid=rig.db.stat().st_uid, pw_gid=rig.db.stat().st_gid))
    monkeypatch.setattr(m.os, 'initgroups', lambda *args: calls.append('groups'))
    monkeypatch.setattr(m.os, 'setgid', lambda *args: calls.append('gid'))
    monkeypatch.setattr(m.os, 'setuid', lambda *args: calls.append('uid'))
    connect = m.connect
    def observed(path, *, writable=False):
        if writable:
            assert calls[-3:] == ['groups', 'gid', 'uid']
            calls.append('write_open')
        return connect(path, writable=writable)
    monkeypatch.setattr(m, 'connect', observed)
    m.run(rig.case, 'apply')
    assert calls == ['guard', 'guard', 'groups', 'gid', 'uid', 'write_open']
    assert m.verify_case(rig.conn, rig.case)[1] is True


def test_package_build_is_repeatable_and_refuses_drift(tmp_path, monkeypatch):
    build_spec = importlib.util.spec_from_file_location('combo_receipt_build', PATH.with_name('build.py'))
    builder = importlib.util.module_from_spec(build_spec)
    build_spec.loader.exec_module(builder)
    source = {'recover.py': PATH.read_bytes(), 'case.json': PATH.with_name('case.json').read_bytes()}
    commit = 'a' * 40
    def git_output(args, **kwargs):
        if args[1] == 'rev-parse':
            return commit + '\n'
        return source[args[-1].split('/')[-1]]
    monkeypatch.setattr(builder.subprocess, 'check_output', git_output)
    builder.build(tmp_path, commit, tmp_path)
    package = tmp_path / ('combo-receipt-' + commit[:7] + '-20261006')
    first = {p.name: p.read_bytes() for p in package.iterdir()}
    launcher = (tmp_path / 'combo-receipt.py').read_bytes()
    builder.build(tmp_path, commit, tmp_path)
    assert first == {p.name: p.read_bytes() for p in package.iterdir()}
    assert launcher == (tmp_path / 'combo-receipt.py').read_bytes()
    (package / 'recover.py').write_text('changed')
    with pytest.raises(ValueError, match='DRIFT'):
        builder.build(tmp_path, commit, tmp_path)
