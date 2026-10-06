"""One pinned COMBO receipt recovery. No publication, settlement or service calls."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import sqlite3
import stat
import subprocess
import time
import urllib.request

LEDGER = Path('/home/arvis/GoalVisionAI/var/lab_combo/ledger.db')
CONFIG = Path('/home/arvis/goalvision-private/combo-telegram.json')
GUARD = Path('/home/arvis/goalvision-operations/prematch-evidence.py')
CAPTURE = Path('/home/arvis/goalvision-private/combo-receipt-e1f7-capture.json')
VERSION = 'COMBO_REPLY_RECEIPT_RECOVERY_V1'
USERNAME = 'GoalVision_AI_Combo_Bot'


class Blocked(ValueError):
    """Only constant, secret-free reasons cross the CLI boundary."""


def require(condition, reason):
    if not condition:
        raise Blocked(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text_digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def regular(path):
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'SYMLINK_REFUSED')
    require(stat.S_ISREG(path.lstat().st_mode), 'REGULAR_FILE_REQUIRED')


def private_json(path):
    regular(path)
    info = path.stat()
    require(stat.S_IMODE(info.st_mode) == 0o600 and info.st_size <= 8192
            and info.st_uid in {0, pwd.getpwnam('arvis').pw_uid}, 'PRIVATE_FILE_REQUIRED')
    return json.loads(path.read_text())


def load_config(case):
    data = private_json(CONFIG)
    require(set(data) == {'token', 'route', 'verified_at', 'start_update_id'}, 'CONFIG_INVALID')
    route = data['route']
    require(digest(route) == case['route_sha256'], 'ROUTE_DRIFT')
    require(route['bot_username'] == '@' + USERNAME and route['chat_type'] == 'private'
            and route['product'] == 'COMBO', 'PRIVATE_COMBO_ROUTE_REQUIRED')
    require(isinstance(data['token'], str) and re.fullmatch(
        re.escape(route['bot_id']) + r':[A-Za-z0-9_-]{20,100}', data['token']), 'CONFIG_INVALID')
    require(data['verified_at'] == route['period_started_at'], 'CONFIG_INVALID')
    return data


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Blocked('TELEGRAM_REDIRECT_REFUSED')


def telegram_read(token, method, parameters=None):
    allowed = {'getMe': {}, 'getWebhookInfo': {}, 'getUpdates': {'limit': 100, 'timeout': 0}}
    require(method in allowed and (parameters or {}) == allowed[method], 'READ_METHOD_REQUIRED')
    request = urllib.request.Request('https://api.telegram.org/bot' + token + '/' + method,
        data=canonical(parameters or {}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=15) as response:
            body = response.read(1048577)
        require(len(body) <= 1048576, 'TELEGRAM_READ_FAILED')
        result = json.loads(body)
        require(result.get('ok') is True, 'TELEGRAM_READ_FAILED')
        return result['result']
    except Exception:
        # HTTP errors contain the token in the URL. Never print exception details.
        raise Blocked('TELEGRAM_READ_FAILED') from None


def positive_int(value):
    return type(value) is int and value > 0


def original_binding(message, case, route):
    require(isinstance(message, dict), 'ORIGINAL_REPLY_REQUIRED')
    forbidden = {'forward_origin', 'forward_date', 'forward_from', 'forward_from_chat',
                 'edit_date', 'external_reply', 'via_bot', 'sender_business_bot'}
    require(not forbidden.intersection(message), 'ORIGINAL_MESSAGE_MODIFIED')
    sender, chat = message.get('from', {}), message.get('chat', {})
    require(type(sender.get('id')) is int and str(sender['id']) == route['bot_id']
            and sender.get('is_bot') is True and sender.get('username') == USERNAME,
            'ORIGINAL_BOT_MISMATCH')
    require(type(chat.get('id')) is int and str(chat['id']) == route['chat_id']
            and chat.get('type') == 'private', 'ORIGINAL_CHAT_MISMATCH')
    require(positive_int(message.get('message_id')), 'ORIGINAL_ID_INVALID')
    require(type(message.get('date')) is int
            and case['original_min_date'] <= message['date'] <= case['original_max_date'],
            'ORIGINAL_DATE_MISMATCH')
    require(isinstance(message.get('text'), str)
            and text_digest(message['text']) == case['message_sha256'], 'ORIGINAL_BODY_MISMATCH')
    return {'message_id': message['message_id'], 'date': message['date'],
            'chat_id': route['chat_id'], 'bot_id': route['bot_id'],
            'message_sha256': case['message_sha256']}


def find_reply(updates, case, route, now):
    require(case['issued_at'] <= now <= case['expires_at'], 'CHALLENGE_EXPIRED')
    require(isinstance(updates, list) and len(updates) <= 100, 'UPDATES_INVALID')
    found = []
    for update in updates:
        if not isinstance(update, dict):
            continue
        message = update.get('message')
        if not isinstance(message, dict) or message.get('text') != case['challenge']:
            continue
        sender, chat = message.get('from', {}), message.get('chat', {})
        if (type(sender.get('id')) is not int or str(sender['id']) != route['chat_id']
                or sender.get('is_bot') is not False or type(chat.get('id')) is not int
                or str(chat['id']) != route['chat_id'] or chat.get('type') != 'private'):
            continue
        require(not {'edit_date', 'forward_origin', 'forward_date', 'external_reply',
                     'via_bot', 'sender_business_bot'}.intersection(message), 'REPLY_MODIFIED')
        require(type(message.get('date')) is int
                and case['issued_at'] <= message['date'] <= min(now + 30, case['expires_at']),
                'REPLY_DATE_INVALID')
        require(positive_int(message.get('message_id'))
                and type(update.get('update_id')) is int and update['update_id'] >= 0,
                'REPLY_ID_INVALID')
        binding = original_binding(message.get('reply_to_message'), case, route)
        found.append({'case_sha256': digest(case), 'original': binding,
                      'update_id': update['update_id'], 'reply_message_id': message['message_id'],
                      'reply_date': message['date']})
    require(found, 'REPLY_NOT_FOUND_NO_OFFSET_ADVANCED')
    require(len({digest(x['original']) for x in found}) == 1, 'AMBIGUOUS_ORIGINAL_REPLY')
    return min(found, key=lambda x: x['update_id'])


def capture_reply(case, config, now, reader=telegram_read):
    route, token = config['route'], config['token']
    me = reader(token, 'getMe')
    require(isinstance(me, dict) and type(me.get('id')) is int
            and str(me['id']) == route['bot_id'] and me.get('is_bot') is True
            and me.get('username') == USERNAME, 'BOT_IDENTITY_MISMATCH')
    webhook = reader(token, 'getWebhookInfo')
    require(isinstance(webhook, dict) and webhook.get('url') == '', 'WEBHOOK_ACTIVE_OR_UNKNOWN')
    updates = reader(token, 'getUpdates', {'limit': 100, 'timeout': 0})
    return find_reply(updates, case, route, now)


def connect(path, *, writable=False):
    regular(path)
    conn = sqlite3.connect(path.as_uri() + ('?mode=rw' if writable else '?mode=ro'),
                           uri=True, timeout=2)
    if not writable:
        conn.execute('PRAGMA query_only=ON')
    return conn


def evidence(conn, kind, identity):
    row = conn.execute('SELECT fingerprint,document FROM evidence WHERE kind=? AND identity=?',
                       (kind, identity)).fetchone()
    if row is None:
        return None
    value = json.loads(row[1])
    require(digest(value) == row[0], 'EVIDENCE_FINGERPRINT_INVALID')
    return value


def verify_case(conn, case):
    pid, key = case['prediction_id'], 'combo_prediction:' + case['prediction_id']
    values = {}
    for kind in ('prediction', 'claim', 'delivery_unknown'):
        value = evidence(conn, kind, pid if kind == 'prediction' else key)
        require(value is not None and digest(value) == case['fingerprints'][kind], 'CASE_EVIDENCE_DRIFT')
        values[kind] = value
    claim = values['claim']
    require(claim['prediction_id'] == pid and values['prediction']['prediction_id'] == pid
            and text_digest(claim['message']) == case['message_sha256']
            and digest(claim['delivery_route']) == case['route_sha256']
            and str(claim['chat_id']) == claim['delivery_route']['chat_id'], 'CASE_BINDING_INVALID')
    receipt, audit = (evidence(conn, k, key) for k in ('receipt', 'delivery_reconciliation'))
    if receipt is not None or audit is not None:
        require(receipt is not None and audit is not None, 'EXISTING_RECEIPT_REQUIRES_REVIEW')
        require(audit.get('version') == VERSION and audit.get('case_sha256') == digest(case)
                and receipt.get('reconciliation_sha256') == digest(audit)
                and receipt.get('status') == 'SENT' and receipt.get('sent') is True
                and receipt.get('delivery_route') == claim['delivery_route']
                and receipt.get('chat_id') == claim['delivery_route']['chat_id']
                and receipt.get('message_id') == audit['proof']['original']['message_id']
                and receipt.get('sent_at_utc') == datetime.fromtimestamp(
                    audit['proof']['original']['date'], timezone.utc).isoformat(), 'RECONCILIATION_CONFLICT')
        return claim, True
    require(evidence(conn, 'settlement', pid) is None
            and evidence(conn, 'receipt', 'combo_settlement:' + pid) is None,
            'SETTLEMENT_STATE_REQUIRES_REVIEW')
    return claim, False


def runtime_guard(case):
    regular(GUARD)
    require(hashlib.sha256(GUARD.read_bytes()).hexdigest() == case['guard_sha256'], 'GUARD_DRIFT')
    result = subprocess.run(['/usr/bin/python3', '-I', '-B', str(GUARD)],
        capture_output=True, text=True, timeout=60, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin'})
    require(result.returncode == 0 and 'current_mode=ENABLED;' in result.stdout
            and 'ADMIN_CODEX_SYSTEMD_DISABLED=PASS' in result.stdout, 'RUNTIME_GUARD_FAILED')


def save_capture(proof):
    parent = CAPTURE.parent
    require(not any(p.is_symlink() for p in (parent, *parent.parents))
            and parent.is_dir() and not parent.stat().st_mode & 0o077, 'PRIVATE_DIRECTORY_REQUIRED')
    if CAPTURE.exists() or CAPTURE.is_symlink():
        require(private_json(CAPTURE) == proof, 'CAPTURE_CONFLICT')
        return
    fd = os.open(CAPTURE, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as output:
        output.write(canonical(proof) + '\n')
        output.flush()
        os.fsync(output.fileno())


def append_reconciliation(conn, case, proof, now):
    """Caller supplies a freshly reverified Telegram proof; one atomic append-only transaction."""
    conn.execute('BEGIN IMMEDIATE')
    try:
        claim, done = verify_case(conn, case)
        if done:
            conn.rollback()
            return False
        require(proof['case_sha256'] == digest(case), 'PROOF_CASE_MISMATCH')
        require(case['issued_at'] <= now <= case['expires_at'], 'CHALLENGE_EXPIRED')
        original = proof['original']
        require(positive_int(original['message_id']) and original['chat_id'] == claim['delivery_route']['chat_id']
                and original['bot_id'] == claim['delivery_route']['bot_id']
                and original['message_sha256'] == case['message_sha256']
                and case['original_min_date'] <= original['date'] <= case['original_max_date'],
                'PROOF_ORIGINAL_MISMATCH')
        triggers = dict(conn.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"))
        require(all(name in triggers and 'RAISE(ABORT' in triggers[name]
                    for name in ('immutable_update', 'immutable_delete')), 'IMMUTABILITY_GUARD_MISSING')
        audit = {'version': VERSION, 'case_sha256': digest(case), 'proof': proof,
                 'confirmed_at_utc': datetime.fromtimestamp(now, timezone.utc).isoformat(),
                 'source': 'TELEGRAM_AUTHENTICATED_OWNER_REPLY',
                 'historical_unknown_retained': True, 'no_message_sent_by_recovery': True}
        receipt = {'status': 'SENT', 'sent': True, 'chat_id': original['chat_id'],
                   'message_id': original['message_id'],
                   'sent_at_utc': datetime.fromtimestamp(original['date'], timezone.utc).isoformat(),
                   'delivery_route': claim['delivery_route'], 'receipt_source': VERSION,
                   'reconciliation_sha256': digest(audit)}
        key = 'combo_prediction:' + case['prediction_id']
        for kind, value in (('delivery_reconciliation', audit), ('receipt', receipt)):
            conn.execute('INSERT INTO evidence(kind,identity,fingerprint,document) VALUES(?,?,?,?)',
                         (kind, key, digest(value), canonical(value)))
        conn.commit()
        return True
    except BaseException:
        conn.rollback()
        raise


def run(case, mode):
    require(case['version'] == VERSION, 'CASE_VERSION_INVALID')
    if mode == 'apply':
        require(os.geteuid() == 0, 'OPERATOR_ROOT_REQUIRED')
    runtime_guard(case)
    with closing(connect(LEDGER)) as conn:
        _, done = verify_case(conn, case)
    if done:
        print('COMBO_RECEIPT_ALREADY_RECONCILED; no writes or API calls')
        return
    now = int(time.time())
    require(case['issued_at'] <= now <= case['expires_at'], 'CHALLENGE_EXPIRED')
    config = load_config(case)
    if mode == 'plan':
        print('COMBO_RECEIPT_PLAN_VALIDATED; no DB writes or API calls')
        print('Reply to the ORIGINAL COMBO with: ' + case['challenge'])
        return
    saved = private_json(CAPTURE) if mode == 'apply' else None
    proof = capture_reply(case, config, now)
    if mode == 'capture':
        save_capture(proof)
        print('COMBO_ORIGINAL_REPLY_VERIFIED; private proof saved; no ledger writes')
        print('proof_sha256=' + digest(proof))
        return
    require(saved == proof, 'LIVE_PROOF_CHANGED')
    runtime_guard(case)
    # Root checks protected guards; the append uses the existing ledger owner's uid.
    # This prevents root-owned WAL/journal files from breaking normal settlement.
    owner = pwd.getpwnam('arvis')
    require(LEDGER.stat().st_uid == owner.pw_uid, 'LEDGER_OWNER_MISMATCH')
    os.initgroups('arvis', owner.pw_gid)
    os.setgid(owner.pw_gid)
    os.setuid(owner.pw_uid)
    with closing(connect(LEDGER, writable=True)) as conn:
        changed = append_reconciliation(conn, case, proof, int(time.time()))
    print('COMBO_RECEIPT_RECONCILED' if changed else 'COMBO_RECEIPT_ALREADY_RECONCILED')
    print('Original claim/unknown retained; no sends; existing natural settlement timer handles result.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--capture', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        case = json.loads(Path(__file__).with_name('case.json').read_text())
        run(case, 'apply' if args.apply else 'capture' if args.capture else 'plan')
    except Blocked as error:
        print('COMBO_RECEIPT_BLOCKED:' + str(error))
        raise SystemExit(1) from None
    except Exception:
        print('COMBO_RECEIPT_BLOCKED:PRIVATE_OPERATION_FAILED')
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
