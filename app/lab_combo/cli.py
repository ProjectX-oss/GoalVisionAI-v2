"""Explicit bounded Lab cycle, suitable for a separately installed VPS timer."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from app.database import Database
from app.current_odds_forward_test.discovery import discover_current_fixture
from app.current_odds_forward_test.input import parse_current_odds
from app.current_odds_forward_test.repository import SQLiteForwardTestRepository
from app.current_odds_forward_test.service import ForwardTestService
from app.current_odds_forward_test.workflow import _analysis_input
from app.football.client import FootballClient
from app.model_activation_audit import resolve_active_reviewed_source_provenance
from app.real_match_lab_analysis.factory import build_real_match_lab_analysis_service
from app.real_match_lab_analysis.input import parse_input
from app.real_match_lab_analysis.fingerprint import canonical_json

from .repository import ComboRepository
from .service import LabComboService


def initialize(source: Path, target: Path) -> None:
    """Copy an explicitly selected model database using SQLite's consistent backup."""
    root = (Path.cwd() / 'var/lab_combo').resolve()
    if root not in target.resolve().parents or source.resolve() == target.resolve():
        raise ValueError('Analysis copy must be beneath var/lab_combo/')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb'):
        pass
    source_connection = sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)
    destination = sqlite3.connect(target)
    try:
        source_connection.backup(destination)
    finally:
        destination.close()
        source_connection.close()


async def cycle(args: argparse.Namespace) -> dict:
    """Discover once or check results once; external retries remain hard bounded."""
    root = (Path.cwd() / 'var/lab_combo').resolve()
    if root not in args.database.resolve().parents or not args.database.is_file():
        raise ValueError('Initialize a dedicated Lab analysis copy first')
    if args.database.resolve() == args.ledger.resolve():
        raise ValueError('Analysis database and combo ledger must differ')
    database = Database(args.database)
    ledger = ComboRepository(args.ledger)
    client = FootballClient(request_limit=40 if args.command == 'discover' else 21)
    client.restrict_requests(40 if args.command == 'discover' else 21)
    output: dict = {'real_combo_found': False, 'lab_telegram_sent': False}
    stage = 'INITIALIZE'
    try:
        singles = SQLiteForwardTestRepository(database)
        service = LabComboService(ledger, singles)
        if args.command == 'settle':
            stage = 'SETTLEMENT'
            if any(not ledger.get('settlement', value['prediction_id']) for value in ledger.all('prediction')):
                await client.account_status()
            output.update(await service.check_results(client))
            pending = [value['prediction_id'] for value in ledger.all('settlement')
                       if ledger.get('receipt', 'prediction:' + value['prediction_id'])
                       and not ledger.get('claim', 'settlement:' + value['prediction_id'])]
        else:
            now = datetime.now(timezone.utc)
            stage = 'DISCOVERY'
            discovery = await discover_current_fixture(client, now=now, maximum_fixtures=50,
                                                       capability_cache_path=Path('var/lab_combo/capabilities.json'))
            output['discovery'] = discovery
            observations, failures = [], {}
            source_commit = None
            if discovery.get('selected_fixtures'):
                stage = 'REVIEW_PROVENANCE'
                source_commit = resolve_active_reviewed_source_provenance(
                    database, 'OFFICIAL_GLOBAL'
                ).source_commit
            analyzer = build_real_match_lab_analysis_service(database)
            forward = ForwardTestService(singles)
            for fixture in discovery.get('selected_fixtures', []):
                identity = str(fixture['provider_fixture_id'])
                try:
                    stage = 'VALIDATE_ODDS'
                    clock = datetime.now(timezone.utc)
                    odds = parse_current_odds(fixture['odds_contract'], now=clock)
                    stage = 'CAPTURE_ODDS'
                    forward.capture_odds(odds)
                    raw = _analysis_input(
                        'combo-' + odds.snapshot_id,
                        fixture,
                        odds,
                        source_commit=source_commit,
                    )
                    raw['operator_notes'] = 'Bounded Lab Combo analysis; existing single-market gates apply.'
                    stage = 'ANALYZE'
                    analysis = analyzer.analyze(parse_input(raw, now=clock))
                    stage = 'CREATE_OBSERVATION'
                    observation = forward.create_observation('combo-' + analysis.analysis_id, analysis.analysis_id, odds.snapshot_id)
                    observations.append(observation.observation_id)
                    if observation.actionable:
                        from app.prediction_explainability.service import PredictionExplainabilityService
                        stage = 'EXPLAINABILITY'
                        PredictionExplainabilityService(database).create_for_analysis(analysis.analysis_id,
                            observation_id=observation.observation_id, created_at_utc=clock.isoformat())
                except (ValueError, KeyError) as exc:
                    failures[identity] = type(exc).__name__
            if observations:
                from app.forward_test_governance.service import GovernanceService
                stage = 'GOVERNANCE'
                GovernanceService(database).evaluate(datetime.now(timezone.utc).isoformat())
            stage = 'PREPARE_COMBO'
            prepared = service.prepare(observations)
            output.update(prepared)
            output['analysis_failures'] = failures
            combo = prepared['combo']
            output['real_combo_found'] = combo is not None
            pending = [combo['prediction_id']] if combo else [
                value['prediction_id'] for value in ledger.all('prediction')
                if not ledger.get('claim', 'prediction:' + value['prediction_id'])]
        stage = 'LAB_DELIVERY'
        if args.send and pending:
            from app.lab_telegram.service import load_lab_telegram_config, validate_lab_telegram_config
            from app.services.telegram_service import TelegramService
            config = load_lab_telegram_config()
            if validate_lab_telegram_config(config) is None:
                transport = TelegramService(config.token)
                async with transport.bot:
                    from app.real_match_lab_analysis.models import LAB_BOT_USERNAME
                    if '@' + (transport.bot.username or '') != LAB_BOT_USERNAME:
                        output['send_blocker'] = 'LAB_BOT_IDENTITY_MISMATCH'
                    else:
                        # One purposeful publication per invocation, including recovery.
                        for identity in pending:
                            result = await service.publish(identity, config, transport, settlement=args.command == 'settle')
                            output['delivery'] = result
                            if result['sent']:
                                output['lab_telegram_sent'] = True
                                break
            else:
                output['send_blocker'] = 'LAB_CREDENTIAL_NOT_CONFIGURED'
        return output
    except Exception as exc:
        # Never serialize provider/Telegram exceptions: they may contain credentials.
        output['terminal_error'] = type(exc).__name__
        output['terminal_stage'] = stage
        if isinstance(exc, sqlite3.IntegrityError):
            output['sqlite_constraint'] = {
                sqlite3.SQLITE_CONSTRAINT_NOTNULL: 'SQLITE_CONSTRAINT_NOTNULL',
                sqlite3.SQLITE_CONSTRAINT_UNIQUE: 'SQLITE_CONSTRAINT_UNIQUE',
                sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY: 'SQLITE_CONSTRAINT_PRIMARYKEY',
                sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY: 'SQLITE_CONSTRAINT_FOREIGNKEY',
            }.get(getattr(exc, 'sqlite_errorcode', None), 'SQLITE_CONSTRAINT')
            # Only this known schema message is safe to retain verbatim.
            known = 'NOT NULL constraint failed: forward_test_governance_scope_statuses.scope_value'
            if str(exc) == known:
                output['sqlite_message'] = known
        return output
    finally:
        output['api_calls_consumed'] = client.request_count
        ledger.append('run', datetime.now(timezone.utc).isoformat(), output)
        await client.close()
        ledger.close()
        database.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('initialize', 'discover', 'settle'))
    parser.add_argument('--database', type=Path, default=Path('var/lab_combo/analysis.db'))
    parser.add_argument('--ledger', type=Path, default=Path('var/lab_combo/ledger.db'))
    parser.add_argument('--source-database', type=Path)
    parser.add_argument('--send', action='store_true', help='Explicit Lab-only send; maximum one message')
    args = parser.parse_args(argv)
    if args.command == 'initialize':
        if args.source_database is None:
            parser.error('--source-database is required for initialization')
        initialize(args.source_database, args.database)
        print('Dedicated Lab analysis copy initialized.')
        return 0
    # Serialize complete cycles across local processes, without a duplicate scheduler.
    import fcntl
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    with args.ledger.with_suffix('.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('{"status":"LAB_COMBO_CYCLE_ALREADY_RUNNING"}')
            return 0
        value = asyncio.run(cycle(args))
    print(canonical_json(value))
    return 1 if value.get('terminal_error') else 0
