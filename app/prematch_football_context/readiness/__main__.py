"""Explicit manual Test/Lab readiness commands; no scheduler or publication switch."""
import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys

from ..capture.schema import initialize as initialize_evidence
from ..snapshot.repository import initialize as initialize_snapshots
from ..fingerprint import canonical_bytes
from .composition import ProspectiveObservation
from .ledger import initialize as initialize_ledger
from .report import coverage


def initialize(root: Path) -> None:
    """Initialize only the three dedicated readiness stores under an explicit root."""
    root.mkdir(parents=True, exist_ok=True)
    initialize_evidence(root/'sources.db')
    initialize_snapshots(root/'snapshots.db')
    initialize_ledger(root/'attempts.db')


def main(argv: list[str] | None = None) -> int:
    """Run one existing no-send PREMATCH cycle only on the explicit cycle action."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Dedicated isolated Test/Lab directory; no production defaults')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    sub.add_parser('report')
    sub.add_parser('verify', help='Read-only report with complete offline snapshot reproduction')
    sub.add_parser('diagnostics', help='Read-only coverage and bounded capture/snapshot diagnostics')
    cycle = sub.add_parser('cycle')
    cycle.add_argument('--environment', required=True, choices=('TEST', 'LAB'))
    cycle.add_argument('--observe', required=True, action='store_true')
    cycle.add_argument('--max-calls', type=int, default=40)
    cycle.add_argument('--horizon-days', type=int, default=1)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.command == 'init':
        initialize(root)
        print('{"initialized":true,"observation_enabled":false}')
        return 0
    if args.command != 'cycle':
        report = coverage(root)
        print(canonical_bytes(report).decode())
        return int(report['readiness'] == 'CAPTURE_BLOCKED')
    if not 1 <= args.max_calls <= 400 or not 1 <= args.horizon_days <= 3:
        parser.error('bounded calls 1..400 and horizon 1..3 required')
    # Runtime imports and existing database constructors occur only for this action.
    from app.lab_v2_shadow.cli import _cycle
    from app.football.configuration import FootballCredentialError
    from app.lab_v2_shadow.quota import DAILY_SAFETY_RESERVE
    runtime = argparse.Namespace(shadow_database=root/'shadow.db', analysis_database=root/'analysis.db',
        adaptive_database=root/'adaptive.db', ledger=root/'lab-ledger.db', capability_cache=root/'var/capabilities.json',
        max_calls=args.max_calls, horizon_days=args.horizon_days, daily_reserve=DAILY_SAFETY_RESERVE, send=False)
    observation = ProspectiveObservation(root, environment=args.environment, clock=lambda: datetime.now(timezone.utc))
    completed = False
    credential_failure = False
    try:
        result = asyncio.run(_cycle(runtime, football_context=observation))
        completed = not bool(result.get('terminal_error'))
        # Exact existing cycle output. Readiness diagnostics never modify its document.
        from app.real_match_lab_analysis.fingerprint import canonical_json
        print(canonical_json(result))
        return int(not completed)
    except FootballCredentialError:
        credential_failure = True
        raise
    finally:
        print(canonical_bytes({'v2_readiness_diagnostics': observation.finish(
            completed=completed, credential_failure=credential_failure)}).decode(), file=sys.stderr)


if __name__ == '__main__':
    raise SystemExit(main())
