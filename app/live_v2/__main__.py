"""No-send operator CLI. Inspection never opens credentials or writable PREMATCH stores."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3

from .contracts import canonical
from .delivery import PrivateConfig
from .quota import Governor, budget, read_prematch
from .runner import Runner
from .settlement import statistics
from .store import Store

COMMANDS = ('status', 'quota', 'discover', 'fixtures', 'markets', 'candidates', 'settlements',
            'statistics', 'telegram-config-check')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Isolated V2 LIVE private foundation; Telegram transport disabled.')
    parser.add_argument('command', choices=COMMANDS)
    parser.add_argument('--store', type=Path, default=Path('var/live_v2/private.sqlite'))
    parser.add_argument('--prematch-audit', type=Path)
    parser.add_argument('--competitions', default='', help='Reviewed provider league IDs, comma separated')
    parser.add_argument('--real-api', action='store_true', help='Explicit bounded discovery; always no-send')
    parser.add_argument('--rehearsal', action='store_true', help='One bounded rehearsal outside the timer window')
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        mapping = json.loads(Path(__file__).with_name('markets.json').read_text())
        if args.command == 'telegram-config-check':
            print(canonical(PrivateConfig.from_environment(os.environ).check()))
            return 0
        if args.command == 'markets':
            print(canonical(mapping))
            return 0
        if args.command == 'quota':
            evidence = read_prematch(args.prematch_audit, now) if args.prematch_audit else {}
            if args.store.exists():
                store = Store(args.store, readonly=True)
                try:
                    report = Governor(store, lambda _: evidence).inspect('inspection', now)
                finally:
                    store.close()
            else:
                report = budget(evidence, now=now, daily_calls=0, slot_calls=0)
            print(canonical(report))
            return 0
        if args.command == 'discover':
            if not args.real_api:
                print(canonical({'status': 'OFFLINE_NO_TRANSPORT', 'api_calls': 0, 'telegram_sends': 0}))
                return 0
            if args.prematch_audit is None:
                raise ValueError('PREMATCH_EVIDENCE_REQUIRED')
            if args.store.resolve() == args.prematch_audit.resolve():
                raise ValueError('ISOLATED_LIVE_STORE_REQUIRED')
            competitions = frozenset(int(x) for x in args.competitions.split(',') if x)
            store = Store(args.store)
            try:
                governor = Governor(store, lambda clock: read_prematch(args.prematch_audit, clock))

                class LazyTransport:
                    def get(self, endpoint: str, query: dict) -> tuple[dict, dict]:
                        from app.football.configuration import resolve_api_football_credential
                        from .provider import FootballHTTP
                        # Resolve only after a durable safe permit; no automatic .env loading.
                        token = resolve_api_football_credential(environment=os.environ,
                                                               env_file=Path('/nonexistent/live-v2-env'))
                        return FootballHTTP(token).get(endpoint, query)

                report = Runner(store, governor, LazyTransport(), mapping, competitions).run(rehearsal=args.rehearsal)
                print(canonical(report))
            finally:
                store.close()
            return 0
        if not args.store.exists():
            print(canonical({'status': 'LIVE_STORE_NOT_INITIALIZED', 'sending': False, 'api_calls': 0}))
            return 0
        store = Store(args.store, readonly=True)
        try:
            if args.command == 'status':
                report = {'product': 'LIVE_V2_PRIVATE', 'sending': False, 'schema': 1,
                          'runs': len(store.all('run')), 'claims': len(store.all('claim')),
                          'unresolved_claims': sum(not store.get('receipt', c['economic_key']) for c in store.all('claim')),
                          'market_review': mapping['review_status']}
            elif args.command == 'statistics':
                report = statistics(store.all('settlement'))
            else:
                report = store.all({'fixtures': 'global_snapshot', 'candidates': 'candidate', 'settlements': 'settlement'}[args.command])
            print(canonical(report))
        finally:
            store.close()
        return 0
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError):
        # Never print exception payloads, paths containing credentials, or environment values.
        print(canonical({'status': 'LIVE_OPERATION_BLOCKED', 'api_attempt_count': 'INSPECT_DURABLE_LIVE_CLAIMS',
                         'details': 'Check reviewed inputs and isolated storage; no automatic retry.'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
