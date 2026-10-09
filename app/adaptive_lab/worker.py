"""Future operator-enabled automation entry point. Never invoked by imports or reports.

No unit files are installed by this module. All mutation commands require an explicit
LAB enable switch and a dedicated audit DB; --send is separate and Lab-locked.
"""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from .contracts import canonical
from .coordinator import LearningCoordinator
from .observations import ReadOnlyLedger
from .repository import AuditRepository


async def live_cycle(repo: AuditRepository, *, send: bool, clock=None) -> dict:
    """Evening Lab only. Collection/settlement never invokes ML or model switching."""
    from . import daypart
    from .quota import SharedQuota
    from app.football.client import FootballClient
    from app.football.quota import FootballQuotaError
    from app.live_lab.runner import LiveRunner, FINAL_REVIEW_RESERVED_ATTEMPTS
    from app.live_lab.service import LiveService
    clock=clock or (lambda:datetime.now(timezone.utc))
    if not daypart.enabled():
        return {'status':'LIVE_EVENING_MODE_REQUIRED','api_calls':0,'deliveries':[]}
    discover=daypart.live_window(clock())
    pending=[r for r in repo.all('live_publications','LIVE')
             if not repo.get('live_settlements',r['selection_id'])]
    shadow=[r for r in repo.all('shadow_predictions','LIVE')
            if not repo.get('shadow_settlements',r['prediction_id'])]
    results=[r for r in repo.all('live_settlements','LIVE')
             if not repo.get('live_result_claims',r['prediction_id'])]
    if not discover and not (pending or shadow or results):
        return {'status':'LIVE_IDLE_NO_PENDING_RESULTS','api_calls':0,'deliveries':[]}
    probability_band=daypart.probability_band_enabled()
    service=LiveService(repo,clock=clock,allow_provider_feed=daypart.feed_quotes_enabled(),
                        quote_age_diagnostic=daypart.quote_age_diagnostic_enabled(),
                        probability_band=probability_band)
    client=None
    runner=None
    scanned={'status':'LIVE_RESULTS_ONLY','candidates':[]}
    api_calls=0
    budget=None
    try:
        if discover or pending or shadow:
            client=FootballClient(request_limit=80)
            # The durable shared authorizer enforces the changing results reserve
            # on every attempt; a tiny local floor must not override that policy.
            client.restrict_requests(80,daily_reserve=20)
            quota=SharedQuota(repo)
            quota.bind(client,clock,allow_status_preflight=True,status_preflight_category='LIVE_SETTLEMENT')
            try:
                await quota.call('LIVE_SETTLEMENT',client.account_status)
                budget=daypart.live_budget(client.quota_snapshot(),clock(),consumed=client.request_count)
                if budget <= client.request_count:
                    raise FootballQuotaError('PROTECTED_QUOTA_RESERVE')
                client.restrict_requests(budget,daily_reserve=20)
                runner=LiveRunner(service,client,quota,clock=clock)
                await runner.settle()
                if discover and daypart.live_window(clock()):
                    # Hold attempts for one exact final fixture/events/odds refresh.
                    # The total budget, provider limits and settlement reserve are unchanged.
                    scanned=await runner.scan(request_ceiling=max(0,budget-FINAL_REVIEW_RESERVED_ATTEMPTS))
            except FootballQuotaError:
                scanned={'status':'LIVE_QUOTA_BOUNDED_STOP','candidates':[]}
            except Exception:
                scanned={'status':'LIVE_PROVIDER_REVIEW_UNAVAILABLE','candidates':[]}
        from app.live_lab.selection import select_candidates
        candidates=select_candidates(scanned['candidates'], probability_band=probability_band)
        settled=[r['prediction_id'] for r in repo.all('live_settlements','LIVE')
                 if not repo.get('live_result_claims',r['prediction_id'])]
        deliveries=[]
        if send and (candidates or settled):
            from app.lab_telegram.service import load_lab_telegram_config,validate_lab_telegram_config
            from app.lab_combo.presentation import LabTelegramTransport
            from app.real_match_lab_analysis.models import LAB_BOT_USERNAME
            from app.lab_combo.secure_logging import install_lab_secret_redaction
            config=load_lab_telegram_config()
            if validate_lab_telegram_config(config) is not None:
                return {'status':'LAB_CONFIGURATION_REJECTED','api_calls':client.request_count if client else 0}
            install_lab_secret_redaction(config.token)
            transport=LabTelegramTransport(config.token)
            async with transport.bot:
                if '@'+(transport.bot.username or '')!=LAB_BOT_USERNAME:
                    return {'status':'LAB_BOT_IDENTITY_MISMATCH','api_calls':client.request_count if client else 0}
                for identity in settled:
                    deliveries.append(await service.publish_result(identity,config,transport))
                for candidate in candidates:
                    if daypart.live_window(clock()) and runner is not None:
                        deliveries.append(await service.publish(candidate['prediction_id'],config,transport,refresh=runner.refresh))
        return {'status':scanned['status'],'candidates':len(candidates),'settled':len(settled),
                'deliveries':deliveries,'api_calls':client.request_count if client else 0,
                'automatic_training':False,'automatic_promotion':False,'automatic_rollback':False,
                'request_budget':{'cycle_ceiling':budget,'final_review_reserved_attempts':FINAL_REVIEW_RESERVED_ATTEMPTS,
                                  'scan_ceiling':max(0,budget-FINAL_REVIEW_RESERVED_ATTEMPTS) if budget is not None else None},
                'discovery_evidence':{k:v for k,v in scanned.items() if k!='candidates'}}
    finally:
        if client is not None:
            await client.close()


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('initialize','learning-cycle','live-cycle'))
    parser.add_argument('--database',required=True,type=Path)
    parser.add_argument('--ledger',type=Path)
    parser.add_argument('--enable-lab-automation',action='store_true')
    parser.add_argument('--send',action='store_true')
    args=parser.parse_args(argv)
    if not args.enable_lab_automation:
        parser.error('Explicit --enable-lab-automation is required; no defaults enable mutation')
    if args.ledger and args.ledger.resolve()==args.database.resolve():
        parser.error('Audit database must be separate from authoritative publication ledger')
    if args.command=='learning-cycle' and not args.ledger:
        parser.error('--ledger required')
    repo=AuditRepository(args.database)
    try:
        if args.command=='initialize':
            result={'status':'LAB_AUDIT_SCHEMA_READY'}
        elif args.command=='learning-cycle':
            ledger=ReadOnlyLedger(args.ledger)
            try:
                coordinator=LearningCoordinator(repo)
                result={'PREMATCH':coordinator.sync_prematch(ledger,now=datetime.now(timezone.utc)),
                        'LIVE':coordinator.after_settlement('LIVE',now=datetime.now(timezone.utc))}
            finally:
                ledger.close()
        else:
            result=asyncio.run(live_cycle(repo,send=args.send))
        print(canonical(result))
    finally:
        repo.close()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
