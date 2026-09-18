"""Explicit weekly Lab report worker; no API-Football or LIVE execution path."""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime,timezone
from pathlib import Path
from .contracts import canonical
from .observations import ReadOnlyLedger
from .repository import AuditRepository
from .weekly import freeze,deliver,latest_due,statistics,message,week_bounds


async def run(args: argparse.Namespace) -> dict:
    """Preview is inert; --send uses only the reviewed existing Lab destination."""
    now=datetime.now(timezone.utc)
    source=ReadOnlyLedger(args.ledger)
    try:
        if not args.send:
            start,_=week_bounds(now)
            result={'statistics':statistics(source,week_start=start,as_of=now)}
            return {**result,'message':message(result),'sent':False,'status':'PREVIEW_ONLY'}
        repo=AuditRepository(args.database)
        try:
            report=freeze(repo,source,now=now)
            source.connection.rollback()
            if repo.get('weekly_receipts',report['report_id']):return {'status':'ALREADY_SENT','sent':False}
            if repo.get('weekly_claims',report['report_id']):return {'status':'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED','sent':False}
            from app.lab_telegram.service import load_lab_telegram_config,validate_lab_telegram_config
            config=load_lab_telegram_config()
            if validate_lab_telegram_config(config) is not None:return {'status':'LAB_CONFIGURATION_REJECTED','sent':False}
            from app.lab_combo.presentation import LabTelegramTransport
            from app.lab_combo.secure_logging import install_lab_secret_redaction
            from app.real_match_lab_analysis.models import LAB_BOT_USERNAME
            install_lab_secret_redaction(config.token)
            transport=LabTelegramTransport(config.token)
            async with transport.bot:
                if '@'+(transport.bot.username or '')!=LAB_BOT_USERNAME:return {'status':'LAB_BOT_IDENTITY_MISMATCH','sent':False}
                return await deliver(repo,report,config,transport,now=now)
        finally:repo.close()
    finally:source.close()


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger',type=Path,default=Path('var/lab_combo/ledger.db'))
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--send',action='store_true')
    args=parser.parse_args(argv)
    if args.database.resolve()==args.ledger.resolve():parser.error('Dedicated report audit database required')
    result=asyncio.run(run(args));print(canonical(result))
    return 0 if result['status'] in {'SENT','ALREADY_SENT','PREVIEW_ONLY'} else 1


if __name__=='__main__':raise SystemExit(main())
