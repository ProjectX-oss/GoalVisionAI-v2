"""Fixed private bot, durable claims, validated receipts and no ambiguous retries."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from time import monotonic
import json
import re
from typing import Mapping, Protocol
from urllib.request import Request, urlopen

from .contracts import digest, fresh, integer
from .presentation import prediction, result
from .store import Store

LAB_CHAT = '-1003510920417'
CONFIRM = 'SEND_LIVE_TO_FIXED_PRIVATE_CHAT'


@dataclass(frozen=True)
class PrivateConfig:
    token: str = field(repr=False)
    chat_id: str = ''
    expected_username: str = ''
    expected_bot_id: str = ''
    contract: str = 'PRIVATE'
    started: bool = False
    enabled: bool = False

    @classmethod
    def from_environment(cls, env: Mapping[str, str]) -> 'PrivateConfig':
        return cls(env.get('LIVE_BOT_TOKEN', ''), env.get('LIVE_PRIVATE_CHAT_ID', ''),
                   env.get('LIVE_EXPECTED_BOT_USERNAME', '').removeprefix('@'),
                   env.get('LIVE_EXPECTED_BOT_ID', ''), env.get('LIVE_DESTINATION_CONTRACT', 'PRIVATE'),
                   env.get('LIVE_USER_STARTED_BOT') == 'true', env.get('LIVE_SEND_ENABLED') == 'true')

    def check(self) -> dict:
        """Safe offline configuration check; no identities/tokens echoed."""
        checks = {'token_configured': bool(re.fullmatch(r'\d+:[A-Za-z0-9_-]+', self.token)),
                  'private_chat_configured': self.chat_id.isdigit() and int(self.chat_id or '0') > 0,
                  'expected_identity_configured': bool(re.fullmatch(r'[A-Za-z0-9_]+bot', self.expected_username, re.I))
                      and self.expected_bot_id.isdigit() and int(self.expected_bot_id or '0') > 0,
                  'not_prematch_lab': self.chat_id != LAB_CHAT,
                  'private_contract': self.contract == 'PRIVATE', 'user_started_bot': self.started}
        return {'status': 'CONFIGURED' if all(checks.values()) else 'PRIVATE_CONFIG_BLOCKED',
                'checks': checks, 'sending_enabled': self.enabled, 'network_calls': 0}


class PrivateTransport(Protocol):
    def identity(self) -> dict: ...
    def send(self, chat_id: str, text: str) -> dict: ...


class TelegramHTTP:
    """Real direct-private transport. Construct only after separately enabled send gates."""
    def __init__(self, config: PrivateConfig) -> None:
        if config.check()['status'] != 'CONFIGURED' or not config.enabled:
            raise ValueError('PRIVATE_SEND_DISABLED')
        self.config = config

    def _request(self, method: str, value: dict) -> dict:
        request = Request(f'https://api.telegram.org/bot{self.config.token}/{method}',
                          data=json.dumps(value).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=10) as response:
                return json.loads(response.read(100000))
        except Exception:
            raise RuntimeError('TELEGRAM_TRANSPORT_UNKNOWN') from None

    def identity(self) -> dict:
        return self._request('getMe', {})

    def send(self, chat_id: str, text: str) -> dict:
        if chat_id != self.config.chat_id:
            raise ValueError('FIXED_PRIVATE_DESTINATION_REQUIRED')
        return self._request('sendMessage', {'chat_id': chat_id, 'text': text,
                                            'link_preview_options': {'is_disabled': True}})


def preview(store: Store, candidate_id: str, config: PrivateConfig, now: datetime) -> str:
    """Freeze exact message bytes and destination from configuration, not candidate data."""
    candidate = store.get('candidate', candidate_id)
    if not candidate or not candidate.get('qualified') or config.check()['status'] != 'CONFIGURED':
        raise ValueError('PRIVATE_PREVIEW_BLOCKED')
    key = candidate['economic_key']
    document = {'economic_key': key, 'candidate_id': candidate_id, 'text': prediction(candidate),
                'chat_id': config.chat_id, 'bot_id': config.expected_bot_id,
                'bot_username': config.expected_username, 'at': now.isoformat(), 'kind': 'prediction'}
    store.append('preview', key, document, now, ('candidate', candidate_id))
    return key


def result_preview(store: Store, key: str, config: PrivateConfig, now: datetime) -> str:
    settlement = store.get('settlement', key)
    statistics = store.get('statistics', key)
    if not settlement or not statistics or config.check()['status'] != 'CONFIGURED':
        raise ValueError('RESULT_PREVIEW_BLOCKED')
    result_key = 'result:'+key
    document = {'economic_key': result_key, 'text': result(settlement, statistics), 'chat_id': config.chat_id,
                'bot_id': config.expected_bot_id, 'bot_username': config.expected_username,
                'at': now.isoformat(), 'kind': 'result', 'settlement_id': key}
    store.append('preview', result_key, document, now, ('settlement', key))
    return result_key


def valid_ack(ack: dict, config: PrivateConfig, text: str) -> bool:
    result = ack.get('result', {})
    return (ack.get('ok') is True and integer(result.get('message_id'), 1)
            and str(result.get('chat', {}).get('id')) == config.chat_id
            and result.get('chat', {}).get('type') == 'private'
            and str(result.get('from', {}).get('id')) == config.expected_bot_id
            and result.get('from', {}).get('is_bot') is True
            and result.get('from', {}).get('username', '').lower() == config.expected_username.lower()
            and result.get('text') == text)


def deliver(store: Store, key: str, config: PrivateConfig, transport: PrivateTransport,
            *, confirmation: str, now: datetime) -> str:
    """Claim before send. A claim without a receipt always requires manual reconciliation."""
    if confirmation != CONFIRM or not config.enabled or config.check()['status'] != 'CONFIGURED':
        raise ValueError('PRIVATE_SEND_DISABLED')
    document = store.get('preview', key)
    if not document or (document['chat_id'], document['bot_id'], document['bot_username']) != (
        config.chat_id, config.expected_bot_id, config.expected_username):
        raise ValueError('PRIVATE_PREVIEW_DESTINATION_MISMATCH')
    if store.get('claim', key):
        return 'ALREADY_CLAIMED_NO_RESEND'
    if document['kind'] == 'prediction':
        candidate = store.get('candidate', document['candidate_id'])
        if not fresh(candidate['state']['retrieved_at'], now, 30) or not fresh(
            candidate['market']['quote']['provider_at'], now, 30):
            raise ValueError('STALE_PRIVATE_PREVIEW')
    started = monotonic()
    try:
        identity = transport.identity()
        bot = identity.get('result', {})
        if (identity.get('ok') is not True or bot.get('is_bot') is not True
            or str(bot.get('id')) != config.expected_bot_id
            or bot.get('username', '').lower() != config.expected_username.lower()):
            raise ValueError
    except Exception:
        raise ValueError('PRIVATE_BOT_IDENTITY_UNVERIFIED') from None
    effective_now = now + timedelta(seconds=monotonic()-started)
    if document['kind'] == 'prediction' and not fresh(candidate['state']['retrieved_at'], effective_now, 30):
        raise ValueError('STALE_PRIVATE_PREVIEW')
    with store.transaction():
        if store.get('claim', key):
            return 'ALREADY_CLAIMED_NO_RESEND'
        store.append('claim', key, {'economic_key': key, 'preview_fingerprint': digest(document),
                                  'at': now.isoformat()}, now, ('preview', key))
    try:
        ack = transport.send(config.chat_id, document['text'])
        if not valid_ack(ack, config, document['text']):
            raise ValueError
        store.append('receipt', key, {'economic_key': key, 'message_id': ack['result']['message_id'],
                     'chat_id': config.chat_id, 'bot_id': config.expected_bot_id,
                     'text_fingerprint': digest(document['text']), 'at': now.isoformat()}, now, ('claim', key))
        return 'DELIVERED'
    except Exception:
        # If persistence fails too, the pre-transport claim still blocks every resend.
        store.append('delivery_unknown', key, {'economic_key': key, 'status': 'MANUAL_RECONCILIATION_REQUIRED'},
                     now, ('claim', key))
        return 'DELIVERY_UNKNOWN_NO_RESEND'


def reconcile(store: Store, key: str, ack: dict, config: PrivateConfig, *,
              operator_reference: str, now: datetime) -> None:
    """Record externally verified acknowledgement; never resend or release a claim."""
    document = store.get('preview', key)
    if (not operator_reference or not store.get('claim', key) or not document
        or (document['chat_id'], document['bot_id'], document['bot_username']) != (
            config.chat_id, config.expected_bot_id, config.expected_username)
        or not valid_ack(ack, config, document['text'])):
        raise ValueError('RECONCILIATION_PROOF_REQUIRED')
    store.append('receipt', key, {'economic_key': key, 'message_id': ack['result']['message_id'],
                 'chat_id': config.chat_id, 'bot_id': config.expected_bot_id,
                 'text_fingerprint': digest(document['text']), 'at': now.isoformat(),
                 'operator_reference': operator_reference}, now, ('claim', key))
