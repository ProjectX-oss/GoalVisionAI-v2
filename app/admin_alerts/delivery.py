"""Fixed private ADMIN delivery. No getUpdates, webhook, or PREMATCH resend API."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import time
from typing import Protocol
import urllib.error
import urllib.request

from .model import digest
from .store import Store


@dataclass(frozen=True)
class SenderConfig:
    """Explicit dedicated ADMIN identity, destination and operator /start attestation."""
    enabled: bool = False
    token_file: str = ''
    bot_id: int = 0
    bot_username: str = ''
    private_chat_id: int = 0
    operator_confirmed_start: bool = False

    def validate(self) -> None:
        if (not self.enabled or not self.operator_confirmed_start or self.bot_id <= 0 or
                self.private_chat_id <= 0 or not re.fullmatch(r'[A-Za-z0-9_]{5,64}', self.bot_username)):
            raise DeliveryError('CONFIGURATION_REQUIRED', permanent=True)


class DeliveryError(Exception):
    """Fixed machine code only; never include remote exception/response text."""
    def __init__(self, code: str, *, permanent: bool = False, retry_after: int = 0,
                 uncertain: bool = False) -> None:
        self.code, self.permanent, self.retry_after, self.uncertain = code, permanent, retry_after, uncertain
        super().__init__(code)


class Transport(Protocol):
    def validate(self) -> None: ...
    def send(self, text: str) -> dict: ...


class Telegram:
    """Standard-library transport mirrors existing validated receipt semantics.

    The general Telegram helper cannot pin bot identity or private-chat type and
    imports an installed dependency; this standalone adapter needs neither.
    """
    def __init__(self, config: SenderConfig) -> None:
        config.validate()
        self.config = config
        path = Path(config.token_file)
        if not path.is_file() or path.stat().st_mode & 0o077:
            raise DeliveryError('SECRET_FILE_PERMISSIONS', permanent=True)
        token = path.read_text().strip()
        if not re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,100}', token):
            raise DeliveryError('TOKEN_INVALID', permanent=True)
        self._token = token

    def _call(self, method: str, values: dict) -> dict:
        request = urllib.request.Request('https://api.telegram.org/bot' + self._token + '/' + method,
            data=json.dumps(values).encode(), headers={'Content-Type': 'application/json'}, method='POST')
        try:
            # Reject redirects so credentials cannot be forwarded to another origin.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req: object, fp: object, code: int, msg: str,
                                     headers: object, newurl: str) -> None:
                    return None
            opener = urllib.request.build_opener(NoRedirect())
            with opener.open(request, timeout=3) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                raise DeliveryError('RESPONSE_OVERSIZED', uncertain=method == 'sendMessage')
            result = json.loads(raw)
        except urllib.error.HTTPError as error:
            retry = 0
            if error.code == 429:
                try:
                    retry = int(json.loads(error.read(4096)).get('parameters', {}).get('retry_after', 0))
                except (ValueError, TypeError):
                    retry = 60
            raise DeliveryError('RATE_LIMIT' if error.code == 429 else 'HTTP_REJECTED',
                permanent=error.code in (400, 401, 403, 404) or 300 <= error.code < 400,
                retry_after=max(0, min(retry, 86400)), uncertain=error.code >= 500 and method == 'sendMessage') from None
        except (OSError, ValueError, TimeoutError):
            raise DeliveryError('TRANSPORT_UNCERTAIN', uncertain=method == 'sendMessage') from None
        if not isinstance(result, dict) or result.get('ok') is not True:
            code = result.get('error_code') if isinstance(result, dict) else None
            retry = (result.get('parameters') or {}).get('retry_after', 0) if isinstance(result, dict) else 0
            raise DeliveryError('API_REJECTED', permanent=code in (400, 401, 403, 404),
                                retry_after=min(86400, max(0, retry)) if type(retry) is int else 0,
                                uncertain=method == 'sendMessage' and code is None)
        value = result.get('result')
        if not isinstance(value, dict):
            raise DeliveryError('INVALID_RECEIPT', uncertain=method == 'sendMessage')
        return value

    def validate(self) -> None:
        me = self._call('getMe', {})
        if me.get('id') != self.config.bot_id or me.get('username') != self.config.bot_username or me.get('is_bot') is not True:
            raise DeliveryError('BOT_IDENTITY_MISMATCH', permanent=True)
        chat = self._call('getChat', {'chat_id': self.config.private_chat_id})
        if chat.get('id') != self.config.private_chat_id or chat.get('type') != 'private':
            raise DeliveryError('PRIVATE_DESTINATION_MISMATCH', permanent=True)

    def send(self, text: str) -> dict:
        return self._call('sendMessage', {'chat_id': self.config.private_chat_id, 'text': text})


def dispatch(store: Store, config: SenderConfig, transport: Transport, now: float,
             *, deadline: float | None = None) -> int:
    """At most five sends/scan, twenty/hour; durable attempts precede transport."""
    config.validate()
    state = store.get('delivery', {})
    if state.get('permanent') or state.get('next', 0) > now:
        return 0
    used = store.db.execute('SELECT count(*) FROM attempts WHERE started>?', (now - 3600,)).fetchone()[0]
    budget = max(0, min(5, 20 - used))
    if not budget:
        return 0
    if not store.db.execute("SELECT 1 FROM outbox WHERE state IN ('PENDING','UNCERTAIN') AND due<=? AND attempts<5 LIMIT 1", (now,)).fetchone():
        return 0
    try:
        transport.validate()
    except DeliveryError as failure:
        with store.db:
            attempts = state.get('validation_attempts', 0) + 1
            store.put('delivery', {'code': failure.code, 'permanent': failure.permanent or attempts >= 5,
                                   'validation_attempts': attempts,
                                   'next': now + max(300, failure.retry_after)})
        return 0
    sent = 0
    for _ in range(budget):
        if deadline is not None and time.monotonic() > deadline - 4:
            break
        rows = store.db.execute('''SELECT o.* FROM outbox o JOIN incidents i ON i.id=o.incident
            WHERE o.state IN ('PENDING','UNCERTAIN') AND o.due<=? AND o.attempts<5
            ORDER BY i.severity DESC,o.created LIMIT 1000''', (now,)).fetchall()
        if not rows:
            break
        backlog = len(rows) > 5 or now - min(r['created'] for r in rows) > 1800
        batch = rows if backlog else rows[:1]
        batch_id = digest([r['id'] for r in batch])
        body = batch[0]['body'] if not backlog else ('🚨 GoalVision ADMIN • PREMATCH\n'
            f"Uzkrāto paziņojumu kopsavilkums: {len(batch)}.\n"
            'Pārbaudīt vietējo sanitizēto incidentu pārskatu.\n'
            'Incidenti: ' + ', '.join(r['incident'] for r in batch[:20]) +
            ('\nPārējie incidenti saglabāti ADMIN datubāzē.' if len(batch) > 20 else '') +
            '\nKopsavilkums: ' + batch_id)
        # Persist each retry's original outbox identity. A crash here leaves UNCERTAIN.
        with store.db:
            cursor = store.db.execute('INSERT INTO attempts(outbox,started,result) VALUES (?,?,?)',
                                      (batch[0]['id'], now, 'ATTEMPTED'))
            attempt_id = cursor.lastrowid
            for row in batch:
                store.db.execute("UPDATE outbox SET state='ATTEMPTING',attempts=attempts+1 WHERE id=?", (row['id'],))
        try:
            receipt = transport.send(body)
            chat = receipt.get('chat') or {}
            if (chat.get('id') != config.private_chat_id or chat.get('type') != 'private' or
                    type(receipt.get('message_id')) is not int or receipt['message_id'] <= 0):
                raise DeliveryError('INVALID_RECEIPT', permanent=True, uncertain=True)
            safe_receipt = {'chat_id': config.private_chat_id, 'message_id': receipt['message_id'],
                            'batch_id': batch_id, 'acknowledged_at': now}
            # If commit fails, ATTEMPTING remains on disk; next scan treats it as uncertain.
            with store.db:
                for row in batch:
                    store.db.execute("UPDATE outbox SET state='SENT',acknowledged=1,receipt=? WHERE id=?",
                                     (json.dumps(safe_receipt), row['id']))
                    store.db.execute('''UPDATE incidents SET last_sent=?,notified_state=CASE WHEN state='RECOVERED'
                        THEN 'RECOVERED' ELSE 'OPEN' END,state=CASE WHEN state='ESCALATED' THEN 'REPEATED' ELSE state END WHERE id=?''',
                        (now, row['incident']))
                store.db.execute("UPDATE attempts SET result='RECEIPT_PERSISTED' WHERE id=?", (attempt_id,))
                store.put('delivery', {'code': 'HEALTHY', 'next': 0, 'permanent': False})
            sent += 1
        except DeliveryError as failure:
            with store.db:
                for row in batch:
                    attempts = row['attempts'] + 1
                    status = 'PERMANENT' if failure.permanent else 'EXHAUSTED' if attempts >= 5 else 'UNCERTAIN' if failure.uncertain else 'PENDING'
                    store.db.execute('UPDATE outbox SET state=?,due=?,error=? WHERE id=?',
                        (status, now + max(failure.retry_after, min(1800, 30 * 2 ** (attempts - 1))), failure.code, row['id']))
                store.db.execute('UPDATE attempts SET result=? WHERE id=?', (failure.code, attempt_id))
                store.put('delivery', {'code': failure.code, 'permanent': failure.permanent,
                    'next': now + max(failure.retry_after, min(1800, 30 * 2 ** max(r['attempts'] for r in batch)))})
            break  # outage never drains a backlog in a burst
    return sent
