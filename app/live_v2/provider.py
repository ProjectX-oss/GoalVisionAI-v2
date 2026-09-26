"""Bounded current-only HTTP; no retries, credential output, or import-time calls."""
from __future__ import annotations

import json
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import Request

from app.football.quota import FootballQuotaReport


class Transport(Protocol):
    def get(self, endpoint: str, query: dict) -> tuple[dict, dict]: ...


class FootballHTTP:
    """One invocation is exactly one HTTP attempt, with redirects disabled."""
    def __init__(self, token: str) -> None:
        self._token = token

    def get(self, endpoint: str, query: dict) -> tuple[dict, dict]:
        from urllib.request import HTTPRedirectHandler, build_opener

        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req: object, fp: object, code: int, msg: str,
                                 headers: object, newurl: str) -> None:
                return None

        if endpoint not in {'/fixtures', '/odds/live', '/odds/live/bets', '/fixtures/statistics',
                            '/fixtures/events', '/fixtures/lineups'}:
            raise ValueError('UNSUPPORTED_LIVE_ENDPOINT')
        request = Request('https://v3.football.api-sports.io'+endpoint+'?'+urlencode(query),
                          headers={'x-apisports-key': self._token})
        try:
            with build_opener(NoRedirect).open(request, timeout=10) as response:
                payload = json.loads(response.read(4_000_001))
                quota = FootballQuotaReport.from_headers(response.headers).as_dict()
            if payload.get('errors') or not isinstance(payload.get('response'), list):
                raise ValueError
            # Do not retain provider error text or request header echoes.
            return {'response': payload['response'], 'results': payload.get('results'),
                    'paging': payload.get('paging'), 'errors': []}, quota
        except Exception:
            raise RuntimeError('LIVE_PROVIDER_REQUEST_FAILED') from None
