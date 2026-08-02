"""Signed ephemeral sessions and CSRF protection without persistence."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Session:
    session_id: str
    operator_identifier: str
    issued_at: int
    expires_at: int
    csrf_nonce: str


class SessionSecurity:
    def __init__(self, secret: bytes, ttl_seconds: int = 3600, csrf_ttl_seconds: int = 1800) -> None:
        self.secret=secret; self.ttl=ttl_seconds; self.csrf_ttl=csrf_ttl_seconds

    def create(self, operator_identifier: str, now: int | None = None) -> tuple[Session,str]:
        current=int(now or time.time()); value=Session(secrets.token_hex(16),operator_identifier,current,current+self.ttl,secrets.token_hex(16)); return value,self._encode(value.__dict__ if hasattr(value,"__dict__") else {k:getattr(value,k) for k in value.__slots__})

    def load(self, cookie: str | None, now: int | None = None) -> Session | None:
        if not cookie:return None
        try:
            payload,signature=cookie.rsplit(".",1); expected=hmac.new(self.secret,payload.encode(),hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature,expected):return None
            raw=json.loads(base64.urlsafe_b64decode(payload+"==")); session=Session(**raw)
            return session if session.expires_at>=int(now or time.time()) else None
        except (ValueError,TypeError,KeyError,json.JSONDecodeError):return None

    def csrf_token(self, session: Session, action: str, now: int | None = None) -> str:
        bucket=int(now or time.time())//self.csrf_ttl; material=f"{session.session_id}:{session.csrf_nonce}:{action}:{bucket}"; return hmac.new(self.secret,material.encode(),hashlib.sha256).hexdigest()

    def verify_csrf(self, session: Session, action: str, token: str | None, now: int | None = None) -> bool:
        if not token:return False
        current=int(now or time.time())
        for moment in (current,current-self.csrf_ttl):
            if hmac.compare_digest(token,self.csrf_token(session,action,moment)):return True
        return False

    def cookie_header(self, value: str) -> str:
        return f"gv_console_session={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={self.ttl}"

    def _encode(self, raw) -> str:
        payload=base64.urlsafe_b64encode(json.dumps(raw,sort_keys=True,separators=(",",":")).encode()).decode().rstrip("="); signature=hmac.new(self.secret,payload.encode(),hashlib.sha256).hexdigest(); return payload+"."+signature
