"""Small bounded HTTP client with receipts and aggressive secret redaction."""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Mapping

from .fingerprint import sha256_fingerprint
from .provider_models import ProviderQuotaSnapshot, ProviderResponseReceipt


TRANSIENT_STATUS_CODES = frozenset({408, 425, 500, 502, 503, 504})
SECRET_PATTERN = re.compile(r"(?i)(authorization|api[_-]?key|token|secret)(\s*[:=]\s*)([^\s&,]+)")
BEARER_PATTERN = re.compile(r"(?i)bearer\s+[^\s,]+")


class ProviderHttpError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class ProviderHttpResponse:
    payload: object
    receipt: ProviderResponseReceipt


def redact_provider_text(value: object, secrets: tuple[str, ...] = ()) -> str:
    text = str(value)
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    text = BEARER_PATTERN.sub("Bearer [REDACTED]", text)
    return SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", text)


class BoundedJsonHttpClient:
    """GET-only JSON client; it never retries auth, quota, or other 4xx failures."""

    def __init__(
        self, *, base_url: str, secret: str, timeout_seconds: float = 10.0,
        max_retries: int = 2, opener: Callable[..., object] = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout_seconds <= 0 or max_retries < 0 or max_retries > 2:
            raise ValueError("Provider HTTP bounds are invalid")
        self.base_url = base_url.rstrip("/")
        self.secret = secret
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._opener = opener
        self._sleeper = sleeper
        self._request_count = 0
        self.receipts: list[ProviderResponseReceipt] = []

    @property
    def request_count(self) -> int:
        return self._request_count

    def get(self, path: str, params: Mapping[str, object] | None = None) -> ProviderHttpResponse:
        query = urllib.parse.urlencode(sorted((key, str(value)) for key, value in (params or {}).items()))
        url = f"{self.base_url}/{path.lstrip('/')}" + (f"?{query}" if query else "")
        endpoint = redact_provider_text("/" + path.lstrip("/") + (f"?{query}" if query else ""), (self.secret,))
        for attempt in range(self.max_retries + 1):
            self._request_count += 1
            request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.secret}", "Accept": "application/json"})
            try:
                response = self._opener(request, timeout=self.timeout_seconds)
                body = response.read()
                status = int(getattr(response, "status", 200))
                headers = getattr(response, "headers", {})
            except urllib.error.HTTPError as exc:
                status = int(exc.code)
                if status in TRANSIENT_STATUS_CODES and attempt < self.max_retries:
                    self._sleeper(float(2 ** attempt)); continue
                raise ProviderHttpError(status, redact_provider_text(f"provider request failed ({status})", (self.secret,))) from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt < self.max_retries:
                    self._sleeper(float(2 ** attempt)); continue
                raise ProviderHttpError(0, redact_provider_text(f"provider transport failed: {exc}", (self.secret,))) from None
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ProviderHttpError(status, "provider returned incompatible JSON") from None
            quota = _quota(headers)
            receipt_data = {
                "request_number": self._request_count, "method": "GET", "sanitized_endpoint": endpoint,
                "status_code": status, "response_sha256": hashlib.sha256(body).hexdigest(),
                "byte_count": len(body), "quota": quota,
            }
            receipt = ProviderResponseReceipt(**receipt_data, receipt_fingerprint=sha256_fingerprint(receipt_data))
            self.receipts.append(receipt)
            return ProviderHttpResponse(payload, receipt)
        raise AssertionError("unreachable")


def _header(headers: object, *names: str) -> str | None:
    for name in names:
        value = headers.get(name) if hasattr(headers, "get") else None
        if value not in (None, ""):
            return str(value)
    return None


def _integer(value: str | None) -> int | None:
    try: return int(value) if value is not None else None
    except ValueError: return None


def _quota(headers: object) -> ProviderQuotaSnapshot:
    raw = {
        "remaining": _integer(_header(headers, "X-RateLimit-Remaining", "X-Requests-Remaining")),
        "used": _integer(_header(headers, "X-RateLimit-Used", "X-Requests-Used")),
        "limit": _integer(_header(headers, "X-RateLimit-Limit", "X-Requests-Limit")),
        "retry_after_seconds": _integer(_header(headers, "Retry-After")),
    }
    return ProviderQuotaSnapshot(**raw, fingerprint=sha256_fingerprint(raw))
