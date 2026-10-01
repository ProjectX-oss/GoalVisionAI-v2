"""Network-free disposable fake-Codex rehearsal. Never reads production config."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app.admin_alerts.autorepair import enqueue
from app.admin_alerts.model import DISCOVERY, Event
from app.admin_alerts.store import Store
from app.admin_alerts.operator_jobs import sync
from app.admin_autorepair.protocol import DIRECTORIES
from app.admin_autorepair.worker import Config, run_once


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True,help='New disposable evidence directory')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    root=args.output.resolve()
    source=root/'source'; source.mkdir()
    def git(*args: str) -> bytes:
        return subprocess.check_output(['git','-C',str(source),*args],stderr=subprocess.DEVNULL)
    git('init','-q')
    (source/'example.py').write_text('VALUE = 1\n')
    git('add','example.py')
    git('-c','user.name=Offline fixture','-c','user.email=offline@invalid','commit','-qm','Synthetic fixture only')
    def fingerprint() -> str:
        h=hashlib.sha256()
        for path in sorted(source.rglob('*')):
            if path.is_file():
                h.update(str(path.relative_to(source)).encode()); h.update(path.read_bytes())
        return h.hexdigest()
    before=fingerprint()
    spool=root/'spool'; spool.mkdir()
    for name in DIRECTORIES:
        (spool/name).mkdir()
    state=root/'admin-alerts'; state.mkdir()
    store=Store(state)
    try:
        enqueue(store,spool,1000)
        store.ingest([Event(DISCOVERY,'DATABASE_LOCK','pipeline','synthetic',1001,'fixture')],{},1001)
        key=enqueue(store,spool,1001)
        executable=root/'fake-codex'
        executable.write_text('''#!/usr/bin/python3
import pathlib,sys
if '--help' in sys.argv:
    print('--approve-for-me --ignore-user-config --ignore-rules --ephemeral')
else:
    sys.stdin.read()
    pathlib.Path('example.py').write_text('VALUE = 2\\n')
    pathlib.Path(sys.argv[sys.argv.index('--output-last-message')+1]).write_text('Synthetic offline patch. NO NETWORK.')
''')
        executable.chmod(0o755)
        config=Config({'ADMIN':str(source),'PREMATCH':str(source)},str(spool),str(executable))
        result=run_once(config)
        sync(store,spool,result['heartbeat_at'])
        report={'job_id':key,'outcome':result['outcome'],'source_unchanged':before==fingerprint(),
                'operator_notices':[r[0] for r in store.db.execute('SELECT kind FROM operator_outbox ORDER BY rowid')],
                'real_codex_calls':0,'provider_calls':0,'telegram_calls':0}
        (root/'rehearsal.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,sort_keys=True))
        return 0 if report['source_unchanged'] and report['outcome']=='PATCH_READY' else 1
    finally:
        store.close()


if __name__=='__main__':
    raise SystemExit(main())
