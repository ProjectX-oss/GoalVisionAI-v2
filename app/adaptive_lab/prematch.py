"""PREMATCH-only operator/automation entry point. LIVE has no execution branch."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
from pathlib import Path
from .contracts import canonical
from .repository import AuditRepository
from .observations import ReadOnlyLedger


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('status','why-no-picks','observe','research','bootstrap'))
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--ledger',type=Path,default=Path('var/lab_combo/ledger.db'))
    parser.add_argument('--shadow-database',type=Path,default=Path('var/lab_v2/shadow.db'))
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args(argv)
    if args.database.resolve() in {args.ledger.resolve(),args.shadow_database.resolve()}:
        parser.error('Dedicated adaptive database required')
    now=datetime.now(timezone.utc)
    readonly=args.command in ('status','why-no-picks')
    repo=AuditRepository(args.database,readonly=readonly)
    try:
        if args.command=='bootstrap':
            from .baseline import artifact
            from .governance import Governance
            result=Governance(repo).bootstrap(artifact(),now=now)
        elif args.command=='research':
            from .automl import AutoLearner
            result=AutoLearner(repo).run('PREMATCH',now=now)
        else:
            source=ReadOnlyLedger(args.ledger)
            try:
                if args.command=='observe':
                    from .observer import observe
                    result=observe(repo,source,now=now)
                else:
                    from .health import status
                    result=status(repo,source,args.shadow_database,now=now)
            finally:source.close()
        print(canonical(result))
    finally:repo.close()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
