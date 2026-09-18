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


async def live_cycle(repo: AuditRepository, *, send: bool) -> dict:
    from app.football.client import FootballClient
    from app.live_lab.runner import LiveRunner
    from app.live_lab.service import LiveService
    from .quota import SharedQuota
    clock=lambda:datetime.now(timezone.utc)
    coordinator=LearningCoordinator(repo)
    client=FootballClient(request_limit=80)
    client.restrict_requests(80,daily_reserve=750)
    try:
        await client.account_status()  # Existing provider header preflight; no odds fallback.
        quota=SharedQuota(repo)
        quota.claim('STATUS',now=clock(),provider=client.quota_snapshot())
        service=LiveService(repo,clock=clock,after_settlement=lambda _:coordinator.after_settlement('LIVE',now=clock()))
        runner=LiveRunner(service,client,quota,clock=clock)
        settled=await runner.settle()
        coordinator.after_settlement('PREMATCH',now=clock())
        coordinator.after_settlement('LIVE',now=clock())
        settled=[r['prediction_id'] for r in repo.all('live_settlements','LIVE')
                 if not repo.get('live_result_claims',r['prediction_id'])]
        scanned=await runner.scan()
        candidates=[c for c in scanned['candidates'] if not c['blockers']]
        deliveries=[]
        if send and (candidates or settled):
            from app.lab_telegram.service import load_lab_telegram_config,validate_lab_telegram_config
            from app.lab_combo.presentation import LabTelegramTransport
            from app.real_match_lab_analysis.models import LAB_BOT_USERNAME
            from app.lab_combo.secure_logging import install_lab_secret_redaction
            config=load_lab_telegram_config()
            if validate_lab_telegram_config(config) is not None:
                return {'status':'LAB_CONFIGURATION_REJECTED'}
            install_lab_secret_redaction(config.token)
            transport=LabTelegramTransport(config.token)
            async with transport.bot:
                if '@'+(transport.bot.username or '')!=LAB_BOT_USERNAME:
                    return {'status':'LAB_BOT_IDENTITY_MISMATCH'}
                for identity in settled:
                    deliveries.append(await service.publish_result(identity,config,transport))
                for candidate in candidates:
                    deliveries.append(await service.publish(candidate['prediction_id'],config,transport,refresh=runner.refresh))
        return {'status':scanned['status'],'candidates':len(candidates),'settled':len(settled),
                'deliveries':deliveries,'api_calls':client.request_count}
    finally:
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
