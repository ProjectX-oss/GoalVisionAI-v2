"""Explicit bounded Lab cycle, suitable for a separately installed VPS timer."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from app.database import Database
from app.current_odds_forward_test.discovery import discover_current_fixture
from app.current_match_intelligence.policy import IntelligenceBudgetPolicy, IntelligenceFreshnessPolicy
from app.current_match_intelligence.provider import ApiFootballCurrentMatchProvider
from app.current_match_intelligence.repository import SQLiteCurrentMatchIntelligenceRepository
from app.current_match_intelligence.service import CurrentMatchIntelligenceService
from app.football.client import FootballClient
from app.real_match_lab_analysis.fingerprint import canonical_json

from .repository import ComboRepository
from .service import LabComboService
from .experimental import FINAL_REVIEW_START, POLICY_VERSION
from .presentation import LabTelegramTransport, ResultImagePaths


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
    adaptive=None
    if getattr(args,'adaptive_database',None):
        from app.adaptive_lab.repository import AuditRepository
        from app.adaptive_lab.quota import SharedQuota,CATEGORY
        adaptive=AuditRepository(args.adaptive_database)
        SharedQuota(adaptive).bind(client,lambda:datetime.now(timezone.utc),allow_status_preflight=True)
    stage = 'INITIALIZE'
    try:
        intelligence_repository = SQLiteCurrentMatchIntelligenceRepository(database)
        image_directory = getattr(args, 'result_image_directory', Path('app/lab_combo/assets/results'))
        service = LabComboService(
            ledger, None, result_images=ResultImagePaths.from_directory(image_directory),
        )
        if args.command == 'settle':
            stage = 'SETTLEMENT'
            shadow_pending=bool(adaptive and any(not adaptive.get('shadow_settlements',p['prediction_id'])
                              for p in adaptive.all('shadow_predictions','PREMATCH')))
            if _settlement_work_relevant(ledger, datetime.now(timezone.utc)) or shadow_pending:
                if adaptive:
                    token=CATEGORY.set('STATUS')
                    try: await client.account_status()
                    finally: CATEGORY.reset(token)
                else:
                    await client.account_status()
            if adaptive:
                token=CATEGORY.set('SETTLEMENT')
                try:
                    from app.adaptive_lab.coordinator import LearningCoordinator
                    from app.adaptive_lab.observer import settle_pending_shadow
                    output.update(await service.check_results(client,adaptive_learning=LearningCoordinator(adaptive)))
                    remaining=max(0,21-client.request_count)
                    if remaining and shadow_pending:
                        output['shadow']=await settle_pending_shadow(adaptive,client,now=datetime.now(timezone.utc),maximum_calls=min(5,remaining))
                finally: CATEGORY.reset(token)
            else:
                output.update(await service.check_results(client))
            pending = [
                *[('single_settlement', value['prediction_id']) for value in ledger.all('single_settlement')
                  if ledger.get('receipt', 'single_prediction:' + value['prediction_id'])
                  and not ledger.get('claim', 'single_settlement:' + value['prediction_id'])],
                *[('combo_settlement', value['prediction_id']) for value in ledger.all('settlement')
                  if ledger.get('receipt', 'combo_prediction:' + value['prediction_id'])
                  and not ledger.get('claim', 'combo_settlement:' + value['prediction_id'])],
            ]
        else:
            now = datetime.now(timezone.utc)
            await client.account_status()
            stage = 'DISCOVERY'
            discovery = await discover_current_fixture(
                client, now=now, maximum_fixtures=9, maximum_api_calls=40,
                capability_cache_path=Path('var/lab_combo/capabilities.json'),
                quota_already_verified=True, require_team_baseline=False,
            )
            output['discovery'] = discovery
            selected = discovery.get('selected_fixtures', [])
            targets = _recheck_fixture_ids(ledger, now)
            for fixture in selected:
                _seed_discovery_reuse(intelligence_repository, fixture)
                identity = int(fixture['provider_fixture_id'])
                if identity not in targets:
                    targets.append(identity)
                fixture.pop('_current_match_reuse', None)
            if discovery.get('selected_fixture'):
                discovery['selected_fixture'].pop('_current_match_reuse', None)
            snapshots, failures, enrichment = [], {}, []
            for identity in targets:
                try:
                    stage = 'CURRENT_MATCH_INTELLIGENCE'
                    evaluated_at = datetime.now(timezone.utc)
                    kickoff = _known_kickoff(ledger, selected, identity)
                    final_review = kickoff is not None and timedelta(0) < kickoff - evaluated_at <= FINAL_REVIEW_START
                    intelligence = CurrentMatchIntelligenceService(
                        intelligence_repository, ApiFootballCurrentMatchProvider(client),
                        budget=IntelligenceBudgetPolicy(
                            maximum_api_calls=40,
                            detailed_match_window=0,
                            maximum_enriched_fixtures=9,
                        ),
                    )
                    force_refresh = (frozenset({'fixture', 'lineup', 'injuries', 'odds'})
                                     if final_review else frozenset())
                    result = await intelligence.collect(
                        identity, evaluated_at=evaluated_at, force_refresh=force_refresh,
                    )
                    api_calls = result.api_calls_used
                    cache_hits = result.cache_hits
                    cache_misses = result.cache_misses
                    lineup_fresh = any(
                        item.signal == 'confirmed_lineups' and item.status.value == 'FRESH'
                        for item in result.snapshot.freshness
                    )
                    if final_review and lineup_fresh and client.request_count < 40:
                        detailed = CurrentMatchIntelligenceService(
                            intelligence_repository, ApiFootballCurrentMatchProvider(client),
                            budget=IntelligenceBudgetPolicy(
                                maximum_api_calls=40, detailed_match_window=3,
                                maximum_enriched_fixtures=9,
                            ),
                        )
                        detailed_result = await detailed.collect(
                            identity, evaluated_at=datetime.now(timezone.utc),
                        )
                        api_calls += detailed_result.api_calls_used
                        cache_hits += detailed_result.cache_hits
                        cache_misses += detailed_result.cache_misses
                        result = detailed_result
                    if 'INTELLIGENCE_REQUIRED_STAGE_BUDGET_INSUFFICIENT' in result.snapshot.blockers:
                        failures[str(identity)] = 'INTELLIGENCE_REQUIRED_STAGE_BUDGET_INSUFFICIENT'
                        continue
                    snapshots.append(result.snapshot)
                    enrichment.append({'fixture_id': str(identity), 'snapshot_id': result.snapshot.snapshot_id,
                                       'api_calls': api_calls, 'cache_hits': cache_hits,
                                       'cache_misses': cache_misses,
                                       'final_review_refresh': final_review,
                                       'refreshed_sources': sorted(force_refresh),
                                       'lineup': next(x.status.value for x in result.snapshot.freshness if x.signal == 'confirmed_lineups')})
                except (ValueError, KeyError, RuntimeError) as exc:
                    failures[str(identity)] = type(exc).__name__
                if client.request_count >= 40:
                    break
            stage = 'LAB_EXPERIMENTAL_SELECTION'
            prepared = service.prepare_experimental(snapshots)
            output.update(prepared)
            output['policy'] = POLICY_VERSION
            output['intelligence_enrichment'] = enrichment
            output['analysis_failures'] = failures
            output['real_combo_found'] = bool(prepared['combos'])
            pending = [
                *[('single_prediction', value['prediction_id']) for value in prepared['singles']],
                *[('combo_prediction', value['prediction_id']) for value in prepared['combos']],
            ]
        stage = 'LAB_DELIVERY'
        if args.send and pending:
            from app.lab_telegram.service import load_lab_telegram_config, validate_lab_telegram_config
            config = load_lab_telegram_config()
            if validate_lab_telegram_config(config) is None:
                from .secure_logging import install_lab_secret_redaction
                install_lab_secret_redaction(config.token)
                transport = LabTelegramTransport(config.token)
                async with transport.bot:
                    from app.real_match_lab_analysis.models import LAB_BOT_USERNAME
                    if '@' + (transport.bot.username or '') != LAB_BOT_USERNAME:
                        output['send_blocker'] = 'LAB_BOT_IDENTITY_MISMATCH'
                    else:
                        output['deliveries'] = []
                        for kind, identity in pending:
                            result = await service.publish_experimental(kind, identity, config, transport)
                            output['deliveries'].append({'kind': kind, 'prediction_id': identity, **result})
                            if result['sent']:
                                output['lab_telegram_sent'] = True
                        from .settlement import single_statistics, statistics
                        output['single_statistics'] = single_statistics(ledger)
                        output['combo_statistics'] = statistics(ledger, published_only=True)
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
        if adaptive is not None:
            adaptive.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('initialize', 'discover', 'settle'))
    parser.add_argument('--database', type=Path, default=Path('var/lab_combo/analysis.db'))
    parser.add_argument('--ledger', type=Path, default=Path('var/lab_combo/ledger.db'))
    parser.add_argument('--source-database', type=Path)
    parser.add_argument('--adaptive-database', type=Path)
    parser.add_argument('--result-image-directory', type=Path,
                        default=Path('app/lab_combo/assets/results'))
    parser.add_argument('--send', action='store_true', help='Explicit Lab-only sends for qualified immutable evidence')
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


def _seed_discovery_reuse(repository, fixture: dict) -> None:
    reuse = fixture.get('_current_match_reuse') or {}
    fixture_id = int(fixture['provider_fixture_id'])
    odds_retrieved = datetime.fromisoformat(fixture['api_retrieval_timestamp_utc'])
    fixture_retrieved = odds_retrieved
    freshness = IntelligenceFreshnessPolicy()
    if reuse.get('fixture'):
        repository.append_cache(provider='API-FOOTBALL', endpoint='/fixtures', query={'id': fixture_id},
                                retrieved_at=fixture_retrieved, expires_at=fixture_retrieved + freshness.fixture,
                                provider_timestamp=None, payload=reuse['fixture'])
    if reuse.get('odds'):
        provider_time = fixture.get('provider_update_timestamp_utc')
        repository.append_cache(provider='API-FOOTBALL', endpoint='/odds', query={'fixture': fixture_id},
                                retrieved_at=odds_retrieved, expires_at=odds_retrieved + freshness.odds,
                                provider_timestamp=datetime.fromisoformat(provider_time) if provider_time else None,
                                payload=reuse['odds'])


def _recheck_fixture_ids(ledger: ComboRepository, now: datetime) -> list[int]:
    latest = {}
    for watch in ledger.all('fixture_watch'):
        current = latest.get(watch['fixture_id'])
        if current is None or watch['evaluated_at_utc'] > current['evaluated_at_utc']:
            latest[watch['fixture_id']] = watch
    result = []
    for watch in latest.values():
        kickoff = datetime.fromisoformat(watch['kickoff_utc'])
        stage = watch.get('candidate_stage')
        revisit = stage in {'EARLY_CANDIDATE', 'FINAL_REVIEW_REQUIRED'} or (
            stage is None and watch['lineup_status'] != 'FRESH'
        )
        if now < kickoff <= now + timedelta(minutes=75) and revisit:
            result.append(int(watch['fixture_id']))
    return sorted(result, key=lambda fixture_id: (latest[str(fixture_id)]['kickoff_utc'], fixture_id))


def _known_kickoff(ledger: ComboRepository, selected: list[dict], fixture_id: int) -> datetime | None:
    for fixture in selected:
        if str(fixture.get('provider_fixture_id')) == str(fixture_id):
            value = fixture.get('kickoff_utc')
            if value:
                return datetime.fromisoformat(value)
    watches = [value for value in ledger.all('fixture_watch')
               if str(value['fixture_id']) == str(fixture_id)]
    if not watches:
        return None
    latest = max(watches, key=lambda value: value['evaluated_at_utc'])
    return datetime.fromisoformat(latest['kickoff_utc'])


def _settlement_work_relevant(ledger: ComboRepository, now: datetime) -> bool:
    from .experimental import SETTLEMENT_RELEVANCE_AFTER_KICKOFF
    singles = any(ledger.get('receipt', 'single_prediction:' + value['prediction_id'])
                  and not ledger.get('single_settlement', value['prediction_id'])
                  and now >= datetime.fromisoformat(value['kickoff_utc']) + SETTLEMENT_RELEVANCE_AFTER_KICKOFF
                  for value in ledger.all('single_prediction'))
    combos = any(ledger.get('receipt', 'combo_prediction:' + value['prediction_id'])
                 and not ledger.get('settlement', value['prediction_id'])
                 and now >= min(datetime.fromisoformat(leg['kickoff_utc']) for leg in value['legs']) + SETTLEMENT_RELEVANCE_AFTER_KICKOFF
                 for value in ledger.all('prediction'))
    return singles or combos
