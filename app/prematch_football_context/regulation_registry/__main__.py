"""Explicit local manual CLI. No source discovery, scraping or automatic trust."""
import argparse
from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3

from ..fingerprint import canonical_bytes
from .contracts import decode
from .repository import Registry, initialize
from .service import resolve


def main(argv: list[str] | None = None) -> int:
    """Validate/import complete reviewed JSON, inspect, resolve, or verify offline."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('init', 'validate', 'import', 'inspect', 'resolve', 'verify'):
        command_parser = sub.add_parser(command)
        if command != 'validate':
            command_parser.add_argument('--db', type=Path, required=True)
        if command in ('validate', 'import'):
            command_parser.add_argument('record', type=Path)
        if command == 'inspect':
            command_parser.add_argument('--review-id', required=True)
        if command == 'resolve':
            command_parser.add_argument('--provider', required=True)
            command_parser.add_argument('--competition-id', type=int, required=True)
            command_parser.add_argument('--season', type=int, required=True)
            command_parser.add_argument('--cutoff', required=True)
    args = parser.parse_args(argv)
    try:
        output: object
        if args.command == 'init':
            initialize(args.db)
            output = {'status': 'INITIALIZED_EMPTY'}
        elif args.command in ('validate', 'import'):
            with args.record.open('rb') as source:
                document = source.read(32769)
            record = decode(document.decode('utf-8'))
            if args.command == 'import':
                with closing(Registry(args.db, writable=True)) as registry:
                    registry.append(record)
            output = record
        elif args.command == 'resolve':
            output = resolve(args.db, provider=args.provider, competition_id=args.competition_id,
                             season=args.season, cutoff=datetime.fromisoformat(args.cutoff.replace('Z', '+00:00')))
        else:
            with closing(Registry(args.db)) as registry:
                records = registry.verify()
                if args.command == 'inspect':
                    output = next((r for r in records if r.review_id == args.review_id), None)
                    if output is None:
                        raise ValueError('REVIEW_NOT_FOUND')
                else:
                    output = {'status': 'VERIFIED', 'records': len(records)}
        print(canonical_bytes(output).decode())
        return 0
    except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError):
        print('{"status":"REJECTED_INVALID_OR_UNAVAILABLE_EVIDENCE"}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
