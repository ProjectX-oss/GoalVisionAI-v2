"""Repair operator outbox, independent of incident lifecycle and correlation."""
from __future__ import annotations

import json
from pathlib import Path
import time
from typing import TYPE_CHECKING

from app.admin_autorepair.protocol import TERMINAL, check_spool, read_json, validate_status
from .delivery import DeliveryError, SenderConfig, Transport
from .model import digest

if TYPE_CHECKING:
    from .store import Store


def message(bundle: dict, status: dict, kind: str) -> str:
    """Describe validated worker evidence; completion never claims deployment."""
    mode = ('Tikai izpēte' if bundle['mode'] == 'DIAGNOSE_ONLY'
            else 'Izpēte un labojuma sagatavošana izolētā kopijā')
    icon, action = '⏳', 'Pagaidām tava rīcība nav vajadzīga.'
    if kind == 'STARTED':
        label = 'Sāk izpēti'
    elif kind == 'RUNNING':
        label = ('Turpina izpēti' if bundle['mode'] == 'DIAGNOSE_ONLY'
                 else 'Turpina izpēti un labojuma sagatavošanu')
    elif kind == 'COMPLETED' and status['outcome'] == 'PATCH_READY':
        icon, label = '🛠️', 'Gaida pārbaudi un apstiprinājumu'
        action = ('Labojums sagatavots izolētā kopijā. Jāpārbauda izmaiņas un testu '
                  'rezultāti, tad jāapstiprina uzstādīšana. Produkcijā vēl nav uzstādīts.')
    elif kind == 'COMPLETED':
        icon = '📋'
        label = ('Izpēte pabeigta' if status['outcome'] == 'DIAGNOSIS_ONLY'
                 else 'Darbs pabeigts bez koda labojuma')
        action = 'Jāpārskata izpētes rezultāts un jāizlemj nākamā rīcība.'
    else:
        icon = '⚠️'
        label = {'STALLED': 'Nav svaiga progresa ziņojuma',
                 'TIMEOUT': 'Sasniegts darba laika limits',
                 'FAILED': 'Darbs beidzās ar kļūdu'}[kind]
        action = ('Vairāk nekā 3 minūtes nav saņemts darba progresa apstiprinājums. '
                  'Jāpārbauda darba stāvoklis.' if kind == 'STALLED' else
                  'Nepieciešama darba kļūdas pārbaude; automātiska atkārtojuma nebūs.')
    seconds = int(status['elapsed_seconds'])
    return '\n'.join((f'{icon} GoalVision ADMIN • Auto-Repair',
        f'Statuss: {label}', f'Režīms: {mode}', f'Darbība: {action}',
        f"Mērķis: {bundle['target']}", f"Incidents: {bundle['incident_id']}",
        f"Mainīti faili: {status['changed_files']}",
        f'Ilgums: {seconds // 60} min {seconds % 60} s',
        f"Kods: {kind} / {status['outcome'] or 'IN_PROGRESS'}",
        f"Kļūmes kods: {status['failure'] if kind != 'STARTED' and status['failure'] else 'NAV'}",
        f"Darbs: {bundle['job_id']}"))


def notice(store: Store, bundle: dict, status: dict, kind: str, key: object, now: float) -> None:
    """Idempotent machine-only notification. No worker log/message is read here."""
    body = message(bundle, status, kind)
    store.db.execute('''INSERT OR IGNORE INTO operator_outbox(id,job,kind,body,created,due)
        VALUES (?,?,?,?,?,?)''', (digest((bundle['job_id'], kind, key)), bundle['job_id'], kind, body, now, now))


def sync(store: Store, spool: Path, now: float) -> int:
    """Read at most 100 known status documents/scan; round-robin avoids starvation."""
    check_spool(spool)
    after = store.get('repair_status_cursor', '')
    rows = store.db.execute('SELECT id,bundle FROM repair_jobs WHERE id>? ORDER BY id LIMIT 100', (after,)).fetchall()
    processed = 0
    with store.db:
        store.db.execute("UPDATE operator_outbox SET state='UNCERTAIN',error='INTERRUPTED_ATTEMPT' WHERE state='ATTEMPTING'")
        for row in rows:
            bundle = json.loads(row['bundle'])
            try:
                status = validate_status(read_json(spool / 'status' / (row['id'] + '.json')), bundle)
            except (OSError, ValueError, TypeError, KeyError, RecursionError):
                continue
            if status['heartbeat_at'] > now + 60:
                continue
            old = store.db.execute('SELECT * FROM operator_jobs WHERE id=?', (row['id'],)).fetchone()
            if old and (old['state'] in TERMINAL or status['sequence'] < old['sequence']):
                continue
            previous = json.loads(old['status']) if old else None
            if previous and (status['started_at'] != previous['started_at']
                    or status['heartbeat_at'] < previous['heartbeat_at']
                    or (status['sequence'] == old['sequence'] and status != previous)):
                continue
            last_notice = old['last_notice'] if old else status['started_at']
            stall_generation = old['stall_generation'] if old else 0
            # STARTED survives a complete job between two monitor scans.
            notice(store, bundle, {**status, 'outcome': '', 'changed_files': 0, 'elapsed_seconds': 0}, 'STARTED', 0, now)
            state = status['state']
            if state not in TERMINAL and now - status['heartbeat_at'] > 180:
                state = 'STALLED'
                if not old or old['state'] != 'STALLED':
                    stall_generation += 1
                    notice(store, bundle, status, state, stall_generation, now)
            elif state in TERMINAL:
                notice(store, bundle, status, state, 0, now)
            elif state == 'RUNNING' and now - status['started_at'] >= 600 and now - last_notice >= 600:
                notice(store, bundle, status, 'RUNNING', status['sequence'], now)
                last_notice = now
            store.db.execute('''INSERT INTO operator_jobs VALUES (?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET state=excluded.state,sequence=excluded.sequence,
                status=excluded.status,last_notice=excluded.last_notice,stall_generation=excluded.stall_generation''',
                (row['id'], state, status['sequence'], json.dumps(status, sort_keys=True), last_notice, stall_generation))
            processed += 1
        store.put('repair_status_cursor', rows[-1]['id'] if len(rows) == 100 else '')
    return processed


def hourly_attempts(store: Store, now: float) -> int:
    """One shared 20/hour budget for both independent delivery ledgers."""
    return sum(store.db.execute(f'SELECT count(*) FROM {table} WHERE started>?', (now - 3600,)).fetchone()[0]
               for table in ('attempts', 'operator_attempts'))


def dispatch(store: Store, config: SenderConfig, transport: Transport, now: float, *,
             scan_remaining: int = 5, deadline: float | None = None) -> int:
    """Receipt-backed replay suppression; uncertain sends are held, never retried.

    Telegram cannot guarantee network exactly-once. Holding uncertain attempts is
    intentional: it trades a potentially missing notification for no duplicate.
    """
    config.validate()
    budget = max(0, min(scan_remaining, 5, 20 - hourly_attempts(store, now)))
    state = store.get('operator_delivery', {})
    incident_state = store.get('delivery', {})
    if (not budget or state.get('permanent') or state.get('next', 0) > now
            or incident_state.get('permanent') or incident_state.get('next', 0) > now):
        return 0
    rows = store.db.execute('''SELECT * FROM operator_outbox WHERE state='PENDING' AND due<=?
        AND attempts<5 ORDER BY created,rowid LIMIT ?''', (now, budget)).fetchall()
    if not rows or (store.root / 'DISABLED').exists():
        return 0
    try:
        transport.validate()
    except DeliveryError as failure:
        with store.db:
            store.put('operator_delivery', {'permanent': failure.permanent, 'next': now + max(300, failure.retry_after)})
        return 0
    sent = 0
    for row in rows:
        if (store.root / 'DISABLED').exists() or (deadline is not None and time.monotonic() > deadline - 4):
            break
        with store.db:
            attempt = store.db.execute("INSERT INTO operator_attempts(outbox,started,result) VALUES (?,?,'ATTEMPTED')",
                                       (row['id'], now)).lastrowid
            store.db.execute("UPDATE operator_outbox SET state='ATTEMPTING',attempts=attempts+1 WHERE id=?", (row['id'],))
        try:
            receipt = transport.send(row['body'])
            chat = receipt.get('chat') or {}
            if (chat.get('id') != config.private_chat_id or chat.get('type') != 'private'
                    or type(receipt.get('message_id')) is not int or receipt['message_id'] <= 0):
                raise DeliveryError('INVALID_RECEIPT', uncertain=True, permanent=True)
            safe = {'chat_id': config.private_chat_id, 'message_id': receipt['message_id'], 'acknowledged_at': now}
            with store.db:
                store.db.execute("UPDATE operator_outbox SET state='SENT',receipt=? WHERE id=?", (json.dumps(safe), row['id']))
                store.db.execute("UPDATE operator_attempts SET result='RECEIPT_PERSISTED' WHERE id=?", (attempt,))
                store.put('operator_delivery', {'permanent': False, 'next': 0})
            sent += 1
        except DeliveryError as failure:
            outcome = ('UNCERTAIN' if failure.uncertain else 'PERMANENT' if failure.permanent else
                       'EXHAUSTED' if row['attempts'] >= 4 else 'PENDING')
            due = now + max(failure.retry_after, min(1800, 30 * 2**row['attempts']))
            with store.db:
                store.db.execute('UPDATE operator_outbox SET state=?,due=?,error=? WHERE id=?',
                                 (outcome, due, failure.code, row['id']))
                store.db.execute('UPDATE operator_attempts SET result=? WHERE id=?', (failure.code, attempt))
                store.put('operator_delivery', {'permanent': failure.permanent, 'next': due})
            break
    return sent
